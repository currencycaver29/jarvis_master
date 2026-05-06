"""Notion connector — search + page block extraction."""

from __future__ import annotations

import base64
import logging
from typing import Optional
from urllib.parse import urlencode

from apps.shail.mcp.base import FetchHit, MCPProvider
from apps.shail.mcp._oauth import get_json, ingest_record, post_form, post_json
from apps.shail.mcp_store import update_index_status
from apps.shail.settings import get_settings

logger = logging.getLogger(__name__)

AUTH_URL    = "https://api.notion.com/v1/oauth/authorize"
TOKEN_URL   = "https://api.notion.com/v1/oauth/token"
API         = "https://api.notion.com/v1"
API_VERSION = "2022-06-28"


class _Notion:
    name   = "notion"
    label  = "Notion"
    scopes: list[str] = []  # Notion scopes are workspace-wide (no scope param)

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.notion_client_id and s.notion_client_secret)

    def oauth_authorize_url(self, *, state: str, redirect_uri: str) -> str:
        s = get_settings()
        params = {
            "client_id":     s.notion_client_id,
            "response_type": "code",
            "owner":         "user",
            "redirect_uri":  redirect_uri,
            "state":         state,
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, *, code: str, redirect_uri: str) -> dict:
        s = get_settings()
        basic = base64.b64encode(f"{s.notion_client_id}:{s.notion_client_secret}".encode()).decode()
        token = await post_json(
            TOKEN_URL,
            {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
            headers={
                "Authorization": f"Basic {basic}",
                "Notion-Version": API_VERSION,
                "Content-Type":   "application/json",
            },
        )
        return {
            "access_token":  token["access_token"],
            "refresh_token": None,           # Notion tokens don't expire
            "expires_at":    None,
            "scope":         "",
            "metadata": {
                "workspace_name": token.get("workspace_name", ""),
                "workspace_id":   token.get("workspace_id", ""),
                "bot_id":         token.get("bot_id", ""),
            },
        }

    async def index(self, *, user_id: str, access_token: str, refresh_token: Optional[str], settings: dict) -> int:
        update_index_status(user_id, self.name, status="indexing", indexed_count=0)
        headers = self._headers(access_token)
        ingested = 0
        try:
            cursor = None
            max_pages = 100
            while ingested < max_pages:
                body = {"filter": {"value": "page", "property": "object"}, "page_size": 50}
                if cursor:
                    body["start_cursor"] = cursor
                resp = await post_json(f"{API}/search", body, headers=headers)
                results = resp.get("results", [])
                if not results:
                    break
                for page in results:
                    if ingested >= max_pages:
                        break
                    pid = page.get("id")
                    if not pid:
                        continue
                    title = self._extract_title(page)
                    text = await self._fetch_page_text(pid, headers)
                    if not text:
                        continue
                    ingested += ingest_record(
                        user_id=user_id, provider=self.name, doc_id=pid,
                        title=title, content=text,
                        url=page.get("url"),
                    )
                    update_index_status(user_id, self.name, status="indexing", indexed_count=ingested)
                if not resp.get("has_more"):
                    break
                cursor = resp.get("next_cursor")
            update_index_status(user_id, self.name, status="idle", indexed_count=ingested)
        except Exception as e:
            logger.exception("notion index failed: %s", e)
            update_index_status(user_id, self.name, status="error", error=str(e)[:300])
        return ingested

    async def fetch_relevant(
        self, *, user_id: str, query: str, k: int,
        access_token: str, refresh_token: Optional[str], settings: dict,
    ) -> list[FetchHit]:
        headers = self._headers(access_token)
        try:
            resp = await post_json(
                f"{API}/search",
                {"query": query, "page_size": k},
                headers=headers,
                timeout=2.0,
            )
        except Exception as e:
            logger.warning("notion fetch_relevant failed: %s", e)
            return []
        hits: list[FetchHit] = []
        for r in (resp.get("results") or [])[:k]:
            if r.get("object") != "page":
                continue
            hits.append(FetchHit(
                id=r["id"],
                title=self._extract_title(r),
                snippet=(r.get("url") or "")[:200],
                url=r.get("url"),
            ))
        return hits

    @staticmethod
    def _headers(token: str) -> dict:
        return {
            "Authorization":   f"Bearer {token}",
            "Notion-Version":  API_VERSION,
            "Content-Type":    "application/json",
        }

    @staticmethod
    def _extract_title(page: dict) -> str:
        # Notion page titles live under properties.<some_title_prop>.title[*].plain_text
        props = page.get("properties") or {}
        for v in props.values():
            if isinstance(v, dict) and v.get("type") == "title":
                arr = v.get("title") or []
                if arr:
                    return "".join(t.get("plain_text", "") for t in arr) or "(untitled)"
        return "(untitled)"

    async def _fetch_page_text(self, page_id: str, headers: dict) -> str:
        """Fetch up to 50 child blocks and concat their plain text."""
        try:
            resp = await get_json(
                f"{API}/blocks/{page_id}/children",
                headers=headers,
                params={"page_size": "50"},
            )
        except Exception as e:
            logger.warning("notion blocks fetch failed (%s): %s", page_id, e)
            return ""
        chunks: list[str] = []
        for block in resp.get("results") or []:
            t = block.get("type")
            inner = block.get(t) if t else None
            if not inner:
                continue
            rich = inner.get("rich_text") or inner.get("text") or []
            line = "".join(rt.get("plain_text", "") for rt in rich if isinstance(rt, dict))
            if line:
                chunks.append(line)
        return "\n".join(chunks)[:8000]


notion_provider = _Notion()

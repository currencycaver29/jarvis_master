"""
Gmail connector — RAG-indexed (no live search on chat queries).

Uses the same Google OAuth client as Drive but requests gmail.readonly
scope. After OAuth completes, the user picks which labels to index in
the Connections UI; the indexer pulls metadata + body text for messages
in those labels and embeds into the user's Gmail Chroma namespace.

Active fetch on chat queries does a vector search over that namespace
(no live API calls — would be too slow + privacy-noisy).
"""

from __future__ import annotations

import base64
import logging
from typing import Optional
from urllib.parse import urlencode

from apps.shail.mcp.base import FetchHit, MCPProvider
from apps.shail.mcp._oauth import (
    expires_at_iso, get_json, ingest_record, mcp_namespace, post_form,
)
from apps.shail.mcp_store import update_index_status
from apps.shail.settings import get_settings
from shail.memory.embeddings import embed_query as emb_q
from shail.memory.rag import _get_store

logger = logging.getLogger(__name__)

AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO  = "https://www.googleapis.com/oauth2/v2/userinfo"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1"

DEFAULT_LABELS = ["INBOX", "IMPORTANT", "STARRED"]


class _Gmail:
    name   = "gmail"
    label  = "Gmail"
    scopes = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/userinfo.email",
        "openid",
    ]

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.google_client_id and s.google_client_secret)

    def oauth_authorize_url(self, *, state: str, redirect_uri: str) -> str:
        s = get_settings()
        params = {
            "client_id":     s.google_client_id,
            "redirect_uri":  redirect_uri,
            "response_type": "code",
            "scope":         " ".join(self.scopes),
            "access_type":   "offline",
            "prompt":        "consent",
            "state":         state,
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, *, code: str, redirect_uri: str) -> dict:
        s = get_settings()
        token = await post_form(TOKEN_URL, {
            "code":          code,
            "client_id":     s.google_client_id,
            "client_secret": s.google_client_secret,
            "redirect_uri":  redirect_uri,
            "grant_type":    "authorization_code",
        })
        info: dict = {}
        try:
            info = await get_json(USERINFO, headers={"Authorization": f"Bearer {token['access_token']}"})
        except Exception as e:
            logger.warning("gmail userinfo failed: %s", e)
        return {
            "access_token":  token["access_token"],
            "refresh_token": token.get("refresh_token"),
            "expires_at":    expires_at_iso(token.get("expires_in")),
            "scope":         token.get("scope", ""),
            "metadata":      {"email": info.get("email", "")},
        }

    async def index(self, *, user_id: str, access_token: str, refresh_token: Optional[str], settings: dict) -> int:
        """Indexes messages in the user-selected labels. Cap: 500 messages."""
        update_index_status(user_id, self.name, status="indexing", indexed_count=0)
        labels = settings.get("labels") or DEFAULT_LABELS
        headers = {"Authorization": f"Bearer {access_token}"}
        ingested = 0
        max_msgs = 500
        try:
            for lbl in labels:
                if ingested >= max_msgs:
                    break
                page_token: Optional[str] = None
                fetched_in_label = 0
                while ingested < max_msgs and fetched_in_label < 200:
                    params = {
                        "labelIds": lbl,
                        "maxResults": "50",
                    }
                    if page_token:
                        params["pageToken"] = page_token
                    listing = await get_json(
                        f"{GMAIL_API}/users/me/messages",
                        headers=headers, params=params,
                    )
                    msgs = listing.get("messages") or []
                    for m in msgs:
                        if ingested >= max_msgs:
                            break
                        body = await self._fetch_message(m["id"], headers)
                        if body is None:
                            continue
                        ingested += ingest_record(
                            user_id=user_id, provider=self.name, doc_id=m["id"],
                            title=body["title"],
                            content=body["text"],
                            url=f"https://mail.google.com/mail/u/0/#inbox/{m['id']}",
                            extra_meta={"label": lbl, "from": body.get("from", ""),
                                        "date": body.get("date", "")},
                        )
                        fetched_in_label += 1
                        update_index_status(user_id, self.name, status="indexing", indexed_count=ingested)
                    page_token = listing.get("nextPageToken")
                    if not page_token:
                        break
            update_index_status(user_id, self.name, status="idle", indexed_count=ingested)
        except Exception as e:
            logger.exception("gmail index failed: %s", e)
            update_index_status(user_id, self.name, status="error", error=str(e)[:300])
        return ingested

    async def _fetch_message(self, mid: str, headers: dict) -> Optional[dict]:
        try:
            m = await get_json(
                f"{GMAIL_API}/users/me/messages/{mid}",
                headers=headers,
                params={"format": "full"},
            )
        except Exception as e:
            logger.warning("gmail fetch msg failed (%s): %s", mid, e)
            return None
        payload = m.get("payload") or {}
        title = ""
        sender = ""
        date = ""
        for h in payload.get("headers") or []:
            n = h.get("name", "").lower()
            if n == "subject": title = h.get("value", "")
            elif n == "from":   sender = h.get("value", "")
            elif n == "date":   date = h.get("value", "")
        text = self._extract_body(payload)[:8000]
        if not text:
            text = m.get("snippet", "")
        return {"title": title or "(no subject)", "text": text, "from": sender, "date": date}

    def _extract_body(self, payload: dict) -> str:
        # Walk parts recursively, prefer text/plain
        if not payload:
            return ""
        if payload.get("mimeType") == "text/plain":
            data = ((payload.get("body") or {}).get("data") or "")
            return self._b64url_decode(data)
        for part in payload.get("parts") or []:
            t = self._extract_body(part)
            if t:
                return t
        return ""

    @staticmethod
    def _b64url_decode(s: str) -> str:
        if not s:
            return ""
        try:
            return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)).decode("utf-8", errors="ignore")
        except Exception:
            return ""

    async def fetch_relevant(
        self, *, user_id: str, query: str, k: int,
        access_token: str, refresh_token: Optional[str], settings: dict,
    ) -> list[FetchHit]:
        # Gmail privacy-first: no live API search on every chat query.
        # Use the embedded namespace populated at index time.
        try:
            store = _get_store()
            emb = emb_q(query)
            hits = store.query(
                query_embedding=emb,
                namespace=mcp_namespace(user_id, self.name),
                k=k,
            )
        except Exception as e:
            logger.warning("gmail vector search failed: %s", e)
            return []
        out: list[FetchHit] = []
        for content, _score, meta in hits:
            out.append(FetchHit(
                id=str(meta.get("provider_id") or meta.get("id", "")),
                title=meta.get("title", "(untitled)"),
                snippet=(content or "")[:200],
                url=meta.get("sourceUrl"),
                extra={"from": meta.get("from", ""), "date": meta.get("date", "")},
            ))
        return out


gmail_provider = _Gmail()

"""
OAuth + chunked-ingest helpers shared across MCP providers.

Keeps the per-provider modules focused on their unique endpoints/scopes
rather than reinventing token exchange + indexing plumbing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from shail.memory.rag import ingest

logger = logging.getLogger(__name__)


def expires_at_iso(expires_in_seconds: Optional[int]) -> Optional[str]:
    if not expires_in_seconds:
        return None
    return (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in_seconds))).isoformat()


async def post_form(
    url: str, data: dict, *, headers: Optional[dict] = None, timeout: float = 15.0,
) -> dict:
    """POST application/x-www-form-urlencoded; raise on non-2xx; return JSON."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, data=data, headers=headers or {})
        resp.raise_for_status()
        return resp.json()


async def post_json(
    url: str, payload: dict, *, headers: Optional[dict] = None, timeout: float = 15.0,
) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers=headers or {})
        resp.raise_for_status()
        return resp.json()


async def get_json(
    url: str, *, headers: Optional[dict] = None, params: Optional[dict] = None, timeout: float = 15.0,
) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, headers=headers or {}, params=params or {})
        resp.raise_for_status()
        return resp.json()


def mcp_namespace(user_id: str, provider: str) -> str:
    return f"mcp_{user_id}_{provider}"


def ingest_record(
    *, user_id: str, provider: str, doc_id: str,
    title: str, content: str, url: Optional[str] = None,
    extra_meta: Optional[dict] = None,
) -> int:
    """Embed and store one MCP document. Returns 1 on success, 0 on empty/failed."""
    if not content or len(content.strip()) < 10:
        return 0
    namespace = mcp_namespace(user_id, provider)
    metadata = {
        "id":          f"{provider}:{doc_id}",
        "customId":    f"{provider}:{doc_id}",
        "provider":    provider,
        "provider_id": doc_id,
        "title":       title or "(untitled)",
        "summary":     (content or "")[:400],
        "tier":        "important",
        "source":      f"mcp_{provider}",
        "namespace":   namespace,
    }
    if url:
        metadata["sourceUrl"] = url
    if extra_meta:
        metadata.update(extra_meta)
    try:
        chunks = ingest(records=[{
            "id":        f"{provider}:{doc_id}",
            "content":   content[:10_000],
            "namespace": namespace,
            "metadata":  metadata,
        }])
        return 1 if chunks else 0
    except Exception as e:
        logger.warning("mcp ingest failed (%s/%s): %s", provider, doc_id, e)
        return 0

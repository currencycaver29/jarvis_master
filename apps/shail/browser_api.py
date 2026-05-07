"""
SHAIL Browser Extension API
────────────────────────────
Provides memory capture, search, retrieval, delete, and stats endpoints
consumed exclusively by the SHAIL Chrome extension.

All captures are stored in the "browser_memory" namespace of the local
vector store (ChromaDB by default). No auth required — local-only, CORS
is covered by the wildcard middleware in main.py.

Endpoints (all prefixed with /browser when mounted):
  GET  /me                  → Backend health + info for Options page
  POST /capture             → Ingest a page visit or AI conversation
  POST /search              → Semantic search + empty-query browse
  GET  /memories/{id}       → Full content fetch for detail view
  DELETE /memories/{id}     → Delete a memory
  GET  /stats               → Stats for popup cards
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from shail.memory.rag import _get_store, ingest, search as rag_search
from apps.shail.settings import get_settings
from apps.shail.auth_store import (
    get_user_by_api_key, touch_api_key_last_used, touch_user_last_seen,
    get_user_settings, update_user_settings,
)
from apps.shail.capture_log import write_event
from apps.shail.blueprints import (
    generate_blueprint, get_blueprint as bp_get, delete_blueprint as bp_delete,
    get_blueprint_ids,
)

logger = logging.getLogger(__name__)

browser_router = APIRouter()

# ── Namespace for all browser extension captures ───────────────────────────
NS_BROWSER = "browser_memory"  # legacy / anonymous namespace

_bearer = HTTPBearer(auto_error=False)


def _get_namespace(
    credentials: Optional[HTTPAuthorizationCredentials],
) -> str:
    """
    Return the ChromaDB namespace for this request.
    - Authenticated (valid API key) → "user_{user_id}"
    - Anonymous / no key → "browser_memory" (backward-compatible)
    """
    if credentials:
        key = credentials.credentials
        user_id = get_user_by_api_key(key)
        if user_id:
            touch_api_key_last_used(key)
            touch_user_last_seen(user_id)
            return f"user_{user_id}"
    return NS_BROWSER


# ── Pydantic request / response models ─────────────────────────────────────

class CaptureRequest(BaseModel):
    """Mirrors CaptureCandidate from contracts.ts."""
    customId: str = Field(..., description="SHA-256 fingerprint — used as vector store record ID")
    conversationId: Optional[str] = None  # provider UUID; present when stable customId scheme is active
    eventType: str = Field(..., description="ai_conversation | page_visit | manual")
    sourceApp: str = Field(..., description="chatgpt | claude | gemini | perplexity | web")
    sourceUrl: str
    timestamp: str = Field(..., description="ISO 8601 UTC")
    title: Optional[str] = None
    userText: Optional[str] = None        # ai_conversation only
    assistantText: Optional[str] = None   # ai_conversation only
    pageContent: Optional[str] = None     # page_visit only


class CaptureResponse(BaseModel):
    memoryId: str
    status: str   # "created" | "duplicate"
    summary: Optional[str] = None


class SearchRequest(BaseModel):
    query: str = Field(default="")
    k: int = Field(default=20, ge=1, le=100)
    sourceApp: Optional[str] = None
    after: Optional[str] = None   # ISO 8601 — return only memories with timestamp >= after


class MemoryItem(BaseModel):
    id: str
    customId: str
    eventType: str
    sourceApp: str
    sourceUrl: str
    title: str
    summary: str
    timestamp: str
    tags: List[str] = Field(default_factory=list)
    pinned: bool = False
    score: Optional[float] = None
    content: Optional[str] = None   # full content — only populated in GET /memories/{id}


class SearchResponse(BaseModel):
    items: List[MemoryItem]
    total: int


class DeleteResponse(BaseModel):
    ok: bool
    id: str


class MeResponse(BaseModel):
    status: str = "ok"
    backend: str = "jarvis_master"
    version: str = "1.0.0"
    vectorStore: str
    embeddingModel: str
    memoriesCount: int


class StatsResponse(BaseModel):
    totalMemories: int
    memoriesThisWeek: int
    topSource: Optional[str]
    lastCapturedAt: Optional[str]
    backendVersion: str = "1.0.0"


# ── Helpers ─────────────────────────────────────────────────────────────────

def _parse_tags(raw: Any) -> List[str]:
    if isinstance(raw, list):
        return [str(t) for t in raw]
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(t) for t in parsed]
        except Exception:
            return [s.strip() for s in raw.split(",") if s.strip()]
    return []


def _meta_to_item(
    record_id: str,
    content: str,
    score: float,
    meta: Dict[str, Any],
    include_content: bool = False,
) -> MemoryItem:
    """Convert raw vector store record into a MemoryItem."""
    # Pull title from metadata; fall back to parsing the content header
    title = meta.get("title", "")
    if not title:
        m = re.match(r"^\[(\w+)\]\s+([^\n]+)", content or "")
        title = m.group(2).strip() if m else ""

    # Strip the "[sourceApp] Title\n\n" capture header for the summary
    body_start = (content or "").find("\n\n")
    body = content[body_start + 2:] if body_start >= 0 else (content or "")
    summary = meta.get("summary") or body[:400]

    return MemoryItem(
        id=record_id,
        customId=meta.get("customId", record_id),
        eventType=meta.get("eventType", "page_visit"),
        sourceApp=meta.get("sourceApp", "web"),
        sourceUrl=meta.get("sourceUrl", ""),
        title=title,
        summary=summary,
        timestamp=meta.get("timestamp", datetime.now(timezone.utc).isoformat()),
        tags=_parse_tags(meta.get("tags")),
        pinned=meta.get("pinned", "false") == "true",
        score=round(score, 4) if score else None,
        content=content if include_content else None,
    )


def _count_memories(store, namespace: str) -> int:
    """Best-effort count of records in a given namespace."""
    try:
        if hasattr(store, "collection"):  # Chroma
            result = store.collection.get(
                where={"namespace": namespace},
                include=[],  # fastest — IDs only
            )
            return len(result.get("ids", []))
    except Exception:
        pass
    return 0


# ── Endpoints ────────────────────────────────────────────────────────────────

@browser_router.get("/me", response_model=MeResponse)
async def get_me(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> MeResponse:
    """Health check + backend info for the Options page."""
    settings = get_settings()
    store = _get_store()
    namespace = _get_namespace(credentials)
    count = _count_memories(store, namespace)
    return MeResponse(
        vectorStore=settings.rag_vector_store,
        embeddingModel=settings.ollama_embed_model,
        memoriesCount=count,
    )


@browser_router.post("/capture", response_model=CaptureResponse, status_code=201)
async def capture_memory(
    req: CaptureRequest,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> CaptureResponse:
    """
    Ingest a browser capture (page visit or AI conversation) into local memory.

    Uses `customId` as the vector store record ID so upsert is naturally
    idempotent — re-capturing the same page on the same day is a no-op.
    The extension's local dedup (shail_doc_index) prevents most redundant
    calls, but the backend handles any that slip through gracefully.
    """
    namespace = _get_namespace(credentials)

    # Build the content string in the canonical format the extension expects on readback
    if req.eventType == "ai_conversation":
        content = (
            f"[{req.sourceApp}] {req.title or 'AI Conversation'}\n\n"
            f"User: {req.userText or ''}\n\n"
            f"Assistant: {req.assistantText or ''}"
        )
    else:
        content = f"[web] {req.title or req.sourceUrl}\n\n{req.pageContent or ''}"

    # 50K accommodates full-session transcripts from the Sprint 1 cumulative
    # session buffer (was 20K / ~10 turns). Blueprint generator self-caps at 16K.
    content = content[:50_000]
    summary = content[:400]

    chunk_count = ingest(
        records=[
            {
                "id": req.customId,
                "content": content,
                "namespace": namespace,
                "metadata": {
                    "id": req.customId,
                    "customId": req.customId,
                    "conversationId": req.conversationId or "",
                    "eventType": req.eventType,
                    "sourceApp": req.sourceApp,
                    "source": f"browser_{req.sourceApp}",
                    "tier": "important",
                    "sourceUrl": req.sourceUrl,
                    "title": req.title or "",
                    "summary": summary,
                    "timestamp": req.timestamp,
                    "captured_ts": str(time.time()),
                    "pinned": "false",
                    "tags": "[]",
                    "namespace": namespace,
                },
            }
        ]
    )

    if chunk_count == 0:
        raise HTTPException(
            status_code=500,
            detail="Embedding failed — check Ollama is running (ollama serve) with nomic-embed-text pulled",
        )

    # Capture log: emit one CAPTURE event then one INDEX event (both fire
    # for any successful ingest — the embedding step is what made INDEX a
    # separate signal in the brief). Auth-scoped to the current user.
    log_user_id = namespace.removeprefix("user_") if namespace.startswith("user_") else None
    write_event("CAPTURE", f"{req.sourceApp}: {(req.title or req.sourceUrl)[:80]}",
                user_id=log_user_id, ref_id=req.customId)
    write_event("INDEX", f"embedded {chunk_count} chunk(s) for {req.sourceApp}",
                user_id=log_user_id, ref_id=req.customId)

    # Fire blueprint extraction in the background — does not block the
    # capture response. Failures are logged inside generate_blueprint
    # and never bubble up; the original capture is already saved.
    async def _bp_task():
        try:
            bp = await generate_blueprint(
                req.customId,
                content=content,
                content_type=req.eventType,
                user_id=log_user_id,
                namespace=namespace,
            )
            if bp:
                write_event(
                    "BLUEPRINT",
                    f"extracted {len(bp.get('decisions',[]))}d/{len(bp.get('open_questions',[]))}q/{len(bp.get('next_actions',[]))}a",
                    user_id=log_user_id, ref_id=req.customId,
                )
        except Exception as e:  # defensive: never crash the event loop
            logger.warning("blueprint task crashed for %s: %s", req.customId, e)

    asyncio.create_task(_bp_task())

    return CaptureResponse(
        memoryId=req.customId,
        status="created",
        summary=summary,
    )


@browser_router.post("/search", response_model=SearchResponse)
async def search_memories(
    req: SearchRequest,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> SearchResponse:
    """
    Search browser memories.

    Empty query → browse mode: returns all records sorted by timestamp (newest first).
    Non-empty query → semantic search via Gemini embeddings + ChromaDB KNN.
    """
    store = _get_store()
    namespace = _get_namespace(credentials)

    if not req.query.strip():
        # ── Browse mode: list all records visible to this user ────────────
        # Signed-in users see their namespace AND the anonymous namespace
        # (pre-login captures) until they claim them via /claim-anonymous.
        # Anonymous users see only browser_memory.
        try:
            if hasattr(store, "collection"):  # ChromaVectorStore
                namespaces_to_fetch = [namespace]
                if namespace != NS_BROWSER:
                    namespaces_to_fetch.append(NS_BROWSER)

                seen_ids: set = set()
                items = []
                for ns in namespaces_to_fetch:
                    try:
                        result = store.collection.get(
                            where={"namespace": ns},
                            include=["documents", "metadatas"],
                        )
                    except Exception as ns_exc:
                        logger.warning("Browse namespace %s failed: %s", ns, ns_exc)
                        continue
                    for rid, doc, meta in zip(
                        result.get("ids", []),
                        result.get("documents", []),
                        result.get("metadatas", []),
                    ):
                        if rid not in seen_ids:
                            seen_ids.add(rid)
                            items.append(_meta_to_item(rid, doc or "", 0.0, meta or {}))

                if req.after:
                    items = [i for i in items if i.timestamp >= req.after]
                items.sort(key=lambda x: x.timestamp, reverse=True)
                return SearchResponse(items=items[: req.k], total=len(items))
            else:
                # PgVector: return empty for now (browse not yet implemented for PG)
                return SearchResponse(items=[], total=0)
        except Exception as exc:
            logger.error("Browse failed: %s", exc)
            return SearchResponse(items=[], total=0)

    # ── Semantic search ────────────────────────────────────────────────────
    try:
        results = rag_search(query=req.query, k=req.k, namespace=namespace)
        # Signed-in users: also search anonymous namespace and merge
        if namespace != NS_BROWSER:
            try:
                anon_results = rag_search(query=req.query, k=req.k, namespace=NS_BROWSER)
                results = list(results) + list(anon_results)
            except Exception:
                pass
    except Exception as exc:
        logger.error("Search failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    seen_ids: set = set()
    items = []
    for content, dist_score, metadata in results:
        record_id = metadata.get("customId") or metadata.get("id") or str(uuid.uuid4())
        if record_id in seen_ids:
            continue
        seen_ids.add(record_id)
        similarity = max(0.0, 1.0 - dist_score / 2.0)
        items.append(_meta_to_item(record_id, content, similarity, metadata))

    # Sort by relevance then date-filter
    items.sort(key=lambda x: x.score or 0.0, reverse=True)
    if req.after:
        items = [i for i in items if i.timestamp >= req.after]

    return SearchResponse(items=items[: req.k], total=len(items))


@browser_router.get("/memories/{memory_id}", response_model=MemoryItem)
async def get_memory(memory_id: str) -> MemoryItem:
    """Fetch full content of a single memory (for the detail view)."""
    store = _get_store()
    if hasattr(store, "collection"):
        try:
            result = store.collection.get(
                ids=[memory_id],
                include=["documents", "metadatas"],
            )
            ids = result.get("ids", [])
            if ids:
                doc = (result.get("documents") or [""])[0] or ""
                meta = (result.get("metadatas") or [{}])[0] or {}
                return _meta_to_item(ids[0], doc, 0.0, meta, include_content=True)
        except Exception as exc:
            logger.error("get_memory failed for %s: %s", memory_id, exc)
    raise HTTPException(status_code=404, detail="Memory not found")


@browser_router.delete("/memories/{memory_id}", response_model=DeleteResponse)
async def delete_memory(
    memory_id: str,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> DeleteResponse:
    """Delete a memory by ID.

    SECURITY (Sprint 1 fix): verify ownership via namespace before delete.
    Anonymous callers can delete only memories in NS_BROWSER namespace.
    """
    store = _get_store()
    if not hasattr(store, "collection"):
        raise HTTPException(status_code=501, detail="Delete not supported for this store")

    primary_ns = _get_namespace(credentials)
    # Try primary namespace first, then fall back to anonymous namespace so that
    # memories captured before the user signed in can still be deleted.
    matched_ns: Optional[str] = None
    for ns in (primary_ns, NS_BROWSER):
        if matched_ns is not None:
            break
        try:
            result = store.collection.get(ids=[memory_id], where={"namespace": ns})
            if result.get("ids"):
                matched_ns = ns
        except Exception as exc:
            logger.error("ownership check failed for %s (ns=%s): %s", memory_id, ns, exc)
            raise HTTPException(status_code=500, detail=str(exc))
    if matched_ns is None:
        raise HTTPException(status_code=404, detail="Memory not found")

    try:
        store.collection.delete(ids=[memory_id])
        try:
            bp_delete(memory_id)
        except Exception as exc:
            logger.warning("blueprint cascade delete failed for %s: %s", memory_id, exc)
        log_user_id = primary_ns.removeprefix("user_") if primary_ns.startswith("user_") else None
        write_event("PRUNE", f"memory deleted: {memory_id[:12]}",
                    user_id=log_user_id, ref_id=memory_id)
        return DeleteResponse(ok=True, id=memory_id)
    except Exception as exc:
        logger.error("Delete failed for %s: %s", memory_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@browser_router.get("/blueprint/{memory_id}")
async def get_memory_blueprint(
    memory_id: str,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    """Fetch the structured blueprint for a memory.

    Returns 404 if no blueprint exists yet (extraction pending or failed).
    The dashboard MemDetail view polls this endpoint after a capture to
    surface decisions / open_questions / next_actions.
    """
    bp = bp_get(memory_id)
    if not bp:
        raise HTTPException(status_code=404, detail="Blueprint not yet generated")
    return bp


class BlueprintIdsRequest(BaseModel):
    ids: List[str] = Field(default_factory=list)


@browser_router.post("/blueprint-ids")
async def list_blueprint_ids(req: BlueprintIdsRequest) -> dict:
    """Return the subset of provided memory IDs that have a blueprint.

    Used by the Memories list to render BLUEPRINT badges with one batch
    query per page-load instead of one fetch per card.
    """
    return {"ids": list(get_blueprint_ids(req.ids))}


@browser_router.get("/stats", response_model=StatsResponse)
async def get_stats(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> StatsResponse:
    """Compute stats for popup cards from local browser_memory records."""
    store = _get_store()
    namespace = _get_namespace(credentials)
    try:
        if hasattr(store, "collection"):  # ChromaVectorStore
            result = store.collection.get(
                where={"namespace": namespace},
                include=["metadatas"],
            )
            metadatas: List[Dict[str, Any]] = [m or {} for m in result.get("metadatas", [])]
            total = len(metadatas)

            week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            this_week = sum(
                1 for m in metadatas if m.get("timestamp", "") >= week_ago
            )

            source_counts: Dict[str, int] = {}
            latest_ts: Optional[str] = None
            for m in metadatas:
                src = m.get("sourceApp", "web")
                source_counts[src] = source_counts.get(src, 0) + 1
                ts = m.get("timestamp")
                if ts and (latest_ts is None or ts > latest_ts):
                    latest_ts = ts

            top_source = (
                max(source_counts, key=lambda k: source_counts[k])
                if source_counts
                else None
            )

            return StatsResponse(
                totalMemories=total,
                memoriesThisWeek=this_week,
                topSource=top_source,
                lastCapturedAt=latest_ts,
            )
    except Exception as exc:
        logger.error("Stats failed: %s", exc)

    return StatsResponse(
        totalMemories=0,
        memoriesThisWeek=0,
        topSource=None,
        lastCapturedAt=None,
    )


# ── Export / Import ───────────────────────────────────────────────────────────

class ImportResponse(BaseModel):
    imported: int
    skipped: int


@browser_router.get("/export")
async def export_memories(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
):
    """Download all memories for the authenticated namespace as a JSON file."""
    store = _get_store()
    namespace = _get_namespace(credentials)
    try:
        if hasattr(store, "collection"):
            result = store.collection.get(
                where={"namespace": namespace},
                include=["documents", "metadatas"],
            )
            items = []
            for rid, doc, meta in zip(
                result.get("ids", []),
                result.get("documents", []),
                result.get("metadatas", []),
            ):
                items.append(_meta_to_item(rid, doc or "", 0.0, meta or {}, include_content=True).dict())
            payload = json.dumps(items, ensure_ascii=False, indent=2)
            return Response(
                content=payload,
                media_type="application/json",
                headers={"Content-Disposition": 'attachment; filename="shail-export.json"'},
            )
    except Exception as exc:
        logger.error("Export failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    raise HTTPException(status_code=501, detail="Export not supported for this store")


@browser_router.post("/import", response_model=ImportResponse, status_code=200)
async def import_memories(
    body: List[MemoryItem],
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> ImportResponse:
    """Re-index a JSON export. Skips records whose customId already exists."""
    namespace = _get_namespace(credentials)
    store = _get_store()

    # Collect existing customIds to skip duplicates
    existing_ids: set = set()
    if hasattr(store, "collection"):
        try:
            existing = store.collection.get(
                where={"namespace": namespace}, include=[]
            )
            existing_ids = set(existing.get("ids", []))
        except Exception:
            pass

    imported = 0
    skipped = 0
    records_to_ingest = []
    for item in body:
        record_id = item.customId or item.id
        if record_id in existing_ids:
            skipped += 1
            continue
        content = item.content or item.summary or f"[{item.sourceApp}] {item.title}"
        records_to_ingest.append({
            "id": record_id,
            "content": content,
            "namespace": namespace,
            "metadata": {
                "id": record_id,
                "customId": record_id,
                "eventType": item.eventType,
                "sourceApp": item.sourceApp,
                "source": f"browser_{item.sourceApp}",
                "tier": "important",
                "sourceUrl": item.sourceUrl,
                "title": item.title or "",
                "summary": item.summary or content[:400],
                "timestamp": item.timestamp,
                "captured_ts": str(time.time()),
                "pinned": "true" if item.pinned else "false",
                "tags": json.dumps(item.tags),
                "namespace": namespace,
            },
        })

    if records_to_ingest:
        try:
            count = ingest(records=records_to_ingest)
            imported = count
        except Exception as exc:
            logger.error("Import ingest failed: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))

    return ImportResponse(imported=imported, skipped=skipped)


# ── Capture settings ──────────────────────────────────────────────────────────

class CaptureSettingsResponse(BaseModel):
    capture_enabled: bool
    blocked_domains: List[str]
    ollama_model: str
    external_api_key: str


class CaptureSettingsUpdate(BaseModel):
    capture_enabled: Optional[bool] = None
    blocked_domains: Optional[List[str]] = None
    ollama_model: Optional[str] = None
    external_api_key: Optional[str] = None


@browser_router.get("/capture-settings", response_model=CaptureSettingsResponse)
async def get_capture_settings(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> CaptureSettingsResponse:
    """Get per-user capture settings from SQLite."""
    namespace = _get_namespace(credentials)
    # Anonymous users get static defaults — no user_settings row
    if namespace == NS_BROWSER:
        return CaptureSettingsResponse(
            capture_enabled=True, blocked_domains=[], ollama_model="", external_api_key=""
        )
    user_id = namespace.removeprefix("user_")
    settings = get_user_settings(user_id)
    return CaptureSettingsResponse(**settings)


@browser_router.put("/capture-settings", response_model=CaptureSettingsResponse)
async def put_capture_settings(
    req: CaptureSettingsUpdate,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> CaptureSettingsResponse:
    """Update per-user capture settings."""
    namespace = _get_namespace(credentials)
    if namespace == NS_BROWSER:
        raise HTTPException(status_code=401, detail="Sign in to save settings")
    user_id = namespace.removeprefix("user_")
    updates = {k: v for k, v in req.dict().items() if v is not None}
    settings = update_user_settings(user_id, **updates)
    return CaptureSettingsResponse(**settings)


@browser_router.get("/anonymous-count")
async def get_anonymous_count() -> dict:
    """Count memories captured before sign-in (browser_memory namespace)."""
    try:
        result = store.collection.get(where={"namespace": NS_BROWSER})
        return {"count": len(result["ids"])}
    except Exception:
        return {"count": 0}


class ClaimAnonymousRequest(BaseModel):
    ids: Optional[list] = None  # None = claim all; list of str = claim specific IDs


@browser_router.post("/claim-anonymous")
async def claim_anonymous_memories(
    req: ClaimAnonymousRequest = ClaimAnonymousRequest(),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    """Move browser_memory records into the authenticated user's namespace.

    If req.ids is None, claims all anonymous records.
    If req.ids is a list of IDs, claims only those specific records.
    """
    namespace = _get_namespace(credentials)
    if namespace == NS_BROWSER:
        raise HTTPException(status_code=401, detail="Sign in required")
    try:
        if req.ids is not None:
            # Selective claim: fetch only the specified IDs
            result = store.collection.get(
                ids=req.ids,
                include=["metadatas"],
            )
        else:
            # Claim all anonymous records
            result = store.collection.get(
                where={"namespace": NS_BROWSER},
                include=["metadatas"],
            )
        ids = result["ids"]
        if not ids:
            return {"claimed": 0}
        # Only move records that are actually in the anonymous namespace
        paired = list(zip(ids, result["metadatas"]))
        to_move = [(rid, m) for rid, m in paired if m.get("namespace") == NS_BROWSER]
        if not to_move:
            return {"claimed": 0}
        move_ids = [rid for rid, _ in to_move]
        new_metas = [{**m, "namespace": namespace} for _, m in to_move]
        store.collection.update(ids=move_ids, metadatas=new_metas)
        return {"claimed": len(move_ids)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@browser_router.get("/anonymous-memories")
async def list_anonymous_memories() -> dict:
    """List anonymous memories available to claim (summary only, no auth required)."""
    try:
        result = store.collection.get(
            where={"namespace": NS_BROWSER},
            include=["metadatas"],
        )
        items = []
        for rid, meta in zip(result.get("ids", []), result.get("metadatas", [])):
            items.append({
                "id": rid,
                "title": meta.get("title") or meta.get("sourceUrl") or "",
                "sourceApp": meta.get("sourceApp", "web"),
                "timestamp": meta.get("timestamp", ""),
            })
        items.sort(key=lambda x: x["timestamp"], reverse=True)
        return {"items": items, "total": len(items)}
    except Exception:
        return {"items": [], "total": 0}


# ── LLM provider settings ──────────────────────────────────────────────────

class LLMSettingsResponse(BaseModel):
    """Returned to the dashboard. Never includes raw API keys — only flags."""
    active_provider: str = "ollama"
    active_model: str = ""
    openai_configured: bool = False
    anthropic_configured: bool = False


class LLMSettingsUpdate(BaseModel):
    """All fields optional. Pass an empty string for *_api_key to clear it."""
    active_provider: Optional[str] = None
    active_model: Optional[str] = None
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None


class LLMTestRequest(BaseModel):
    provider: str
    api_key: str = ""
    model: str = ""


@browser_router.get("/llm-settings", response_model=LLMSettingsResponse)
async def get_llm_settings(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> LLMSettingsResponse:
    namespace = _get_namespace(credentials)
    if namespace == NS_BROWSER:
        # Anonymous: return defaults.
        return LLMSettingsResponse(active_provider="ollama")
    user_id = namespace.removeprefix("user_")
    s = get_user_settings(user_id)
    return LLMSettingsResponse(
        active_provider=s.get("active_provider") or "ollama",
        active_model=s.get("active_model") or "",
        openai_configured=bool(s.get("openai_api_key")),
        anthropic_configured=bool(s.get("anthropic_api_key")),
    )


@browser_router.put("/llm-settings", response_model=LLMSettingsResponse)
async def put_llm_settings(
    req: LLMSettingsUpdate,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> LLMSettingsResponse:
    namespace = _get_namespace(credentials)
    if namespace == NS_BROWSER:
        raise HTTPException(status_code=401, detail="Sign in to save settings")
    user_id = namespace.removeprefix("user_")
    updates = {k: v for k, v in req.dict().items() if v is not None}
    if updates.get("active_provider") and updates["active_provider"] not in ("ollama", "openai", "anthropic"):
        raise HTTPException(status_code=400, detail="unknown provider")
    update_user_settings(user_id, **updates)
    return await get_llm_settings(credentials)


@browser_router.post("/llm-settings/test")
async def test_llm_settings(req: LLMTestRequest) -> dict:
    """Validate a provider/key combo without saving. Used by the Settings
    page Test button. No auth needed — the user types their own key here.
    """
    from apps.shail.llm import test_provider
    ok, info = await test_provider(req.provider, req.api_key, req.model)
    return {"ok": ok, "info": info}


# ── Capture log ────────────────────────────────────────────────────────────

@browser_router.get("/capture-log")
async def get_capture_log(
    limit: int = 200,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    """Return the most recent capture-log events for the signed-in user.
    In-memory ring buffer; resets on backend restart.
    """
    namespace = _get_namespace(credentials)
    if namespace == NS_BROWSER:
        raise HTTPException(status_code=401, detail="Sign in to view capture log")
    user_id = namespace.removeprefix("user_")
    from apps.shail.capture_log import read_events
    events = read_events(user_id, limit=limit)
    return {"events": events, "count": len(events)}


# ── Routes (auto-discovered memory clusters) ───────────────────────────────

@browser_router.get("/routes")
async def get_routes(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    """Auto-discovered clusters of the user's memories.

    Clustering rule (v1): bucket by tag. Memories with no tags fall into
    a per-source bucket (e.g. "chatgpt", "web") so we still surface a
    useful structure for fresh accounts. Returns the top 8 buckets by
    memory count.

    Read-only — the user can browse a cluster's memories, but the
    clustering is built by SHAIL, not the user.
    """
    store = _get_store()
    namespace = _get_namespace(credentials)
    if not hasattr(store, "collection"):
        return {"routes": []}

    try:
        result = store.collection.get(where={"namespace": namespace}, include=["metadatas"])
        metadatas = [m or {} for m in result.get("metadatas", [])]
    except Exception as e:
        logger.warning("get_routes store fetch failed: %s", e)
        return {"routes": []}

    buckets: Dict[str, Dict[str, Any]] = {}

    def _bump(label: str, axis: str, meta: dict) -> None:
        b = buckets.setdefault(
            label.lower(),
            {"label": label, "axis": axis, "count": 0, "latest_ts": "", "sample_titles": []},
        )
        b["count"] += 1
        ts = meta.get("timestamp", "")
        if ts and ts > b["latest_ts"]:
            b["latest_ts"] = ts
        title = meta.get("title")
        if title and len(b["sample_titles"]) < 3 and title not in b["sample_titles"]:
            b["sample_titles"].append(title)

    for m in metadatas:
        # Tags are stored as JSON-encoded strings in metadata.
        tags_raw = m.get("tags")
        tag_list: List[str] = []
        if isinstance(tags_raw, str) and tags_raw.startswith("["):
            try:
                tag_list = [t for t in json.loads(tags_raw) if isinstance(t, str)]
            except Exception:
                tag_list = []
        elif isinstance(tags_raw, list):
            tag_list = [t for t in tags_raw if isinstance(t, str)]

        if tag_list:
            for t in tag_list:
                _bump(t, "tag", m)
        else:
            src = m.get("sourceApp") or "web"
            _bump(src, "source", m)

    routes = sorted(buckets.values(), key=lambda r: (-r["count"], r["label"]))[:8]
    return {"routes": routes, "total_clusters": len(buckets)}


# ── Horizon (passive wishlist of suggested ascents) ────────────────────────

@browser_router.get("/horizon")
async def get_horizon(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    """Topics that recur across the user's memories but don't yet have an
    active ascent. Surface them as candidate goals — clicking "Start ascent"
    on the dashboard converts a horizon item into a real ascent.

    Detection (v1): pick clusters from /routes that have ≥3 memories AND
    whose label doesn't appear (case-insensitive) in any active ascent's
    name or description. Manual conversion only — we never auto-create.
    """
    namespace = _get_namespace(credentials)
    if namespace == NS_BROWSER:
        # Anonymous: no ascents to compare against, no horizon either.
        return {"items": []}
    user_id = namespace.removeprefix("user_")

    # Reuse /routes clustering by calling the same logic inline.
    routes_resp = await get_routes(credentials)
    clusters = routes_resp.get("routes", [])

    # Existing active ascents for filtering.
    from apps.shail.auth_store import _conn
    with _conn() as con:
        rows = con.execute(
            "SELECT name, description FROM ascents WHERE user_id = ? AND status = 'active'",
            (user_id,),
        ).fetchall()
    existing_text = " ".join(
        ((r["name"] or "") + " " + (r["description"] or "")) for r in rows
    ).lower()

    items: List[Dict[str, Any]] = []
    for c in clusters:
        if c.get("count", 0) < 3:
            continue
        label = (c.get("label") or "").strip()
        if not label:
            continue
        if label.lower() in existing_text:
            continue
        items.append({
            "label": label,
            "axis": c.get("axis", "tag"),
            "memory_count": c["count"],
            "latest_ts": c.get("latest_ts", ""),
            "sample_titles": c.get("sample_titles", []),
            "suggested_name": label.title(),
            "suggested_description": (
                f"Auto-detected from {c['count']} related memories. "
                + ("Recent: " + ", ".join(c.get("sample_titles", [])[:2]) if c.get("sample_titles") else "")
            ).strip(),
        })

    return {"items": items[:6], "total_candidates": len(items)}

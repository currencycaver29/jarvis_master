"""
Dashboard chat endpoint — RAG-augmented LLM with persistent multi-session
chat history, structured citation tokens, and unified retrieval across
memories, blueprints, past chats, and the open web.

Endpoints (all auth-required):
    GET    /browser/chat/sessions             list all sessions for user
    POST   /browser/chat/sessions             create empty session
    GET    /browser/chat/sessions/{id}        full message thread
    PATCH  /browser/chat/sessions/{id}        rename / toggle pin
    DELETE /browser/chat/sessions/{id}        cascade delete

    POST   /browser/chat                      send a message; SSE response

POST /browser/chat body:
    {
      "message": "...",
      "session_id": "<uuid>" | null,    // omit to auto-create
      "stream": true | false            // default true
    }

Streaming response is SSE with typed events:
    data: {"type":"meta","session_id":"...","provider":"...","model":"...","fellback":false}
    data: {"type":"source_status","source":"memories|web|past_chat","status":"fetching|done","count":N}
    data: {"type":"memories","items":[{id,title,score}]}
    data: {"type":"past_chats","items":[{session_id,message_id,title,score}]}
    data: {"type":"web","items":[{title,url,snippet}]}
    data: {"type":"delta","text":"..."}        // repeated
    data: {"type":"done","message_id":"..."}

The assistant is instructed to emit structured citation tokens like
{{cite:memory:abc}}, {{cite:web:1}}, {{cite:chat:xyz}} which the frontend
parses into clickable CitationLink components.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import AsyncIterator, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from apps.shail.auth_store import (
    get_user_by_api_key,
    touch_api_key_last_used,
    touch_user_last_seen,
)
from apps.shail.blueprints import (
    format_blueprint_for_context, get_blueprints_for_ids,
)
from apps.shail.capture_log import write_event
from apps.shail import chat_store
from apps.shail.llm import call_llm, get_user_llm_config, stream_llm
from apps.shail.web_search import (
    format_for_prompt as web_format,
    needs_web_search,
    search as web_search,
)
from shail.memory.rag import _get_store, ingest, search as rag_search
from shail.memory.embeddings import embed_query as emb_q

logger = logging.getLogger(__name__)

chat_router = APIRouter()
_bearer = HTTPBearer(auto_error=False)

CHAT_SYSTEM_PROMPT = (
    "You are SHAIL — a personal AI assistant with access to the user's "
    "captured memories (private notes from their browsing and AI conversations), "
    "their previous chats with you, and live web results when they're relevant.\n\n"
    "CITATION RULES — read carefully:\n"
    "When you reference any source, you MUST emit a structured citation token "
    "inline at the point of reference. Tokens look like:\n"
    "  {{cite:memory:<memory_id>}}    for captured memories\n"
    "  {{cite:chat:<message_id>}}     for past chat messages\n"
    "  {{cite:web:<index>}}           for live web results (1-based index)\n"
    "  {{cite:mcp:<provider>:<id>}}   for connected sources (drive/notion/github/gmail)\n"
    "Use ONLY ids from the AVAILABLE CITATIONS block below. Never invent ids. "
    "Never use the older [Memory: title] or [1]/[2] formats. Place tokens "
    "next to the claim they support. Be concise and direct."
)

RAG_K           = 6
WEB_MAX_RESULTS = 3
WEB_TIMEOUT     = 3.0
PAST_CHAT_K     = 3

# ── Auth ────────────────────────────────────────────────────────────────────

def _require_user(credentials: Optional[HTTPAuthorizationCredentials]) -> str:
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    user_id = get_user_by_api_key(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid API key")
    touch_api_key_last_used(credentials.credentials)
    touch_user_last_seen(user_id)
    return user_id


# ── Heuristics ──────────────────────────────────────────────────────────────

# Triggers past-chat retrieval. Match on whole-word boundaries to avoid
# false positives like "before" matching "beforehand" — we want explicit
# references to prior conversations, not generic prose.
_PRIOR_CHAT_PATTERNS = re.compile(
    r"\b(earlier|previously|before|last\s+time|last\s+week|last\s+month|"
    r"yesterday|we\s+discussed|we\s+talked|you\s+said|you\s+told|you\s+mentioned|"
    r"remember\s+when|remember\s+what|continue|continuing)\b",
    re.IGNORECASE,
)


def references_prior_chat(query: str, *, is_first_in_session: bool) -> bool:
    """Decide whether to pull past-chat RAG for this query.

    True when:
      - explicit temporal/conversational trigger words match, OR
      - this is the first message in a brand-new session AND the query is
        long enough that the user is likely opening with a continuation
        ("ok now let's pick up where we left off…")
    """
    if _PRIOR_CHAT_PATTERNS.search(query):
        return True
    if is_first_in_session and len(query.split()) >= 8:
        # Be conservative on greenfield sessions: only pull past chats when
        # the user wrote a substantial message (not "hi"). We bias toward
        # quietly including continuity context.
        return True
    return False


# ── Past-chat RAG namespace ─────────────────────────────────────────────────

def _past_chat_namespace(user_id: str) -> str:
    return f"chat_{user_id}"


def _index_past_chat_turn(
    *, user_id: str, session_id: str, user_msg_id: str, assistant_msg_id: str,
    user_text: str, assistant_text: str, session_title: str,
) -> None:
    """Embed a completed Q+A pair into the user's past-chat namespace.
    Errors are logged and swallowed — past-chat indexing is best-effort.
    """
    try:
        record_id = assistant_msg_id  # one indexed turn per assistant reply
        content = f"Q: {user_text}\n\nA: {assistant_text}"
        ingest(records=[{
            "id": record_id,
            "content": content[:6000],
            "namespace": _past_chat_namespace(user_id),
            "metadata": {
                "id": record_id,
                "type": "chat_turn",
                "session_id": session_id,
                "session_title": session_title,
                "user_message_id": user_msg_id,
                "assistant_message_id": assistant_msg_id,
                "title": session_title,
                "summary": user_text[:200],
                "namespace": _past_chat_namespace(user_id),
            },
        }])
    except Exception as e:
        logger.warning("past-chat index failed (session=%s): %s", session_id, e)


def _search_past_chats(user_id: str, query: str, k: int = PAST_CHAT_K) -> list:
    """Vector search over the user's past-chat namespace. Returns hits in
    the same shape rag_search uses: (content, score, meta) tuples.
    """
    try:
        store = _get_store()
        emb = emb_q(query)
        return store.query(
            query_embedding=emb,
            namespace=_past_chat_namespace(user_id),
            k=k,
        )
    except Exception as e:
        logger.warning("past-chat search failed: %s", e)
        return []


# ── Pydantic models ─────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: Optional[str] = None
    stream: bool = True


class WebSourceOut(BaseModel):
    title: str
    url: str
    snippet: str = ""


class MemoryCitation(BaseModel):
    id: str
    title: str
    score: float = 0.0


class PastChatCitation(BaseModel):
    message_id: str
    session_id: str
    session_title: str
    snippet: str
    score: float = 0.0


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    message_id: str
    provider: str
    model: str
    fellback: bool = False
    memories: List[MemoryCitation] = Field(default_factory=list)
    past_chats: List[PastChatCitation] = Field(default_factory=list)
    web_sources: List[WebSourceOut] = Field(default_factory=list)
    used_web: bool = False


class SessionPatch(BaseModel):
    title: Optional[str] = None
    pinned: Optional[bool] = None


# ── Context build ───────────────────────────────────────────────────────────

async def _build_context(
    user_id: str, query: str, *, is_first_in_session: bool,
) -> tuple[str, list[MemoryCitation], list[PastChatCitation], list[WebSourceOut]]:
    """Run all retrieval sources in parallel; combine into a single context
    block plus structured citation lists.
    """
    namespace = f"user_{user_id}"

    async def _rag() -> list:
        try:
            return rag_search(query, k=RAG_K, namespace=namespace)
        except Exception as e:
            logger.warning("rag_search failed in chat: %s", e)
            return []

    async def _past() -> list:
        if not references_prior_chat(query, is_first_in_session=is_first_in_session):
            return []
        return await asyncio.to_thread(_search_past_chats, user_id, query, PAST_CHAT_K)

    rag_task  = asyncio.create_task(_rag())
    past_task = asyncio.create_task(_past())
    web_task = (
        asyncio.create_task(web_search(query, max_results=WEB_MAX_RESULTS, timeout=WEB_TIMEOUT))
        if needs_web_search(query) else None
    )

    rag_hits     = await rag_task
    past_hits    = await past_task
    web_results  = await web_task if web_task else []

    parts: list[str] = []
    citations: list[MemoryCitation] = []
    past_chat_cites: list[PastChatCitation] = []
    web_sources: list[WebSourceOut] = []

    # ── Memories ──
    if rag_hits:
        hit_ids = [
            (m.get("customId") or m.get("id") or m.get("memory_id") or "")
            for _, _, m in rag_hits
        ]
        blueprints = get_blueprints_for_ids([i for i in hit_ids if i])

        rag_lines = ["[AVAILABLE CITATIONS — Memories]"]
        for content, score, meta in rag_hits:
            mid = meta.get("customId") or meta.get("id") or meta.get("memory_id") or ""
            title = meta.get("title", "(untitled)")
            snippet = (content or "").strip().replace("\n", " ")[:300]
            block = f"[memory_id={mid}] {title}\n{snippet}"
            bp = blueprints.get(mid) if mid else None
            if bp:
                hl = format_blueprint_for_context(bp)
                if hl:
                    block += f"\n  blueprint:\n{hl}"
            rag_lines.append(block)
            if mid:
                citations.append(MemoryCitation(id=mid, title=title, score=float(score)))
                write_event("RECALL", f"memory used as chat context: {title[:60]}",
                            user_id=user_id, ref_id=mid)
        parts.append("\n\n".join(rag_lines))

    # ── Past chats ──
    if past_hits:
        chat_lines = ["[AVAILABLE CITATIONS — Past chats from this user]"]
        for content, score, meta in past_hits:
            asst_id = meta.get("assistant_message_id") or meta.get("id") or ""
            sess_id = meta.get("session_id") or ""
            title   = meta.get("session_title") or "(prior chat)"
            snippet = (content or "").strip().replace("\n", " ")[:280]
            chat_lines.append(f"[message_id={asst_id}] (from session: {title})\n{snippet}")
            if asst_id:
                past_chat_cites.append(PastChatCitation(
                    message_id=asst_id,
                    session_id=sess_id,
                    session_title=title,
                    snippet=snippet[:200],
                    score=float(score),
                ))
                write_event("RECALL", f"past chat used as context: {title[:60]}",
                            user_id=user_id, ref_id=asst_id)
        parts.append("\n\n".join(chat_lines))

    # ── Web ──
    if web_results:
        parts.append("[AVAILABLE CITATIONS — Web results]\n" + web_format(web_results))
        web_sources = [WebSourceOut(**r) for r in web_results]

    return "\n\n---\n\n".join(parts), citations, past_chat_cites, web_sources


def _sse(event: dict) -> bytes:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")


# ── Auto-title generation ───────────────────────────────────────────────────

async def _autotitle(session_id: str, user_id: str, first_user_msg: str, first_assistant_msg: str) -> None:
    """Generate a 4-6 word title for a fresh session. Fire-and-forget."""
    try:
        prompt = (
            f"Generate a 4-6 word title for this conversation. "
            f"Reply with ONLY the title — no quotes, no punctuation at the end.\n\n"
            f"User: {first_user_msg[:300]}\nAssistant: {first_assistant_msg[:300]}"
        )
        title, _ = await call_llm(
            messages=[{"role": "user", "content": prompt}],
            user_id=user_id,
            system_prompt="You title conversations concisely.",
        )
        title = (title or "").strip().strip('"').strip("'")[:80]
        if title:
            chat_store.update_session(session_id, user_id, title=title)
    except Exception as e:
        logger.warning("autotitle failed for %s: %s", session_id, e)


# ── Session endpoints ──────────────────────────────────────────────────────

@chat_router.get("/sessions")
async def list_sessions(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    user_id = _require_user(credentials)
    return {"items": chat_store.list_sessions(user_id)}


@chat_router.post("/sessions")
async def create_session(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    user_id = _require_user(credentials)
    return chat_store.create_session(user_id)


@chat_router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    user_id = _require_user(credentials)
    sess = chat_store.get_session(session_id, user_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    sess["messages"] = chat_store.get_messages(session_id, user_id)
    return sess


@chat_router.patch("/sessions/{session_id}")
async def patch_session(
    session_id: str,
    body: SessionPatch,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    user_id = _require_user(credentials)
    sess = chat_store.update_session(session_id, user_id, title=body.title, pinned=body.pinned)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return sess


@chat_router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    user_id = _require_user(credentials)
    ok = chat_store.delete_session(session_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True, "id": session_id}


# ── Main chat endpoint ──────────────────────────────────────────────────────

@chat_router.post("")
async def chat(
    req: ChatRequest,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
):
    user_id = _require_user(credentials)
    cfg = get_user_llm_config(user_id)

    # Resolve / create session
    session: Optional[dict] = None
    if req.session_id:
        session = chat_store.get_session(req.session_id, user_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        is_first = chat_store.get_message_count(session["id"]) == 0
    else:
        session = chat_store.create_session(user_id, title=req.message[:60] or "New chat")
        is_first = True

    session_id = session["id"]

    # Persist the user message FIRST so it's not lost if streaming dies
    user_msg = chat_store.append_message(
        session_id, user_id, role="user", content=req.message,
    )

    # Build the unified RAG context
    context, citations, past_chats, web_sources = await _build_context(
        user_id, req.message, is_first_in_session=is_first,
    )

    # Reload prior thread for the LLM
    prior = chat_store.get_messages(session_id, user_id)
    history_msgs = [
        {"role": m["role"], "content": m["content"]}
        for m in prior if m["role"] in ("user", "assistant") and m["id"] != user_msg["id"]
    ]
    messages = history_msgs + [{"role": "user", "content": req.message}]

    # ── Non-streaming path ──
    if not req.stream:
        answer, meta = await call_llm(
            messages=messages, user_id=user_id,
            context=context, system_prompt=CHAT_SYSTEM_PROMPT,
        )
        asst_msg = chat_store.append_message(
            session_id, user_id, role="assistant", content=answer,
            citations=_collect_citations(citations, past_chats, web_sources),
            provider=meta.get("provider"), model=meta.get("model"),
        )
        # Index into past-chat RAG and auto-title (fire-and-forget)
        _schedule_post_reply(
            user_id=user_id, session_id=session_id,
            user_msg=user_msg, assistant_msg=asst_msg,
            session_title=session["title"], is_first=is_first,
        )
        return ChatResponse(
            answer=answer, session_id=session_id, message_id=asst_msg["id"],
            provider=meta.get("provider", cfg["provider"]),
            model=meta.get("model", cfg["model"]),
            fellback=meta.get("fellback", False),
            memories=citations, past_chats=past_chats,
            web_sources=web_sources, used_web=bool(web_sources),
        )

    # ── Streaming path ──
    async def _stream() -> AsyncIterator[bytes]:
        yield _sse({
            "type": "meta", "session_id": session_id,
            "provider": cfg["provider"], "model": cfg["model"],
            "fellback": cfg.get("fellback", False),
            "is_first": is_first,
            "session_title": session["title"],
        })
        if citations:
            yield _sse({"type": "memories", "items": [c.model_dump() for c in citations]})
        if past_chats:
            yield _sse({"type": "past_chats", "items": [c.model_dump() for c in past_chats]})
        if web_sources:
            yield _sse({"type": "web", "items": [s.model_dump() for s in web_sources]})

        chosen_meta = cfg
        full_answer_parts: list[str] = []
        async for chunk, meta in stream_llm(
            messages=messages, user_id=user_id,
            context=context, system_prompt=CHAT_SYSTEM_PROMPT,
        ):
            chosen_meta = meta
            full_answer_parts.append(chunk)
            yield _sse({"type": "delta", "text": chunk})

        full_answer = "".join(full_answer_parts)

        if chosen_meta.get("fellback") and not cfg.get("fellback"):
            yield _sse({
                "type": "meta",
                "provider": chosen_meta["provider"],
                "model": chosen_meta["model"],
                "fellback": True,
                "reason": chosen_meta.get("reason", ""),
            })

        # Persist the assistant reply
        asst_msg = chat_store.append_message(
            session_id, user_id, role="assistant", content=full_answer,
            citations=_collect_citations(citations, past_chats, web_sources),
            provider=chosen_meta.get("provider"),
            model=chosen_meta.get("model"),
        )

        _schedule_post_reply(
            user_id=user_id, session_id=session_id,
            user_msg=user_msg, assistant_msg=asst_msg,
            session_title=session["title"], is_first=is_first,
        )

        yield _sse({"type": "done", "message_id": asst_msg["id"]})

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _collect_citations(
    memories: list[MemoryCitation],
    past_chats: list[PastChatCitation],
    web_sources: list[WebSourceOut],
) -> list[dict]:
    """Flatten the citation lists into a single JSON-serialisable array
    that the chat_messages.citations column stores. Used by the dashboard
    to re-hydrate citation chips when loading old threads.
    """
    out: list[dict] = []
    for m in memories:
        out.append({"type": "memory", "id": m.id, "title": m.title, "score": m.score})
    for c in past_chats:
        out.append({
            "type": "chat", "id": c.message_id,
            "session_id": c.session_id, "title": c.session_title,
            "snippet": c.snippet, "score": c.score,
        })
    for i, w in enumerate(web_sources, start=1):
        out.append({"type": "web", "id": str(i), "title": w.title, "url": w.url, "snippet": w.snippet})
    return out


def _schedule_post_reply(
    *, user_id: str, session_id: str,
    user_msg: dict, assistant_msg: dict,
    session_title: str, is_first: bool,
) -> None:
    """Fire post-reply background tasks: past-chat indexing + autotitle."""
    async def _run():
        try:
            _index_past_chat_turn(
                user_id=user_id, session_id=session_id,
                user_msg_id=user_msg["id"], assistant_msg_id=assistant_msg["id"],
                user_text=user_msg["content"], assistant_text=assistant_msg["content"],
                session_title=session_title,
            )
        except Exception as e:
            logger.warning("past-chat index task crashed: %s", e)
        if is_first:
            try:
                await _autotitle(session_id, user_id, user_msg["content"], assistant_msg["content"])
            except Exception as e:
                logger.warning("autotitle task crashed: %s", e)
    asyncio.create_task(_run())

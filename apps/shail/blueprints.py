"""
Blueprint generation pipeline — structured knowledge extraction.

A "blueprint" is NOT a summary. A summary compresses content into prose;
a blueprint extracts discrete, queryable knowledge atoms from a capture
(AI conversation or web page) so the system can retrieve and act on them
independently of the original transcript.

Storage: SQLite table `blueprints`, one row per memory_id. JSON blob.

Pipeline:
    /capture succeeds → asyncio.create_task(generate_blueprint(...))
    → call_llm() with structured-extraction prompt
    → parse JSON → store in SQLite
    → blueprint becomes available via GET /browser/blueprint/{id}
    → chat_api injects blueprint highlights into RAG context

The generator is best-effort. Any failure is logged and silently dropped
— the original capture is already saved, so blueprint absence is degraded
service, not data loss.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from apps.shail.llm import call_llm
from apps.shail.settings import get_settings

logger = logging.getLogger(__name__)

BLUEPRINT_VERSION = 1

# ── Schema ──────────────────────────────────────────────────────────────────

def init_blueprint_db() -> None:
    """Create the blueprints table if absent. Called at app startup."""
    path = get_settings().sqlite_path
    with sqlite3.connect(path) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript("""
            CREATE TABLE IF NOT EXISTS blueprints (
                memory_id   TEXT PRIMARY KEY,
                user_id     TEXT,
                namespace   TEXT,
                version     INTEGER NOT NULL,
                content_type TEXT NOT NULL,
                blueprint   TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_blueprints_user ON blueprints(user_id);
        """)


# ── Prompts ─────────────────────────────────────────────────────────────────

_EXTRACTION_INSTRUCTION = """Extract the structured knowledge atoms from the capture below.
Output STRICT JSON only — no prose, no markdown fences. Schema:

{
  "summary": "<one sentence — what happened, not what was said>",
  "decisions": ["<concrete choice made or position taken>", ...],
  "questions_answered": [{"q": "<question>", "a": "<one-line answer>"}, ...],
  "open_questions": ["<unresolved question or unknown>", ...],
  "next_actions": ["<actionable todo implied by the content>", ...],
  "key_entities": ["<name, lib, person, project, technology>", ...],
  "code_references": [{"language": "<lang>", "purpose": "<what it does>"}, ...]
}

Rules:
- Empty arrays for fields with nothing to extract — never invent.
- Decisions are CHOICES, not facts. ("chose X over Y", not "X exists")
- Open questions are things still unknown after the conversation.
- Next actions are things the user (not the assistant) should do.
- Entities: 3–8 max, the most central. No generic terms.
- Code references describe code present, not just mentioned.
- Output the JSON object, nothing else.
"""

_AI_CONV_PREFACE = "This is an AI assistant conversation. Extract knowledge from BOTH user messages and assistant replies."
_WEB_PREFACE = "This is a web page captured by the user. Extract the knowledge they likely cared about."


def _build_extraction_prompt(content_type: str, content: str) -> tuple[str, str]:
    """Return (system_prompt, user_message) for the extraction call."""
    preface = _AI_CONV_PREFACE if content_type == "ai_conversation" else _WEB_PREFACE
    system = (
        "You are a knowledge-extraction engine. You read captures and emit "
        "strict JSON describing the structured atoms inside them. You never "
        "summarize or paraphrase as prose."
    )
    user_msg = f"{preface}\n\n{_EXTRACTION_INSTRUCTION}\n\n--- CAPTURE ---\n{content}\n--- END ---"
    return system, user_msg


# ── Parsing ─────────────────────────────────────────────────────────────────

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_REQUIRED_FIELDS = (
    "summary", "decisions", "questions_answered",
    "open_questions", "next_actions", "key_entities", "code_references",
)


def _parse_blueprint(raw: str) -> Optional[dict]:
    """Parse the LLM output. Tolerant of code fences and trailing prose.
    Returns None if no valid JSON object can be extracted.
    """
    if not raw:
        return None
    cleaned = _FENCE_RE.sub("", raw.strip())

    # Find the first {...} block — LLMs sometimes emit prose before/after.
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    candidate = cleaned[start:end + 1]

    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    # Coerce missing fields to safe defaults rather than reject — partial
    # blueprints are still useful.
    out = {
        "summary": str(data.get("summary") or "")[:500],
        "decisions": _coerce_str_list(data.get("decisions")),
        "questions_answered": _coerce_qa_list(data.get("questions_answered")),
        "open_questions": _coerce_str_list(data.get("open_questions")),
        "next_actions": _coerce_str_list(data.get("next_actions")),
        "key_entities": _coerce_str_list(data.get("key_entities"))[:8],
        "code_references": _coerce_code_list(data.get("code_references")),
    }
    return out


def _coerce_str_list(v) -> list[str]:
    if not isinstance(v, list):
        return []
    return [str(x).strip()[:300] for x in v if isinstance(x, (str, int, float)) and str(x).strip()][:12]


def _coerce_qa_list(v) -> list[dict]:
    if not isinstance(v, list):
        return []
    out = []
    for item in v[:12]:
        if isinstance(item, dict):
            q = str(item.get("q") or item.get("question") or "").strip()[:300]
            a = str(item.get("a") or item.get("answer") or "").strip()[:300]
            if q:
                out.append({"q": q, "a": a})
    return out


def _coerce_code_list(v) -> list[dict]:
    if not isinstance(v, list):
        return []
    out = []
    for item in v[:8]:
        if isinstance(item, dict):
            out.append({
                "language": str(item.get("language") or "").strip()[:30],
                "purpose":  str(item.get("purpose")  or "").strip()[:200],
            })
    return out


# ── CRUD ────────────────────────────────────────────────────────────────────

def save_blueprint(
    memory_id: str,
    blueprint: dict,
    *,
    user_id: Optional[str],
    namespace: str,
    content_type: str,
) -> None:
    path = get_settings().sqlite_path
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(path) as con:
        con.execute(
            "INSERT OR REPLACE INTO blueprints "
            "(memory_id, user_id, namespace, version, content_type, blueprint, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (memory_id, user_id, namespace, BLUEPRINT_VERSION, content_type,
             json.dumps(blueprint, ensure_ascii=False), now),
        )


def get_blueprint(memory_id: str) -> Optional[dict]:
    path = get_settings().sqlite_path
    with sqlite3.connect(path) as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT blueprint, content_type, created_at, version "
            "FROM blueprints WHERE memory_id = ?",
            (memory_id,),
        ).fetchone()
    if not row:
        return None
    try:
        bp = json.loads(row["blueprint"])
    except json.JSONDecodeError:
        return None
    return {
        "memory_id": memory_id,
        "version": row["version"],
        "content_type": row["content_type"],
        "created_at": row["created_at"],
        **bp,
    }


def get_blueprint_ids(memory_ids: list[str]) -> set[str]:
    """Return the subset of memory_ids that have a blueprint row.
    Used by the Memories list to render a BLUEPRINT badge without
    fetching the full blueprint per card.
    """
    if not memory_ids:
        return set()
    path = get_settings().sqlite_path
    placeholders = ",".join("?" for _ in memory_ids)
    with sqlite3.connect(path) as con:
        rows = con.execute(
            f"SELECT memory_id FROM blueprints WHERE memory_id IN ({placeholders})",
            memory_ids,
        ).fetchall()
    return {r[0] for r in rows}


def get_blueprints_for_ids(memory_ids: list[str]) -> dict[str, dict]:
    """Batch fetch — one query for multiple ids. Used by chat_api RAG."""
    if not memory_ids:
        return {}
    path = get_settings().sqlite_path
    placeholders = ",".join("?" for _ in memory_ids)
    with sqlite3.connect(path) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            f"SELECT memory_id, blueprint FROM blueprints WHERE memory_id IN ({placeholders})",
            memory_ids,
        ).fetchall()
    out: dict[str, dict] = {}
    for r in rows:
        try:
            out[r["memory_id"]] = json.loads(r["blueprint"])
        except json.JSONDecodeError:
            continue
    return out


def delete_blueprint(memory_id: str) -> None:
    path = get_settings().sqlite_path
    with sqlite3.connect(path) as con:
        con.execute("DELETE FROM blueprints WHERE memory_id = ?", (memory_id,))


# ── Generation ──────────────────────────────────────────────────────────────

async def generate_blueprint(
    memory_id: str,
    *,
    content: str,
    content_type: str,
    user_id: Optional[str],
    namespace: str,
) -> Optional[dict]:
    """Run the extraction LLM call, parse, save. Best-effort — returns
    None on failure but never raises into the caller.
    """
    if not content or len(content.strip()) < 40:
        return None  # too thin to extract anything meaningful

    # 16K char cap accommodates 10-turn AI conversations after the multi-turn
    # extractor lands. Below this we trust the LLM's context window; above it
    # we'd need chunked extraction (deferred to v2).
    system_prompt, user_msg = _build_extraction_prompt(content_type, content[:16000])
    try:
        raw, meta = await call_llm(
            messages=[{"role": "user", "content": user_msg}],
            user_id=user_id,
            system_prompt=system_prompt,
        )
    except Exception as e:
        logger.warning("blueprint LLM call failed for %s: %s", memory_id, e)
        return None

    bp = _parse_blueprint(raw)
    if not bp:
        logger.warning("blueprint parse failed for %s (raw head: %s)", memory_id, (raw or "")[:120])
        return None

    try:
        save_blueprint(memory_id, bp,
                       user_id=user_id, namespace=namespace, content_type=content_type)
    except Exception as e:
        logger.warning("blueprint save failed for %s: %s", memory_id, e)
        return None
    return bp


# ── Context formatter for RAG ───────────────────────────────────────────────

def format_blueprint_for_context(bp: dict, *, max_lines: int = 6) -> str:
    """Render a blueprint as a compact context block for chat RAG.
    Highlights the actionable atoms (decisions, open_questions, next_actions)
    first because those are what make blueprint > summary for chat.
    """
    lines: list[str] = []
    if bp.get("decisions"):
        for d in bp["decisions"][:3]:
            lines.append(f"  • decided: {d}")
    if bp.get("open_questions"):
        for q in bp["open_questions"][:2]:
            lines.append(f"  • open: {q}")
    if bp.get("next_actions"):
        for a in bp["next_actions"][:2]:
            lines.append(f"  • todo: {a}")
    if bp.get("key_entities"):
        ents = ", ".join(bp["key_entities"][:5])
        if ents:
            lines.append(f"  • entities: {ents}")
    return "\n".join(lines[:max_lines])

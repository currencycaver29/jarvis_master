"""
Chat session + message persistence layer.

Tables (created by `init_auth_db()` in auth_store.py):
    chat_sessions   — one row per conversation (user_id, title, pinned, timestamps)
    chat_messages   — one row per turn (session_id, role, content, citations JSON)

This module owns all reads/writes for those tables. The chat API and the
past-chat RAG indexer both go through here.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from apps.shail.auth_store import _conn

# ── Helpers ─────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Sessions ────────────────────────────────────────────────────────────────

def create_session(user_id: str, title: str = "New chat") -> dict:
    sid = str(uuid.uuid4())
    now = _now()
    with _conn() as con:
        con.execute(
            "INSERT INTO chat_sessions (id, user_id, title, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (sid, user_id, title, now, now),
        )
    return {"id": sid, "user_id": user_id, "title": title,
            "created_at": now, "updated_at": now, "pinned": False}


def get_session(session_id: str, user_id: str) -> Optional[dict]:
    """Returns the session dict if it belongs to user_id, else None."""
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM chat_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()
    return _row_to_session(row) if row else None


def list_sessions(user_id: str, limit: int = 100) -> list[dict]:
    """Newest first, with message_count + last_message_preview for sidebar."""
    with _conn() as con:
        rows = con.execute(
            """SELECT s.*,
                      (SELECT COUNT(*) FROM chat_messages WHERE session_id = s.id) AS msg_count,
                      (SELECT content FROM chat_messages
                       WHERE session_id = s.id AND role = 'user'
                       ORDER BY created_at DESC LIMIT 1) AS last_user_msg
               FROM chat_sessions s
               WHERE s.user_id = ?
               ORDER BY s.pinned DESC, s.updated_at DESC
               LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    out: list[dict] = []
    for r in rows:
        d = _row_to_session(r)
        d["message_count"] = int(r["msg_count"] or 0)
        d["preview"] = (r["last_user_msg"] or "")[:120]
        out.append(d)
    return out


def update_session(
    session_id: str, user_id: str,
    *, title: Optional[str] = None, pinned: Optional[bool] = None,
) -> Optional[dict]:
    fields: list[str] = []
    values: list[Any] = []
    if title is not None:
        fields.append("title = ?"); values.append(title)
    if pinned is not None:
        fields.append("pinned = ?"); values.append(1 if pinned else 0)
    if not fields:
        return get_session(session_id, user_id)
    fields.append("updated_at = ?"); values.append(_now())
    values.extend([session_id, user_id])
    with _conn() as con:
        cur = con.execute(
            f"UPDATE chat_sessions SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
            values,
        )
        if cur.rowcount == 0:
            return None
    return get_session(session_id, user_id)


def delete_session(session_id: str, user_id: str) -> bool:
    with _conn() as con:
        cur = con.execute(
            "DELETE FROM chat_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )
        # CASCADE deletes chat_messages automatically
    return cur.rowcount > 0


def touch_session(session_id: str) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
            (_now(), session_id),
        )


def _row_to_session(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "title": row["title"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "pinned": bool(row["pinned"]),
    }


# ── Messages ────────────────────────────────────────────────────────────────

def append_message(
    session_id: str,
    user_id: str,
    role: str,
    content: str,
    *,
    citations: Optional[list] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """Append a single message. Bumps the session's updated_at as a side effect."""
    if role not in ("user", "assistant"):
        raise ValueError(f"invalid role: {role}")
    mid = str(uuid.uuid4())
    now = _now()
    cit_json = json.dumps(citations) if citations else None
    with _conn() as con:
        con.execute(
            "INSERT INTO chat_messages "
            "(id, session_id, user_id, role, content, citations, provider, model, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (mid, session_id, user_id, role, content, cit_json, provider, model, now),
        )
        con.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )
    return {
        "id": mid, "session_id": session_id, "user_id": user_id, "role": role,
        "content": content, "citations": citations or [],
        "provider": provider, "model": model, "created_at": now,
    }


def get_messages(session_id: str, user_id: str, limit: int = 500) -> list[dict]:
    """Full thread, oldest first. Returns empty list if session not owned by user."""
    with _conn() as con:
        owner = con.execute(
            "SELECT 1 FROM chat_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()
        if not owner:
            return []
        rows = con.execute(
            "SELECT * FROM chat_messages WHERE session_id = ? "
            "ORDER BY created_at ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [_row_to_message(r) for r in rows]


def get_message_count(session_id: str) -> int:
    with _conn() as con:
        row = con.execute(
            "SELECT COUNT(*) AS c FROM chat_messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return int(row["c"]) if row else 0


def get_message(message_id: str) -> Optional[dict]:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM chat_messages WHERE id = ?", (message_id,),
        ).fetchone()
    return _row_to_message(row) if row else None


def _row_to_message(row: sqlite3.Row) -> dict:
    citations: list = []
    if row["citations"]:
        try:
            citations = json.loads(row["citations"])
        except json.JSONDecodeError:
            citations = []
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "user_id": row["user_id"],
        "role": row["role"],
        "content": row["content"],
        "citations": citations,
        "provider": row["provider"],
        "model": row["model"],
        "created_at": row["created_at"],
    }

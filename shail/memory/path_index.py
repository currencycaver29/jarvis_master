"""
Path Index — Tier 3 memory.

Stores lightweight metadata pointers to local files.
No content chunks are stored here — on query the file is read at retrieval time.
"""

from __future__ import annotations

import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional


# ── Schema ────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS path_index (
    id          TEXT PRIMARY KEY,
    path        TEXT NOT NULL UNIQUE,
    file_type   TEXT NOT NULL,
    size_bytes  INTEGER,
    mtime       REAL,
    title       TEXT,
    summary_snippet TEXT,
    indexed_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_path_index_path  ON path_index(path);
CREATE INDEX IF NOT EXISTS idx_path_index_type  ON path_index(file_type);
CREATE INDEX IF NOT EXISTS idx_path_index_mtime ON path_index(mtime DESC);
"""

_SCAN_ROOTS = [
    Path.home() / "Documents",
    Path.home() / "Desktop",
    Path.home() / "Downloads",
]

_INCLUDE_EXTS = {
    ".pdf", ".docx", ".doc", ".txt", ".md", ".pages",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs",
    ".csv", ".json", ".yaml", ".yml",
    ".xls", ".xlsx", ".pptx",
}

_SKIP_DIRS = {
    ".git", ".svn", "node_modules", "__pycache__", ".DS_Store",
    "venv", "env", ".venv",
}


@contextmanager
def _conn(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        con.executescript(_DDL)
        con.commit()
        yield con
    finally:
        con.close()


# ── Write ─────────────────────────────────────────────────────────────────────

def upsert_file(db_path: str, file_path: str) -> Optional[str]:
    """Add or refresh a single file's metadata in the index. Returns record id."""
    p = Path(file_path)
    if not p.exists() or not p.is_file():
        return None
    ext = p.suffix.lower()
    if ext not in _INCLUDE_EXTS:
        return None
    try:
        stat = p.stat()
    except OSError:
        return None

    with _conn(db_path) as con:
        existing = con.execute("SELECT id FROM path_index WHERE path = ?", (str(p),)).fetchone()
        record_id = existing["id"] if existing else str(uuid.uuid4())
        con.execute(
            """
            INSERT INTO path_index (id, path, file_type, size_bytes, mtime, title, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                file_type   = excluded.file_type,
                size_bytes  = excluded.size_bytes,
                mtime       = excluded.mtime,
                title       = excluded.title,
                indexed_at  = excluded.indexed_at
            """,
            (record_id, str(p), ext.lstrip("."), stat.st_size, stat.st_mtime, p.stem, time.time()),
        )
        con.commit()
    return record_id


def remove_file(db_path: str, file_path: str) -> None:
    with _conn(db_path) as con:
        con.execute("DELETE FROM path_index WHERE path = ?", (file_path,))
        con.commit()


# ── Scan ─────────────────────────────────────────────────────────────────────

def scan(db_path: str, roots: Optional[List[str]] = None) -> int:
    """
    Walk configured roots, upsert every matching file. Returns count of files indexed.
    Skips files that haven't changed (mtime unchanged).
    """
    scan_roots = [Path(r) for r in roots] if roots else _SCAN_ROOTS
    count = 0

    with _conn(db_path) as con:
        existing: Dict[str, float] = {
            row["path"]: row["mtime"]
            for row in con.execute("SELECT path, mtime FROM path_index")
        }

    for root in scan_roots:
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fname in filenames:
                fpath = Path(dirpath) / fname
                if fpath.suffix.lower() not in _INCLUDE_EXTS:
                    continue
                try:
                    mtime = fpath.stat().st_mtime
                except OSError:
                    continue
                if str(fpath) in existing and existing[str(fpath)] == mtime:
                    continue
                if upsert_file(db_path, str(fpath)):
                    count += 1

    return count


# ── Search ────────────────────────────────────────────────────────────────────

def search(db_path: str, query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Keyword search over filename/path. Returns metadata rows.
    Full content is NOT returned here — callers read the file on demand.
    """
    terms = [f"%{t}%" for t in query.split() if t]
    if not terms:
        with _conn(db_path) as con:
            rows = con.execute(
                "SELECT * FROM path_index ORDER BY mtime DESC LIMIT ?", (limit,)
            ).fetchall()
    else:
        like_clauses = " OR ".join(
            ["(LOWER(path) LIKE ? OR LOWER(title) LIKE ?)"] * len(terms)
        )
        params: list = []
        for t in terms:
            params.extend([t.lower(), t.lower()])
        params.append(limit)
        with _conn(db_path) as con:
            rows = con.execute(
                f"SELECT * FROM path_index WHERE {like_clauses} ORDER BY mtime DESC LIMIT ?",
                params,
            ).fetchall()

    return [dict(r) for r in rows]


def get_by_id(db_path: str, record_id: str) -> Optional[Dict[str, Any]]:
    with _conn(db_path) as con:
        row = con.execute("SELECT * FROM path_index WHERE id = ?", (record_id,)).fetchone()
    return dict(row) if row else None


def stats(db_path: str) -> Dict[str, Any]:
    with _conn(db_path) as con:
        total = con.execute("SELECT COUNT(*) FROM path_index").fetchone()[0]
        by_type = {
            row[0]: row[1]
            for row in con.execute(
                "SELECT file_type, COUNT(*) FROM path_index GROUP BY file_type ORDER BY 2 DESC"
            )
        }
    return {"total": total, "by_type": by_type}

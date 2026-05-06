"""
One-shot Chroma metadata migration for Phase 1 namespace unification.

Backfills `tier` and `source` on existing records:
  - records with metadata.eventType set → tier=important, source=browser_<sourceApp>
  - records in shail_ephemeral collection → tier=ephemeral, source unchanged
  - records in shail_important collection → tier=important, source unchanged
  - records with no namespace metadata → namespace="local"

Idempotent: re-running is safe.

Usage:
  cd ~/jarvis_master
  source services_env/bin/activate
  python scripts/migrate_namespaces.py
"""

from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shail.memory.rag import _get_store, COLLECTION_EPHEMERAL, COLLECTION_IMPORTANT, get_tier_store


def _backfill(store, default_tier: str | None) -> int:
    if not hasattr(store, "collection"):
        return 0
    raw = store.collection.get(include=["metadatas"])
    ids = raw.get("ids") or []
    metas = raw.get("metadatas") or []
    if not ids:
        return 0
    updated_ids: list[str] = []
    updated_metas: list[dict] = []
    for rid, meta in zip(ids, metas):
        m = dict(meta or {})
        changed = False
        if "namespace" not in m:
            m["namespace"] = "local"
            changed = True
        if "tier" not in m:
            if default_tier:
                m["tier"] = default_tier
                changed = True
            elif m.get("eventType"):
                m["tier"] = "important"
                changed = True
        if "source" not in m:
            if m.get("sourceApp"):
                m["source"] = f"browser_{m['sourceApp']}"
                changed = True
            elif default_tier == "ephemeral":
                m["source"] = m.get("source") or "macos_fs"
                changed = True
            elif default_tier == "important":
                m["source"] = m.get("source") or "manual"
                changed = True
        if changed:
            updated_ids.append(rid)
            updated_metas.append(m)
    if updated_ids:
        store.collection.update(ids=updated_ids, metadatas=updated_metas)
    return len(updated_ids)


def main() -> None:
    base = _get_store()
    n_base = _backfill(base, default_tier=None)
    print(f"base store: backfilled {n_base} records")

    eph = get_tier_store(COLLECTION_EPHEMERAL)
    if eph is not base:
        n_eph = _backfill(eph, default_tier="ephemeral")
        print(f"shail_ephemeral: backfilled {n_eph} records")

    imp = get_tier_store(COLLECTION_IMPORTANT)
    if imp is not base:
        n_imp = _backfill(imp, default_tier="important")
        print(f"shail_important: backfilled {n_imp} records")

    print("Migration complete.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Migrate shail_rag ChromaDB collection from 3072-dim (Gemini) to 768-dim (nomic-embed-text).

Steps:
1. Dump all records (text + metadata) from shail_rag
2. Delete the shail_rag collection
3. Re-embed each record with nomic-embed-text via Ollama
4. Upsert into freshly created shail_rag (now 768-dim)
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

CHROMA_PATH = Path.home() / "Library/Application Support/SHAIL/memory/chroma"
COLLECTION_NAME = "shail_rag"
OLLAMA_BASE = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"


def embed(text: str) -> list[float]:
    payload = json.dumps({"model": EMBED_MODEL, "prompt": text}).encode()
    req = urllib.request.Request(
        f"{OLLAMA_BASE}/api/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["embedding"]


def main():
    try:
        import chromadb
    except ImportError:
        print("ERROR: chromadb not installed. Activate venv first.")
        sys.exit(1)

    # ── 1. Connect and dump ──────────────────────────────────────────────────
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))

    existing_names = [c.name for c in client.list_collections()]
    if COLLECTION_NAME not in existing_names:
        print(f"Collection '{COLLECTION_NAME}' not found. Nothing to migrate.")
        return

    col = client.get_collection(COLLECTION_NAME)
    total = col.count()
    print(f"Found {total} records in '{COLLECTION_NAME}' (dim={col.metadata}).")

    if total == 0:
        print("Collection empty — deleting and recreating with 768-dim config.")
        client.delete_collection(COLLECTION_NAME)
        client.get_or_create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
        print("Done.")
        return

    # Fetch everything (no embeddings — we discard old vectors)
    result = col.get(include=["documents", "metadatas"])
    ids    = result.get("ids", [])
    docs   = result.get("documents", []) or [""] * len(ids)
    metas  = result.get("metadatas", []) or [{}] * len(ids)
    print(f"Dumped {len(ids)} records.")

    # ── 2. Test Ollama reachable ─────────────────────────────────────────────
    print(f"Testing Ollama embed at {OLLAMA_BASE} with model {EMBED_MODEL}...")
    try:
        test_vec = embed("test")
        dim = len(test_vec)
        print(f"Ollama OK — embedding dim = {dim}")
    except Exception as exc:
        print(f"ERROR: Cannot reach Ollama: {exc}")
        print("Start Ollama and ensure nomic-embed-text is pulled, then retry.")
        sys.exit(1)

    # ── 3. Delete old collection ─────────────────────────────────────────────
    client.delete_collection(COLLECTION_NAME)
    print(f"Deleted old '{COLLECTION_NAME}'.")

    # ── 4. Create fresh collection ───────────────────────────────────────────
    new_col = client.get_or_create_collection(
        COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    print(f"Created fresh '{COLLECTION_NAME}'.")

    # ── 5. Re-embed and upsert ───────────────────────────────────────────────
    batch_ids   = []
    batch_docs  = []
    batch_metas = []
    batch_vecs  = []

    errors = 0
    for i, (rid, doc, meta) in enumerate(zip(ids, docs, metas)):
        text = doc or ""
        try:
            vec = embed(text if text else " ")  # Ollama rejects empty string
            batch_ids.append(rid)
            batch_docs.append(doc)
            batch_metas.append(meta or {})
            batch_vecs.append(vec)
            print(f"  [{i+1}/{total}] re-embedded '{rid[:16]}...' ({len(vec)}-dim)")
        except Exception as exc:
            print(f"  [{i+1}/{total}] WARN: skip '{rid[:16]}...' — {exc}")
            errors += 1
        # Small delay to avoid hammering Ollama
        time.sleep(0.05)

    if batch_ids:
        new_col.upsert(
            ids=batch_ids,
            documents=batch_docs,
            metadatas=batch_metas,
            embeddings=batch_vecs,
        )
        print(f"\nUpserted {len(batch_ids)} records into '{COLLECTION_NAME}'.")

    if errors:
        print(f"WARNING: {errors} records skipped due to embed errors.")

    print(f"\nMigration complete. Collection now has {new_col.count()} records at {dim}-dim.")
    print("Restart the FastAPI backend to pick up the fix.")


if __name__ == "__main__":
    main()

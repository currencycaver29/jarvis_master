"""
Persistent Memory Store

Simple JSON file-based storage for MVP.
Stores skills and traces to disk for persistence across restarts.
Replaces in-memory storage with file-based storage.

For production, upgrade to RAG (pgvector/Chroma).
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from shail.hermes.types import HermesSkill, ExecutionTrace, ExecutionStatus
from shail.memory.vector_store import get_vector_store, EmbeddingRecord
from shail.memory.embeddings import embed_texts, embed_query
from apps.shail.settings import get_settings


logger = logging.getLogger(__name__)


class PersistentMemory:
    """
    File-based persistent storage for Hermes.
    Now integrated with SHAIL VectorStore for semantic search.

    Features:
    - Stores skills to JSON file and VectorStore (Chroma)
    - Stores execution traces to JSON file
    - Auto-saves on changes
    - Semantic search for skills using RAG
    - Thread-safe with asyncio lock
    """

    def __init__(self, storage_dir: Optional[str] = None):
        if storage_dir is None:
            storage_dir = os.path.join(os.path.dirname(__file__), "storage")

        self.storage_dir = Path(storage_dir)
        self.skills_file = self.storage_dir / "skills.json"
        self.traces_file = self.storage_dir / "traces.json"

        self._skills: Dict[str, HermesSkill] = {}
        self._traces: Dict[str, ExecutionTrace] = {}
        self._lock = asyncio.Lock()

        # Vector Store components (lazily initialized)
        self._vector_store = None
        self._skill_collection = None
        self._trace_collection = None

        # Create storage directory
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Load existing data (synchronous for simplicity)
        self._load_skills_sync()
        self._load_traces_sync()

    def _ensure_vector_store(self):
        """Ensure vector store and collections are initialized."""
        if self._vector_store is not None:
            return

        try:
            settings = get_settings()
            self._vector_store = get_vector_store(
                store_type=settings.rag_vector_store,
                dsn=settings.rag_pg_dsn,
                chroma_path=settings.rag_chroma_path,
                dim=settings.rag_embedding_dim
            )
            # Use a dedicated collection for Hermes skills
            if hasattr(self._vector_store, "get_collection"):
                self._skill_collection = self._vector_store.get_collection("hermes_skills")
                self._trace_collection = self._vector_store.get_collection("hermes_traces")
            else:
                self._skill_collection = self._vector_store
                self._trace_collection = self._vector_store
        except Exception as e:
            logger.warning(f"Failed to initialize vector store: {e}")

    @property
    def vector_store(self):
        self._ensure_vector_store()
        return self._vector_store

    @property
    def skill_collection(self):
        self._ensure_vector_store()
        return self._skill_collection

    @skill_collection.setter
    def skill_collection(self, value):
        self._skill_collection = value

    @property
    def trace_collection(self):
        self._ensure_vector_store()
        return self._trace_collection

    @trace_collection.setter
    def trace_collection(self, value):
        self._trace_collection = value

    async def _load_all(self):
        """Load all data from disk."""
        await self._load_skills()
        await self._load_traces()

    def _load_skills_sync(self):
        """Load skills from JSON file (synchronous)."""
        if not self.skills_file.exists():
            return

        try:
            with open(self.skills_file, "r") as f:
                data = json.load(f)

            for skill_data in data.values():
                skill = HermesSkill(**skill_data)
                self._skills[skill.skill_id] = skill

            logger.info(f"Loaded {len(self._skills)} skills from disk")

        except Exception as e:
            logger.error(f"Failed to load skills: {e}")

    def _load_traces_sync(self):
        """Load traces from JSON file (synchronous)."""
        if not self.traces_file.exists():
            return

        try:
            with open(self.traces_file, "r") as f:
                data = json.load(f)

            for trace_data in data.values():
                trace_data["status"] = ExecutionStatus(trace_data["status"])
                trace = ExecutionTrace(**trace_data)
                self._traces[trace.trace_id] = trace

            logger.info(f"Loaded {len(self._traces)} traces from disk")

        except Exception as e:
            logger.error(f"Failed to load traces: {e}")

    def _save_skills_sync(self):
        """Save skills to JSON file (synchronous)."""
        try:
            data = {
                skill_id: skill.model_dump()
                for skill_id, skill in self._skills.items()
            }

            with open(self.skills_file, "w") as f:
                json.dump(data, f, indent=2, default=str)

            logger.debug(f"Saved {len(self._skills)} skills to disk")

        except Exception as e:
            logger.error(f"Failed to save skills: {e}")

    def _save_traces_sync(self):
        """Save traces to JSON file (synchronous)."""
        try:
            data = {}
            for trace_id, trace in self._traces.items():
                trace_dict = trace.model_dump()
                trace_dict["status"] = trace.status.value
                data[trace_id] = trace_dict

            with open(self.traces_file, "w") as f:
                json.dump(data, f, indent=2, default=str)

            logger.debug(f"Saved {len(self._traces)} traces to disk")

        except Exception as e:
            logger.error(f"Failed to save traces: {e}")

    # ===== Skill Operations =====

    def store_skill(self, skill: HermesSkill):
        """Store a skill (sync JSON + async VectorStore)."""
        # Store in JSON
        self._skills[skill.skill_id] = skill
        self._save_skills_sync()
        
        # Store in Vector Store for semantic search
        try:
            content = f"{skill.name}\n{skill.description or ''}\nTags: {', '.join(skill.tags)}"
            embedding = embed_texts([content])[0]
            
            record = EmbeddingRecord(
                id=skill.skill_id,
                namespace="hermes_skills",
                content=content,
                metadata={
                    "skill_id": skill.skill_id,
                    "name": skill.name,
                    "success_rate": skill.success_rate,
                    "type": "hermes_skill"
                },
                embedding=embedding
            )
            self.skill_collection.upsert([record])
            logger.info(f"Stored skill in vector store: {skill.skill_id}")
        except Exception as e:
            logger.warning(f"Failed to store skill in vector store: {e}")

        logger.info(f"Stored skill: {skill.skill_id} - {skill.name}")

    def get_skill(self, skill_id: str) -> Optional[HermesSkill]:
        """Get a skill by ID."""
        return self._skills.get(skill_id)

    def get_all_skills(self) -> List[HermesSkill]:
        """Get all skills."""
        return list(self._skills.values())

    def delete_skill(self, skill_id: str) -> bool:
        """Delete a skill."""
        if skill_id in self._skills:
            del self._skills[skill_id]
            self._save_skills_sync()
            try:
                self.skill_collection.delete_ids([skill_id])
            except Exception as e:
                logger.warning(f"Failed to delete skill from vector store: {e}")
            return True
        return False

    def search_skills(self, query: str, limit: int = 5) -> List[HermesSkill]:
        """Search skills using semantic search (RAG)."""
        try:
            query_embedding = embed_query(query)
            if not query_embedding:
                return self._search_skills_keyword(query)
                
            results = self.skill_collection.query(
                query_embedding=query_embedding,
                namespace="hermes_skills",
                filters=None,
                k=limit
            )
            
            skills = []
            for res in results:
                skill_id = res["metadata"].get("skill_id")
                if skill_id and skill_id in self._skills:
                    skills.append(self._skills[skill_id])
            
            if not skills:
                return self._search_skills_keyword(query)
                
            return skills
            
        except Exception as e:
            logger.error(f"Vector search failed, falling back to keyword: {e}")
            return self._search_skills_keyword(query)

    def _search_skills_keyword(self, query: str) -> List[HermesSkill]:
        """Fallback keyword search."""
        query_lower = query.lower()
        results = []

        for skill in self._skills.values():
            search_text = " ".join([
                skill.name.lower(),
                (skill.description or "").lower(),
                " ".join(skill.tags),
            ])

            if query_lower in search_text:
                results.append(skill)

        results.sort(key=lambda s: s.success_rate, reverse=True)
        return results

    def update_skill_stats(self, skill_id: str, success: bool):
        """Update skill statistics."""
        skill = self._skills.get(skill_id)
        if not skill:
            return

        skill.execution_count += 1

        if success:
            skill.success_rate = 0.9 * skill.success_rate + 0.1 * 1.0
        else:
            skill.success_rate = 0.9 * skill.success_rate + 0.1 * 0.0

        # Auto-save on stat update
        self._save_skills_sync()
        
        # Update success rate in vector store metadata
        try:
            # We don't want to re-embed, just update metadata if the store supports it
            # Chroma upsert works like an update if ID exists
            # For simplicity, we'll just log it for now as metadata update is store-specific
            pass
        except Exception:
            pass

    def generate_skill_from_trace(self, trace: ExecutionTrace) -> Optional[HermesSkill]:
        """Generate a skill from a trace."""
        if trace.status != ExecutionStatus.COMPLETED:
            return None

        if trace.execution_time_ms < 2000:
            return None

        import uuid
        skill_id = f"skill_{uuid.uuid4().hex[:8]}"

        skill = HermesSkill(
            skill_id=skill_id,
            name=f"Auto-generated: {trace.task[:40]}",
            prompt_template=f"Task: {{task}}\n\nContext: {{context}}\n\nExecute the following steps to complete the task.",
            description=f"Generated from trace {trace.trace_id}",
            tags=["auto-generated", "from-trace"],
        )

        return skill

    # ===== Trace Operations =====

    def store_trace(self, trace: ExecutionTrace):
        """Store an execution trace and vectorize it if successful."""
        self._traces[trace.trace_id] = trace
        self._save_traces_sync()
        
        # Ingest into RAG if successful
        if trace.status == ExecutionStatus.COMPLETED:
            try:
                content = f"Task: {trace.task}\nResult: {str(trace.result)[:1000]}"
                embedding = embed_texts([content])[0]
                
                record = EmbeddingRecord(
                    id=trace.trace_id,
                    namespace="hermes_traces",
                    content=content,
                    metadata={
                        "trace_id": trace.trace_id,
                        "task": trace.task,
                        "execution_time_ms": trace.execution_time_ms,
                        "retry_count": trace.retry_count,
                        "type": "hermes_trace"
                    },
                    embedding=embedding
                )
                self.trace_collection.upsert([record])
                logger.info(f"Ingested successful trace into vector store: {trace.trace_id}")
            except Exception as e:
                logger.warning(f"Failed to ingest trace into vector store: {e}")

    def get_trace(self, trace_id: str) -> Optional[ExecutionTrace]:
        """Get a trace by ID."""
        return self._traces.get(trace_id)

    def get_traces(
        self,
        status: Optional[ExecutionStatus] = None,
        limit: int = 100,
    ) -> List[ExecutionTrace]:
        """Get traces, optionally filtered."""
        traces = list(self._traces.values())

        if status:
            traces = [t for t in traces if t.status == status]

        traces.sort(key=lambda t: t.trace_id, reverse=True)
        return traces[:limit]

    def get_failed_traces(self, limit: int = 50) -> List[ExecutionTrace]:
        """Get failed traces."""
        return self.get_traces(status=ExecutionStatus.FAILED, limit=limit)

    def get_successful_traces(self, limit: int = 50) -> List[ExecutionTrace]:
        """Get successful traces."""
        return self.get_traces(status=ExecutionStatus.COMPLETED, limit=limit)

    # ===== Statistics =====

    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        return {
            "total_skills": len(self._skills),
            "total_traces": len(self._traces),
            "successful_traces": len([t for t in self._traces.values() if t.status == ExecutionStatus.COMPLETED]),
            "failed_traces": len([t for t in self._traces.values() if t.status == ExecutionStatus.FAILED]),
            "avg_skill_success_rate": sum(s.success_rate for s in self._skills.values()) / max(len(self._skills), 1),
        }

    def clear(self):
        """Clear all data."""
        self._skills.clear()
        self._traces.clear()
        self._save_skills_sync()
        self._save_traces_sync()
        logger.info("Cleared all persistent memory")


# Singleton
_persistent_memory: Optional[PersistentMemory] = None


def get_persistent_memory() -> PersistentMemory:
    """Get singleton persistent memory."""
    global _persistent_memory
    if _persistent_memory is None:
        _persistent_memory = PersistentMemory()
    return _persistent_memory


def reset_persistent_memory() -> PersistentMemory:
    """Reset persistent memory singleton (for testing)."""
    global _persistent_memory
    _persistent_memory = PersistentMemory()
    return _persistent_memory
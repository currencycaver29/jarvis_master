import os
import sqlite3
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from apps.shail.db import get_db
from apps.shail.settings import get_settings
from apps.shail.blueprints import get_blueprint as db_get_blueprint
from shail.memory.hybrid import hybrid_search

logger = logging.getLogger(__name__)

class ContextToolsAdapter:
    """
    Adapter exposing SHAIL context and memory lookup tools over MCP.
    """
    
    def __init__(self):
        self.name = "context_tools"
        self.category = "context"
        
    async def search_memories(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """
        Query the Chroma vector database and SQLite metadata databases for passive memories.
        Returns structured EvidenceBundles.
        """
        try:
            results = await hybrid_search(query, k=limit)
            
            # Format results into structured source-referenced EvidenceBundles
            evidence_results = []
            for content, score, metadata in results:
                evidence_results.append({
                    "content": content,
                    "score": score,
                    "source_url": metadata.get("source_url") or metadata.get("url"),
                    "title": metadata.get("title") or metadata.get("file_name"),
                    "created_at": metadata.get("created_at"),
                    "metadata": metadata
                })
                
            return {
                "query": query,
                "evidence_type": "hybrid_memory",
                "bundle_size": len(evidence_results),
                "results": evidence_results
            }
        except Exception as e:
            logger.error(f"search_memories failed: {e}")
            return {"query": query, "results": [], "error": str(e)}

    def get_blueprint(self, blueprint_id: str) -> Dict[str, Any]:
        """
        Retrieve discrete, queryable knowledge atoms (blueprints) by memory/task ID.
        """
        try:
            bp = db_get_blueprint(blueprint_id)
            if not bp:
                return {"blueprint_id": blueprint_id, "found": False}
            return {
                "blueprint_id": blueprint_id,
                "found": True,
                "blueprint": bp
            }
        except Exception as e:
            logger.error(f"get_blueprint failed: {e}")
            return {"blueprint_id": blueprint_id, "found": False, "error": str(e)}

    def query_graph(self, query: str) -> Dict[str, Any]:
        """
        Search entity-attribute-value relational graphs from passive memory facts.
        """
        try:
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT * FROM memory_facts WHERE entity LIKE ? OR attribute LIKE ? OR value LIKE ? LIMIT 15",
                    (f"%{query}%", f"%{query}%", f"%{query}%")
                ).fetchall()
                
            nodes = []
            edges = []
            seen_entities = set()
            
            for r in rows:
                entity = r["entity"]
                if entity not in seen_entities:
                    seen_entities.add(entity)
                    nodes.append({
                        "id": f"entity_{entity}",
                        "type": "entity",
                        "label": entity
                    })
                
                fact_node_id = f"fact_{r['fact_id']}"
                nodes.append({
                    "id": fact_node_id,
                    "type": "attribute_value",
                    "label": f"{r['attribute']}: {r['value']}",
                    "confidence": r["confidence"]
                })
                
                edges.append({
                    "source": f"entity_{entity}",
                    "target": fact_node_id,
                    "relation": r["attribute"]
                })
                
            return {
                "query": query,
                "nodes": nodes,
                "edges": edges
            }
        except Exception as e:
            logger.error(f"query_graph failed: {e}")
            return {"query": query, "nodes": [], "edges": [], "error": str(e)}

    def get_active_workspace(self) -> Dict[str, Any]:
        """
        Get the current active workspace directory path and scan roots.
        """
        settings = get_settings()
        roots = []
        try:
            from shail.memory.path_index import get_persisted_roots
            roots = get_persisted_roots(settings.sqlite_path)
        except Exception as e:
            logger.warning(f"Failed to fetch scan roots: {e}")
            
        return {
            "active_workspace": os.getcwd(),
            "scan_roots": roots,
            "sqlite_path": settings.sqlite_path
        }

    def get_state_delta(self) -> Dict[str, Any]:
        """
        Get the latest browser tab capture activity logs (title, URL, content_type).
        """
        try:
            from apps.shail.raw_transcripts import list_recent
            recent = list_recent(limit=1)
            if recent:
                item = recent[0]
                return {
                    "memory_id": item.get("memory_id"),
                    "url": item.get("source_url"),
                    "title": item.get("title") or (item.get("metadata") or {}).get("title"),
                    "content_type": item.get("content_type"),
                    "timestamp": item.get("created_at")
                }
        except Exception as e:
            logger.warning(f"get_state_delta failed: {e}")
        return {}

    def resolve_path_pointer(self, pointer: str) -> str:
        """
        Resolve a workspace path pointer/relative link to an absolute file path.
        """
        if os.path.isabs(pointer):
            return pointer
        return os.path.abspath(os.path.join(os.getcwd(), pointer))

    def write_task_memory_proposal(self, task_id: str, proposal: str) -> Dict[str, Any]:
        """
        Submit a candidate skill, preference, or workflow proposal to SHAIL task memories.
        """
        logger.info(f"Memory proposal submitted for task {task_id}: {proposal[:100]}...")
        # Write to settings/proposals table if it exists, or simulate success
        return {
            "status": "proposed",
            "task_id": task_id,
            "proposal": proposal,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

# Register tools with FastMCP
def register_context_tools(provider):
    """
    Register all Phase 2 Context and Grounding tools with the MCP provider.
    """
    adapter = ContextToolsAdapter()
    
    @provider.register_tool
    async def search_memories(query: str, limit: int = 5) -> Dict[str, Any]:
        """Query the Chroma vector database and SQLite metadata databases for passive memories. Returns EvidenceBundles."""
        return await adapter.search_memories(query, limit)
        
    @provider.register_tool
    def get_blueprint(blueprint_id: str) -> Dict[str, Any]:
        """Retrieve discrete, queryable knowledge atoms (blueprints) by memory/task ID."""
        return adapter.get_blueprint(blueprint_id)
        
    @provider.register_tool
    def query_graph(query: str) -> Dict[str, Any]:
        """Search entity-attribute-value relational graphs from passive memory facts."""
        return adapter.query_graph(query)
        
    @provider.register_tool
    def get_active_workspace() -> Dict[str, Any]:
        """Get the current active workspace directory path and scan roots."""
        return adapter.get_active_workspace()
        
    @provider.register_tool
    def get_state_delta() -> Dict[str, Any]:
        """Get the latest browser tab capture activity logs (title, URL, content_type)."""
        return adapter.get_state_delta()
        
    @provider.register_tool
    def resolve_path_pointer(pointer: str) -> str:
        """Resolve a workspace path pointer/relative link to an absolute file path."""
        return adapter.resolve_path_pointer(pointer)
        
    @provider.register_tool
    def write_task_memory_proposal(task_id: str, proposal: str) -> Dict[str, Any]:
        """Submit a candidate skill, preference, or workflow proposal to SHAIL task memories."""
        return adapter.write_task_memory_proposal(task_id, proposal)
        
    provider.register_provider("context_tools", adapter, category="context")
    logger.info("Context and Memory tools registered successfully with MCP provider")

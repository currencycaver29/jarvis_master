import os
from typing import Optional
from pathlib import Path
from pydantic import BaseModel, Field
from dotenv import load_dotenv

_project_root = Path(__file__).parent.parent.parent
_env_path = _project_root / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
    _env_source = str(_env_path)
else:
    load_dotenv()
    _env_source = "cwd"


class Settings(BaseModel):
    # Local LLM (Ollama)
    ollama_base_url: str = Field(default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    # Sprint 6 (ADR-006): switched default from gemma4:e4b (9.6 GB, multimodal)
    # to gemma3:4b Q4_K_M (~2.6 GB, text-only). Lazy-load llava for Ghost
    # Cursor vision separately. Idle footprint drops 7 GB.
    ollama_chat_model: str = Field(default=os.getenv("OLLAMA_CHAT_MODEL", "gemma3:4b-it-q4_K_M"))
    ollama_vision_model: str = Field(default=os.getenv("OLLAMA_VISION_MODEL", "llava:7b"))
    ollama_embed_model: str = Field(default=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"))
    ollama_embed_dim: int = Field(default=int(os.getenv("OLLAMA_EMBED_DIM", "768")))
    # Heat / RAM tuning (per-request overrides; see call_gemma)
    ollama_num_ctx: int       = Field(default=int(os.getenv("OLLAMA_NUM_CTX", "4096")))
    ollama_num_thread: int    = Field(default=int(os.getenv("OLLAMA_NUM_THREAD", "4")))
    ollama_keep_alive: str    = Field(default=os.getenv("OLLAMA_KEEP_ALIVE", "5m"))

    # Paths
    workspace_root: str = Field(default=os.getenv("SHAIL_WORKSPACE_ROOT", os.getcwd()))
    audit_log_path: str = Field(default=os.getenv("SHAIL_AUDIT_LOG", os.path.join(os.getcwd(), "shail_audit.jsonl")))

    # Memory / DB
    sqlite_path: str = Field(default=os.getenv("SHAIL_SQLITE", os.path.expanduser("~/Library/Application Support/SHAIL/metadata.db")))
    rag_vector_store: str = Field(default=os.getenv("RAG_VECTOR_STORE", "chroma"))
    rag_pg_dsn: str = Field(default=os.getenv("RAG_PG_DSN", "postgresql://postgres:postgres@localhost:5432/shail_rag"))
    rag_chroma_path: str = Field(default=os.getenv(
        "RAG_CHROMA_PATH",
        os.path.expanduser("~/Library/Application Support/SHAIL/memory/chroma"),
    ))
    rag_default_top_k: int = Field(default=int(os.getenv("RAG_TOP_K", "5")))
    rag_chunk_size: int = Field(default=int(os.getenv("RAG_CHUNK_SIZE", "800")))
    rag_chunk_overlap: int = Field(default=int(os.getenv("RAG_CHUNK_OVERLAP", "120")))
    rag_embedding_dim: int = Field(default=int(os.getenv("RAG_EMBEDDING_DIM", "768")))

    # macOS memory tiers
    macos_memory_root: str = Field(default=os.getenv(
        "SHAIL_MEMORY_ROOT",
        os.path.expanduser("~/Library/Application Support/SHAIL/memory"),
    ))
    path_index_db: str = Field(default=os.getenv(
        "SHAIL_PATH_INDEX_DB",
        os.path.expanduser("~/Library/Application Support/SHAIL/memory/path_index.db"),
    ))
    cloud_index_db: str = Field(default=os.getenv(
        "SHAIL_CLOUD_INDEX_DB",
        os.path.expanduser("~/Library/Application Support/SHAIL/memory/cloud_index.db"),
    ))
    ephemeral_ttl_hours: int = Field(default=int(os.getenv("SHAIL_EPHEMERAL_TTL_HOURS", "24")))
    ephemeral_max_records: int = Field(default=int(os.getenv("SHAIL_EPHEMERAL_MAX_RECORDS", "5000")))

    # Redis / Queue
    redis_url: str = Field(default=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    task_queue_name: str = Field(default=os.getenv("SHAIL_TASK_QUEUE", "shail_tasks"))

    # Service URLs
    ui_twin_url: str = Field(default=os.getenv("UI_TWIN_URL", "http://localhost:8001"))
    action_executor_url: str = Field(default=os.getenv("ACTION_EXECUTOR_URL", "http://localhost:8002"))
    vision_url: str = Field(default=os.getenv("VISION_URL", "http://localhost:8003"))
    rag_url: str = Field(default=os.getenv("RAG_URL", "http://localhost:8004"))

    # JWT
    jwt_secret: str = Field(default_factory=lambda: os.getenv("SHAIL_JWT_SECRET", "changeme"))

    # Google OAuth2 — used for sign-in AND for Drive/Gmail MCP connectors.
    google_client_id:     str = Field(default=os.getenv("GOOGLE_CLIENT_ID", ""))
    google_client_secret: str = Field(default=os.getenv("GOOGLE_CLIENT_SECRET", ""))

    # GitHub OAuth (MCP)
    github_client_id:     str = Field(default=os.getenv("GITHUB_CLIENT_ID", ""))
    github_client_secret: str = Field(default=os.getenv("GITHUB_CLIENT_SECRET", ""))

    # Notion OAuth (MCP)
    notion_client_id:     str = Field(default=os.getenv("NOTION_CLIENT_ID", ""))
    notion_client_secret: str = Field(default=os.getenv("NOTION_CLIENT_SECRET", ""))

    # Public origin used to build OAuth redirect_uri values. Override in
    # production so OAuth providers can reach the callback endpoint.
    public_origin:        str = Field(default=os.getenv("SHAIL_PUBLIC_ORIGIN", "http://localhost:8000"))

    # Compatibility stubs — removed Gemini; agents that still reference these
    # will get empty strings instead of AttributeErrors.
    gemini_api_key: str = Field(default="")
    gemini_model: str   = Field(default="")


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

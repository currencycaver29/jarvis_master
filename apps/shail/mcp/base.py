"""
MCP provider contract.

Every connector implements this protocol. Concrete providers handle the
specifics (OAuth scopes, indexing, search, fetch) — the FastAPI router
and chat RAG only ever see this interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass
class FetchHit:
    """One result from active-fetch on a connector. Returned to chat RAG."""
    id: str                      # provider-local id
    title: str
    snippet: str = ""
    url: Optional[str] = None    # native URL to open the source
    extra: dict = field(default_factory=dict)


@dataclass
class IndexProgress:
    """Background indexer progress, exposed to the Connections UI."""
    indexed: int
    total: int
    status: str                  # "idle" | "indexing" | "error"
    error: Optional[str] = None


class MCPProvider(Protocol):
    """Provider interface — all four connectors implement this."""
    name: str
    label: str                   # human-readable
    scopes: list[str]            # OAuth scopes requested

    def is_configured(self) -> bool:
        """True iff client_id/secret are present in env so OAuth can run."""
        ...

    def oauth_authorize_url(self, *, state: str, redirect_uri: str) -> str:
        """Build the provider's authorize URL for the OAuth start step."""
        ...

    async def exchange_code(
        self, *, code: str, redirect_uri: str,
    ) -> dict:
        """Exchange the OAuth callback code for tokens. Returns dict with
        keys: access_token, refresh_token (optional), expires_at,
        scope, metadata (provider-specific account info).
        """
        ...

    async def index(self, *, user_id: str, access_token: str, refresh_token: Optional[str], settings: dict) -> int:
        """Initial indexer — fetch up to provider's cap of recent docs,
        embed via shail.memory.rag.ingest into the user's MCP namespace.
        Returns the number of records ingested.
        Should call mcp_store.update_index_status during progress.
        """
        ...

    async def fetch_relevant(
        self, *, user_id: str, query: str, k: int,
        access_token: str, refresh_token: Optional[str], settings: dict,
    ) -> list[FetchHit]:
        """Active fetch on chat query. Hard 2s timeout enforced by caller.
        Implementations may search live (Drive/Notion/GitHub) or query
        the indexed Chroma namespace (Gmail).
        """
        ...

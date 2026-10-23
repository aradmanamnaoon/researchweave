"""Headless research lifecycle and evidence domain."""

from __future__ import annotations

from pathlib import Path

from .discovery import HTTPTransport
from .facade import EvidenceFacade

__all__ = ["EvidenceFacade", "build_evidence_facade"]


def build_evidence_facade(workspace_root: str | Path, *,
                          allow_local_writes: bool = False,
                          allow_remote_queries: bool = False,
                          metadata_transport: HTTPTransport | None = None) -> EvidenceFacade:
    """Construct the facade with a host-selected root and write policy."""
    return EvidenceFacade(Path(workspace_root), allow_local_writes=allow_local_writes,
                          allow_remote_queries=allow_remote_queries,
                          metadata_transport=metadata_transport)

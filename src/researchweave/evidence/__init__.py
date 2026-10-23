"""Headless research lifecycle and evidence domain."""

from __future__ import annotations

from pathlib import Path

from .facade import EvidenceFacade

__all__ = ["EvidenceFacade", "build_evidence_facade"]


def build_evidence_facade(workspace_root: str | Path, *,
                          allow_local_writes: bool = False) -> EvidenceFacade:
    """Construct the facade with a host-selected root and write policy."""
    return EvidenceFacade(Path(workspace_root), allow_local_writes=allow_local_writes)

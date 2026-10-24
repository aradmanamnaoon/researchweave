"""Packaged visual assets used by the desktop shell."""

from __future__ import annotations

from pathlib import Path

ASSET_ROOT = Path(__file__).resolve().parents[1] / "assets"


def asset_path(name: str) -> Path:
    """Return a packaged asset path without assuming the current working directory."""

    return ASSET_ROOT / name

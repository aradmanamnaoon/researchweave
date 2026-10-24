"""Render the canonical ResearchWeave SVG mark to release-friendly PNG/ICO files."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    source = repo / "assets" / "branding" / "researchweave-mark.svg"
    png = repo / "assets" / "branding" / "researchweave-icon.png"
    ico = repo / "assets" / "branding" / "researchweave.ico"

    renderer = QSvgRenderer(str(source))
    if not renderer.isValid():
        raise RuntimeError(f"Invalid SVG mark: {source}")
    canvas = QImage(512, 512, QImage.Format.Format_ARGB32)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    renderer.render(painter)
    painter.end()
    if not canvas.save(str(png), "PNG"):
        raise RuntimeError(f"Could not save rendered PNG: {png}")

    with Image.open(png) as image:
        image.save(
            ico,
            format="ICO",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
    print(f"png={png}")
    print(f"ico={ico}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

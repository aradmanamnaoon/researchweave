"""Reproducible descriptive charts with an accessible data representation.

Standalone numerical binning is independently testable, while Qt draws a
native, printable and keyboard-discoverable chart without extra dependencies.
No inferential or clinical significance is implied by the result.
"""

from __future__ import annotations

import html
import math
import struct
import zlib
from dataclasses import asdict, dataclass
from statistics import fmean
from typing import Any, Literal

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import QFrame, QWidget

from .contracts import UIError

MAX_CHART_VALUES = 50_000
MAX_BINS = 60


@dataclass(frozen=True)
class Bin:
    lower: float
    upper: float
    count: int
    label: str


@dataclass(frozen=True)
class ChartSpec:
    title: str
    column: str
    kind: Literal["histogram", "bar"]
    x_label: str
    y_label: str
    bins: tuple[Bin, ...]
    n: int
    missing_n: int
    min_value: float
    max_value: float
    mean: float
    source_label: str = "Local data; verify source and units"
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "bins": [asdict(item) for item in self.bins],
            "rendered_data_type": "descriptive-observed-data",
            "scientific_assumption_validated": False,
            "accessibility_data": self.accessible_table(),
        }

    def accessible_table(self) -> list[dict[str, Any]]:
        return [
            {"interval": item.label, "count": item.count, "lower": item.lower, "upper": item.upper}
            for item in self.bins
        ]


def nice_number(value: float) -> str:
    """Finite numeric formatting suitable for labels, not statistical inference."""
    if not math.isfinite(value):
        raise UIError(
            "INVALID_INPUT",
            "Non-finite values cannot be plotted.",
            "Exclude missing or invalid numeric records.",
        )
    if abs(value) >= 1e7 or 0 < abs(value) < 1e-4:
        return f"{value:.3g}"
    return f"{value:.6g}"


def histogram(
    values: list[float | None],
    *,
    column: str,
    bins: int = 10,
    source_label: str = "Local dataset",
    unit: str = "",
) -> ChartSpec:
    if len(values) > MAX_CHART_VALUES:
        raise UIError(
            "RESOURCE_LIMIT",
            "Chart exceeds 50,000 sample values.",
            "Plot a reviewed bounded dataset or aggregate first.",
        )
    if isinstance(bins, bool) or not isinstance(bins, int) or not 1 <= bins <= MAX_BINS:
        raise UIError(
            "INVALID_INPUT",
            "Histogram bins must be between 1 and 60.",
            "Choose a smaller positive whole number of bins.",
        )
    if not isinstance(column, str) or not column.strip() or len(column) > 100:
        raise UIError(
            "INVALID_INPUT",
            "Missing descriptive chart variable.",
            "Choose a named numeric variable.",
        )
    if not isinstance(unit, str) or len(unit) > 60:
        raise UIError(
            "INVALID_INPUT",
            "Unit label is too long.",
            "Use a short measurement unit or leave blank.",
        )
    if not isinstance(source_label, str) or len(source_label) > 180:
        raise UIError(
            "INVALID_INPUT",
            "Dataset origin label is too long.",
            "Record a short origin description.",
        )
    filtered = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise UIError(
                "INVALID_INPUT",
                "Dataset contains a nonnumeric chart value.",
                "Review variable typing before plotting.",
            )
        if not math.isfinite(value):
            continue
        filtered.append(float(value))
    if not filtered:
        raise UIError(
            "INVALID_INPUT",
            "No finite values are available for plotting.",
            "Choose a numeric variable with observed measurements.",
        )
    low = min(filtered)
    high = max(filtered)
    count = len(filtered)
    if low == high:
        # A constant variable has a real narrow interval, never an empty plot.
        pad = max(0.5, abs(low) * 0.01)
        low -= pad
        high += pad
        bins = 1
    increment = (high - low) / bins
    buckets = [0] * bins
    for value in filtered:
        index = min(bins - 1, max(0, math.floor((value - low) / increment)))
        buckets[index] += 1
    if sum(buckets) != count:
        raise UIError(
            "INTEGRITY_FAILURE",
            "Histogram lost input observations.",
            "Review dataset values and retry.",
        )
    groups = tuple(
        Bin(
            lower=low + index * increment,
            upper=low + (index + 1) * increment,
            count=buckets[index],
            label=f"{nice_number(low + index * increment)}–"
            f"{nice_number(low + (index + 1) * increment)}",
        )
        for index in range(bins)
    )
    unit_note = f" ({unit})" if unit else ""
    return ChartSpec(
        title=f"Descriptive distribution · {column}",
        column=column,
        kind="histogram",
        x_label=f"{column}{unit_note}",
        y_label="Observation count",
        bins=groups,
        n=count,
        missing_n=len(values) - count,
        min_value=min(filtered),
        max_value=max(filtered),
        mean=fmean(filtered),
        source_label=source_label,
        description=(
            f"Histogram of {count} finite observed values with "
            f"{len(values) - count} invalid or missing entries omitted. "
            "Bars show counts; no statistical significance is inferred."
        ),
    )


def categorical_bar(
    values: list[str | None],
    *,
    column: str,
    source_label: str = "Local dataset",
) -> ChartSpec:
    """Count bounded categorical observations without statistical inference."""
    if len(values) > MAX_CHART_VALUES:
        raise UIError(
            "RESOURCE_LIMIT",
            "Chart exceeds 50,000 sample values.",
            "Plot a reviewed bounded dataset or aggregate first.",
        )
    if not isinstance(column, str) or not column.strip() or len(column) > 100:
        raise UIError(
            "INVALID_INPUT",
            "Missing descriptive chart variable.",
            "Choose a named categorical variable.",
        )
    counts: dict[str, int] = {}
    missing = 0
    for value in values:
        if value is None or not str(value).strip():
            missing += 1
            continue
        label = str(value).strip()
        if len(label) > 160:
            raise UIError(
                "INVALID_INPUT",
                "Categorical label is too long.",
                "Clean the categorical variable before plotting.",
            )
        counts[label] = counts.get(label, 0) + 1
    if not counts:
        raise UIError(
            "INVALID_INPUT",
            "No observed categories are available for plotting.",
            "Choose a categorical variable with observed values.",
        )
    if len(counts) > MAX_BINS:
        raise UIError(
            "RESOURCE_LIMIT",
            "Categorical chart has more than 60 distinct levels.",
            "Filter or regroup reviewed categories before plotting.",
        )
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))
    bins = tuple(
        Bin(float(index), float(index + 1), count, label)
        for index, (label, count) in enumerate(ordered)
    )
    observed = sum(counts.values())
    return ChartSpec(
        title=f"Observed category counts · {column}",
        column=column,
        kind="bar",
        x_label=column,
        y_label="Observation count",
        bins=bins,
        n=observed,
        missing_n=missing,
        min_value=0.0,
        max_value=float(max(counts.values())),
        mean=float(observed / len(counts)),
        source_label=source_label,
        description=(
            f"Bar chart of {observed} observed categorical values across {len(counts)} "
            f"levels with {missing} missing entries omitted. No statistical significance "
            "or ordering is inferred."
        ),
    )


def chart_svg(
    spec: ChartSpec,
    *,
    width: int = 900,
    height: int = 500,
) -> str:
    """Export a deterministic self-contained SVG with readable axis titles."""
    if not 400 <= width <= 4096 or not 240 <= height <= 2160:
        raise UIError(
            "INVALID_INPUT",
            "Unsupported SVG chart dimensions.",
            "Choose a width between 400 and 4096 and height 240–2160.",
        )
    margins = (88, 54, 30, 86)
    left, top, right, bottom = margins
    plot_width = width - left - right
    plot_height = height - top - bottom
    n_bars = max(1, len(spec.bins))
    max_count = max(1, max(item.count for item in spec.bins))
    padding = 2 if n_bars > 25 else 5
    column_width = plot_width / n_bars
    escaped_title = html.escape(spec.title, quote=True)
    escaped_x = html.escape(spec.x_label, quote=True)
    escaped_y = html.escape(spec.y_label, quote=True)
    escaped_description = html.escape(spec.description, quote=True)
    escaped_source = html.escape(spec.source_label, quote=True)
    components = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        'role="img" aria-labelledby="title desc">',
        f'<title id="title">{escaped_title}</title>',
        f'<desc id="desc">{escaped_description}</desc>',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#FFFFFF"/>',
        f'<text x="{left}" y="32" font-family="sans-serif" '
        f'font-size="19" fill="#182339">{escaped_title}</text>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" '
        'stroke="#334155" stroke-width="2"/>',
        f'<line x1="{left}" y1="{top + plot_height}" '
        f'x2="{left + plot_width}" y2="{top + plot_height}" '
        'stroke="#334155" stroke-width="2"/>',
    ]
    for tick in range(5):
        amount = max_count * tick / 4
        y = top + plot_height - tick * plot_height / 4
        components.append(
            f'<line x1="{left}" y1="{y:.2f}" '
            f'x2="{left + plot_width}" y2="{y:.2f}" '
            'stroke="#D8E1EC" stroke-width="1"/>'
        )
        components.append(
            f'<text x="{left - 10}" y="{y + 5:.2f}" text-anchor="end" '
            f'font-family="sans-serif" font-size="12" fill="#445269">'
            f"{nice_number(amount)}</text>"
        )
    for position, item in enumerate(spec.bins):
        fraction = item.count / max_count
        bar_height = plot_height * fraction
        x = left + column_width * position + padding / 2
        y = top + plot_height - bar_height
        bar_width = max(0.5, column_width - padding)
        escaped_interval = html.escape(item.label, quote=True)
        components.extend(
            [
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width:.2f}" '
                f'height="{bar_height:.2f}" fill="#315FAC">'
                f"<title>{escaped_interval}: {item.count}</title></rect>"
            ]
        )
    components.extend(
        [
            f'<text x="{left + plot_width / 2:.2f}" y="{height - 42}" '
            f'text-anchor="middle" font-family="sans-serif" '
            f'font-size="14" fill="#182339">{escaped_x}</text>',
            f'<text x="18" y="{top + plot_height / 2:.2f}" '
            f'transform="rotate(-90 18 {top + plot_height / 2:.2f})" '
            f'text-anchor="middle" font-family="sans-serif" '
            f'font-size="14" fill="#182339">{escaped_y}</text>',
            f'<text x="{left}" y="{height - 16}" '
            f'font-family="sans-serif" font-size="11" '
            f'fill="#445269">{escaped_source}</text>',
            "</svg>",
        ]
    )
    return "\n".join(components)


def chart_png(spec: ChartSpec, *, width: int = 900, height: int = 500) -> bytes:
    """Render a deterministic dependency-free PNG with descriptive metadata.

    The raster contains axes, gridlines and bars. Human-readable title/axis/source
    labels are stored in standard PNG text chunks so headless export never depends
    on a GUI application or font database.
    """
    if not 400 <= width <= 4096 or not 240 <= height <= 2160:
        raise UIError(
            "INVALID_INPUT",
            "Unsupported PNG chart dimensions.",
            "Choose a width between 400 and 4096 and height 240–2160.",
        )
    left, top, right, bottom = 88, 54, 30, 86
    plot_width = max(1, width - left - right)
    plot_height = max(1, height - top - bottom)
    max_count = max(1, max(item.count for item in spec.bins))
    pixels = bytearray(b"\xff\xff\xff" * width * height)

    def set_pixel(x: int, y: int, rgb: tuple[int, int, int]) -> None:
        if 0 <= x < width and 0 <= y < height:
            offset = (y * width + x) * 3
            pixels[offset : offset + 3] = bytes(rgb)

    def horizontal(y: int, x1: int, x2: int, rgb: tuple[int, int, int]) -> None:
        for x in range(max(0, x1), min(width, x2 + 1)):
            set_pixel(x, y, rgb)

    def vertical(x: int, y1: int, y2: int, rgb: tuple[int, int, int]) -> None:
        for y in range(max(0, y1), min(height, y2 + 1)):
            set_pixel(x, y, rgb)

    axis = (24, 35, 57)
    grid = (216, 225, 236)
    bar = (49, 95, 172)
    vertical(left, top, top + plot_height, axis)
    horizontal(top + plot_height, left, left + plot_width, axis)
    for tick in range(5):
        y = round(top + plot_height - tick * plot_height / 4)
        horizontal(y, left, left + plot_width, grid)
    column_width = plot_width / max(1, len(spec.bins))
    for index, group in enumerate(spec.bins):
        bar_height = round(plot_height * group.count / max_count)
        x1 = round(left + index * column_width + 1)
        x2 = round(left + (index + 1) * column_width - 2)
        y1 = top + plot_height - bar_height
        y2 = top + plot_height - 1
        for y in range(max(top, y1), min(height, y2 + 1)):
            horizontal(y, x1, x2, bar)

    def chunk(kind: bytes, data: bytes) -> bytes:
        payload = kind + data
        return (
            struct.pack(">I", len(data))
            + payload
            + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
        )

    rows = []
    stride = width * 3
    for y in range(height):
        start = y * stride
        rows.append(b"\x00" + bytes(pixels[start : start + stride]))
    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png += chunk(
        b"IHDR",
        struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0),
    )
    metadata = {
        "Title": spec.title,
        "Description": spec.description,
        "XLabel": spec.x_label,
        "YLabel": spec.y_label,
        "Source": spec.source_label,
        "PlotType": spec.kind,
    }
    for key, value in metadata.items():
        png += chunk(b"tEXt", key.encode("latin-1") + b"\x00" + value.encode("utf-8"))
    png += chunk(b"IDAT", zlib.compress(b"".join(rows), level=9))
    png += chunk(b"IEND", b"")
    return bytes(png)


class HistogramWidget(QFrame):
    """Native chart with an accessible textual alternative and limited paint work."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(280, 180)
        self.setAccessibleName("Descriptive histogram")
        self.setAccessibleDescription("Import numeric data and run a summary to draw bars")
        self.spec: ChartSpec | None = None
        self._bar_color = QColor("#315FAC")
        self._axis_color = QColor("#182339")
        self._grid_color = QColor("#D8E1EC")

    def set_chart(self, spec: ChartSpec | None) -> None:
        self.spec = spec
        if spec is None:
            self.setAccessibleDescription("No chart data. Import and summarize a variable.")
        else:
            self.setAccessibleDescription(spec.description + " Accessible data table below.")
        self.update()

    def paintEvent(self, event: QPaintEvent | None) -> None:
        if event is None:
            return
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))
        painter.setPen(QPen(self._axis_color))
        if self.spec is None:
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "No descriptive chart computed"
            )
            painter.end()
            return
        spec = self.spec
        width = max(1, self.width())
        height = max(1, self.height())
        metrics = QFontMetrics(painter.font())
        painter.drawText(
            16, 24, metrics.elidedText(spec.title, Qt.TextElideMode.ElideRight, max(50, width - 40))
        )
        left = 60
        top = 42
        right = 20
        bottom = 50
        plot_width = max(1, width - left - right)
        plot_height = max(1, height - top - bottom)
        painter.drawLine(left, top, left, top + plot_height)
        painter.drawLine(left, top + plot_height, left + plot_width, top + plot_height)
        max_value = max(1, max(item.count for item in spec.bins))
        for tick in range(5):
            amount = round(max_value * tick / 4)
            y = top + plot_height - tick * plot_height / 4
            painter.setPen(QPen(self._grid_color))
            painter.drawLine(left, round(y), left + plot_width, round(y))
            painter.setPen(QPen(self._axis_color))
            painter.drawText(8, round(y + 5), str(amount))
        bar_width = plot_width / max(1, len(spec.bins))
        painter.setPen(QPen(self._bar_color))
        for index, group in enumerate(spec.bins):
            h = plot_height * group.count / max_value
            painter.fillRect(
                QRectF(
                    left + index * bar_width + 1,
                    top + plot_height - h,
                    max(1, bar_width - 2),
                    h,
                ),
                self._bar_color,
            )
        painter.setPen(QPen(self._axis_color))
        painter.drawText(
            left,
            height - 15,
            metrics.elidedText(
                spec.x_label, Qt.TextElideMode.ElideRight, max(50, width - left - right)
            ),
        )
        painter.end()

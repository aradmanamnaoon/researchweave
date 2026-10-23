"""Headless accessible chart export from explicit dataset and variable selections."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .errors import require
from .models import Dataset, digest, finite_number


def render_plot(
    dataset: Dataset,
    *,
    x: str,
    output: Path,
    y: str | None = None,
    kind: str = "scatter",
    x_label: str | None = None,
    y_label: str | None = None,
    title: str = "",
) -> dict[str, Any]:
    require(kind in ("scatter", "line", "histogram", "box"), "Unsupported chart type")
    require(x in dataset.columns and (y is None or y in dataset.columns), "Unknown chart columns")
    require(
        kind in ("histogram", "box") or y is not None, "Two chart axes required for scatter/line"
    )
    require(output.suffix.lower() in (".svg", ".png", ".pdf"), "Unsupported chart export")
    require(output.parent.is_dir(), "Output folder does not exist", "NOT_FOUND")
    require(not output.exists(), "Destination already exists", "CONFLICT")
    rows = [
        row for row in dataset.records if row[x] is not None and (y is None or row[y] is not None)
    ]
    require(bool(rows), "No complete chart observations")
    xs = [finite_number(row[x]) for row in rows]
    ys = [finite_number(row[y]) for row in rows] if y is not None else None
    fig, ax = plt.subplots(figsize=(7, 4.5), layout="constrained")
    try:
        if kind == "scatter":
            ax.scatter(xs, ys, marker="o", alpha=0.8)
        elif kind == "line":
            require(len(set(xs)) == len(xs), "Line x axis must contain unique values")
            ordered = sorted(zip(xs, ys, strict=True))
            ax.plot([v[0] for v in ordered], [v[1] for v in ordered])
        elif kind == "histogram":
            ax.hist(xs, bins="auto", edgecolor="black")
        else:
            ax.boxplot(xs, tick_labels=[x])
        ax.set_xlabel(x_label or x)
        ax.set_ylabel(y_label or ("Frequency" if kind == "histogram" else y or "Value"))
        ax.set_title(title)
        ax.grid(alpha=0.2)
        fig.savefig(output, metadata={"Creator": "ResearchWeave Scientific Analysis"})
    finally:
        plt.close(fig)
    return {
        "kind": kind,
        "spec": {
            "kind": kind,
            "x": x,
            "y": y,
            "x_label": x_label,
            "y_label": y_label,
            "title": title,
        },
        "n_used": len(rows),
        "n_excluded": len(dataset.records) - len(rows),
        "dataset_revision": dataset.revision,
        "path": str(output),
        "sha256": __import__("hashlib").sha256(output.read_bytes()).hexdigest(),
        "alt_text": f"{kind} chart of {x}"
        + (f" against {y}" if y else "")
        + f" with {len(rows)} complete observations",
        "data_hash": digest({"x": xs, "y": ys}),
    }

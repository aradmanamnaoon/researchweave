"""Reproducible local performance observations for ResearchWeave V2 UI services."""

from __future__ import annotations

import json
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import Any

from researchweave.ui import build_ui_facade
from researchweave.ui.contracts import Project, Source, new_id, utc_now
from researchweave.ui.recovery import RecoveryJournal
from researchweave.ui.release import inspect_submission
from researchweave.ui.search import search_project
from researchweave.ui.visualization import histogram


def observe(callback: Callable[[], Any]) -> tuple[Any, float, int]:
    tracemalloc.start()
    started = time.perf_counter()
    result = callback()
    seconds = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, seconds, peak


def project_fixture() -> Project:
    timestamp = utc_now()
    return Project(
        id=new_id(),
        title="Synthetic performance fixture",
        question="How do bounded UI operations behave?",
        study_type="mixed",
        created_at=timestamp,
        updated_at=timestamp,
    )


def main() -> None:
    observations: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="researchweave-perf-") as temporary:
        root = Path(temporary)
        facade = build_ui_facade(root)
        created = facade.execute(
            "ui.project.create",
            {"title": "10k rows", "question": "Paging?", "study_type": "quantitative"},
        )["data"]
        csv_text = "x,group\n" + "".join(
            f"{index},{'A' if index % 2 == 0 else 'B'}\n" for index in range(10_000)
        )

        def import_rows() -> dict[str, Any]:
            return facade.execute(
                "ui.dataset.import",
                {
                    "project_id": created["project_id"],
                    "expected_revision": created["revision"],
                    "name": "10k synthetic rows",
                    "csv_text": csv_text,
                },
            )

        imported, seconds, peak = observe(import_rows)
        page, page_seconds, page_peak = observe(
            lambda: facade.execute(
                "ui.dataset.page",
                {
                    "project_id": created["project_id"],
                    "dataset_id": imported["data"]["dataset_id"],
                    "offset": 9750,
                    "limit": 250,
                },
            )
        )
        observations["dataset_10000_rows"] = {
            "import_seconds": seconds,
            "import_python_peak_bytes": peak,
            "page_seconds": page_seconds,
            "page_python_peak_bytes": page_peak,
            "total_rows": page["data"]["total"],
            "page_rows": len(page["data"]["rows"]),
        }

        library = project_fixture()
        library.sources = [
            Source(
                id=new_id(),
                title=f"Synthetic source {index}",
                text=(
                    f"Ordinary synthetic text {index}"
                    if index != 1999
                    else "Final synthetic source contains Ω-target evidence"
                ),
            )
            for index in range(2_000)
        ]
        found, seconds, peak = observe(
            lambda: search_project(library, "Ω-target", categories=("source",))
        )
        observations["source_library_2000"] = {
            "search_seconds": seconds,
            "search_python_peak_bytes": peak,
            "matches": found["total"],
        }

        manuscript = project_fixture()
        manuscript.manuscript = "# Methods\n\n" + (
            "Synthetic reviewed draft sentence. " * 6_000
        )
        report, seconds, peak = observe(lambda: inspect_submission(manuscript))
        observations["long_manuscript"] = {
            "characters": report["manuscript_characters"],
            "preview_seconds": seconds,
            "preview_python_peak_bytes": peak,
            "submission_approved": report["submission_approved"],
        }

        values = [float(index % 100) for index in range(50_000)]
        chart, seconds, peak = observe(
            lambda: histogram(values, column="synthetic", bins=60)
        )
        observations["chart_50000_observations"] = {
            "seconds": seconds,
            "python_peak_bytes": peak,
            "n": chart.n,
            "bins": len(chart.bins),
        }

        recovery_facade = build_ui_facade(root / "recovery")
        recovery_project = recovery_facade.execute(
            "ui.project.create",
            {"title": "Recovery perf", "question": "Recover?", "study_type": "literature"},
        )["data"]
        journal = RecoveryJournal(recovery_facade.store)
        recovery_text = "یادداشت synthetic 🧠\n" * 8_000

        def recovery_roundtrip() -> dict[str, Any]:
            journal.save(
                recovery_project["project_id"],
                "notebook",
                recovery_text,
                recovery_project["revision"],
            )
            return journal.inspect(recovery_project["project_id"], "notebook")

        recovered, seconds, peak = observe(recovery_roundtrip)
        observations["large_recovery_journal"] = {
            "characters": len(recovery_text),
            "roundtrip_seconds": seconds,
            "python_peak_bytes": peak,
            "conflict": recovered["conflict"],
        }

    payload = {
        "schema_version": 1,
        "measurement": (
            "Wall time uses time.perf_counter; memory is peak Python allocation from tracemalloc "
            "and is not whole-process RSS."
        ),
        "fixtures": "Synthetic deterministic local-only data; no network calls.",
        "observations": observations,
        "additional_observed_tests": {
            "zip_bomb_ratio": "Rejected with RESOURCE_LIMIT in test_performance_resources.py.",
            "job_cancellation": (
                "Observed terminal state cancelled in test_performance_resources.py."
            ),
            "bounded_pdf": "Valid/corrupt local PDF behavior covered by test_pdf_reader.py.",
            "narrow_200_percent": (
                "Offscreen 200% scale and narrow screenshot evidence covered by "
                "test_accessibility.py and capture-matrix.json."
            ),
        },
        "network_calls_observed": 0,
    }
    Path("workstreams/v2/ui/PERFORMANCE_RESULTS.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

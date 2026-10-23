"""Measure bounded synthetic analysis workloads at 100, 10k and 100k rows."""

from __future__ import annotations

import argparse
import json
import os
import platform
import tempfile
import time
import tracemalloc
from pathlib import Path

from researchweave.analysis.datasets import data_view, import_csv, scan_parquet_page
from researchweave.analysis.statistics import describe


def benchmark(n_rows: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="rw-benchmark-") as raw:
        path = Path(raw) / "synthetic.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            handle.write("id,group,x,y\n")
            for index in range(n_rows):
                handle.write(
                    f"r{index},{'A' if index % 2 == 0 else 'B'},{index % 101},{(index * 3) % 211}\n"
                )
        tracemalloc.start()
        start = time.perf_counter()
        dataset = import_csv(path)
        import_seconds = time.perf_counter() - start
        start = time.perf_counter()
        summary = describe(dataset, "x")
        describe_seconds = time.perf_counter() - start
        start = time.perf_counter()
        view = data_view(dataset, sort_by="id", search="r9", offset=0, limit=100)
        view_seconds = time.perf_counter() - start
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return {
            "rows": n_rows,
            "import_seconds": import_seconds,
            "describe_seconds": describe_seconds,
            "view_seconds": view_seconds,
            "peak_tracemalloc_bytes": peak,
            "rows_per_second_import": n_rows / import_seconds if import_seconds else None,
            "mean_x": summary["mean"],
            "view_matches": view["total"],
        }


def benchmark_parquet_scan(n_rows: int = 100_000) -> dict[str, object]:
    import pyarrow as pa
    import pyarrow.parquet as pq

    with tempfile.TemporaryDirectory(prefix="rw-parquet-benchmark-") as raw:
        path = Path(raw) / "synthetic.parquet"
        table = pa.table(
            {
                "id": [f"r{index}" for index in range(n_rows)],
                "x": [index % 101 for index in range(n_rows)],
                "y": [(index * 3) % 211 for index in range(n_rows)],
            }
        )
        pq.write_table(table, path, row_group_size=10_000)
        tracemalloc.start()
        start = time.perf_counter()
        page = scan_parquet_page(path, offset=54_321, limit=100, columns=["id", "x"])
        scan_seconds = time.perf_counter() - start
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return {
            "rows": n_rows,
            "offset": 54_321,
            "limit": 100,
            "scan_seconds": scan_seconds,
            "peak_tracemalloc_bytes": peak,
            "returned_rows": page["returned_rows"],
            "converted_python_rows": page["converted_python_rows"],
            "materialized_entire_table": page["materialized_entire_table"],
            "reader": page["reader"],
            "selected_columns": page["columns"],
            "first_id": page["rows"][0]["id"],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    results = [benchmark(size) for size in (100, 10_000, 100_000)]
    payload = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "measurement": "time.perf_counter + tracemalloc Python allocation peak",
        "workload": (
            "CSV import, numeric describe, sorted+searched 100-row data view, "
            "and bounded 100k-row Parquet page scan"
        ),
        "results": results,
        "parquet_scan_100k": benchmark_parquet_scan(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

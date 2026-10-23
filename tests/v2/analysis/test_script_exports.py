import json
import subprocess
import sys
from pathlib import Path

import pytest

from researchweave.analysis import build_analysis_facade
from researchweave.analysis.datasets import import_csv
from researchweave.analysis.errors import AnalysisError
from researchweave.analysis.script_exports import (
    export_python_script,
    export_r_script,
    save_syntax,
)


def test_export_executes_in_new_interpreter(tmp_path: Path):
    file = tmp_path / "values.csv"
    file.write_text("score\n1\n3\n5\n", encoding="utf-8")
    data = import_csv(file)
    store = tmp_path / "versions"
    build_analysis_facade(store).store.save(data)
    args = {"dataset_id": data.dataset_id, "revision": data.revision, "column": "score"}
    exported = export_python_script("statistics.describe", args, data)
    target = tmp_path / "replay.py"
    saved = save_syntax(exported, target)
    assert saved["sha256"] == exported.source_sha256
    # S603: use this test's fixed Python executable and generated local script.
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(target), str(store)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["mean"] == 3


def test_scripts_guard_revision_and_unsupported_r(tmp_path: Path):
    file = tmp_path / "values.csv"
    file.write_text("x\n2\n4\n6\n", encoding="utf-8")
    data = import_csv(file)
    with pytest.raises(AnalysisError, match="INTEGRITY_FAILURE"):
        export_python_script(
            "statistics.describe", {"dataset_id": data.dataset_id, "revision": "bad"}, data
        )
    args = {"dataset_id": data.dataset_id, "revision": data.revision, "column": "x"}
    r = export_r_script("statistics.describe", args, data)
    assert "mean(v)" in r.source and "sd(v)" in r.source
    with pytest.raises(AnalysisError, match="UNSUPPORTED"):
        export_r_script("statistics.model", args, data)

"""Explicitly authorized child process execution; not an OS security sandbox."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .errors import AnalysisError, require


def run_script(
    source: str,
    *,
    language: str = "python",
    approved: bool = False,
    timeout_seconds: int = 10,
    directory: Path | None = None,
    max_output_bytes: int = 100_000,
) -> dict[str, Any]:
    require(approved, "Explicit host script approval required", "NEEDS_APPROVAL")
    require(language in ("python", "r"), "Unsupported script language")
    require(1 <= timeout_seconds <= 120, "Timeout outside allowed range")
    require(0 < len(source.encode("utf-8")) <= 200_000, "Script exceeds budget", "RESOURCE_LIMIT")
    require(100 <= max_output_bytes <= 1_000_000, "Output budget outside allowed range")
    runner = sys.executable if language == "python" else shutil.which("Rscript")
    require(bool(runner), "Optional Rscript runtime unavailable", "DEPENDENCY_MISSING")
    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    parent = directory.resolve() if directory else None
    if parent:
        require(parent.is_dir(), "Execution directory does not exist", "NOT_FOUND")
    with tempfile.TemporaryDirectory(prefix="rw-script-", dir=parent) as workspace:
        path = Path(workspace) / ("script.py" if language == "python" else "script.R")
        path.write_text(source, encoding="utf-8")
        environment = {
            k: v
            for k, v in os.environ.items()
            if k.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG"}
        }
        environment["PYTHONIOENCODING"] = "utf-8"
        try:
            # S603: trusted interpreter executable, argument vector, explicit host approval.
            finished = subprocess.run(  # noqa: S603
                [str(runner), str(path)],
                cwd=workspace,
                env=environment,
                shell=False,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AnalysisError("CANCELLED", "Script exceeded execution timeout") from exc
        stdout = finished.stdout[:max_output_bytes].decode("utf-8", errors="replace")
        stderr = finished.stderr[:max_output_bytes].decode("utf-8", errors="replace")
        return {
            "status": "ok" if finished.returncode == 0 else "failed",
            "exit_code": finished.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "output_truncated": (
                len(finished.stdout) > max_output_bytes or len(finished.stderr) > max_output_bytes
            ),
            "script_sha256": source_hash,
            "runner": str(runner),
            "isolation": "process only; script retains user-level OS permissions",
        }

"""Scoped child-process execution with bounded outputs and explicit limitations."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import AnalysisError, require
from .models import canonical_json


@dataclass(frozen=True)
class RuntimeApproval:
    source_hash: str
    language: str
    timeout_seconds: int
    nonce: str
    expires_at: float
    signature: str


class RuntimeAuthorizer:
    """Process-local issuer for approvals bound to exact script content and limits."""

    def __init__(self, *, max_ttl_seconds: int = 300):
        require(1 <= max_ttl_seconds <= 3600, "Invalid runtime approval TTL")
        self._secret = secrets.token_bytes(32)
        self._max_ttl_seconds = max_ttl_seconds
        self._consumed: set[str] = set()

    def _payload(
        self, source_hash: str, language: str, timeout_seconds: int, nonce: str, expires_at: float
    ) -> bytes:
        return canonical_json(
            {
                "source_hash": source_hash,
                "language": language,
                "timeout_seconds": timeout_seconds,
                "nonce": nonce,
                "expires_at": expires_at,
            }
        )

    def issue(
        self,
        source: str,
        *,
        language: str = "python",
        timeout_seconds: int = 10,
        ttl_seconds: int = 60,
        now: float | None = None,
    ) -> RuntimeApproval:
        _validate_script_request(source, language, timeout_seconds)
        require(1 <= ttl_seconds <= self._max_ttl_seconds, "Runtime approval TTL outside range")
        source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        nonce = secrets.token_hex(16)
        expires_at = float(time.time() if now is None else now) + ttl_seconds
        payload = self._payload(source_hash, language, timeout_seconds, nonce, expires_at)
        signature = hmac.new(self._secret, payload, hashlib.sha256).hexdigest()
        return RuntimeApproval(source_hash, language, timeout_seconds, nonce, expires_at, signature)

    def verify_and_consume(
        self,
        approval: object,
        source: str,
        *,
        language: str,
        timeout_seconds: int,
        now: float | None = None,
    ) -> RuntimeApproval:
        require(
            isinstance(approval, RuntimeApproval),
            "Explicit script approval required",
            "NEEDS_APPROVAL",
        )
        current = float(time.time() if now is None else now)
        source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        require(
            approval.source_hash == source_hash,
            "Script changed after approval",
            "PERMISSION_DENIED",
        )
        require(
            approval.language == language,
            "Runtime language changed after approval",
            "PERMISSION_DENIED",
        )
        require(
            approval.timeout_seconds == timeout_seconds,
            "Runtime limits changed after approval",
            "PERMISSION_DENIED",
        )
        require(current <= approval.expires_at, "Script approval expired", "PERMISSION_DENIED")
        require(
            approval.nonce not in self._consumed,
            "Script approval already used",
            "PERMISSION_DENIED",
        )
        payload = self._payload(
            approval.source_hash,
            approval.language,
            approval.timeout_seconds,
            approval.nonce,
            approval.expires_at,
        )
        expected = hmac.new(self._secret, payload, hashlib.sha256).hexdigest()
        require(
            hmac.compare_digest(expected, approval.signature),
            "Script approval invalid",
            "PERMISSION_DENIED",
        )
        self._consumed.add(approval.nonce)
        return approval


def _validate_script_request(source: str, language: str, timeout_seconds: int) -> None:
    require(language in ("python", "r"), "Unsupported script language")
    require(1 <= timeout_seconds <= 120, "Timeout outside allowed range")
    require(0 < len(source.encode("utf-8")) <= 200_000, "Script exceeds budget", "RESOURCE_LIMIT")


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        taskkill = shutil.which("taskkill")
        require(bool(taskkill), "Windows process-tree terminator unavailable", "DEPENDENCY_MISSING")
        subprocess.run(  # noqa: S603
            [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
            shell=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _runner_version(runner: str, language: str) -> str:
    if language == "python":
        return sys.version.split()[0]
    completed = subprocess.run(  # noqa: S603
        [runner, "--version"],
        capture_output=True,
        check=False,
        shell=False,
        timeout=5,
    )
    raw = completed.stdout or completed.stderr
    return raw.decode("utf-8", errors="replace").strip()[:500]


def _artifacts(workspace: Path, script_name: str, *, max_files: int = 100) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for path in sorted(item for item in workspace.rglob("*") if item.is_file()):
        relative = path.relative_to(workspace).as_posix()
        if relative in {script_name, "stdout.bin", "stderr.bin"}:
            continue
        require(len(output) < max_files, "Script artifact count exceeds budget", "RESOURCE_LIMIT")
        size = path.stat().st_size
        require(size <= 50_000_000, "Script artifact exceeds size budget", "RESOURCE_LIMIT")
        output.append(
            {
                "path": relative,
                "size": size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return output


def run_script(
    source: str,
    *,
    authorizer: RuntimeAuthorizer,
    approval: RuntimeApproval | None = None,
    language: str = "python",
    timeout_seconds: int = 10,
    directory: Path | None = None,
    max_output_bytes: int = 100_000,
) -> dict[str, Any]:
    """Execute one approved script in a temporary process workspace.

    The process boundary, environment filtering and workspace isolation reduce
    accidental coupling. This is deliberately not described as an OS security
    sandbox because the script retains the current user's operating-system rights.
    """

    _validate_script_request(source, language, timeout_seconds)
    require(100 <= max_output_bytes <= 1_000_000, "Output budget outside allowed range")
    authorizer.verify_and_consume(
        approval,
        source,
        language=language,
        timeout_seconds=timeout_seconds,
    )
    runner = sys.executable if language == "python" else shutil.which("Rscript")
    require(bool(runner), "Optional Rscript runtime unavailable", "DEPENDENCY_MISSING")
    runner = str(runner)
    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    parent = directory.resolve() if directory else None
    if parent:
        require(parent.is_dir(), "Execution directory does not exist", "NOT_FOUND")
    with tempfile.TemporaryDirectory(prefix="rw-script-", dir=parent) as raw_workspace:
        workspace = Path(raw_workspace)
        script_name = "script.py" if language == "python" else "script.R"
        path = workspace / script_name
        stdout_path = workspace / "stdout.bin"
        stderr_path = workspace / "stderr.bin"
        path.write_text(source, encoding="utf-8")
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG"}
        }
        environment["PYTHONIOENCODING"] = "utf-8"
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
            process = subprocess.Popen(  # noqa: S603
                [runner, str(path)],
                cwd=workspace,
                env=environment,
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
                creationflags=creationflags,
                start_new_session=os.name != "nt",
            )
            try:
                return_code = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                _terminate_process_tree(process)
                raise AnalysisError("CANCELLED", "Script exceeded execution timeout") from exc
        stdout_bytes = stdout_path.read_bytes()
        stderr_bytes = stderr_path.read_bytes()
        artifacts = _artifacts(workspace, script_name)
        return {
            "status": "ok" if return_code == 0 else "failed",
            "exit_code": return_code,
            "stdout": stdout_bytes[:max_output_bytes].decode("utf-8", errors="replace"),
            "stderr": stderr_bytes[:max_output_bytes].decode("utf-8", errors="replace"),
            "output_truncated": (
                len(stdout_bytes) > max_output_bytes or len(stderr_bytes) > max_output_bytes
            ),
            "script_sha256": source_hash,
            "runner": runner,
            "runner_version": _runner_version(runner, language),
            "artifacts": artifacts,
            "network_policy": "not restricted by this process-only executor",
            "isolation": (
                "temporary process workspace only; script retains user-level OS permissions"
            ),
        }

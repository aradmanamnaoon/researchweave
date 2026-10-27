"""Generate conservative, deterministic Rust-migration baseline evidence.

Run from any directory: python scripts/rust_rewrite/generate_census.py
No files outside docs/verification/rust-rewrite are written.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs" / "verification" / "rust-rewrite"
RECOVERY_TAG = "archive/python-final-c84cdf1"
RECOVERY_BUNDLE = ROOT.parent / "researchweave-recovery" / "researchweave-python-final-c84cdf1.bundle"


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], stderr=subprocess.DEVNULL)


def classify(path: str) -> dict[str, str]:
    lower = path.lower()
    parts = lower.split("/")
    suffix = Path(lower).suffix
    privacy = "review" if any(x in parts for x in ("examples", "fixtures", "screenshots")) else "low"
    secret = "review" if any(x in lower for x in ("credential", "secret", "token", ".env", "keyring")) else "low"
    if lower == ".env.example":
        secret = "template-review"
    if any(x in parts for x in ("src", "tests", "assets", "docs", "packaging", "scripts", ".agents", ".github")):
        value = "high"
    elif suffix in (".bundle", ".db", ".sqlite", ".rwproj"):
        value = "review"
        privacy = "review"
    else:
        value = "review"
    if any(x in parts for x in ("workstreams", "prompts")):
        privacy = "review"
    return {
        "privacy_risk": privacy,
        "secret_risk": secret,
        "migration_value": value,
        "final_disposition": "review" if privacy == "review" or secret != "low" else "preserve",
        "rationale": "Conservative path-based triage; inspect contents before removal or publication.",
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    tracked = [p.decode("utf-8", "surrogateescape") for p in git("ls-files", "-z").split(b"\0") if p]
    statuses = {}
    for record in git("status", "--porcelain=v1", "-z", "--untracked-files=all").split(b"\0"):
        if record:
            decoded = record.decode("utf-8", "surrogateescape")
            statuses[decoded[3:]] = decoded[:2]
    entries = []
    for relative in sorted(tracked):
        path = ROOT / relative
        kind = "symlink" if path.is_symlink() else "file" if path.is_file() else "missing"
        entries.append({
            "path": relative,
            "type": kind,
            "size_bytes": path.lstat().st_size if path.exists() or path.is_symlink() else None,
            "git_state": statuses.get(relative, "tracked-clean"),
            **classify(relative),
        })
    try:
        tag_commit = git("rev-parse", f"{RECOVERY_TAG}^{{commit}}").decode().strip()
    except subprocess.CalledProcessError:
        tag_commit = None
    bundle = {
        "path": str(RECOVERY_BUNDLE),
        "exists": RECOVERY_BUNDLE.is_file(),
        "size_bytes": RECOVERY_BUNDLE.stat().st_size if RECOVERY_BUNDLE.is_file() else None,
        "sha256": sha256(RECOVERY_BUNDLE) if RECOVERY_BUNDLE.is_file() else None,
    }
    recovery = {
        "tag": RECOVERY_TAG,
        "tag_commit": tag_commit,
        "bundle": bundle,
        "note": "Observed local artifacts only; bundle integrity and restore require separate verification.",
    }
    baseline = {
        "schema_version": 1,
        "git_head": git("rev-parse", "HEAD").decode().strip(),
        "git_branch": git("branch", "--show-current").decode().strip(),
        "tracked_count": len(entries),
        "entries": entries,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, payload in (("repository-census.json", baseline), ("recovery-metadata.json", recovery)):
        (OUTPUT / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(entries)} tracked entries; recovery tag commit: {tag_commit}; bundle present: {bundle['exists']}")


if __name__ == "__main__":
    main()

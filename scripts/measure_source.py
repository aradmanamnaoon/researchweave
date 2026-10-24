"""Measure substantive first-party Python source lines without counting padding."""

from __future__ import annotations

import argparse
import ast
import io
import json
import tokenize
from collections import defaultdict
from pathlib import Path


def docstring_lines(tree: ast.AST) -> set[int]:
    lines: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            end = getattr(first, "end_lineno", first.lineno)
            lines.update(range(first.lineno, end + 1))
    return lines


def substantive_lines(path: Path) -> int:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    excluded = docstring_lines(tree)
    token_lines: set[int] = set()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in {
            tokenize.COMMENT,
            tokenize.ENCODING,
            tokenize.ENDMARKER,
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.NEWLINE,
            tokenize.NL,
        }:
            continue
        start, end = token.start[0], token.end[0]
        token_lines.update(line for line in range(start, end + 1) if line not in excluded)
    return len(token_lines)


def measure(root: Path) -> dict[str, object]:
    package_root = root / "src" / "researchweave"
    files = sorted(package_root.rglob("*.py"))
    per_package: dict[str, int] = defaultdict(int)
    per_file: dict[str, int] = {}
    for path in files:
        relative = path.relative_to(root).as_posix()
        count = substantive_lines(path)
        per_file[relative] = count
        parts = path.relative_to(package_root).parts
        package = parts[0] if len(parts) > 1 else "package-root"
        per_package[package] += count
    return {
        "method": (
            "AST/tokenize count of physical lines containing executable/declarative Python tokens; "
            "blank lines, comment-only lines, module/class/function docstrings, tests, fixtures, "
            "vendored and generated files are excluded by scope."
        ),
        "source_root": str(package_root.resolve()),
        "python_files": len(files),
        "per_package": dict(sorted(per_package.items())),
        "total_substantive_sloc": sum(per_file.values()),
        "per_file": per_file,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    report = measure(args.root.resolve())
    payload = json.dumps(report, indent=2, sort_keys=True)
    print(payload)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

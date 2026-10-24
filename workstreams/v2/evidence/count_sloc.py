"""Deterministic first-party Python SLOC counter for V2 evidence handoff.

Exclude blank, comment-only, and docstring-only lines. A line containing
both executable code and a comment is counted as code. Source root is fixed.
"""

from __future__ import annotations

import ast
import io
import json
import tokenize
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[3] / "src" / "researchweave" / "evidence"
OUTPUT = Path(__file__).with_name("CODE_METRICS.json")


def code_lines(path: Path) -> int:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    docstring_lines: set[int] = set()

    def collect(body: list[ast.stmt]) -> None:
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            if isinstance(body[0].value.value, str):
                docstring_lines.update(range(body[0].lineno, body[0].end_lineno + 1))

    collect(tree.body)
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            collect(node.body)
    meaningful: set[int] = set()
    stream = tokenize.generate_tokens(io.StringIO(source).readline)
    for token in stream:
        if token.type in (
            tokenize.COMMENT,
            tokenize.NL,
            tokenize.NEWLINE,
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.ENDMARKER,
            tokenize.ENCODING,
        ):
            continue
        meaningful.update(range(token.start[0], token.end[0] + 1))
    return len(meaningful - docstring_lines)


def main() -> None:
    files = sorted(SOURCE_ROOT.rglob("*.py"))
    counts = {file.relative_to(SOURCE_ROOT).as_posix(): code_lines(file) for file in files}
    result = {
        "definition": "Token-based nonblank noncomment Python code lines minus AST docstring lines",
        "scope": "src/researchweave/evidence/**/*.py",
        "files": len(files),
        "meaningful_source_lines": sum(counts.values()),
        "file_lines": counts,
        "exclusions": "tests, workstreams, Markdown, fixtures, docstrings, comments, blanks",
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"files": result["files"], "meaningful_source_lines": result["meaningful_source_lines"]}
        )
    )


if __name__ == "__main__":
    main()

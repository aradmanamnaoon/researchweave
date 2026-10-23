"""Measure source SLOC without counting blank, comment or docstring-only lines."""

from __future__ import annotations

import ast
import json
import sys
import tokenize
from pathlib import Path


def count(path: Path) -> int:
    with path.open("rb") as stream:
        tokens = list(tokenize.tokenize(stream.readline))
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstring_lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if not node.body:
            continue
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                docstring_lines.update(range(first.lineno, first.end_lineno + 1))
    meaningful: set[int] = set()
    for token in tokens:
        if token.type in {
            tokenize.COMMENT,
            tokenize.NL,
            tokenize.NEWLINE,
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.ENCODING,
            tokenize.ENDMARKER,
        }:
            continue
        meaningful.update(range(token.start[0], token.end[0] + 1))
    return len(meaningful - docstring_lines)


def main() -> None:
    root = Path(sys.argv[1])
    sources = sorted(root.rglob("*.py"))
    output = {
        "definition": "token-bearing lines excluding blanks, comments and AST docstring spans",
        "source_root": "src/researchweave/ai",
        "python_file_count": len(sources),
        "python_sloc": sum(count(path) for path in sources),
        "files": {str(path.relative_to(root)).replace("\\", "/"): count(path) for path in sources},
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()

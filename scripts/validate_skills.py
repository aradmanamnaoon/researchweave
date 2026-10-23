"""Validate repo-local skill metadata and safe relative references."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".agents" / "skills"
NAME = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")


def validate() -> list[str]:
    errors: list[str] = []
    names: set[str] = set()
    for folder in sorted(SKILLS.iterdir()) if SKILLS.exists() else []:
        if not folder.is_dir():
            errors.append(f"{folder}: unexpected file")
            continue
        file = folder / "SKILL.md"
        if not file.is_file():
            errors.append(f"{folder.name}: missing SKILL.md")
            continue
        raw = file.read_text(encoding="utf-8")
        match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", raw, re.S)
        if not match:
            errors.append(f"{folder.name}: missing YAML frontmatter")
            continue
        try:
            meta = yaml.safe_load(match.group(1))
        except yaml.YAMLError as exc:
            errors.append(f"{folder.name}: invalid YAML: {exc}")
            continue
        if not isinstance(meta, dict):
            errors.append(f"{folder.name}: frontmatter must be a mapping")
            continue
        name, desc = meta.get("name"), meta.get("description")
        if not isinstance(name, str) or not NAME.fullmatch(name):
            errors.append(f"{folder.name}: invalid name")
        elif name in names:
            errors.append(f"{folder.name}: duplicate name {name}")
        else:
            names.add(name)
        if not isinstance(desc, str) or not 15 <= len(desc) <= 1024:
            errors.append(f"{folder.name}: description must be 15–1024 characters")
        body = raw[match.end() :]
        words = re.findall(r"\b[\w-]+\b", body)
        if len(words) < 200:
            errors.append(f"{folder.name}: insufficient guidance ({len(words)} words)")
        for item in LINK.findall(body):
            url = item.split("#", 1)[0].strip()
            if not url or "://" in url or url.startswith(("mailto:", "#")):
                continue
            target = (folder / url).resolve()
            if not target.is_relative_to(folder.resolve()) or not target.exists():
                errors.append(f"{folder.name}: broken/escaping local reference {item}")
    if len(names) < 24:
        errors.append(f"expected at least 24 unique skills; found {len(names)}")
    return errors


if __name__ == "__main__":
    problems = validate()
    if problems:
        print("\n".join(f"FAIL: {problem}" for problem in problems))
        sys.exit(1)
    print(f"OK: {len(list(SKILLS.glob('*/SKILL.md')))} skills validated")

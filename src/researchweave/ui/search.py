"""Bounded, deterministic local search over project research artifacts.

Search is literal Unicode casefold matching; it does not invent quotations,
consult remote services or pretend to perform semantic similarity search.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal, cast

from .contracts import Project, UIError

MAX_QUERY = 200
MAX_RESULTS = 500
MAX_SNIPPET = 320


@dataclass(frozen=True)
class SearchHit:
    kind: Literal[
        "source", "annotation", "evidence", "claim", "manuscript", "notebook", "protocol"
    ]
    record_id: str
    title: str
    snippet: str
    offset: int
    length: int
    verified: bool
    source_id: str = ""
    reference: str = ""

    def as_dict(self) -> dict[str, str | int | bool]:
        return asdict(self)


def _fragment(value: str, offset: int, size: int) -> str:
    """Return a bounded readable context around the first literal match."""
    lead = max(0, offset - 80)
    trailing = min(len(value), offset + size + 160)
    content = value[lead:trailing].replace("\r", " ").replace("\n", " ")
    if len(content) > MAX_SNIPPET:
        content = content[:MAX_SNIPPET]
    return ("… " if lead else "") + content + (" …" if trailing < len(value) else "")


def _matches(content: str, query: str) -> int:
    """Use codepoint offsets from the original string, including Unicode."""
    # Casefold can expand individual characters (e.g. German ß -> ss).
    # A reversible normalized-character map preserves offsets for highlighting.
    lowered: list[str] = []
    reverse: list[int] = []
    for index, character in enumerate(content):
        folded = character.casefold()
        lowered.append(folded)
        reverse.extend([index] * len(folded))
    normalized = "".join(lowered)
    found = normalized.find(query.casefold())
    return reverse[found] if found >= 0 else -1


def search_project(
    project: Project,
    query: str,
    *,
    limit: int = 50,
    offset: int = 0,
    categories: tuple[str, ...] | None = None,
) -> dict[str, object]:
    if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY:
        raise UIError("INVALID_INPUT", "Search requires 1–200 characters.",
                      "Enter a shorter term or phrase.")
    if (isinstance(limit, bool) or not isinstance(limit, int)
            or not 1 <= limit <= MAX_RESULTS):
        raise UIError("INVALID_INPUT", "Search page limit must be 1–500.",
                      "Choose a smaller results page.")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise UIError("INVALID_INPUT", "Search page offset must be nonnegative.",
                      "Go back to the first page.")
    permitted = {
        "source", "annotation", "evidence", "claim", "manuscript", "notebook", "protocol"
    }
    if categories is None:
        categories = tuple(sorted(permitted))
    if not isinstance(categories, tuple) or any(name not in permitted for name in categories):
        raise UIError("INVALID_INPUT", "Unknown research search category.",
                      "Filter by source, annotation, manuscript, notebook or protocol.")
    term = query.strip()
    hits: list[SearchHit] = []
    if "source" in categories:
        for source in project.sources:
            for segment, label in ((source.title, "title"), (source.text, "text")):
                start = _matches(segment, term)
                if start >= 0:
                    hits.append(SearchHit(
                        "source", source.id, source.title,
                        _fragment(segment, start, len(term)), start,
                        len(term), source.verified, source.id,
                        f"{source.source_label} · {label}",
                    ))
                    break
    if "annotation" in categories:
        for note in project.annotations:
            for segment in (note.quote, note.memo, note.code):
                start = _matches(segment, term)
                if start >= 0:
                    hits.append(SearchHit(
                        "annotation", note.id, f"Code: {note.code}",
                        _fragment(segment, start, len(term)), start,
                        len(term), False, note.source_id, "Coded source excerpt",
                    ))
                    break
    if "evidence" in categories:
        for evidence in project.evidence:
            for segment in (evidence.quote, evidence.note):
                start = _matches(segment, term)
                if start >= 0:
                    hits.append(SearchHit(
                        "evidence", evidence.id, "Evidence passage",
                        _fragment(segment, start, len(term)), start, len(term),
                        False, evidence.source_id, "Source-linked evidence anchor",
                    ))
                    break
    if "claim" in categories:
        for claim in project.claims:
            start = _matches(claim.text, term)
            if start >= 0:
                hits.append(SearchHit(
                    "claim", claim.id, "Draft claim",
                    _fragment(claim.text, start, len(term)), start, len(term),
                    False, "", "Draft claim requiring human scientific review",
                ))
    for category, title, content in (
        ("manuscript", "Manuscript draft", project.manuscript),
        ("notebook", "Research notes", project.notebook),
    ):
        if category in categories:
            start = _matches(content, term)
            if start >= 0:
                hits.append(SearchHit(
                    cast(Literal["manuscript", "notebook"], category), project.id, title,
                    _fragment(content, start, len(term)), start,
                    len(term), False, "", "Locally authored draft",
                ))
    if "protocol" in categories:
        protocol = project.protocol
        if isinstance(protocol, dict):
            values = protocol.get("values", {})
            if isinstance(values, dict):
                for key, value in values.items():
                    if not isinstance(key, str) or not isinstance(value, str):
                        continue
                    found = _matches(value, term)
                    if found >= 0:
                        hits.append(SearchHit(
                            "protocol", project.id,
                            f"Protocol: {key.replace('_', ' ').title()}",
                            _fragment(value, found, len(term)), found,
                            len(term), False, "", "Unverified draft protocol",
                        ))
    priority = {
        "source": 0, "evidence": 1, "annotation": 2, "claim": 3,
        "protocol": 4, "manuscript": 5, "notebook": 6,
    }
    hits.sort(key=lambda hit: (priority[hit.kind], hit.title.casefold(), hit.record_id))
    return {
        "query": term,
        "total": len(hits),
        "limit": limit,
        "offset": offset,
        "hits": [hit.as_dict() for hit in hits[offset:offset + limit]],
        "search_method": "literal Unicode casefold; local project only",
        "partial": False,
        "warnings": (
            ["Only the first match per artifact is shown; this is not semantic retrieval."]
        ),
    }

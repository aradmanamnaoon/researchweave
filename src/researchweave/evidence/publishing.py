"""Local bibliography, manuscript auditing and transparent submission packets."""

from __future__ import annotations

import re
from typing import Any

from .errors import require
from .library import LibraryService
from .models import canonical_json, sha256
from .storage import ProjectStore
from .writing import CITATION_PATTERN, WritingService


class PublishingService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self.writing = WritingService(store)
        self.library = LibraryService(store)

    def bibliography(self, manuscript_id: str, style: str = "plain") -> dict[str, Any]:
        """A transparent limited renderer; no claim of complete CSL compliance."""
        require(style in {"plain", "numbered"}, "Unsupported style; use plain or numbered")
        sections = self.writing.sections(manuscript_id)
        require(bool(sections), "Manuscript not found", "NOT_FOUND")
        keys: dict[str, str] = {}
        for section in sections:
            for key in CITATION_PATTERN.findall(section["body"]):
                require(
                    key in section["citations"], "Unmapped manuscript citation", "INTEGRITY_FAILURE"
                )
                ref_id = section["citations"][key]
                require(
                    key not in keys or keys[key] == ref_id,
                    "Citation key maps to multiple references",
                    "INTEGRITY_FAILURE",
                )
                keys[key] = ref_id
        entries = []
        for index, (key, ref_id) in enumerate(sorted(keys.items()), 1):
            ref = self.library.get_reference(ref_id)
            authors = ", ".join(ref.authors) if ref.authors else "[authors unavailable]"
            year = str(ref.year) if ref.year is not None else "[year unavailable]"
            citation = f"{authors} ({year}). {ref.title}."
            if ref.doi:
                citation += f" https://doi.org/{ref.doi}"
            if style == "numbered":
                citation = f"[{index}] {citation}"
            entries.append(
                {
                    "key": key,
                    "reference_id": ref_id,
                    "text": citation,
                    "metadata_status": ref.metadata_status,
                    "identity_verified": ref.metadata_status == "verified",
                    "claim_support_verified": False,
                }
            )
        return {
            "style": style,
            "entries": entries,
            "complete_csl_style": False,
            "text": "\n".join(str(row["text"]) for row in entries) + "\n",
        }

    def check_manuscript(
        self,
        manuscript_id: str,
        required_sections: tuple[str, ...] = ("Abstract", "Methods", "Results", "Discussion"),
    ) -> dict[str, Any]:
        sections = self.writing.sections(manuscript_id)
        require(bool(sections), "Manuscript not found", "NOT_FOUND")
        issues = list(self.writing.inspect(manuscript_id)["issues"])
        existing = {row["section"].casefold() for row in sections}
        for required in required_sections:
            if required.casefold() not in existing:
                issues.append({"section": required, "code": "MISSING_REQUIRED_SECTION"})
        for row in sections:
            body = row["body"]
            if not body.strip():
                issues.append({"section": row["section"], "code": "EMPTY_SECTION"})
            if re.search(r"\b(?:TODO|TBD|INSERT CITATION|PLACEHOLDER)\b", body, re.I):
                issues.append({"section": row["section"], "code": "UNRESOLVED_PLACEHOLDER"})
            if "@" in body and re.search(r"\[@[^\]]*$", body):
                issues.append({"section": row["section"], "code": "MALFORMED_CITATION_MARKER"})
        return {
            "manuscript_id": manuscript_id,
            "issues": issues,
            "ready_for_submission": not issues,
            "scientific_claims_verified": False,
            "checks": [
                "section_completeness",
                "reference_identity",
                "citation_mappings",
                "placeholder_scan",
            ],
        }

    def submission_packet(
        self, manuscript_id: str, journal: str, *, allow_incomplete: bool = False
    ) -> dict[str, Any]:
        require(bool(journal.strip()) and len(journal) <= 200, "Journal name required")
        check = self.check_manuscript(manuscript_id)
        if check["issues"] and not allow_incomplete:
            require(
                False,
                "Resolve manuscript validation issues before preparing submission",
                "INTEGRITY_FAILURE",
            )
        bibliography = self.bibliography(manuscript_id)
        manuscript = self.writing.render_markdown(manuscript_id)
        manifest = {
            "schema_version": 1,
            "manuscript_id": manuscript_id,
            "target_journal": journal,
            "files": [
                {"name": "manuscript.md", "sha256": sha256(manuscript.encode("utf-8"))},
                {
                    "name": "bibliography.txt",
                    "sha256": sha256(bibliography["text"].encode("utf-8")),
                },
            ],
            "validation": check,
            "submission_performed": False,
            "editorial_requirements_verified": False,
            "ethics_approval_asserted": False,
        }
        return {
            "manifest": manifest,
            "manifest_json": canonical_json(manifest),
            "files": {"manuscript.md": manuscript, "bibliography.txt": bibliography["text"]},
            "warnings": (["Packet contains unresolved issues"] if check["issues"] else [])
            + ["Confirm journal-specific instructions and ethics declarations manually"],
        }

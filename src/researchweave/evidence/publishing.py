"""Local bibliography, manuscript auditing and transparent submission packets."""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from .claim_support import ClaimSupportService
from .errors import EvidenceError, require
from .library import LibraryService
from .models import canonical_json, now_utc, sha256
from .storage import ProjectStore
from .writing import CITATION_PATTERN, WritingService


class PublishingService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self.writing = WritingService(store)
        self.library = LibraryService(store)

    def bibliography(self, manuscript_id: str, style: str = "plain") -> dict[str, Any]:
        """A transparent limited renderer; no claim of complete CSL compliance."""
        require(
            style in {"plain", "numbered", "apa-basic", "harvard-basic", "vancouver-basic"},
            "Unsupported bibliography style",
        )
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
            doi_text = f" https://doi.org/{ref.doi}" if ref.doi else ""
            if style == "apa-basic":
                citation = f"{authors} ({year}). {ref.title}.{doi_text}"
            elif style == "harvard-basic":
                citation = f"{authors} ({year}) {ref.title}.{doi_text}"
            elif style == "vancouver-basic":
                citation = f"{authors}. {ref.title}. {year}.{doi_text}"
            else:
                citation = f"{authors} ({year}). {ref.title}.{doi_text}"
            if style in {"numbered", "vancouver-basic"}:
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
            "style_fidelity": (
                "basic deterministic rendering; not a complete CSL implementation"
                if style not in {"plain", "numbered"}
                else "researchweave basic style"
            ),
            "missing_metadata_preserved_as_placeholders": True,
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
        claim_check = ClaimSupportService(self.store).check(manuscript_id)
        for claim_issue in claim_check["issues"]:
            issues.append(
                {
                    "claim_id": claim_issue["claim_id"],
                    "code": claim_issue["code"],
                    "section": "registered_claim",
                }
            )
        return {
            "manuscript_id": manuscript_id,
            "issues": issues,
            "ready_for_submission": not issues,
            "scientific_claims_verified": False,
            "registered_claims": claim_check["registered_claims"],
            "registered_claim_issues": claim_check["issues"],
            "claim_coverage_complete": claim_check["claim_coverage_complete"],
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

    def export_submission_packet(
        self,
        manuscript_id: str,
        journal: str,
        destination: Path,
        *,
        allow_incomplete: bool = False,
        requirements: dict[str, Any] | None = None,
        supplied_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Atomically write a checksum-verified draft submission ZIP."""
        require(destination.name.endswith(".rw-submission.zip"),
                "Submission export needs .rw-submission.zip suffix")
        destination = destination.resolve()
        require(destination.parent.is_dir(), "Submission destination parent must exist")
        require(not destination.exists(), "Submission destination already exists", "CONFLICT")
        rules = dict(requirements or {})
        metadata = dict(supplied_metadata or {})
        allowed_metadata = {
            "title",
            "authors",
            "affiliations",
            "funding",
            "conflicts",
            "ethics",
            "data_availability",
            "author_contributions",
            "corresponding_author",
        }
        require(
            set(metadata).issubset(allowed_metadata),
            "Submission metadata contains unsupported fields",
        )
        base = self.submission_packet(
            manuscript_id, journal, allow_incomplete=allow_incomplete
        )
        sections = self.writing.sections(manuscript_id)
        section_names = {row["section"] for row in sections}
        unmet: list[dict[str, Any]] = []
        for name, rule in sorted(rules.items()):
            if name == "required_sections":
                require(
                    isinstance(rule, list) and all(isinstance(item, str) for item in rule),
                    "required_sections must be a list of section names",
                )
                missing = sorted(set(rule) - section_names)
                if missing:
                    unmet.append({"requirement": name, "status": "unmet", "missing": missing})
            elif name == "max_abstract_characters":
                require(type(rule) is int and rule > 0,
                        "max_abstract_characters must be positive")
                abstract = next(
                    (row["body"] for row in sections if row["section"] == "Abstract"),
                    "",
                )
                if len(abstract) > rule:
                    unmet.append({
                        "requirement": name,
                        "status": "unmet",
                        "actual": len(abstract),
                        "maximum": rule,
                    })
            else:
                unmet.append({
                    "requirement": name,
                    "status": "manual_review_required",
                    "rule": rule,
                })
        if unmet and not allow_incomplete:
            raise EvidenceError(
                "INCOMPLETE_SUBMISSION",
                "Venue requirements are not fully satisfied",
                "Resolve requirements or explicitly allow an incomplete draft packet.",
            )
        validation = self.check_manuscript(manuscript_id)
        manuscript_text = str(base["files"]["manuscript.md"])
        title = metadata.get("title")
        authors = metadata.get("authors")
        affiliations = metadata.get("affiliations")
        corresponding = metadata.get("corresponding_author")
        title_page_lines = [
            "# Submission Title Page",
            "",
            f"Target journal: {journal}",
            f"Title: {title if isinstance(title, str) and title.strip() else '[not supplied]'}",
            "",
            "## Authors",
            canonical_json(authors) if authors is not None else "[not supplied]",
            "",
            "## Affiliations",
            canonical_json(affiliations) if affiliations is not None else "[not supplied]",
            "",
            "## Corresponding author",
            canonical_json(corresponding) if corresponding is not None else "[not supplied]",
            "",
            "Only user-supplied metadata is rendered above.",
        ]
        title_page = "\n".join(title_page_lines) + "\n"
        checklist = "\n".join(
            [
                "# Human Submission Review Checklist",
                "",
                "- [ ] Confirm journal-specific author instructions and file naming.",
                "- [ ] Inspect the blinded manuscript for identifying text written "
                "inside sections.",
                "- [ ] Confirm title-page authors, affiliations, and corresponding-author details.",
                "- [ ] Confirm ethics, funding, conflicts, data availability, and "
                "contributions only "
                "when supplied by the authors.",
                "- [ ] Confirm figures, captions, numbering, permissions, and required resolution.",
                "- [ ] Review all integrity warnings and unresolved venue requirements.",
                "- [ ] Perform the actual journal submission manually; this packet "
                "does not submit.",
                "",
            ]
        )
        payloads: dict[str, bytes] = {
            "manuscript.md": manuscript_text.encode(),
            "blinded-manuscript.md": manuscript_text.encode(),
            "title-page.md": title_page.encode(),
            "human-review-checklist.md": checklist.encode(),
            "bibliography.txt": str(base["files"]["bibliography.txt"]).encode(),
            "integrity-report.json": (canonical_json(validation) + "\n").encode(),
            "venue-requirements.json": (
                canonical_json({
                    "journal": journal,
                    "requirements": rules,
                    "unmet_or_manual": unmet,
                }) + "\n"
            ).encode(),
            "supplied-metadata.json": (canonical_json(metadata) + "\n").encode(),
        }
        extension_by_media_type = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/svg+xml": "svg",
            "application/pdf": "pdf",
        }
        figure_manifest: list[dict[str, Any]] = []
        for index, figure in enumerate(self.writing.figures(manuscript_id), 1):
            media_type = str(figure["media_type"])
            extension = extension_by_media_type.get(media_type)
            require(extension is not None, "Unsupported stored figure format", "INTEGRITY_FAILURE")
            digest = str(figure["digest"])
            data = self.store.get_object(digest)
            require(sha256(data) == digest, "Figure object checksum mismatch", "INTEGRITY_FAILURE")
            path = f"figures/figure-{index:03d}-{figure['id']}.{extension}"
            payloads[path] = data
            figure_manifest.append(
                {
                    "figure_id": figure["id"],
                    "label": figure["label"],
                    "caption": figure["caption"],
                    "media_type": media_type,
                    "sha256": digest,
                    "path": path,
                }
            )
        payloads["figures.json"] = (canonical_json(figure_manifest) + "\n").encode()
        inventory = [
            {"path": name, "sha256": sha256(data), "bytes": len(data)}
            for name, data in sorted(payloads.items())
        ]
        manifest = {
            **base["manifest"],
            "format": "researchweave-submission-packet",
            "version": 1,
            "generated_at": now_utc(),
            "requirements": rules,
            "unmet_or_manual_requirements": unmet,
            "metadata_fields_supplied": sorted(metadata),
            "fabricated_metadata_fields": [],
            "blinded_manuscript_generated": True,
            "blinded_manuscript_human_review_required": True,
            "figure_count": len(figure_manifest),
            "human_review_checklist_included": True,
            "submission_performed": False,
            "files": inventory,
        }
        payloads["manifest.json"] = (canonical_json(manifest) + "\n").encode()
        staged: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=".rw-submission-",
                suffix=".tmp",
                dir=destination.parent,
                delete=False,
            ) as handle:
                staged = Path(handle.name)
            with zipfile.ZipFile(
                staged, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
            ) as archive:
                for name, data in sorted(payloads.items()):
                    info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = (stat.S_IFREG | 0o600) << 16
                    info.create_system = 3
                    archive.writestr(info, data)
            with zipfile.ZipFile(staged, "r") as archive:
                decoded = json.loads(archive.read("manifest.json"))
                for item in decoded["files"]:
                    data = archive.read(item["path"])
                    require(
                        len(data) == item["bytes"] and sha256(data) == item["sha256"],
                        "Submission packet checksum mismatch",
                        "INTEGRITY_FAILURE",
                    )
            require(not destination.exists(), "Submission destination appeared", "CONFLICT")
            os.replace(staged, destination)
            return {
                "path": str(destination),
                "bytes": destination.stat().st_size,
                "journal": journal,
                "ready_for_submission": validation["ready_for_submission"] and not unmet,
                "submission_performed": False,
                "manifest_sha256": sha256(payloads["manifest.json"]),
                "warnings": base["warnings"],
            }
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)

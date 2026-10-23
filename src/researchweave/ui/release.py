"""Read-only manuscript submission preview with explicit unmet review gates.

The UI supports research writing without fabricating ethics approvals, journals,
authors, funding information, acceptance or complete bibliographic references.
Any 'ready' state is strictly file structure readiness for human review.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .contracts import Project, UIError
from .diagnostics import audit_project
from .evidence import draft_manuscript_reference, inspect_claim

MAX_MANUSCRIPT_PREVIEW = 250_000
MAX_RELEASE_ITEMS = 500
MAX_FILE_LABEL = 120
_HEADER = re.compile(r"^#{1,6}\s+\S+", re.MULTILINE)
_CITATION = re.compile(r"\[\s*(?:citation needed|source needed|todo citation)\s*\]",
                       re.IGNORECASE)


@dataclass(frozen=True)
class ReleaseGate:
    id: str
    heading: str
    state: Literal["pass", "blocked", "manual-review", "not-applicable"]
    rationale: str
    next_action: str
    evidence_count: int = 0

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class SubmissionPreview:
    project_id: str
    project_revision: int
    title: str
    manuscript_sha256: str
    manuscript_characters: int
    gates: list[ReleaseGate] = field(default_factory=list)
    source_registry: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        blocking = [item.id for item in self.gates if item.state == "blocked"]
        manual = [item.id for item in self.gates if item.state == "manual-review"]
        return {
            "schema_version": 1,
            "preview_only": True,
            "project_id": self.project_id,
            "revision": self.project_revision,
            "title": self.title,
            "manuscript_sha256": self.manuscript_sha256,
            "manuscript_characters": self.manuscript_characters,
            "structural_status": (
                "blocked" if blocking else
                "requires-manual-review" if manual else
                "structurally-ready-for-human-review"
            ),
            "submission_approved": False,
            "ethics_approved": False,
            "journal_selected": False,
            "ready_to_publish": False,
            "gates": [item.as_dict() for item in self.gates],
            "blocking_gates": blocking,
            "manual_gates": manual,
            "source_registry": self.source_registry,
            "draft_claims": self.claims,
            "warnings": list(self.warnings),
            "next_step": (
                "Resolve blocked file and evidence issues, verify bibliographic "
                "records, complete real ethics and journal forms, then obtain "
                "independent human review."
            ),
        }


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _gate(
    key: str,
    heading: str,
    state: Literal["pass", "blocked", "manual-review", "not-applicable"],
    why: str,
    next_action: str,
    evidence_count: int = 0,
) -> ReleaseGate:
    return ReleaseGate(key, heading, state, why, next_action, evidence_count)


def inspect_submission(project: Project) -> dict[str, Any]:
    """Return a current, immutable in-memory preview; no external calls occur."""
    if len(project.manuscript) > MAX_MANUSCRIPT_PREVIEW:
        raise UIError("RESOURCE_LIMIT", "Manuscript exceeds preview capacity.",
                      "Split large text into smaller sections.")
    preview = SubmissionPreview(
        project_id=project.id,
        project_revision=project.revision,
        title=project.title,
        manuscript_sha256=_sha256(project.manuscript),
        manuscript_characters=len(project.manuscript),
    )

    if not project.manuscript.strip():
        preview.gates.append(_gate(
            "MANUSCRIPT_MISSING", "Draft manuscript",
            "blocked", "No manuscript body has been saved.",
            "Write and save a manuscript draft before preparing a submission.",
        ))
    else:
        preview.gates.append(_gate(
            "MANUSCRIPT_PRESENT", "Draft manuscript",
            "pass", "A nonempty local draft is saved.",
            "Review structure, journal style and accuracy with a human reader.",
        ))

    headers = _HEADER.findall(project.manuscript)
    if not headers:
        preview.gates.append(_gate(
            "STRUCTURE_HEADINGS", "Document structure",
            "manual-review", "No Markdown section headings were detected.",
            "Confirm the required title, abstract and section structure for the venue.",
        ))
    else:
        preview.gates.append(_gate(
            "STRUCTURE_HEADINGS", "Document structure",
            "pass", f"{len(headers)} Markdown section headings were detected.",
            "Confirm required sections and capitalization against venue instructions.",
            len(headers),
        ))

    placeholder_count = len(_CITATION.findall(project.manuscript))
    if placeholder_count:
        preview.gates.append(_gate(
            "CITATION_PLACEHOLDER", "Unresolved citations",
            "blocked",
            f"{placeholder_count} explicit citation placeholders remain in manuscript text.",
            "Replace placeholders only after checking genuine source metadata.",
            placeholder_count,
        ))
    else:
        preview.gates.append(_gate(
            "CITATION_PLACEHOLDER", "Unresolved citations",
            "manual-review",
            "No explicit placeholder markers detected; uncited claims may still exist.",
            "Inspect every factual assertion and the real reference list.",
        ))

    hashes = {
        source.id: _sha256(source.text)
        for source in project.sources
    }
    broken_source_ids = [
        source.id for source in project.sources
        if source.content_hash and hashes[source.id] != source.content_hash
    ]
    for source in project.sources[:MAX_RELEASE_ITEMS]:
        preview.source_registry.append({
            "source_id": source.id,
            "title": source.title,
            "user_label": source.source_label,
            "content_sha256": hashes[source.id],
            "checksum_matched": source.id not in broken_source_ids,
            "metadata_verified": source.verified,
            "has_complete_bibliography": False,
        })
    if broken_source_ids:
        preview.gates.append(_gate(
            "SOURCE_INTEGRITY", "Source integrity",
            "blocked", f"{len(broken_source_ids)} source content hashes do not match.",
            "Restore the original source records before linking citations.",
        ))
    elif project.sources:
        preview.gates.append(_gate(
            "SOURCE_INTEGRITY", "Source integrity",
            "pass", "Recorded source content hashes match current local source text.",
            "Verify source authenticity and bibliographic metadata separately.",
            len(project.sources),
        ))
    else:
        preview.gates.append(_gate(
            "SOURCE_INTEGRITY", "Source integrity",
            "manual-review", "No local evidence sources are registered.",
            "Import the sources supporting each manuscript claim.",
        ))

    unverified_sources = sum(not source.verified for source in project.sources)
    if unverified_sources:
        preview.gates.append(_gate(
            "BIBLIOGRAPHY_VERIFICATION", "Bibliographic metadata",
            "manual-review",
            f"{unverified_sources} source records still have unverified metadata.",
            "Check publication details using the original source and venue style.",
            unverified_sources,
        ))
    else:
        preview.gates.append(_gate(
            "BIBLIOGRAPHY_VERIFICATION", "Bibliographic metadata",
            "manual-review", "Local flags cannot independently certify a citation.",
            "Validate all citations and DOIs against actual publications.",
        ))

    unlinked_claims = 0
    invalid_claims = 0
    for claim in project.claims[:MAX_RELEASE_ITEMS]:
        if not claim.supporting_evidence:
            unlinked_claims += 1
        try:
            check = inspect_claim(project, claim)
            if check["integrity"] != "matched":
                invalid_claims += 1
            preview.claims.append({
                "claim_id": claim.id,
                "draft_text": claim.text,
                "supporting_count": len(check["supporting"]),
                "challenging_count": len(check["challenging"]),
                "evidence_integrity": check["integrity"],
                "scientifically_verified": False,
                "warnings": check["warnings"],
            })
        except UIError:
            invalid_claims += 1
            preview.claims.append({
                "claim_id": claim.id,
                "draft_text": claim.text,
                "evidence_integrity": "failed",
                "scientifically_verified": False,
                "warnings": ["Referenced source or evidence record is missing."],
            })
    if invalid_claims:
        preview.gates.append(_gate(
            "CLAIM_LINKS", "Evidence linkage",
            "blocked", f"{invalid_claims} claims reference broken evidence records.",
            "Inspect original source excerpts and repair the claim links.",
        ))
    elif unlinked_claims:
        preview.gates.append(_gate(
            "CLAIM_LINKS", "Evidence linkage",
            "manual-review", f"{unlinked_claims} claim drafts have no supporting anchor.",
            "Link claims to relevant verified sources and examine contradictions.",
        ))
    else:
        preview.gates.append(_gate(
            "CLAIM_LINKS", "Evidence linkage",
            "manual-review",
            "All saved claim links are present, but semantic support is unverified.",
            "Have a qualified human review whether sources support each claim.",
            len(project.claims),
        ))

    integrity = audit_project(project)
    errors = integrity["summary"]["errors"]
    if errors:
        preview.gates.append(_gate(
            "PROJECT_INTEGRITY", "Project integrity",
            "blocked", f"{errors} structural integrity findings need attention.",
            "Open Diagnostics and resolve failed source, annotation and dataset checks.",
        ))
    else:
        preview.gates.append(_gate(
            "PROJECT_INTEGRITY", "Project integrity",
            "pass", "No structural integrity errors were detected.",
            "Continue methodological, ethics and source-quality review.",
        ))

    if project.protocol:
        missing = [
            name for name, text in project.protocol.get("values", {}).items()
            if isinstance(text, str) and not text.strip()
        ]
        preview.gates.append(_gate(
            "PROTOCOL_REVIEW", "Research design protocol",
            "manual-review", f"{len(missing)} protocol fields are currently empty.",
            "Complete the relevant required fields and obtain methodological review.",
        ))
    else:
        preview.gates.append(_gate(
            "PROTOCOL_REVIEW", "Research design protocol",
            "manual-review", "No saved methods protocol accompanies this draft.",
            "Create a study design protocol and document deviations transparently.",
        ))

    preview.gates.extend([
        _gate(
            "ETHICS", "Research ethics", "manual-review",
            "Ethics approval or exemption has not been validated.",
            "Provide real approval, consent or documented exemption where applicable.",
        ),
        _gate(
            "DATA_ACCESS", "Data availability and privacy", "manual-review",
            "Licensing, data sharing permissions and disclosure risks were not inspected.",
            "Review dataset licenses, consent terms and disclosure obligations.",
        ),
        _gate(
            "VENUE", "Journal or conference requirements", "manual-review",
            "No venue-specific submission rules were verified.",
            "Read the target journal's current author instructions and forms.",
        ),
        _gate(
            "AUTHORSHIP", "Authorship, funding and conflicts", "manual-review",
            "Identity, contribution, funding and interest disclosures need human completion.",
            "Confirm author information and all mandatory declarations.",
        ),
    ])
    preview.warnings.extend([
        "Never submit this preview as evidence of ethics or peer-review approval.",
        "BibTeX/DOI metadata were not retrieved or fabricated.",
        "A clean hash and an attached quotation cannot establish research truth.",
    ])
    if len(project.sources) > MAX_RELEASE_ITEMS or len(project.claims) > MAX_RELEASE_ITEMS:
        preview.warnings.append(
            "Only first 500 source/claim records were shown; the entire project was not "
            "individually enumerated in this preview."
        )
    return preview.as_dict()


def submission_markdown(project: Project) -> dict[str, Any]:
    """Generate a source-qualified review packet to copy or export manually."""
    status = inspect_submission(project)
    lines = [
        f"# Draft submission review: {project.title}",
        "",
        f"Project ID: {project.id}",
        f"Revision: {project.revision}",
        f"Manuscript SHA-256: {status['manuscript_sha256']}",
        f"Structural status: {status['structural_status']}",
        "Submission approved: No",
        "",
        "## Human review gates",
        "",
    ]
    for gate in status["gates"]:
        lines.append(
            f"- [{gate['state']}] {gate['heading']}: {gate['rationale']}"
        )
        lines.append(f"  Next: {gate['next_action']}")
    lines.extend(["", "## Draft claims and source trace", ""])
    for claim in project.claims[:MAX_RELEASE_ITEMS]:
        try:
            reference = draft_manuscript_reference(project, claim.id)
            source_text = ", ".join(reference["source_ids"])
        except UIError:
            source_text = "unavailable or broken source links"
        lines.extend([
            f"- Draft: {claim.text}",
            f"  Source record IDs: {source_text}",
            "  Citation: [Requires human verification of bibliographic metadata]",
        ])
    lines.extend([
        "", "## Draft manuscript", "",
        project.manuscript or "[No manuscript text saved]",
        "", "## Disclosure", "",
        "This is a local file review preview with synthetic-capable tooling. "
        "It provides no publication, citation, methodological, ethics or "
        "authorship certification.",
        "",
    ])
    content = "\n".join(lines)
    return {
        "filename_suggestion": "submission-review.md",
        "format": "text/markdown",
        "bytes": len(content.encode("utf-8")),
        "sha256": _sha256(content),
        "content": content,
        "preview_only": True,
        "warnings": status["warnings"],
    }

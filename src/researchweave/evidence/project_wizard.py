"""Validated beginner and advanced project creation with lifecycle guidance."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .errors import EvidenceError, require
from .models import canonical_json, now_utc
from .storage import ProjectStore

ALLOWED_MODES = {"beginner", "advanced"}
ALLOWED_DESIGNS = {
    "exploratory",
    "observational",
    "experimental",
    "systematic_review",
    "qualitative",
    "mixed_methods",
    "secondary_analysis",
}
ALLOWED_STAGES = {
    "planning",
    "protocol",
    "discovery",
    "screening",
    "extraction",
    "synthesis",
    "writing",
}


def preview_project(
    *,
    title: str,
    question: str,
    design: str,
    mode: str = "beginner",
    locale: str = "en",
    privacy: str = "private",
    stage: str = "planning",
    description: str = "",
    tags: list[str] | None = None,
    advanced: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate creation inputs and return non-mutating setup guidance."""
    require(bool(title.strip()) and len(title.strip()) <= 300, "Project title is required")
    require(
        bool(question.strip()) and len(question.strip()) <= 5000,
        "Research question is required",
    )
    require(design in ALLOWED_DESIGNS, "Unsupported research design")
    require(mode in ALLOWED_MODES, "Project mode must be beginner or advanced")
    require(
        2 <= len(locale) <= 20 and all(char.isalnum() or char in "-_" for char in locale),
        "Invalid project locale",
    )
    require(privacy in {"private", "public"}, "Project privacy must be private or public")
    require(stage in ALLOWED_STAGES, "Unknown project lifecycle stage")
    require(len(description) <= 10_000, "Project description is too long", "RESOURCE_LIMIT")
    normalized_tags = sorted({tag.strip().casefold() for tag in (tags or []) if tag.strip()})
    require(len(normalized_tags) <= 50, "Project has too many tags", "RESOURCE_LIMIT")
    require(all(len(tag) <= 80 for tag in normalized_tags), "Project tag is too long")
    advanced_data = dict(advanced or {})
    require(len(advanced_data) <= 50, "Advanced project metadata is too large", "RESOURCE_LIMIT")
    permitted_advanced = {
        "registry_id",
        "institution",
        "team",
        "target_venue",
        "review_type",
        "planned_completion",
        "data_classification",
        "notes",
    }
    require(
        set(advanced_data).issubset(permitted_advanced),
        "Advanced metadata contains unsupported fields",
    )
    if mode == "beginner":
        require(
            not advanced_data,
            "Beginner mode does not accept advanced metadata",
        )
    guidance: list[str] = []
    if stage == "planning":
        guidance.append("Refine the research question before collecting or screening evidence.")
        guidance.append("Record a protocol before confirmatory analysis when applicable.")
    if design == "systematic_review":
        guidance.extend(
            [
                "Define eligibility criteria before screening.",
                "Record every search run and duplicate-removal decision.",
                "Keep report identities separate from underlying study identities.",
            ]
        )
    elif design == "experimental":
        guidance.extend(
            [
                "Record allocation, outcomes, exclusions, and analysis plans before analysis.",
                "Amend protocols append-only with rationale and timestamp.",
            ]
        )
    elif design == "observational":
        guidance.extend(
            [
                "Record population, exposure, comparison, outcome, and confounding assumptions.",
                "Do not interpret association as causation without a defensible design.",
            ]
        )
    elif design == "qualitative":
        guidance.append("Record sampling, context, coding approach, reflexivity, and audit trail.")
    else:
        guidance.append("Record methodology and evidence provenance before drawing conclusions.")
    warnings = []
    if privacy == "public":
        warnings.append(
            "Public classification does not itself publish data; review confidential content "
            "before any export or sharing action."
        )
    return {
        "valid": True,
        "writes": 0,
        "metadata": {
            "title": title.strip(),
            "question": question.strip(),
            "design": design,
            "mode": mode,
            "locale": locale,
            "privacy": privacy,
            "stage": stage,
            "description": description.strip(),
            "tags": normalized_tags,
            "advanced": advanced_data,
        },
        "guidance": guidance,
        "warnings": warnings,
        "hypotheses_generated": 0,
        "network_queries": 0,
    }


def create_project(
    destination: Path,
    *,
    title: str,
    question: str,
    design: str,
    mode: str = "beginner",
    locale: str = "en",
    privacy: str = "private",
    stage: str = "planning",
    description: str = "",
    tags: list[str] | None = None,
    advanced: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a project atomically after validating the complete wizard payload."""
    preview = preview_project(
        title=title,
        question=question,
        design=design,
        mode=mode,
        locale=locale,
        privacy=privacy,
        stage=stage,
        description=description,
        tags=tags,
        advanced=advanced,
    )
    destination = destination.absolute()
    require(destination.parent.is_dir(), "Project parent directory must exist")
    require(not destination.exists(), "Project destination already exists", "CONFLICT")
    staging_parent = Path(
        tempfile.mkdtemp(prefix=".rw-project-", dir=destination.parent)
    )
    staging_project = staging_parent / "project"
    try:
        with ProjectStore.create(
            staging_project,
            preview["metadata"]["title"],
            preview["metadata"]["question"],
            preview["metadata"]["design"],
            preview["metadata"]["locale"],
            preview["metadata"]["privacy"],
        ) as store:
            metadata = preview["metadata"]

            def persist(conn: Any) -> None:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS project_profile ("
                    "singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
                    "mode TEXT NOT NULL, stage TEXT NOT NULL, description TEXT NOT NULL, "
                    "tags_json TEXT NOT NULL, advanced_json TEXT NOT NULL, "
                    "created_at TEXT NOT NULL)"
                )
                conn.execute(
                    "INSERT INTO project_profile VALUES (1,?,?,?,?,?,?)",
                    (
                        metadata["mode"],
                        metadata["stage"],
                        metadata["description"],
                        canonical_json(metadata["tags"]),
                        canonical_json(metadata["advanced"]),
                        now_utc(),
                    ),
                )

            _, revision = store.mutate(
                "project.wizard_profile",
                {
                    "mode": metadata["mode"],
                    "stage": metadata["stage"],
                    "tags": metadata["tags"],
                    "advanced_fields": sorted(metadata["advanced"]),
                    "hypotheses_generated": 0,
                },
                persist,
                expected_revision=0,
            )
            project_id = store.info().id
            require(store.audit()["ok"], "New project failed integrity audit", "INTEGRITY_FAILURE")
        require(not destination.exists(), "Project destination appeared", "CONFLICT")
        os.replace(staging_project, destination)
        return {
            "project_id": project_id,
            "revision": revision,
            "path": str(destination),
            "privacy": preview["metadata"]["privacy"],
            "mode": preview["metadata"]["mode"],
            "stage": preview["metadata"]["stage"],
            "guidance": preview["guidance"],
            "hypotheses_generated": 0,
        }
    except BaseException:
        if destination.exists():
            raise
        raise
    finally:
        if staging_parent.exists():
            shutil.rmtree(staging_parent)


def project_profile(store: ProjectStore) -> dict[str, Any]:
    """Read wizard metadata from a project created with this service."""
    table = store.conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_profile'"
    ).fetchone()
    if table is None:
        return {
            "mode": "legacy",
            "stage": "unknown",
            "description": "",
            "tags": [],
            "advanced": {},
            "profile_available": False,
        }
    row = store.conn.execute("SELECT * FROM project_profile WHERE singleton=1").fetchone()
    if row is None:
        raise EvidenceError(
            "INTEGRITY_FAILURE",
            "Project profile table exists without its singleton row",
            "Restore a verified backup or repair the project profile explicitly.",
        )
    import json

    return {
        "mode": row["mode"],
        "stage": row["stage"],
        "description": row["description"],
        "tags": json.loads(row["tags_json"]),
        "advanced": json.loads(row["advanced_json"]),
        "created_at": row["created_at"],
        "profile_available": True,
    }

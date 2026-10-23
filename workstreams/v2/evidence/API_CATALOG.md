# Evidence API catalog

The public factory is `researchweave.evidence.build_evidence_facade`. Example:

```python
import base64
from pathlib import Path
from researchweave.evidence import build_evidence_facade

facade = build_evidence_facade(Path("./my-local-workspace"), allow_local_writes=True)
created = facade.execute(
    "project.create",
    {"title": "Memory project", "question": "How does recall vary?",
     "design": "exploratory", "privacy": "private"}, {}
)
project_id = created["data"]["project_id"]
source = facade.execute("library.import", {
    "project_id": project_id, "title": "Synthetic source",
    "media_type": "text/plain",
    "data_base64": base64.b64encode(b"Synthetic observation.").decode()
}, {})
print(facade.execute("project.integrity", {"project_id": project_id}, {}))
```

The available operation count is `len(facade.capability_manifest())`; never rely on the historical count above. The manifest is dynamically built from the registered facade commands. Call `facade.capability_manifest()` to inspect the exact command names, effects and declared required fields in the tested branch. Mutating requests support `expected_revision` in context for stale-state detection. The `project.restore` command extracts to the archive's original project UUID and refuses to overwrite an existing project. Verification and previews are read-only.

### Additional implemented operation families (2026-10-23)

`project.*` handles encrypted archives, recovery snapshots, artifact bundles,
selective clones, integrity and verified event timeline. `library.*` handles
structured local collections, tags, incremental full-text index synchronization,
page-level extraction, evidence preservation and read-only diagnostics.
`reference.*` covers reversible metadata aliases, explicit observation history,
opt-in provider identity matching, update monitoring, and human-confirmed
source-anchored citation graph edges with GraphML export. Provider identity
lookups require `allow_remote_queries=True` **and an injected approved HTTPS
transport**. Network requests never run by default.

`review.*` handles independent screening, adjudication, extraction,
versioned forms, bias appraisal, findings, gaps, narrative synthesis, PRISMA
accounting/CSV/Markdown/Mermaid export, and shareable packets.
`writing.*` handles revisioned manuscript sections, deterministic bibliography,
claim checks and guarded submission packet previews. `migration.*` provides
Markdown, user-owned Zotero CSL-JSON and Obsidian vault preview, import, receipt,
loss accounting, undo and export. Supported operations are subject to the
acceptance gaps identified in `ACCEPTANCE_MATRIX.md`.

Every response uses the common fields `request_id`, `status`, `data`,
`artifacts`, `warnings`, `error`, `provenance`, `impact`. Host-permission controls
are required for writes; external-network operations are fail-closed offline.
The generated manifest's JSON Schemas still lack complete typed property and
cross-field validation and must be enriched before final public UI integration.

Contract update: all 104 operations now declare JSON Schema 2020-12
argument types and bounds for required/known optional fields, shared standard
response envelopes, sensitivity markers and effect-specific risks. The
`contracts.py` checks execute before command side effects. Deep nested
validation and command-specific result payload schemas remain partial.

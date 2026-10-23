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

The facade reports 30 named operations in `capability_manifest()`. Refer to `capabilities.v1.json` for machine-readable declarations. All are offline; GUI bindings require final integration. Mutating requests support `expected_revision` in context for stale-state detection. API command `project.restore` accepts a fresh `destination_id` to avoid overwriting any existing project. Verification and previews are read-only.

Unsupported: encrypted archive, live discovery, PDF/OCR, external proprietary migrations, FTS5 ranking, complete PRISMA source retrieval, journal submission, export-to-DOCX/PDF, full permissions/undo engine. No operation for these is advertised.

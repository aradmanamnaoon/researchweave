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

The facade reports 38 named operations in `capability_manifest()`. Refer to `capabilities.v1.json` for machine-readable declarations. All are offline; GUI bindings require final integration. Mutating requests support `expected_revision` in context for stale-state detection. The `project.restore` command extracts to the archive's original project UUID and refuses to overwrite an existing project. Verification and previews are read-only. Indexed search operations are `library.index_rebuild`, `library.index_health`, and `library.fts_search`; typed extraction operations are `review.extract` and `review.evidence_matrix`. Markdown import/export interop uses `migration.markdown_preview`, `migration.markdown_import` and `migration.markdown_undo`.

Unsupported: encrypted archive, live discovery, PDF/OCR, proprietary direct app access, complete PRISMA retrieval, journal submission, DOCX/PDF export and general undo engine. These operations are not advertised.

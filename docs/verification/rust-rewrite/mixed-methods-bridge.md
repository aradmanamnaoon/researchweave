# §40.57 — Native mixed-methods bridge

The analysis crate still exposes compatibility-level `mixed.joint_display`
(Read) and `mixed.joint_display_sensitive` (SensitiveExport). They are the
low-level computational route and must not be presented as persisted-project
verified because their bounded coding snapshot is caller supplied.

The desktop trusted host now additionally registers
`mixed.persisted_joint_display` (Read) and
`mixed.persisted_joint_display_sensitive` (SensitiveExport). Those operations
never accept coding hashes, case maps, codebooks or excerpts from command
arguments. The host binds an `EvidenceHandler` to the already authenticated
active project, reads `qualitative.mixed_provenance`, injects the trusted
project UUID, reloads the requested immutable dataset revision through
`AnalysisService`, and calls `verified_mixed_joint_display`.

The analysis crate has no dependency on the evidence crate's persisted coding
model. Callers therefore supply an explicit bounded snapshot:

```json
{
  "dataset_id": "<stored dataset ID>",
  "revision": "<immutable revision>",
  "case_column": "case",
  "measure_column": "outcome",
  "code_id": "theme",
  "coding_hash": "<64 lowercase hex SHA-256 of authoritative coding project>",
  "codebook_ids": ["theme"],
  "qualitative_cases": [
    {"case_id": "case-1", "code_ids": ["theme"]}
  ],
  "min_reporting_cases": 3
}
```

Each qualitative case is unique; each code must belong to the supplied
codebook. Every qualitative case must map to exactly one quantitative case.
Each arm must contain at least 3 and at most the configured minimum of 50
reporting cases to prevent disclosure. Unmapped, duplicate, non-finite or
non-numeric values fail closed. Missing outcomes are excluded from group
aggregates. The output explicitly disclaims causal interpretation.

If either selected variable is private, the caller must route through the
SensitiveExport operation with `include_private=true`. Quotes additionally
require `allow_quotes=true`, `include_private=true`, bounded excerpts with
source hashes and matching code IDs. The ordinary Read route rejects those
flags and any excerpt payload. The router must enforce approval for
SensitiveExport before dispatch.

**Intentional difference from Python:** The analysis crate remains independent
of evidence persistence; authentication and provenance composition live at the
trusted host boundary rather than inside the numerical kernel. Supplying a
syntactically valid coding hash alone still proves nothing. The desktop route
obtains and verifies the persisted snapshot itself, while the low-level legacy
route is retained only for compatibility and is not used by the Mixed Methods
workspace.

Focused analysis tests cover descriptive aggregates, threshold suppression,
duplicate case rejection, code existence, invalid provenance format and
sensitive flag denial. The desktop integration test additionally constructs
the persisted source/code/transcript/annotation chain, imports the six-case
immutable dataset, obtains the evidence snapshot through the trusted host and
reproduces the Python golden (coded mean 2, not-coded mean 5). It rejects an
injected `coding_hash`, and the sensitive operation still fails without router
approval. The full desktop suite passes 25/25 after this integration. Broad
Windows UIA also verifies that transcript-case controls are reachable and that
the Mixed Methods action goes through the trusted persisted-provenance route.

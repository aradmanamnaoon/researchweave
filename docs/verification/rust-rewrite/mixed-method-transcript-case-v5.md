# §40.57 — persisted transcript-to-case mapping (schema v5)

The project schema now has `qualitative_transcripts` with a primary key
referencing `document_text.source_id`, explicit bounded nonempty `case_id`,
boolean `confidential`, the verified extracted text `body_hash`, and
`recorded_at`. Multiple source transcripts **may** name the same case;
one source cannot be registered twice. A v4→v5 migration takes a verified
SQLite backup, installs this table without modifying existing highlights,
and leaves it empty. No source-to-case relationship is inferred.

Project-scoped LocalWrite capabilities `qualitative.transcript_register`
and `qualitative.transcript_update` require
`expected_content_hash`, `expected_body_hash`, source ID, explicit case ID
and confidentiality. They verify the existing document's exact SHA-256
before using the existing project revision/event/CAS/replay/approval
mutation pipeline. Event payloads contain hashes rather than transcript
text, source IDs or case IDs; persisted mapping itself is private project
metadata. `qualitative.transcripts` is a read-only metadata view.

The authoritative qualitative `state` and canonical `content_hash` now
include ordered transcript records, in addition to codes and annotations.
Read-only `qualitative.mixed_provenance` independently checks transcript
document hashes and every existing annotation's code, Unicode span and
quotation against persisted extracted text. It emits a no-quote case-code
snapshot with **all registered cases, including uncoded ones**, plus
`case_counts` (coding occurrences, not independent sampling units).
Multiple transcripts with a shared case accumulate occurrences.
`case_mapping_available=false` and an empty mapped-case snapshot prevent
legacy annotations lacking explicit transcript mapping from silently
entering quantitative reports.

The analysis crate exposes
`joint_display_with_verified_host_snapshot(dataset, options, persisted, sensitive)`
as a host-composition helper: caller options may contain case/outcome
columns and the project identifier, **not caller-provided case maps or
coding hashes**. It derives those solely from a separately supplied trusted
persisted evidence snapshot, checks that the projects match, then executes
the existing immutable-dataset revision/identity, mapping, aggregation
and privacy-threshold checks. Non-sensitive reporting still requires at
least three cases per displayed arm; sensitive export must remain routed
through the existing CommandRouter approval.

**Trusted host integration:** The desktop router now performs this composition.
For the authenticated active project it binds an `EvidenceHandler` to the
canonical project directory, reads `qualitative.mixed_provenance` internally,
injects the trusted project UUID and invokes the analysis service's
`verified_mixed_joint_display` against the requested immutable dataset
revision. Command arguments for `mixed.persisted_joint_display` cannot contain
coding hashes, codebooks, case maps or excerpts; unknown provenance fields fail
closed. The sensitive sibling retains the router's one-use approval boundary.
The legacy low-level `mixed.joint_display` remains for compatibility and is
not wired to the desktop Mixed Methods workspace.

Local regression tests exercise verified v4 migration backups with no
fabricated mapping, six-case/duplicate-transcript aggregation, restart
stability, stale hashes/replay, event privacy and rejected forged
host-helper maps or mismatched project/quantitative cases. A desktop-host
integration test constructs the full persisted source/code/mapping/annotation
chain and immutable dataset, then verifies the composed result and approval
boundary. Windows UIA verifies the new mapping controls and trusted-route
invocation; a populated successful joint-display UIA run remains useful future
coverage rather than a prerequisite for the tested host composition claim.

The verified host helper's golden reproduces Python
`tests/v2/analysis/test_mixed_methods.py`: quantitative case IDs and scores
1–6, `theme` and `context` annotations for the first three cases,
six total annotation occurrences, coded mean 2 and uncoded mean 5.
The transcript-6→`unknown` remapping is incompatible with the persisted
dataset cases and fails the mapping check. A four-case disclosure threshold,
private score without sensitive approval, and non-sensitive direct quote
requests are rejected. The separate evidence fixture also checks aggregation
when two transcripts share a case.

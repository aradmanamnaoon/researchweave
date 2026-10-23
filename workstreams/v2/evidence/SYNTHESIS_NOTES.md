# Evidence synthesis and publishing — worker-2

Source root: `src/researchweave/evidence` on `rebuild/v2-evidence`.
These modules remain uncommitted for prime integration.

## API contract for facade

- `SynthesisService(store).assess_bias(record_id, template, assessor, responses, expected_revision=None)`: RE-031, audited append-only appraisal; templates `randomized-v1`, `observational-v1`. Every domain requires a manual judgment and explanation. Never generates clinical decisions or automatic risk classifications.
- `SynthesisService(store).add_finding(Finding(...), expected_revision=None)`: RE-034; requires active source with verified quote anchor; `compare(question)` groups strictly by population/outcome/measure/unit/timepoint, reports directional disagreement only as a potential conflict.
- `register_gap(question, searches, limitations, expected_revision=None)` and `gaps()`: RE-035; each search documents database, date, strategy; explicit absence caveat.
- `compose(title, sections, save=True, expected_revision=None)` and `outline(id)`: RE-036; section shape `{heading,narrative,finding_ids}`; validated evidence links and warnings for uncited interpretation.
- `PublishingService(store).bibliography(manuscript_id, style="plain")`: RE-038; deterministic plain or numbered formatting, explicitly not complete CSL.
- `check_manuscript(manuscript_id, required_sections=(...))`: RE-039; checks missing/empty sections, placeholders, unverified reference metadata, citation mappings. A clean structural check does not certify scientific claims.
- `submission_packet(manuscript_id, journal, allow_incomplete=False)`: RE-040; deterministic in-memory manifest, Markdown and bibliography with SHA256 hashes; submission is never claimed or performed.

The facade should instantiate these classes with the existing `ProjectStore` and expose namespaced command handlers. No GUI or network requirements. The new tables are lazily created with `CREATE TABLE IF NOT EXISTS`; the project revision/event is committed through `ProjectStore.mutate` for writes.

## Constraints and next steps

Plain and numbered bibliography are deliberately limited styles; full CSL requires a verified processor/style registry. Submission checklist must be completed against the target journal. Narrative claims remain explicitly unverified even when their referenced findings have verified source anchors. Appraisals are aids for trained human reviewers, with manual qualitative judgments and no medical decision support. Database tables added by the new module need export/restore coverage in project archive migration before describing archive portability as complete.

## Synthetic acceptance tests

`tests/v2/evidence/test_synthesis_publishing.py` covers persistence after project reopen, verified anchor requirement, grouping of incompatible findings, missing evidence caveats, explicit unsupported narrative marking, manual appraisal validation, manuscript warning and packet guard. Fixture strings are self-authored synthetic data with no external licensing requirements.

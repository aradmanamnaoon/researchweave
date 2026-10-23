# UI integration contracts

The UI facade is intentionally offline and provider-neutral. `UIFacade.capability_manifest()` exposes **105** current operations; `capabilities.v1.json` and `API_CATALOG.md` are generated from that live manifest.

## Scientific analysis

External scientific methods implement the typed `AnalysisBackend` protocol in `workflows.py`. Results must include method/version/configuration, input provenance, assumptions, exclusions/missing-data handling, outputs, uncertainty/diagnostics and reproducibility metadata. Missing methods must return unavailable/dependency state, never synthetic inference.

## Notebook execution

`ui.code.execution.status` remains disabled until the host provides: separate process boundary; explicit user confirmation; time and memory/resource limits; cooperative cancellation; bounded working directory; stdout/stderr capture; provenance; `shell=True` disabled; no `eval`; no untrusted pickle.

## AI/provider execution

The UI owns proposal, scope fingerprint, approval/denial and timeline state. A provider adapter may execute only after validating the exact approval fingerprint and must record provider/model/input/output/timestamps/approval/idempotency. Network destination and egress scope must be explicit. Credentials must stay outside project/audit/log content.

## Integrations and sync

Optional external adapters remain disconnected by default. Connection/revoke/status must reflect real provider state. Sync must preview changes/conflicts, require explicit upload/overwrite review, preserve local usability offline and never silently send project data.

## Authentication

Local reviewer aliases are not authenticated identities. Any real multiuser reviewer integration must supply authenticated session identity without weakening the existing peer-vote masking/adjudication invariants.

## Native validation

Integration/release owners must perform native screen-reader, keyboard, DPI/multi-monitor and forced-crash validation before claiming those platform behaviors.

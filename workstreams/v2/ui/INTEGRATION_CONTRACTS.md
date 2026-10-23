# UI integration contracts

The UI facade is offline and provider-neutral. `UIFacade.capability_manifest()` exposes **115** current operations; `capabilities.v1.json` and `API_CATALOG.md` are generated from the live manifest at source commit `80ec481`.

## Scientific analysis

External scientific methods implement the typed `AnalysisBackend` protocol in `workflows.py`. Results must preserve method/version/configuration, input provenance, assumptions, exclusions/missing-data handling, outputs, uncertainty/diagnostics and reproducibility metadata. Unsupported methods remain unavailable rather than simulated.

## Notebook execution

`ui.code.execution.status` remains disabled until a host provides a separate process boundary, explicit user confirmation, time/memory/resource limits, cancellation, bounded working directory, stdout/stderr capture, provenance, no arbitrary `shell=True`, no `eval`, and no untrusted pickle.

## AI/provider execution

The UI owns proposal scope, fingerprint, exact approval/denial and timeline state. A provider adapter may execute only after validating the exact approved fingerprint and must record provider/model/input/output/timestamps/approval/idempotency. Network destination and data-egress scope must be explicit. Credentials must remain outside project/audit/log content.

## Notifications and retry

Persistent notifications may carry `retry_operation`/`retry_arguments`, but `ui.notification.retry` executes only a hardcoded allowlist of local read-only operations. Retry injects the current project ID, records zero network hosts/local writes in its response, and rejects write/unknown operations with `PERMISSION_DENIED`.

## Integrations and sync

Optional external adapters remain disconnected by default. Connection/revoke/status must reflect real provider state. Sync must preview changes/conflicts, require explicit upload/overwrite review, preserve offline local usability and never silently send project data.

## Authentication

Local reviewer aliases are not authenticated identities. Any multiuser reviewer integration must supply authenticated session identity without weakening peer-vote masking/adjudication invariants.

## Native validation

Release/integration owners must perform native screen-reader, keyboard/focus, DPI/multi-monitor and multi-OS validation before claiming those platform behaviors.

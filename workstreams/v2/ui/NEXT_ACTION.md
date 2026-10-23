# Next actions after Worker 4

All independently feasible local UI work identified in the Worker 4 acceptance matrix is implemented and validated. Remaining work requires integration infrastructure or native platform observation rather than more local scaffolding:

1. Supply a production scientific `AnalysisBackend` for regression/correlation/group-comparison methods and domain diagnostics. Descriptive analysis is already real; unsupported inferential methods remain `DEPENDENCY_MISSING`.
2. Supply a safe isolated notebook runtime only if it provides process isolation, explicit confirmation, time/resource limits, cancellation, bounded working directory, stdout/stderr capture and provenance.
3. Integrate real AI/provider and optional external adapters with explicit egress approval, external credential handling, truthful availability, rate-limit/error behavior and no consumer-subscription impersonation.
4. Add optional remote sync/conflict resolution. Local backups already provide preview, integrity verification, attack-resistant archive handling and restore-to-new-project behavior.
5. Supply a durable external job runner if background tasks must survive process restart; process-local callbacks are intentionally not serialized.
6. Perform native release QA: NVDA/VoiceOver/Orca, real keyboard/focus behavior, Windows/Linux/macOS rendering, multi-monitor geometry and 100/150/200% native DPI.
7. Connect real upstream source/search/registry events if PRISMA/protocol state must be derived beyond the local screening/deviation records already supported.

Do not push or merge from this worker worktree. Integration should review the current 50-story matrix and these explicit blockers before fast-forwarding the final integration branch.

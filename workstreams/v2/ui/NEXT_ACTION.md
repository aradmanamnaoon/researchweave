# Next actions after Worker 4

All independently feasible local UI work in this branch is implemented and validated. Remaining work depends on integration or native-platform validation rather than more local scaffolding:

1. Connect a production scientific analysis backend to the typed `AnalysisBackend` interface for regression/correlation/group-comparison methods and domain diagnostics. Descriptive analysis already runs locally; unavailable inferential methods correctly return `DEPENDENCY_MISSING`.
2. Integrate an isolated notebook execution host only if it provides process boundaries, explicit confirmation, time/resource limits, cancellation, bounded working directory, stdout/stderr capture and provenance. The current UI intentionally disables arbitrary Python/R execution.
3. Add real provider/integration hosts for AI or external services with explicit egress approval, credentials outside logs/state, rate-limit/error handling and truthful availability. Current provider/agent screens do not execute network calls.
4. Add optional remote sync/conflict handling; current backups are local, approval-gated, checksum verified and restore into a new project.
5. Run native accessibility/platform QA: NVDA/VoiceOver/Orca, real Windows/Linux/macOS keyboard/focus, multi-monitor/HiDPI at 100/150/200%, and forced-process crash recovery.
6. Deepen professional PDF text-anchor/search/highlight/page-citation integration and structured manuscript/evidence cross-navigation.
7. If desired, add durable external job-runner persistence, typed activity target links, unified SVG/PNG file export, and fuller protocol/PRISMA upstream event integrations.

Do not push or merge from this worker worktree. The integration owner should review the conservative UX matrix and external blockers before fast-forwarding the final integration branch.

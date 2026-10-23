# Current limitations

The local ResearchWeave V2 UI implements every independently feasible Worker 4 behavior found during the final partial-story audit. Remaining `partial` stories in the acceptance matrix are intentionally bounded by external services or native-platform validation.

- **Scientific inference:** descriptive statistics are real. No production regression/correlation/group-comparison backend is bundled; unsupported inferential methods return `DEPENDENCY_MISSING` rather than fabricated statistics.
- **Notebook execution:** disabled because a conforming isolated Python/R runtime is unavailable. No `eval`, arbitrary `shell=True`, in-process untrusted interpreter or untrusted pickle path exists.
- **AI/providers/integrations:** provider configuration, scoped proposals, exact approvals/denials and timeline state are local. No live model/provider/network execution or consumer-subscription access is claimed.
- **Review identity:** screening aliases remain local convenience labels, not authenticated identities.
- **PRISMA/protocol upstream derivation:** screening events, explicit PRISMA fields, protocol amendments/deviations and structured exports are local and durable. Full upstream search/dedup/retrieval/registry event derivation needs real external source systems.
- **Sync:** backup/restore is local and integrity checked; no remote sync backend is bundled.
- **Jobs:** progress/cancel/retry/stale-result suppression works process-locally and Dashboard exposes retained state. Durable cross-restart jobs require an external job runner because callbacks cannot be safely serialized.
- **PDF:** local rendering, SHA integrity, page navigation, QtPdf text-layer search/highlighting and page/hash references work. OCR is not attempted and arbitrary text-selection coordinates are not claimed when QtPdf cannot verify them reliably.
- **Accessibility/platform:** automated accessible names, contrast, chart alternatives, scaling and offscreen screenshots pass. NVDA/VoiceOver/Orca, native multi-OS/HiDPI/multi-monitor and full native keyboard/focus behavior remain unobserved.
- **Crash recovery:** an actual child process now writes a journal and exits via `os._exit(17)`; reopening verifies the exact draft. This validates application journal survival, not a general OS crash-dump guarantee.

Measured source size is **11,053 meaningful production SLOC** across **24 Python modules**. The facade registers **115 operations**. Final UI coverage is **81%** with **141 UI tests passed** and **145 repository-wide tests passed**.

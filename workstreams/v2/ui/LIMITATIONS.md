# Current limitations

The local ResearchWeave V2 UI now implements all independently feasible Worker 4 behavior, but several requirements remain intentionally **partial** because they depend on external backends or native validation.

- **Scientific inference:** descriptive statistics are real. No production regression/correlation/group-comparison backend is bundled; the typed adapter returns `DEPENDENCY_MISSING` rather than fabricating inference. The Journey 2 regression backend is deterministic test-only data and is explicitly labeled non-scientific.
- **Notebook execution:** disabled because a safe subprocess/container host is unavailable. No `eval`, arbitrary `shell=True`, in-process untrusted interpreter or untrusted pickle path exists.
- **AI/providers/integrations:** provider configuration, scoped proposals, approvals, denial and timeline state are local. No model/provider/network execution, consumer-subscription access, or fake availability is claimed.
- **Review identity:** screening aliases are local convenience labels, not authenticated identities.
- **PRISMA:** screening stages are event-derived; upstream search/dedup/retrieval counts require real source-system events and remain unknown unless explicitly entered.
- **Sync:** backup/restore is local and integrity checked; no remote sync backend is bundled.
- **Jobs:** progress/cancel/retry/stale-result protection works within the process. Durable restart recovery requires an external job runner because arbitrary callbacks cannot be safely serialized.
- **PDF/manuscript:** local PDF integrity/navigation works, but professional text-coordinate search/highlight/page anchors and fully structured manuscript/evidence cross-navigation remain partial.
- **Accessibility/platform:** automated names, contrast, chart alternatives, scaling and offscreen screenshot tests pass, but NVDA/VoiceOver/Orca and native multi-OS/HiDPI/multi-monitor behavior have not been observed.
- **Keyboard:** deterministic command routing is tested; a long Windows Qt offscreen QTest key-event sequence crashes, so native end-to-end keyboard success is not claimed.
- **Crash recovery:** 250 ms journals, hash verification and revision-conflict restore are tested; no separate-process forced-kill acceptance test was run.

Measured source size is **9,968 meaningful production SLOC** across **24 Python modules** using the documented AST/tokenize method; 105 facade operations are registered. Final UI coverage is **82%** with **133 UI tests passed**. These metrics do not remove the native/external limitations above.

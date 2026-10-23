# UI facade API catalog

Generated from `UIFacade.capability_manifest()` at the current branch state. Registered operations: **105**.

| Operation | Effect | Approval | Summary |
| --- | --- | --- | --- |
| `ui.project.list` | `read` | no | Show saved projects |
| `ui.project.create` | `local-write` | no | Create a local research project |
| `ui.project.open` | `read` | no | Reopen a saved project |
| `ui.project.update` | `local-write` | no | Update research question |
| `ui.project.dashboard` | `read` | no | Summarize current project state |
| `ui.question.read` | `read` | no | Read structured research question |
| `ui.question.update` | `local-write` | no | Update structured research question |
| `ui.templates.list` | `read` | no | List editable study designs |
| `ui.guidance.search` | `read` | no | Find research method explanations |
| `ui.protocol.read` | `read` | no | Read project research protocol |
| `ui.protocol.start` | `local-write` | no | Create an editable protocol draft |
| `ui.protocol.update` | `local-write` | no | Revise draft protocol fields |
| `ui.protocol.complete` | `read` | no | Validate protocol for human review |
| `ui.protocol.history` | `read` | no | Read protocol amendment history |
| `ui.source.add` | `local-write` | no | Import a local text source |
| `ui.source.search` | `read` | no | Search project library |
| `ui.source.get` | `read` | no | Read a local source |
| `ui.search.global` | `read` | no | Search all local research objects |
| `ui.evidence.capture` | `local-write` | no | Save source-anchored passage |
| `ui.evidence.list` | `read` | no | List project source excerpts |
| `ui.evidence.inspect` | `read` | no | Check anchored quotation integrity |
| `ui.claim.create` | `local-write` | no | Create draft with evidence references |
| `ui.claim.list` | `read` | no | List claims with provenance warnings |
| `ui.claim.inspect` | `read` | no | Check supporting and conflicting evidence |
| `ui.claim.reference` | `read` | no | Generate unverified citation placeholder |
| `ui.project.audit` | `read` | no | Audit local project structural integrity |
| `ui.recovery.save` | `local-write` | no | Journal unsaved editor text locally |
| `ui.recovery.inspect` | `read` | no | Inspect unsaved editor recovery |
| `ui.recovery.list` | `read` | no | List available local recovery drafts |
| `ui.recovery.discard` | `local-write` | no | Discard exact reviewed recovery draft |
| `ui.release.preview` | `read` | no | Inspect human review gates for a manuscript |
| `ui.release.markdown` | `read` | no | Generate local submission review Markdown |
| `ui.review.vote` | `local-write` | no | Save screening decision |
| `ui.review.counts` | `read` | no | Compute screening counts |
| `ui.review.queue` | `read` | no | List source screening decisions and reasons |
| `ui.screening.vote` | `local-write` | no | Record independent reviewer decision |
| `ui.screening.queue` | `read` | no | Inspect reviewer-blinded screening records |
| `ui.screening.adjudicate` | `local-write` | no | Resolve independent reviewer disagreement |
| `ui.screening.flow` | `read` | no | Calculate recorded screening stage counts |
| `ui.prisma.read` | `read` | no | Read grounded PRISMA flow state |
| `ui.prisma.update` | `local-write` | no | Save explicit PRISMA flow events |
| `ui.extraction.schema` | `read` | no | Read extraction form schema |
| `ui.extraction.schema.update` | `local-write` | no | Version extraction form schema |
| `ui.extraction.record.save` | `local-write` | no | Save validated extraction record |
| `ui.extraction.list` | `read` | no | List extraction records |
| `ui.extraction.export` | `read` | no | Export structured extraction records |
| `ui.qual.annotate` | `local-write` | no | Add a Unicode-safe evidence code |
| `ui.qual.list` | `read` | no | Inspect coded evidence |
| `ui.dataset.import` | `local-write` | no | Import bounded CSV text |
| `ui.dataset.describe` | `read` | no | Summarize numeric values |
| `ui.dataset.list` | `read` | no | Show project data tables |
| `ui.dataset.page` | `read` | no | Read bounded dataset page |
| `ui.dataset.variables` | `read` | no | Inspect column types and missingness |
| `ui.variable.metadata` | `read` | no | Read variable metadata |
| `ui.variable.metadata.update` | `local-write` | no | Save variable metadata |
| `ui.chart.histogram` | `read` | no | Compute descriptive histogram counts |
| `ui.chart.bar` | `read` | no | Compute descriptive categorical counts |
| `ui.chart.svg` | `read` | no | Produce local accessible chart SVG |
| `ui.chart.png` | `read` | no | Produce local descriptive chart PNG |
| `ui.analysis.methods` | `read` | no | List scientific analysis adapter methods |
| `ui.analysis.run` | `local-write` | no | Run and persist a typed scientific analysis |
| `ui.analysis.results` | `read` | no | List versioned analysis results |
| `ui.analysis.export` | `read` | no | Export one analysis result |
| `ui.codebook.list` | `read` | no | List qualitative codebook |
| `ui.codebook.upsert` | `local-write` | no | Create or edit qualitative code |
| `ui.codebook.merge` | `local-write` | no | Merge codes with recoding trace |
| `ui.mixed.list` | `read` | no | List mixed-method evidence links |
| `ui.mixed.add` | `local-write` | no | Link qualitative and quantitative evidence |
| `ui.manuscript.save` | `local-write` | no | Save a manuscript draft |
| `ui.notebook.save` | `local-write` | no | Save local research notes |
| `ui.code.execution.status` | `read` | no | Inspect disabled code execution safety gate |
| `ui.reference.list` | `read` | no | List manuscript references |
| `ui.reference.upsert` | `local-write` | no | Create or correct reference metadata |
| `ui.reference.citation` | `read` | no | Format user-entered citation metadata |
| `ui.tutorial.step` | `local-write` | no | Mark local tutorial step |
| `ui.tutorial.status` | `read` | no | Read tutorial completion state |
| `ui.activity.list` | `read` | no | Read local audit history |
| `ui.preferences.read` | `read` | no | Read desktop preferences |
| `ui.preferences.update` | `local-write` | no | Save validated preferences |
| `ui.localization.read` | `read` | no | Read locale fallback and layout direction |
| `ui.workspace.preset.list` | `read` | no | List validated workspace presets |
| `ui.workspace.preset.save` | `local-write` | no | Save validated workspace preset |
| `ui.workspace.preset.delete` | `local-write` | no | Delete local workspace preset |
| `ui.export.preview` | `read` | no | Preview an offline export |
| `ui.export.write` | `local-write` | yes | Write approved export under host root |
| `ui.backup.plan` | `read` | no | Preview project snapshot |
| `ui.backup.list` | `read` | no | List local integrity-checked snapshots |
| `ui.backup.inspect` | `read` | no | Verify archive before restoring |
| `ui.backup.create` | `local-write` | yes | Create approved immutable backup |
| `ui.backup.restore` | `local-write` | yes | Restore approved backup to new project |
| `ui.agent.propose` | `read` | no | Preview untrusted agent proposal |
| `ui.agent.deny` | `read` | no | Reject untrusted proposed action |
| `ui.agent.action.propose` | `local-write` | no | Persist exact agent action proposal |
| `ui.agent.action.approve` | `local-write` | yes | Approve exact agent action fingerprint |
| `ui.agent.action.deny` | `local-write` | no | Deny exact agent action proposal |
| `ui.agent.action.record` | `local-write` | no | Record approved agent execution state |
| `ui.agent.timeline` | `read` | no | Read persistent agent action timeline |
| `ui.provider.read` | `read` | no | Read provider mode and availability state |
| `ui.provider.update` | `local-write` | no | Configure provider metadata without secrets |
| `ui.privacy.read` | `read` | no | Inspect local privacy and egress state |
| `ui.integration.list` | `read` | no | List optional integration adapter states |
| `ui.integration.disconnect` | `local-write` | no | Keep optional integration disconnected |
| `ui.notification.list` | `read` | no | List persistent actionable notifications |
| `ui.notification.add` | `local-write` | no | Persist redacted actionable notification |
| `ui.notification.dismiss` | `local-write` | no | Dismiss persistent notification |

All capabilities are offline-available in this UI workstream. Network/provider execution is not implied by catalog presence; provider and integration records expose configuration/status only unless an external adapter is supplied.

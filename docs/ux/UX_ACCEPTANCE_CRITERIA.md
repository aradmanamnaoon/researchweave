# ResearchWeave UX Acceptance Criteria

These criteria are additive to the Rust rewrite/master release specification. Passing them does not waive scientific parity, security, migration or release requirements.

## A. Reachability and information architecture

- [ ] Every one of the 39 legacy destinations has a documented mapping and remains reachable through visible navigation or the command center.
- [ ] No required capability is available only through a hidden/debug command.
- [ ] Primary global navigation has no more than 6–7 stable activity roots.
- [ ] A user can identify current project, current work object and current major activity at a glance.
- [ ] Back/forward or equivalent recent-context navigation exists for opened work objects.

## B. Project onboarding

- [ ] Default New Project does not require typing an absolute path.
- [ ] Custom path remains available.
- [ ] Open/import/migrate/recovery paths are clearly distinct.
- [ ] Offline project storage, encrypted backup/recovery and privacy are explained; any optional AI provider data egress requires separate explicit consent.
- [ ] Create/open survives close/relaunch and preserves expected metadata.
- [ ] Failure states provide a recovery action or concrete next step.

## C. Keyboard and focus

- [ ] All major actions are reachable without a mouse.
- [ ] Command center is reachable by shortcut and indexes commands/views/settings/resources.
- [ ] F6/Shift+F6 or documented equivalent cycles major workbench regions.
- [ ] Tab order inside each region is logical and no focus trap is accidental.
- [ ] Focus is visibly indicated at sufficient contrast.
- [ ] Closing dialogs/palettes restores focus predictably.
- [ ] Representative off-screen resources can be reached despite Slint ListView UIA limitations.

## D. Screen-reader/accessibility

- [ ] All interactive controls have accessible names and correct roles.
- [ ] Dynamic job/error/completion states use appropriate live announcements without progress spam.
- [ ] Results/plots provide nonvisual summaries/tables.
- [ ] Windows Narrator/UIA representative workflows are tested on the packaged app.
- [ ] macOS VoiceOver and Linux Orca limitations are tested/documented on target OSes before release where infrastructure permits.
- [ ] High-contrast/system contrast behavior is checked.
- [ ] UI remains usable at supported OS scaling levels.

## E. Persian, Unicode and RTL

- [ ] Persian text round-trips through project fields, notes, search and major editors.
- [ ] Real OS Persian IME composition is verified, not inferred from UIA value assignment.
- [ ] RTL caret movement, selection, copy/paste and mixed Persian/English scientific text are verified.
- [ ] LTR/RTL paragraph direction can be controlled in rich text surfaces where needed.
- [ ] Directional icons/layout mirror only when semantically appropriate.

## F. Responsiveness and long-running work

- [ ] Project/backup/restore/PDF/analysis jobs do not freeze the event loop beyond a measured UI threshold.
- [ ] Long-running jobs expose running/succeeded/failed/cancelled state.
- [ ] Cancellation is offered only where backend semantics support safe cancellation.
- [ ] Completed jobs link to resulting artifact/context.
- [ ] Failure details are redacted when provider/security data may be present.

## G. Scientific/reproducibility UX

- [ ] Dataset transforms clearly produce new immutable revisions.
- [ ] Analysis results show source dataset revision and parameters.
- [ ] Exclusions/missing-data policy/assumptions/warnings are visible or one action away.
- [ ] Review/PRISMA counts are derived from persisted workflow state and unresolved accounting is explicit.
- [ ] Evidence/annotation/manuscript links preserve provenance rather than relying on untracked copy/paste where structured linking exists.
- [ ] Export flows identify what is exported and which revision/artifact produced it.

## H. Approval/privacy UX

- [ ] UI effect labels correspond exactly to core effect classification.
- [ ] Operations requiring approval show an exact preview/scope before approval.
- [ ] AI tool proposals are inert until dispatched through the same host authority.
- [ ] Optional remote AI provider requests make network egress explicit.
- [ ] Credentials are never echoed into normal UI, logs, project content or screenshots.

## I. Visual/design-system quality

- [ ] Shared semantic tokens/components replace repeated literal styling in major shell surfaces.
- [ ] Light and dark themes are complete for transformed surfaces.
- [ ] Contrast meets WCAG AA targets for text and essential state/focus indicators.
- [ ] Comfortable and compact density modes remain readable and do not hide controls.
- [ ] Empty/loading/error/success states use consistent components.
- [ ] Reduced-motion setting removes nonessential motion.
- [ ] UI retains a distinct research-workbench identity and avoids generic dashboard/card proliferation.

## J. Layout/resizing

- [ ] Wide, medium and minimum supported window sizes are exercised with no unreachable primary action.
- [ ] Sidebar/inspector/tray collapse predictably.
- [ ] Large virtualized tables/lists remain usable with keyboard and assistive technology fallback.
- [ ] Layout state persists at user/workspace level without contaminating scientific data.

## K. Measured representative tasks

Record before/after measurements in a verification report for at least:

1. Create a default local project.
2. Reopen an existing project.
3. Open an off-screen capability using keyboard only.
4. Add/open a source and create an evidence note/anchor when implemented.
5. Import a dataset and inspect variables/quality.
6. Run/reopen one statistical analysis and inspect provenance.
7. Perform representative review screening/adjudication when native review is implemented.
8. Export and recover a local project archive without overwriting an existing project.
9. Use contextual AI to generate an inert action proposal and approve/reject it through host policy.

For each task record: action count, success/failure, navigation depth, keyboard-only success, observed blocking latency and recovery from one representative error. Time measurements are optional unless collected with a repeatable method.

## L. Regression gate after each transformation stage

- [ ] `cargo fmt --all -- --check` passes.
- [ ] workspace Clippy with `-D warnings` passes.
- [ ] `cargo test --workspace` passes.
- [ ] real Windows debug app launches.
- [ ] Windows packaged candidate installs and launches when packaging-relevant files changed.
- [ ] project create/open persists.
- [ ] PDF smoke remains functional until superseded by stronger reader tests.
- [ ] command center resolves every registered legacy destination.
- [ ] no new secret/plaintext-network leakage is introduced.

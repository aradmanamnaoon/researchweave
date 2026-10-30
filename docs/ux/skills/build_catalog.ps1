# Reproducible generator for repository-local UX skill documentation.
# Run from the worktree: powershell -NoProfile -ExecutionPolicy Bypass
#   -File docs/ux/skills/build_catalog.ps1
# Only writes docs/ux/skills/<slug>/SKILL.md and docs/ux/100_SKILLS_APPLICATION_MATRIX.md.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $here '../../..')).Path
$ux = Join-Path $repo 'docs/ux'
$catalog = Join-Path $here 'catalog.psv'
$baselineSha = '976656d9ea5ce753f9b170383bf5cb65eb9f263d'
$sourceLines = @(& git -C $repo show "${baselineSha}:crates/researchweave-desktop/ui/main.slint")
if ($LASTEXITCODE -ne 0 -or $sourceLines.Count -lt 2000) {
    throw 'Pinned baseline Slint UI source is unavailable; cannot validate evidence'
}
$data = @()
foreach ($line in Get-Content -LiteralPath $catalog -Encoding UTF8) {
    if (-not $line.Trim() -or $line.StartsWith('#')) { continue }
    $parts = @($line.Split('|'))
    if ($parts.Count -ne 9) { throw "Expected 9 columns, got $($parts.Count): $line" }
    $id, $category, $slug, $goal, $probe, $gate, $location, $finding, $next = $parts
    if ($slug -cnotmatch '^[a-z][a-z0-9-]+$') { throw "Unsafe slug $slug" }
    if ($location -notmatch '^main\.slint:(\d+)-(\d+)$') { throw "Invalid source evidence $location" }
    $start = [int]$Matches[1]
    $end = [int]$Matches[2]
    if ($start -lt 1 -or $start -gt $end -or $end -gt $sourceLines.Count) {
        throw "Source evidence out of bounds for $slug : $location"
    }
    $data += [pscustomobject]@{
        Id=$id; Category=$category; Slug=$slug; Goal=$goal; Probe=$probe;
        Gate=$gate; Location=$location; Start=$start; End=$end;
        Finding=$finding; Next=$next
    }
}
if ($data.Count -ne 100) { throw "Expected 100 distinct skills, got $($data.Count)" }
if (@($data.Slug | Sort-Object -Unique).Count -ne 100) { throw 'Duplicate skill slug' }
if (@($data.Id | Sort-Object -Unique).Count -ne 100) { throw 'Duplicate skill id' }

# These are distinct discipline-specific review methods; the per-skill probe and
# gate below add the target operation and its particular expected outcome.
$methods = @{
    'Navigation' = 'Trace the active project and object identity before and after the route. Check discoverability through visible navigation, command search, and keyboard-only access; avoid losing the work context on route changes.'
    'Onboarding' = 'Use a clean profile and ask a first-time researcher to predict the result before clicking. Record confusion and recovery cost, verify samples are synthetic or licensed, and allow the task to complete fully offline.'
    'Visual design' = 'Compare filled, empty, busy, failure and high-contrast screenshots at 100%, 150%, and 200% scale. Audit semantic tokens, hierarchy, measured contrast and clipping using actual rendered pixels rather than token names.'
    'Interaction' = 'Specify exact keyboard inputs, focus target, escape behavior and result persistence. Include double-activation, cancellation and stale state in the task script; never infer real focus behavior from static declarations.'
    'Accessibility' = 'Use the actual native packaged host with a keyboard and the supported assistive technology. Capture spoken names, roles and state; test real Persian IME where relevant and distinguish source-level hints from accessibility acceptance.'
    'Source workflows' = 'Follow a record from source identity and version through the specific action into persisted evidence. Check stable references, quote positions, screening decisions and traceable provenance without inventing unsupported metadata.'
    'Data analysis' = 'Choose a named immutable dataset revision and independent expected result or fixture. Inspect variables, units, missingness and exclusions; verify the UI displays exactly the backend output with its scientific limits.'
    'Writing' = 'Exercise actual typed content through edit, preview, save, reopen and export. Check selection, citation identity, Unicode, drafts and revision history; distinguish proposed rich formatting from currently available plain text.'
    'Contextual AI' = 'Identify the exact originating object, data scope, permitted effect class and approval requirements. Inspect source grounding, model/provider selection and explicit consent before any egress or state change; test denied and unavailable states.'
    'Reliability' = 'Reproduce with synthetic failure and boundary fixtures in a disposable project. Compare state before and after, validate durable recovery and error redaction, and use installed native packages where platform behavior matters.'
}
foreach ($item in $data) {
    $path = Join-Path (Join-Path $here $item.Slug) 'SKILL.md'
    $folder = Split-Path -Parent $path
    if (-not (Test-Path -LiteralPath $folder)) {
        New-Item -Path $folder -ItemType Directory | Out-Null
    }
    $name = 'rw-' + $item.Slug
    $title = (($item.Slug -replace '-', ' ').Substring(0,1).ToUpper() +
              ($item.Slug -replace '-', ' ').Substring(1))
    $sourceLink = "https://github.com/aradmanamnaoon/researchweave/blob/$baselineSha/crates/researchweave-desktop/ui/main.slint#L$($item.Start)-L$($item.End)"
    $body = @"
---
name: $name
description: $($item.Goal). Use for ResearchWeave Rust/Slint $($item.Category.ToLowerInvariant()) audits and implementation review.
---

# $title

## Trigger and expected output

Use this skill when the goal is to **$($item.Goal.ToLowerInvariant())**. This is a scoped, repeatable ResearchWeave UX engineering skill, not an automatic permission to edit files. Produce a brief audit record with the affected workflow, source evidence, observed behavior, screenshots or assistive-technology logs if obtained, and a pass/fail/pending decision.

**Discipline-specific method ($($item.Category)):** $($methods[$item.Category])

## Repeatable application procedure

1. **Identify the actual interaction.** Read [$($item.Location)]($sourceLink) in the current worktree and trace its callbacks into Rust before modifying behavior. Keep project scope, immutable revision semantics, privacy, and scientific integrity intact.
2. **Exercise the distinguishing probe.** $($item.Probe). Use a disposable local project and representative empty, populated, error, and keyboard-only states. Capture OS, scale, fixture, exact steps and observable output when testing is possible.
3. **Apply the correction.** Compare the observed outcome with the acceptance gate below. Fix the smallest common interaction/component cause, preserve focus and drafts, and verify the action against the typed Rust handler rather than relying on visual mock controls.
4. **Recheck and report.** Repeat the original probe after changes, inspect relevant neighboring states, run targeted tests and a native GUI check, and classify each remaining gap explicitly as unresolved. Attach source and test evidence to the final review.

## Review checklist

- [ ] Entry point and result context for this specific goal are discoverable from the intended task.
- [ ] The probe was exercised with real UI behavior, including a failure or boundary condition, and evidence is linked.
- [ ] No control claims a capability, effect, citation, or analysis output that the backend cannot deliver.
- [ ] Keyboard focus, accessible names, long text, mixed scripts, and offline/error states have been checked where applicable.
- [ ] The targeted acceptance gate is met with an observed result, or recorded as pending/failing.

**Acceptance gate:** $($item.Gate).

## Task-specific evidence to capture

- **Fixture and setup:** Record the project revision, OS/platform and source/document/dataset setup necessary for this specific probe.
- **Reproduction script:** $($item.Probe).
- **Expected observation:** $($item.Gate).
- **Measured result:** Pending until the probe is run on the applicable actual implementation. Record a screenshot, structured output or assistive-technology log with its exact version; a code reference alone is insufficient.

## Baseline application record (static inspection only)

- **Snapshot:** origin/main `976656d`, 2026-10-29; UI may evolve after this snapshot.
- **Evidence:** [$($item.Location)]($sourceLink).
- **Observation:** $($item.Finding).
- **Next test or improvement:** $($item.Next).
- **Status:** Audited against the source and UX requirements. Runtime probe, user research, implementation completion, and packaged-platform pass are **unverified** in this skill record.

Read [UX acceptance criteria](../../UX_ACCEPTANCE_CRITERIA.md), [design system](../../DESIGN_SYSTEM.md), and [AGENTS.md](../../../../AGENTS.md) before applying. Complement with existing `.agents/skills/desktop-accessibility` or `.agents/skills/research-beginner-experience` for their specialties. Existing PyQt6-specific instructions must be adapted to the **Rust/Slint** implementation.
"@
    [System.IO.File]::WriteAllText($path, $body + "`n", (New-Object System.Text.UTF8Encoding($false)))
}

$matrix = New-Object 'System.Collections.Generic.List[string]'
$matrix.Add('# ResearchWeave - 100 Skills Application Matrix')
$matrix.Add('')
$matrix.Add('Baseline: `origin/main` commit `976656d`, static review on 2026-10-29. This document is the audit/application record for **100 independently scoped, repository-authored Rust/Slint UX skill packages**. Skills are stored under `docs/ux/skills/<slug>/SKILL.md` and are **not automatically installed** into the agent-wide `.agents/skills/` registry. The original 27 repository skills remain untouched.')
$matrix.Add('')
$matrix.Add('**Truth in status:** Every row has an authored instruction package and a source-level application note. `Static reviewed` means we inspected the linked code surface and recorded a concrete observation; it does **not** mean the UI feature has been implemented, the interactive probe run, a human usability test completed, or a cross-platform native app verified. All runtime acceptance gates remain **pending evidence** here. Product implementation and QA belong to separately authorized source work.')
$matrix.Add('')
$matrix.Add('The source used in the audit is `crates/researchweave-desktop/ui/main.slint`. Follow the relevant `SKILL.md` for step-by-step exercise, edge states, acceptance, and next verification. Related core guidance: [UX audit](UX_AUDIT.md), [information architecture](INFORMATION_ARCHITECTURE.md), [design system](DESIGN_SYSTEM.md), and [acceptance criteria](UX_ACCEPTANCE_CRITERIA.md).')
$matrix.Add('')
$matrix.Add('| # | Competency and authored skill | Static audit observation | Source | Audit status | GUI / acceptance |')
$matrix.Add('|---:|---|---|---|---|---|')
foreach ($item in $data) {
    $skillLink = "skills/$($item.Slug)/SKILL.md"
    $src = "https://github.com/aradmanamnaoon/researchweave/blob/$baselineSha/crates/researchweave-desktop/ui/main.slint#L$($item.Start)-L$($item.End)"
    $matrix.Add("| $($item.Id) | **$($item.Category):** [$($item.Slug)]($skillLink) | $($item.Finding). **Next:** $($item.Next). | [L$($item.Start)-$($item.End)]($src) | Static reviewed | Pending |")
}
$matrix.Add('')
$matrix.Add('## Coverage, deployment and interpretation')
$matrix.Add('')
$matrix.Add('- **Authored skills:** 100 unique self-contained `SKILL.md` packages, grouped into Navigation (10), Onboarding (10), Visual design (10), Interaction (10), Accessibility (10), Source workflows (10), Data analysis (10), Writing (10), Contextual AI (10), and Reliability (10). Each has a unique goal, specific probe, acceptance gate, repository evidence, and recommended follow-up.')
$matrix.Add('- **Existing skills inspected:** 27 `.agents/skills/*/SKILL.md` packages. `desktop-accessibility` and `research-beginner-experience` are relevant complements; `pyqt6-minimal-design-system` documents legacy PyQt6 patterns and must not be treated as a Slint implementation instruction.')
$matrix.Add('- **Available external skill references inspected:** `/skills/anatomyweave/screen-reader-testing/SKILL.md`, `interaction-design/SKILL.md`, `onboarding/SKILL.md`, `visual-design-foundations/SKILL.md`, and `wcag-audit-patterns/SKILL.md`. Their reusable methods informed native accessibility, feedback, onboarding and visual-system audit checklists. These packs commonly target web/marketing UI; their HTML, CSS, React and funnel guidance is not directly executable or authoritative for this offline Rust desktop app.')
$matrix.Add('- **Application completed in this documentation task:** source-oriented audits and recorded findings on all 100 competencies; skills written and linked. **Application not completed here:** no edits to UI or Rust code, no package installation under `.agents/skills`, and no executed GUI tasks, user studies, or assistive-technology verification.')
$matrix.Add('- **Future evidence requirement:** for each accepted UI implementation, attach exact commit, executed fixture and steps, platform and scaling details, tests and screenshots/logs. Change that row to `Verified` only after the probe actually runs and the acceptance gate passes. Static source mapping alone never upgrades a feature.')
$matrix.Add('- **Rebuild:** run `powershell -NoProfile -ExecutionPolicy Bypass -File docs/ux/skills/build_catalog.ps1` from the worktree. The 100-record `catalog.psv` is the authored source of truth and duplicate/source-range validation is enforced.')
$matrix.Add('')
$matrixPath = Join-Path $ux '100_SKILLS_APPLICATION_MATRIX.md'
if ((Test-Path -LiteralPath $matrixPath) -and
    (Get-Content -LiteralPath $matrixPath -TotalCount 1) -eq
    '# ResearchWeave - Applied 100-skill source audit') {
    # The live audit includes updated source observations and measurements.
    # A baseline skill rebuild must not silently replace that evidence.
    Write-Output 'Preserved applied audit matrix. Refresh it with scripts/ux/audit_skill_probes.ps1.'
} else {
    [System.IO.File]::WriteAllText($matrixPath,
        (($matrix.ToArray() -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
}
Write-Output "Authored $($data.Count) validated skill packages."

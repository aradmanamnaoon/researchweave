# Source-level application of all 100 ResearchWeave UX skill probes.
# Read-only except the regenerated docs/ux/100_SKILLS_APPLICATION_MATRIX.md.
# Re-run from any working directory:
# powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ux/audit_skill_probes.ps1
#
# A marker is a literal source-level witness, not a simulated GUI interaction.
# Multiple conditions use &&; ALL must be observed. Each probe has a distinct
# source target and concrete audit finding, issue, and next runtime test.
param([switch]$SelfTest)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$catalog = Join-Path $root 'docs/ux/skills/catalog.psv'
$matrix = Join-Path $root 'docs/ux/100_SKILLS_APPLICATION_MATRIX.md'
$sourcePaths = @{
    ui = 'crates/researchweave-desktop/ui/main.slint'
    host = 'crates/researchweave-desktop/src/main.rs'
    notes = 'crates/researchweave-project/src/quick_notes.rs'
    project = 'crates/researchweave-project/src/lib.rs'
    ai = 'crates/researchweave-ai/src/contextual.rs'
    analysis = 'crates/researchweave-analysis/src/lib.rs'
    evidence = 'crates/researchweave-evidence/src/lib.rs'
    core = 'crates/researchweave-core/src/lib.rs'
}
$files = @{}
$baselines = @{}
$fileHashes = @{}
foreach ($key in $sourcePaths.Keys) {
    $relative = $sourcePaths[$key]
    $path = Join-Path $root $relative
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing source file: $relative" }
    $files[$key] = @(Get-Content -LiteralPath $path -Encoding UTF8)
    $fileHashes[$key] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
    $committed = @(& git -C $root ls-tree -r --name-only HEAD -- $relative)
    if ($LASTEXITCODE -ne 0) { throw "Cannot check committed source at $relative" }
    $baseline = if ($committed -contains $relative) {
        @(& git -C $root show "HEAD:$relative")
    } else {
        @()
    }
    $baselines[$key] = $baseline
}

# Id | source file | literal witnesses combined with && | source conclusion
# when all witnesses found | specific gap/follow-up if any witness is missing.
# Every probe is mapped to its actual dedicated skill's exercise in catalog.psv.
$specs = @'
001|ui|root.activity == 0 ? "Home"&&selected: root.activity == 5&&ActivityNavButton|Six named activity roots and a reusable rail control are defined|Six-activity mapping is not fully represented in these source markers; inspect route coverage.
002|ui|if root.activity == 1: VerticalLayout&&accessible-label: "PDF Reader workspace screen"&&accessible-label: "Review workspace screen"|Sources navigation retains separate PDF and Review entries in the context sidebar; density remains high|Sources sidebar destination grouping cannot be confirmed; inspect access and hierarchy.
003|host|fn command_matches&&fn command_hint|Rust command matching and hint functions exist; inspect category/disabled-reason output against the UX contract|No separate command matching/hint implementation observed; universal discovery is a source gap.
004|ui|project-title:&&project-revision:&&"Workbench status"|Current project title/revision and workbench status are UI properties|Project scope and revision badges not jointly exposed in this source area.
005|ui|private property <string> object-kind:|Current object kind is page-derived, not a source/document breadcrumb identity|No object-kind marker; inspect other routes for object-aware breadcrumbs.
006|ui|in-out property <int> page: 0|Main navigation still has a single numeric page state; recent typed-object history is not evidenced here|Numeric page state not found; investigate replacement navigation state.
007|ui|show-context-sidebar&&show-inspector&&changed responsive-width|Width-dependent sidebar and inspector are explicit with responsive change handling|Source lacks complete responsive state signals; verify panel recovery.
008|ui|in-out property <int> page: 0&&private property <string> object-kind:|Page state plus inferred object kind is present; typed tab identity is not demonstrated|No simple page/object pair; inspect typed tab-state implementation.
009|ui|accessible-label: "Tutorials workspace screen"&&accessible-label: "Guidance workspace screen"|Global tutorials and guidance destinations remain; in-place per-field help requires a separate audit|Global help destinations not found; discoverable help surface is unclear.
010|host|fn command_page&&fn command_matches|Command resolver and match logic exist; inspect if results represent records versus pages|No command-page resolution witness; universal source search may not be wired.
011|ui|Quick create in managed local storage&&Private by default.|Start Center exposes a private quick-create path without requiring an account|Private managed quick create is missing from inspected Start Center.
012|ui|root.create-default-project(project-name.text)&&root.create-project(project-path.text, project-name.text)|Default and custom-directory creation callbacks coexist|One of default/custom creation routes absent from current UI.
013|ui|"Start a research project"&&"CUSTOM LOCATION"|Start Center exposes local project creation but no explicit sample-template witness in this probe|Start Center form marker missing; template discovery needs manual source follow-up.
014|ui|root.open-project(project-path.text)&&root.restore-backup(|Open existing and restore-backup callbacks exist in different work areas; unified migration path still needs review|Could not locate both project Open and Restore actions in current UI.
015|ui|"Start Center guidance"&&root.create-default-project|First-run guidance and project create call coexist; completion tracking not demonstrated|Guide/create pair absent; first success path requires work.
016|ui|stats-dataset-id := LineEdit&&stats-revision := LineEdit|Statistics collects dataset ID and revision via fields; contextual plain-language definitions remain unproven|Statistics dataset/revision controls not found.
017|ui|"No notes yet. Create your first note."&&"Open a project, then refresh its sources."|Quick Notes and Library provide concrete empty-state guidance in source|Both note and library empty-state guidance not found; review empty screens.
018|ui|text: "Preview section"&&text: "Record previewed section"|Manuscript separates preview and commit controls; cancellation and no-mutation still need host verification|Manuscript preview/record distinction absent from inspected UI.
019|ui|stats-dataset-id := LineEdit&&stats-correlation-x := LineEdit&&stats-model-predictors := LineEdit|Method-specific statistical inputs are on one workspace; no verified beginner-only abstraction|Statistical fields changed; inspect progressive disclosure for novices.
020|ui|Private by default.&&text: "LOCAL FIRST"|Both first-run privacy text and local-first status label are visible in source|Clear offline/privacy wording not evidenced in both locations.
021|ui|in-out property <color> accent:&&background: root.selected&&#26384f|Semantic accent exists alongside a hardcoded rail hover color; token discipline remains incomplete|Expected theme and hover color markers changed; rerun token census.
022|ui|text: "Manuscript"&&font-size: 22px * Theme.ui-scale / 100&&font-size: 10px * Theme.ui-scale / 100|Manuscript has a title-level size while compact metadata type sizes occur elsewhere; hierarchy exists in code|No distinct heading/metadata type sizes observed.
023|ui|in-out property <length> space1:&&padding: 24px&&spacing: 8px|Named spacing tokens coexist with literal 24px padding and 8px gaps; inconsistency still observable|Current layout source no longer matches old spacing pattern; resample tokens.
024|ui|border-radius: Theme.panel-radius&&border-color: Theme.divider&&background: Theme.surface|Panel styling repeats surface, border and radius tokens; review actual nesting depth|Common card surface/border tokens absent; inspect revised visual containment.
025|ui|component ActivityNavButton inherits Rectangle&&colorize: root.selected&&@image-url("../../../assets/icons/jobs.svg")|Activity icons and a bottom-tray SVG use distinct colorization paths; optical parity needs screenshot|Reusable rail/nav icon and job icon not both evidenced.
026|ui|if focus-scope.has-focus: Rectangle&&? Theme.accent-subtle&&enabled: root.pdf-page-count > 0|Focus ring, selected fill, and conditional disabled PDF actions have source witnesses|One or more selected/focused/disabled state witnesses missing.
027|ui|text: Theme.dark-mode ? "Dark theme: on"&&Theme.high-contrast ? "High contrast: on"&&Interface text scale:|Theme, contrast, and scale controls present; rendered contrast and clipping unmeasured|Appearance control trio incomplete in current worktree.
028|ui|background: Theme.reader-canvas&&visible: root.show-inspector&&"Selection and annotations remain pending."|PDF canvas/inspector exist and inspector explicitly identifies annotation limitations|PDF reader canvas/inspector limitation label not fully found; inspect functionality honestly.
029|ui|if root.page == 12: Rectangle&&StandardTableView&&dataset-grid-rows|Data View has a source-bound read-only Slint StandardTableView with explicit row model; verify real paging, original row IDs and exact current-page JSON through GUI|Native table or source-bound row model absent; inspect the current Data View.
030|ui|in-out property <color> data-1:&&in-out property <color> data-4:|Four visual series tokens exist; no chart accessibility pass follows from palette definition|Scientific color series palette was changed or absent.
031|ui|component ActivityNavButton inherits Rectangle&&event.text == Key.Space&&event.text == Key.Return|Rail implements keyboard Space and Return activation; arrow behavior still needs native verification|Keyboard activation contract for rail not present in examined code.
032|ui|keys: @keys(F6)&&keys: @keys(Shift + F6)|Forward/reverse workbench focus traversal bindings exist|No complete F6/Shift F6 traversal pair observed.
033|ui|event.modifiers.control&&command-field.focus()&&event.text == Key.Escape|Command-focus and Escape handling are defined; result keyboard selection needs GUI proof|Command shortcut/escape focus logic cannot be confirmed.
034|ui|root.choose-local-file("pdf")&&"Choose local PDF with native file picker"|PDF uses native chooser callback; focus restoration after cancel is not asserted in source|Native PDF chooser or accessible label missing.
035|ui|root.show-context-sidebar =&&command-field.focus()&&home-activity.focus()|Visibility updates and fallback focus targets exist; inaccessible offscreen items remain a GUI question|Pane visibility/focus fallback evidence incomplete.
036|ui|stats-revision := LineEdit&&"Backup archive path"|Dataset revision and archive path are raw text controls; field-specific validation feedback is not apparent in those declarations|Missing revision/path input markers; inspect field validation routes.
037|ui|text: "Preview registration"&&text: "Register previewed reference"|Reference UI explicitly separates preview from commit|Preview/commit reference action pair not found.
038|host|fn reconcile_manual_writing_save&&fn recovered_writing_requires_flush|Rust host contains draft/manual-save reconciliation and recovery criteria; retry idempotence needs failure test|No writing reconciliation functions found; potential duplicate-save risk.
039|ui|SemanticProgress&&"Open jobs"&&"No active local jobs"|Bottom tray has semantic progress and jobs access; safe job cancellation remains an independent check|Bottom job progress/readout structure not found.
040|ui|text: "Dismiss notifications"&&text: root.durable-notifications|Persistent notification display and bulk dismiss control exist; per-error recovery links unverified|Notifications view lacks one or both durable/dismiss signals.
041|ui|accessible-role: button&&accessible-label: root.label + " activity"|Activity rail supplies accessible role and label; spoken semantics untested|Activity rail accessible role/name declarations missing.
042|ui|accessible-label: root.activity-name + " navigation"&&ScrollView|Context sidebar is scrollable and named, but UIA off-screen keyboard access cannot be inferred|Named ScrollView navigation witness absent.
043|ui|accessible-live-region: polite&&text: root.status|Workbench status has a polite live region and bounded context string; speaking order untested|Polite status announcement signal absent.
044|ui|in-out property <color> warning:&&in-out property <color> conflict:&&"No mock workflow is shown here."|Warning and conflict colors are defined alongside textual unsupported-workflow explanation|Status color and semantic text combinations not all found.
045|ui|enabled: Theme.ui-scale < 200&&min-width: 760px|UI scale cap is 200 and window minimum 760px; overflow at the combination needs a live layout test|Scaling and minimum width constraints not jointly evidenced.
046|ui|high-contrast ? #000000&&high-contrast ? #ffffff&&in-out property <color> focus:|Explicit high-contrast foreground/background/focus roles exist; OS contrast mode not tested|High-contrast theme branches incomplete in inspected source.
047|ui|accessible-label: "Expanded quick note editor"&&edited(value) =>|Editable notes accept source text changes; no native Persian IME acceptance claimed|Quick note editable field or edit callback missing.
048|ui|accessible-label: "Manuscript section body"&&root.manuscript-draft-body|Manuscript editor exposes mixed-script draft content through an accessible text control; real Persian IME, bidirectional caret selection and export direction remain native GUI tasks|Accessible manuscript body or source-bound draft content not located.
049|ui|in-out property <bool> reduced-motion:&&text: Theme.reduced-motion ?|Reduced-motion preference exists; suppression of all nonessential animations requires rendered inspection|Reduced motion state or control absent.
050|ui|accessible-role: progress-indicator&&accessible-value-maximum: 1.0|Progress exports assistive role and numeric range; VoiceOver/Orca/Narrator behavior still untested|Progress role and accessible numeric range not both exposed.
'@ -split "`r?`n" | Where-Object { $_.Trim() -ne '' }

$moreSpecs = @'
051|ui|if root.page == 5: Rectangle&&root.library-action(|Library has a native workspace and action callback; source-to-reader context persistence remains to verify|Library workspace or action entry not visible in current code.
052|ui|root.choose-local-file("pdf")&&root.load-pdf(pdf-path.text|Native PDF browse and Open callbacks exist; malformed-file feedback needs a test|PDF file picker and open flow are not both wired here.
053|ui|root.find-next-pdf(pdf-path.text&&root.pdf-page-number + 1|Find-next search and next-page actions exist; hit accuracy and wrap semantics still need a PDF fixture|PDF find-next or paging callback missing.
054|ui|if root.pdf-highlight-visible: Rectangle&&"Selection and annotations remain pending."|Search-highlight overlay is drawn and selection/annotation work is explicitly pending|PDF selection/annotation capability declaration changed; inspect actual implementation.
055|ui|manuscript-citations := LineEdit&&search-manuscript-references&&insert-manuscript-reference|Manuscript now provides a registered-reference title/ID lookup and canonical citation insertion alongside its legacy manual field; source alone cannot establish picker accessibility or export fidelity|Registered reference search or insertion callback not observed; inspect actual citation picker wiring.
056|ui|text: "Open evidence"&&"PDF reader context inspector"|PDF inspector links to Evidence but does not show a verified source excerpt locally|PDF context/evidence link no longer matches reference pattern.
057|ui|text: "Systematic review"&&root.preview-review-screen(|Review screen provides persisted screening preview controls; no per-record queue status observed in this probe|Review stage and screening controls absent in UI.
058|ui|root.preview-review-screen(&&independent screening votes|Review UI exposes independent screening; blind-peer enforcement must be verified against backing store|Screening callback or independence warning not found.
059|ui|if root.page == 10: Rectangle&&"PRISMA"|PRISMA workspace is reachable; actual event-derived flow arithmetic requires separate backend test|PRISMA view or label not located.
060|ui|root.preview-extraction-values(&&root.preview-extraction-form(|Extraction UI offers schema and value previews; field version handling is a backend acceptance gate|Extraction form/value preview pair incomplete.
061|ui|root.preview-analysis-import(&&root.apply-analysis-preview()|Dataset import uses a preview and apply boundary; error and row-count display need full flow test|Dataset import lacks paired preview/commit in UI.
062|analysis|parent_revision: Some(dataset.revision.clone())&&pub fn transform(dataset: &Dataset|Analysis crate creates a child dataset with parent revision and exposes a typed transform; UI revision history remains to verify|Immutable transform lineage not represented by the expected source witnesses.
063|ui|root.inspect-variable-view(&&root.preview-variable-update(|Variable inspector and preview-update actions exist; missing-data presentation needs fixture|Variable metadata inspect/update controls absent.
064|ui|if root.page == 12: Rectangle&&StandardTableView {&&rows: root.dataset-grid-rows;|Data View includes a native Slint table bound to verified dataset rows; actual columns and pagination need GUI checking|Data View exists, but no row-bound StandardTableView was found; inspect whether only a text preview is rendered.
065|ui|statistics-mode&&stats-model-outcome := LineEdit&&stats-correlation-x := LineEdit|Statistics supports method state and distinct regression/correlation fields; scientific method hints not demonstrated|Method and input selection markers missing.
066|ui|statistics-result-secondary&&statistics-result-provenance|Statistics has separate secondary and provenance outputs; actual assumption warnings need computed result inspection|Statistics output fields for caveats/provenance missing.
067|host|fn statistics_result_summary&&confidence|Rust result formatting mentions confidence-related text and has a summary helper; wording accuracy needs numerical fixture|No confidence-related result formatting witness located.
068|ui|root.export-analysis-script(&&root.load-analysis-result(|Results can load saved outputs and export a script; rerun determinism untested|Saved-result loader or script export callback absent.
069|ui|in-out property <color> data-1:&&statistics-result-primary|Scientific series colors and text result summary exist; actual chart-text alternative not evidenced|Chart palette/text summary witnesses incomplete.
070|ui|root.run-mixed-joint-display(&&mixed-methods-results|Mixed Methods has a joint-display callback and result state; row-level alignment must be tested|Joint display callback or results state missing.
071|ui|text: "+ New note"&&root.create-quick-note()|Quick note creation has a direct action in the Notes workspace; no PDF contextual capture route is proven|Quick note create control missing from current Notes UI.
072|ui|quick-note-search-field := LineEdit&&root.refresh-quick-notes(value, root.quick-note-view)|Notes have a searchable field wired to refresh; exact tag/text result quality is unverified|Quick-note search is not wired to refresh callback.
073|ui|text: "Archive"&&text: "Trash"&&root.quick-note-action("pin"|Notes expose archive, trash and pin actions, but restoration edge cases need testing|Full pin/archive/trash action set missing.
074|host|fn reset_quick_notes_for_project&&quick_note_draft|Rust host handles note project switching and references note drafts; crash autosave still needs fault injection|Project-scoped draft handling markers absent; check recovery.
075|ui|manuscript-section := LineEdit&&writing-show-outline&&root.manuscript-headings|Manuscript exposes a Markdown heading outline with selectable navigation; GUI caret, keyboard, long-document and structured export checks remain pending|No complete manuscript section/heading outline source chain found.
076|ui|manuscript-body := TextEdit&&Standard text editing shortcuts are available.|Long-form TextEdit offers ordinary editing commands; rich styles/headings/lists are not confirmed|No manuscript edit widget with shortcut guidance found.
077|ui|manuscript-citations := LineEdit&&root.manuscript-draft-citations|Citation IDs remain a text field bound to a draft; claim-to-excerpt links unproven|Manuscript citation-binding field absent.
078|ui|root.export-manuscript(manuscript-id.text, "docx")&&root.export-manuscript(manuscript-id.text, "pdf")|DOCX/PDF preparation actions present; rendered comparison and export fidelity unverified|One or both manuscript export formats not exposed.
079|ui|root.publishing-action("check"&&ResearchWeave never submits files|Publishing can run a local readiness check and explicitly disclaims submission; check outputs against actual artifacts|Publishing readiness/privacy control missing.
080|ui|manuscript-word-count&&manuscript-character-count&&manuscript-body := TextEdit|Editor exposes live word/character counts and a long-form text field; long-document performance pending|No word-count and editor trio found.
081|ui|context-ai-open&&"Open contextual AI assistance for this screen"|Global contextual AI help is togglable with accessible label; per-workspace relevance needs native check|No discoverable contextual AI entry point in current UI.
082|ui|context-ai-selection&&"AI help"|Contextual AI has selection state or binding plus shared help; exact PDF-selection provenance remains to inspect|No selection-aware contextual AI state found.
083|ui|if root.page == 14: Rectangle&&context-ai-open|Statistics page and contextual AI availability coexist, but result-specific input scope is unverified|Statistical surface or contextual AI state unavailable.
084|ai|Do not invent citations&&caller_supplied_unverified|Contextual prompt builder instructs against invented citations and labels supplied provenance unverified|Citation safety instruction/host-supplied provenance marker missing.
085|ui|root.stage-agent-action(&&root.approve-agent-action()&&root.execute-agent-action()|AI proposals have separate stage, approval and execute callbacks; host enforcement still required|AI stage/approve/execute sequence incomplete.
086|ui|root.load-agent-action-timeline()&&root.deny-agent-action(|AI action timeline and deny path exist; reversibility remains operation-specific|AI action timeline or denial route missing.
087|ai|policy.authorize(provider)?&&selected_provider: Option<&ProviderProfile>|Contextual prompt preview checks selected provider against EgressPolicy; actual send path must reauthorize|Contextual preview egress policy check missing.
088|ai|Self::Notes =>&&Self::Statistics =>&&Self::Manuscript =>|ContextKind supplies at least three distinct task-specific guidance branches; actual suggested UI prompts require live inspection|Task-specific contextual prompt guidance not all present.
089|ai|pub fn build_preview(&&Result<PromptPreview, AiError>|Pure contextual builder returns a typed fallible preview; provider retries and UI draft recovery remain host responsibilities|Builder/error signature not found; context failures lack typed result.
090|ui|accessible-label: "Contextual AI help panel"&&"Close AI help"|Accessible contextual drawer and close action exist; keyboard focus restoration needs GUI test|Contextual AI drawer lacks accessible label or close affordance.
091|host|analysis_preview_import_at&&source_sha256|Import host uses preview and source hashing; malformed files and atomic commit need fixtures|Import preview/hash source integrity markers not both found.
092|host|fn flush_writing_drafts&&fn restore_writing_drafts|Rust host has explicit manuscript/notebook draft flush/restore operations; visible save status unverified|Writing draft flush or recovery helper missing.
093|ui|text: "Jobs"&&"Current local job progress"|Job tray exposes progress but this probe finds no source-level cancellation contract|Job tray accessible progress and Jobs control missing.
094|ui|root.backup-action("verify-encrypted"&&root.restore-backup(|Encrypted archive verification and recovery are exposed in separate screens; second-device restore test pending|Encrypted verification or restore action missing.
095|host|fn safe_diagnostics&&fn safe_activity|Host has safe diagnostics/activity formatting helpers; credential sentinel leakage must still be tested|One or both redacted diagnostics formatting helpers missing.
096|ui|root.choose-local-file("pdf")&&root.choose-local-file("data")|PDF/dataset browse actions use the native file selection path; OS-specific focus and Unicode tests pending|Native PDF and dataset chooser routing incomplete.
097|ui|min-width: 760px&&preferred-width: 1280px|Window specifies 760px minimum and 1280px preferred width; clipping under 200% scale unmeasured|Window geometric minimum/preferred settings absent.
098|ui|placeholder-text: "Absolute path to a local PDF"&&accessible-label: "Quick note title"|Long path entry and note title control exist; actual long Unicode path round-trip untested|PDF path and note-title witnesses not both present.
099|host|fn statistics_result_summary&&fn analysis_preview_import_at&&fn ai_preview_at|Host has analysis, statistical summary and AI preview helpers; full end-to-end regression suite still needed|One or more host workflow pillars missing.
100|ui|export component MainWindow inherits Window&&accessible-label: "Workbench status"|Native Slint main window and status accessibility are declared; installed Windows/macOS/Linux acceptance cannot follow from source|Native window/status contracts missing from inspected file.
'@ -split "`r?`n" | Where-Object { $_.Trim() -ne '' }
$specs = @($specs) + @($moreSpecs)

function Find-Literal {
    param([string[]]$Lines, [string]$Needle)
    $matches = New-Object 'System.Collections.Generic.List[int]'
    for ($index = 0; $index -lt $Lines.Count; $index++) {
        if ($Lines[$index].IndexOf($Needle, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            $matches.Add($index + 1)
        }
    }
    return $matches.ToArray()
}

function Markdown([string]$value) {
    $value = $value.Replace('|', '\|').Replace('`', "'")
    return [regex]::Replace($value, '\s+', ' ').Trim()
}

if ($SelfTest) {
    $fixture = @('Button { text: "+ New note"; }', 'clicked => { root.create-quick-note(); }')
    $matched = @(Find-Literal -Lines $fixture -Needle 'text: "+ New note"')
    $missing = @(Find-Literal -Lines $fixture -Needle 'rows: root.dataset-grid-rows;')
    $mutated = @('Button { text: "+ Another note"; }', 'clicked => { root.create-quick-note(); }')
    $afterMutation = @(Find-Literal -Lines $mutated -Needle 'text: "+ New note"')
    if ($matched.Count -ne 1 -or $matched[0] -ne 1 -or $missing.Count -ne 0 -or $afterMutation.Count -ne 0) {
        throw 'Source probe regression: match/missing/mutation behavior is incorrect'
    }
    if ($specs.Count -ne 100 -or @($specs | ForEach-Object { $_.Split('|')[0] } | Sort-Object -Unique).Count -ne 100) {
        throw 'Source probe regression: distinct skill coverage has changed'
    }
    Write-Output 'PASS: exact literal source witness, expected gap, mutation sensitivity, and 100 unique probes'
    return
}

$rows = New-Object 'System.Collections.Generic.List[string]'
$observed = @{}
$probeIds = New-Object 'System.Collections.Generic.HashSet[string]'
foreach ($line in $specs) {
    $fields = @($line.Split('|'))
    if ($fields.Count -ne 5) { throw "Probe definition should have 5 fields: $line" }
    $id, $key, $condition, $positive, $negative = $fields
    if (-not $probeIds.Add($id)) { throw "Duplicate probe: $id" }
    if (-not $sourcePaths.ContainsKey($key)) { throw "Unknown file key: $key" }
    if ($condition.Trim().Length -lt 12 -or $positive.Trim().Length -lt 30 -or $negative.Trim().Length -lt 30) {
        throw "Probe too generic: $id"
    }
    $markers = @($condition.Split(@('&&'), [StringSplitOptions]::None))
    if ($markers.Count -lt 1 -or @($markers | Sort-Object -Unique).Count -ne $markers.Count) {
        throw "Missing or duplicated conditions: $id"
    }
    $counts = @()
    $baselineCounts = @()
    $firstLines = @()
    $missing = @()
    $observedLine = $null
    foreach ($needle in $markers) {
        $found = @(Find-Literal -Lines $files[$key] -Needle $needle)
        $baseline = @(Find-Literal -Lines $baselines[$key] -Needle $needle)
        $counts += $found.Count
        $baselineCounts += $baseline.Count
        $firstLines += $(if ($found.Count -gt 0) { "L$($found[0])" } else { 'none' })
        if ($found.Count -eq 0) {
            $missing += $needle
        } elseif ($null -eq $observedLine) {
            $observedLine = $found[0]
        }
    }
    $passed = $missing.Count -eq 0
    $status = if ($passed) { 'Source witness; GUI pending' } else { 'Source gap; GUI pending' }
    $sourceLink = $sourcePaths[$key] -replace '\\', '/'
    $link = if ($observedLine) { "../..//$sourceLink#L$observedLine" } else { "../..//$sourceLink" }
    $link = $link.Replace('../..//', '../../')
    if ($observedLine) {
        $sample = ($files[$key][$observedLine - 1]).Trim()
        if ($sample.Length -gt 135) { $sample = $sample.Substring(0, 132) + '...' }
        $sample = Markdown $sample
        $witness = "**Observed L${observedLine}:** " + $sample
    } else {
        $witness = '**Observed:** none of the required source literals were found'
    }
    $countsText = ($counts -join '/')
    $baselineText = ($baselineCounts -join '/')
    $measure = "Current marker occurrences: **$countsText** (baseline HEAD: **$baselineText**); first lines: $($firstLines -join '/')."
    $conclusion = if ($passed) { $positive } else {
        $missingList = Markdown ($missing -join ' + ')
        "$negative. Missing literal(s): $missingList."
    }
    $observed[$id] = [pscustomobject]@{
        Key = $key
        Markers = $markers
        Current = $counts
        Baseline = $baselineCounts
        Passed = $passed
        Line = $observedLine
        Status = $status
        Description = $conclusion
        Witness = $witness
        Measure = $measure
        SourceLink = $link
    }
}
$catalogRecords = @(Get-Content -LiteralPath $catalog -Encoding UTF8 | Where-Object { $_ -match '^\d{3}\|' })
if ($catalogRecords.Count -ne 100 -or $specs.Count -ne 100 -or $probeIds.Count -ne 100) {
    throw "Coverage mismatch: catalog=$($catalogRecords.Count) specs=$($specs.Count) unique=$($probeIds.Count)"
}
$commit = (& git -C $root rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot identify worktree HEAD' }
$tracked = (& git -C $root status --porcelain -- crates/researchweave-desktop/ui/main.slint crates/researchweave-desktop/src/main.rs crates/researchweave-ai/src/contextual.rs crates/researchweave-project/src/quick_notes.rs).Count

# Deepen important source probes with real cross-control measurements. These
# operate on the same checked source snapshot rather than the baseline docs.
function Source-Section {
    param([string[]]$Lines, [string]$StartText, [string]$EndText)
    $start = -1
    for ($index = 0; $index -lt $Lines.Count; $index++) {
        if ($Lines[$index].Contains($StartText)) { $start = $index; break }
    }
    if ($start -lt 0) { return @() }
    $last = $Lines.Count
    for ($index = $start + 1; $index -lt $Lines.Count; $index++) {
        if ($Lines[$index].Contains($EndText)) { $last = $index; break }
    }
    if ($last -le $start) { return @() }
    return @($Lines[$start..($last - 1)])
}

$measurements = @{}
$uiLines = $files.ui
$railCount = @($uiLines | Where-Object { $_ -match '^\s+(?:[\w-]+\s*:=\s*)?ActivityNavButton\s*\{' }).Count
$sourceSidebar = @(Source-Section -Lines $uiLines -StartText 'if root.activity == 1: VerticalLayout' -EndText 'if root.activity == 2: VerticalLayout')
$manageSidebar = @(Source-Section -Lines $uiLines -StartText 'if root.activity == 5: VerticalLayout' -EndText 'text: root.show-extra-destinations ? "Show fewer sections"')
$sourceEntries = @($sourceSidebar | Where-Object { $_ -match 'SidebarItem\s*\{' }).Count
$manageEntries = @($manageSidebar | Where-Object { $_ -match 'SidebarItem\s*\{' }).Count - 1 # excludes outer More sections toggle
$sourceHidden = @($sourceSidebar | Where-Object { $_ -match 'if root.show-extra-destinations: SidebarItem' }).Count
$manageHidden = @($manageSidebar | Where-Object { $_ -match 'if root.show-extra-destinations: SidebarItem' }).Count
$measurements['001'] = "Six-root rail declaration count: $railCount."
$measurements['002'] = "Sources sidebar declares $sourceEntries entries ($sourceHidden behind extra-destinations); Manage sidebar declares $manageEntries ($manageHidden behind extra-destinations)."
$colorDeclarations = @($uiLines | Where-Object { $_ -match '^\s+in-out property <color>' }).Count
$hardColors = @($uiLines | Select-Object -Skip 60 | Where-Object { $_ -match '#[a-fA-F0-9]{6}' }).Count
$measurements['021'] = "$colorDeclarations declared semantic color properties; $hardColors lines with hardcoded hex colors beyond theme declarations."
$spacingTokens = @($uiLines | Where-Object { $_ -match 'Theme\.space[1-8]' }).Count
$spacingLiterals = @($uiLines | Where-Object { $_ -match '\b(spacing|padding): [0-9]+px' }).Count
$measurements['023'] = "$spacingTokens lines use named spacing tokens; $spacingLiterals lines use direct pixel spacing/padding."
$dataBody = @(Source-Section -Lines $uiLines -StartText 'if root.page == 12: Rectangle' -EndText 'if root.page == 13: Rectangle')
$dataViewList = @($dataBody | Where-Object { $_ -match '\bStandardTableView\s*\{' }).Count
$dataViewFields = @($dataBody | Where-Object { $_ -match 'LineEdit\s*\{' }).Count
$measurements['064'] = "Data View section: $dataViewList rendered StandardTableView controls, $dataViewFields LineEdit controls. (Importing a table globally does not count as actual row-grid rendering.)"
$notesBody = @(Source-Section -Lines $uiLines -StartText 'if root.page == 21: Rectangle' -EndText 'if root.page == 9: Rectangle')
$noteSearches = @($notesBody | Where-Object { $_ -match 'quick-note-search-field' }).Count
$noteActionButtons = @($notesBody | Where-Object { $_ -match 'root.quick-note-action\(' }).Count
$measurements['071'] = "Notes workspace: $noteSearches search-control markers and $noteActionButtons note-action handler references."
$manuscriptBody = @(Source-Section -Lines $uiLines -StartText 'if root.page == 19: Rectangle' -EndText 'if root.page == 22: Rectangle')
$richTools = @($manuscriptBody | Where-Object { $_ -match '\b(text:|accessible-label:).*\b(Bold|Italic|Underline|Heading|Bullets)\b' }).Count
$measurements['076'] = "Manuscript section: $richTools explicitly labeled rich-formatting controls (Bold/Italic/Underline/Heading/Bullets). A text editor and export actions are present; Word-like rich formatting remains unproven."
$contextToggles = @($uiLines | Where-Object { $_ -match 'context-ai-open' }).Count
$measurements['081'] = "Contextual AI state references in Slint: $contextToggles; this count does not identify passage selection or verify source provenance."
$formatExports = @($manuscriptBody | Where-Object { $_ -match 'root.export-manuscript\(' }).Count
$measurements['078'] = "Manuscript export callback references inside its work area: $formatExports."
$measurements['100'] = 'This run exercises 0 native GUI installs; Windows/macOS/Linux packaged acceptance remains unmeasured.'

$rows.Add('# ResearchWeave - Applied 100-skill source audit')
$rows.Add('')
$rows.Add('**Run this audit** with `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ux/audit_skill_probes.ps1` (PowerShell 5.1; no network, GUI, or Rust execution). This script reads the **current working files** and applies a **different concrete source probe for every one of the 100 installed/authored skills**, following the distinct task in its `SKILL.md` and `catalog.psv`. Each probe checks one or more literal source witnesses, reports exact occurrence counts relative to HEAD, captures the live witness line and leaves a next real GUI test. No skill is silently counted as a GUI pass.')
$rows.Add('')
$rows.Add(('**Snapshot:** HEAD `{0}`, worktree under `target/ux-transformation-20261029`, {1} relevant source files reported modified/untracked at audit start. Checks refer to the live working tree, not the original UX baseline. Baseline counts use `git show HEAD:<file>` for comparison. The evidence below is reproducible only at the specified source SHA256 digests; code edited afterward must be audited again.' -f $commit, $tracked))
$rows.Add('')
$rows.Add('| Source | SHA256 at audit | Lines inspected |')
$rows.Add('|---|---|---:|')
foreach ($key in @('ui', 'host', 'notes', 'project', 'ai', 'analysis', 'evidence', 'core')) {
    $relative = $sourcePaths[$key].Replace('\', '/')
    $rows.Add(('| `{0}` | `{1}` | {2} |' -f $relative, $fileHashes[$key], $files[$key].Count))
}
$rows.Add('')
$rows.Add('**Interpretation:** `Source witness` means the exact named implementation signal exists in current source; it **does not** verify the full skill acceptance gate. `Source gap` means a specific expected marker was absent in the checked file and warrants investigation; it is not a definitive claim that no alternative implementation exists. All 100 runtime usability, focus, screen reader, task completion, and multi-OS checks remain **GUI pending** unless independently demonstrated elsewhere. No synthetic test results or human study participants were invented.')
$rows.Add('')
$rows.Add('| ID / applied skill | Distinct task-focused probe from skill | Actual source measurement and observation | Source-level issue / next verification | Source status |')
$rows.Add('|---|---|---|---|---|')
$passedCount = 0
foreach ($record in $catalogRecords) {
    $fields = @($record.Split('|'))
    if ($fields.Count -ne 9) { throw "Malformed catalog row: $record" }
    $id = $fields[0]
    if (-not $observed.ContainsKey($id)) { throw "Missing executable probe for $id" }
    $result = $observed[$id]
    if ($result.Passed) { $passedCount++ }
    $slug = $fields[2]
    $exercise = Markdown $fields[4]
    $gate = Markdown $fields[5]
    $next = Markdown $fields[8]
    $conclusion = Markdown $result.Description
    $witness = Markdown $result.Witness
    $measure = Markdown $result.Measure
    if ($measurements.ContainsKey($id)) { $measure += ' **Scoped measurement:** ' + (Markdown $measurements[$id]) }
    $path = $result.SourceLink
    $rows.Add("| $id [$slug](skills/$slug/SKILL.md) | $exercise | $measure $witness | **Source finding:** $conclusion **Acceptance gate:** $gate. **GUI follow-up:** $next. | [$($result.Status)]($path) |")
}
$rows.Add('')
$rows.Add("## Reproducible audit totals")
$rows.Add('')
$rows.Add("- **100/100 distinct skill probes executed against current source:** $passedCount contained every required source marker; $(100 - $passedCount) had a missing source marker. This is an audited-source finding distribution, not a usability pass rate.")
$rows.Add('- **Runtime/GUI verified by this audit:** 0 of 100. Native app interaction, scientific correctness, platform accessibility, or full product readiness cannot be concluded by inspecting source literals.')
$rows.Add('- **Most actionable findings:** Review any `Source gap` row, then test the specified real workflow and record exact task outcome. Also test all `Source witness` rows because matching a callback or control declaration does not guarantee a working experience.')
$rows.Add('- **Baseline distinction:** Source code counts compare the current modified working tree to the committed HEAD only. HEAD is not a clean historical UX snapshot of later work. Skills authored in `docs/ux/skills` and installed in `/skills/researchweave` still require human/native interactions for actual acceptance.')
$rows.Add('')
foreach ($key in $sourcePaths.Keys) {
    $path = Join-Path $root $sourcePaths[$key]
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $fileHashes[$key]) {
        throw "Source changed during audit: $($sourcePaths[$key]); matrix was not updated"
    }
}
$utf8 = New-Object System.Text.UTF8Encoding($false)
$temporary = Join-Path (Split-Path -Parent $matrix) '_skill_probe_matrix.pending'
[System.IO.File]::WriteAllText($temporary, ($rows.ToArray() -join "`n") + "`n", $utf8)
Move-Item -LiteralPath $temporary -Destination $matrix -Force
Write-Output "Executed $($specs.Count) distinct source probes: $passedCount full-witness, $(100 - $passedCount) source gaps; GUI passes claimed: 0."
Write-Output "Updated $matrix"

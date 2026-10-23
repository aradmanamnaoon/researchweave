# ResearchWeave UI V2 · Local prototype guide

This is a desktop integration prototype, and it uses explicitly synthetic examples. It has no account requirement, sends no telemetry and makes no outside AI requests.

Start a project from the sidebar, provide a descriptive title and answerable research question, then use Library to add your own plain-text note. Search uses local text and a read-only reader. Select a paragraph in Reader and choose Code selected text to attach a keyword to its saved offsets. The Review screen records whether you include, exclude or remain unsure; an exclusion requires an explicit reason. These decisions are screening records, not a full PRISMA statement.

Data View accepts pasted CSV text with a header row. The grid is read-only and reports all rows from a bounded demonstration dataset. Statistics computes descriptive mean, median, minimum, maximum and sample standard deviation, excluding missing or nonnumeric cells. This is not an inferential analysis or causal claim.

Notebook and Manuscript store drafts locally. Use Ctrl+S or the visible Save button. When switching projects or closing with edited writing, the application asks whether to save, discard or cancel. The Export screen previews a local Markdown, JSON or CSV output before asking for explicit confirmation. Existing export files are protected from overwrite.

Global commands: Ctrl+K opens the command palette; Ctrl+N creates a project; Ctrl+F focuses local library search; Ctrl+S saves the active text editor; Ctrl+1 and Ctrl+2 navigate to Dashboard and Library. Preferences offers light, dark and high-contrast themes, compact/comfortable density and 100/150/200% text scaling.

The Agent screen demonstrates proposed-action review and denial only; there is no configured AI execution. The Privacy screen states local-only policy. For advanced research methods and genuine PDFs, wait for composition-root integration with evidence and analysis domains.

Reproduce a test capture from the UI worktree with:

Protocol is an editable research-design draft with four methodology templates; incomplete required fields trigger validation messages. Guidance explains basic research concepts and limitations in context. Global Search searches sources, coded excerpts, manuscript, notes and protocol only within the current project. It is literal text matching and does not establish citation credibility.

Backups provides a local project snapshot plan, a human confirmation before ZIP creation, a list of integrity-verified snapshots, and a separate human confirmation before restoring to a new project ID. Existing projects and backup archives are retained, and the archive contains no credentials. A backup is a project data snapshot, not a guaranteed copy of future large document attachments.

    $env:QT_QPA_PLATFORM='offscreen'
    uv run python -m researchweave.ui.demo --output ./prototype-artifacts --theme light --width 1280 --height 720

The generated PNG is a real Qt screenshot of a synthetic prototype; its manifest records capture settings, a SHA-256 digest and descriptive alt text. It does not depict the released application.

Recovery lists draft copies of unsaved Notebook and Manuscript text. Select one to load into an editor without overwriting the saved project, then review and press Save. If the underlying project has changed, the UI asks before loading the draft. PDF Reader opens an explicitly selected local PDF. Evidence captures quotations with source hashes, and Publishing makes human review requirements visible.

The independent screening service supports two separate local reviewer aliases, explicit exclusion reasons, conflict review and adjudication by a third alias; these identities are not authenticated. Its flow counts reflect only recorded local source screening, not all required PRISMA stages. Source highlighting in Reader now accounts for Qt UTF-16 positions when emoji and other supplementary Unicode symbols appear before selected text.

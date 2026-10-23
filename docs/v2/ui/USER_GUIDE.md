# ResearchWeave UI V2 · Local prototype guide

This is a desktop integration prototype, and it uses explicitly synthetic examples. It has no account requirement, sends no telemetry and makes no outside AI requests.

Start a project from the sidebar, provide a descriptive title and answerable research question, then use Library to add your own plain-text note. Search uses local text and a read-only reader. Select a paragraph in Reader and choose Code selected text to attach a keyword to its saved offsets. The Review screen records whether you include, exclude or remain unsure; an exclusion requires an explicit reason. These decisions are screening records, not a full PRISMA statement.

Data View accepts pasted CSV text with a header row. The grid is read-only and reports all rows from a bounded demonstration dataset. Statistics computes descriptive mean, median, minimum, maximum and sample standard deviation, excluding missing or nonnumeric cells. This is not an inferential analysis or causal claim.

Notebook and Manuscript store drafts locally. Use Ctrl+S or the visible Save button. When switching projects or closing with edited writing, the application asks whether to save, discard or cancel. The Export screen previews a local Markdown, JSON or CSV output before asking for explicit confirmation. Existing export files are protected from overwrite.

Global commands: Ctrl+K opens the command palette; Ctrl+N creates a project; Ctrl+F focuses local library search; Ctrl+S saves the active text editor; Ctrl+1 and Ctrl+2 navigate to Dashboard and Library. Preferences offers light, dark and high-contrast themes, compact/comfortable density and 100/150/200% text scaling.

The Agent screen demonstrates proposed-action review and denial only; there is no configured AI execution. The Privacy screen states local-only policy. For advanced research methods and genuine PDFs, wait for composition-root integration with evidence and analysis domains.

Reproduce a test capture from the UI worktree with:

    $env:QT_QPA_PLATFORM='offscreen'
    uv run python -m researchweave.ui.demo --output ./prototype-artifacts --theme light --width 1280 --height 720

The generated PNG is a real Qt screenshot of a synthetic prototype; its manifest records capture settings, a SHA-256 digest and descriptive alt text. It does not depict the released application.

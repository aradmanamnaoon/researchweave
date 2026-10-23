"""Functional PyQt6 desktop shell; every enabled action routes to a local service."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QCloseEvent, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .contracts import Preferences
from .design import apply_theme, named
from .facade import UIFacade
from .jobs import JobManager
from .models import ResearchTableModel

SCREENS = (
    "Dashboard", "Search", "Protocol", "Library", "Reader", "Review", "Data View", "Variable View",
    "Statistics", "Qualitative", "Manuscript", "Notebook", "Agent", "Privacy",
    "Exports", "Backups", "Jobs", "Guidance", "Preferences", "Activity", "About",
)


def button(text: str, callback: Callable[..., Any], *,
           primary: bool = False) -> QPushButton:
    widget = QPushButton(text)
    named(widget, text)
    if primary:
        widget.setObjectName("primary")
    widget.clicked.connect(callback)
    return widget


def heading(text: str) -> QLabel:
    widget = QLabel(text)
    widget.setObjectName("sectionTitle")
    return widget


class CommandPalette(QDialog):
    def __init__(self, parent: ResearchWindow) -> None:
        super().__init__(parent)
        self.setWindowTitle("Navigate or run a command")
        self.setAccessibleName("Command palette")
        self.resize(480, 380)
        layout = QVBoxLayout(self)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Find a screen or action")
        named(self.query, "Search available commands")
        layout.addWidget(self.query)
        self.results = QListWidget()
        named(self.results, "Matching commands")
        layout.addWidget(self.results)
        self.query.textChanged.connect(self.refresh)
        self.query.returnPressed.connect(self.activate)
        self.results.itemActivated.connect(lambda _item: self.activate())
        self.refresh("")

    def refresh(self, query: str) -> None:
        self.results.clear()
        actions = ("Create project", "Import text source", "Search library", "Export preview")
        self.results.addItems(
            [name for name in (*SCREENS, *actions) if query.casefold() in name.casefold()]
        )
        if self.results.count():
            self.results.setCurrentRow(0)

    def activate(self) -> None:
        current = self.results.currentItem()
        if current is None:
            return
        name = current.text()
        self.accept()
        parent = self.parent()
        if isinstance(parent, ResearchWindow):
            if name in SCREENS:
                parent.navigate(name)
            elif name == "Create project":
                parent.create_project()
            elif name == "Import text source":
                parent.import_source()
            elif name == "Search library":
                parent.navigate("Library")
                parent.search.setFocus()
            elif name == "Export preview":
                parent.navigate("Exports")


class ResearchWindow(QMainWindow):
    def __init__(self, facade: UIFacade) -> None:
        super().__init__()
        self.facade = facade
        self.prefs = self.facade.settings.load()
        self.project_id = self.prefs.last_project_id
        self.revision = 0
        self.current_source_id = ""
        self.current_dataset_id = ""
        self._editor_loading = False
        self.protocol_fields: dict[str, QPlainTextEdit] = {}
        self.jobs = JobManager()
        self.jobs.error.connect(lambda _key, message: self._set_status(message))
        self.jobs.changed.connect(lambda key, state: self._set_status(f"{key}: {state}"))
        self.setWindowTitle("ResearchWeave · Local research desktop")
        self.setMinimumSize(760, 490)
        self.resize(1260, 780)
        self._build()
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, self.prefs)
        self.refresh_projects()
        if self.project_id:
            self.open_project(self.project_id)
        self.navigate(self.prefs.selected_screen if self.prefs.selected_screen in SCREENS
                      else "Dashboard")
        self._set_status("Offline-ready · no AI credentials required")

    def _build(self) -> None:
        root = QWidget()
        row = QHBoxLayout(root)
        row.setContentsMargins(12, 12, 12, 8)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        row.addWidget(self.splitter)
        self.setCentralWidget(root)
        sidebar = QWidget()
        side = QVBoxLayout(sidebar)
        side.addWidget(heading("researchweave"))
        side.addWidget(QLabel("Private by default · local workspace"))
        self.project_picker = QComboBox()
        named(self.project_picker, "Current project")
        self.project_picker.currentIndexChanged.connect(self._selected_project)
        side.addWidget(self.project_picker)
        side.addWidget(button("＋ New project", self.create_project, primary=True))
        self.nav = QListWidget()
        named(self.nav, "Workspace navigation", "Use up and down arrows to select a screen")
        self.nav.addItems(SCREENS)
        self.nav.currentTextChanged.connect(self.navigate)
        side.addWidget(self.nav)
        side.addWidget(button("⌘  Commands · Ctrl+K", self.show_palette))
        self.splitter.addWidget(sidebar)
        center = QWidget()
        center_layout = QVBoxLayout(center)
        self.page_heading = heading("Dashboard")
        center_layout.addWidget(self.page_heading)
        self.pages = QStackedWidget()
        self.pages.setAccessibleName("Active research workspace")
        center_layout.addWidget(self.pages)
        self.splitter.addWidget(center)
        self.splitter.setSizes([self.prefs.sidebar_width, 930])
        self._build_pages()
        self._set_status("Ready")
        self._shortcut("Ctrl+K", self.show_palette)
        self._shortcut("Ctrl+N", self.create_project)
        self._shortcut("Ctrl+F", self.focus_search)
        self._shortcut("Ctrl+S", self.save_active)
        self._shortcut("Ctrl+1", lambda: self.navigate("Dashboard"))
        self._shortcut("Ctrl+2", lambda: self.navigate("Library"))

    def _shortcut(self, keys: str, callback: Callable[..., Any]) -> None:
        action = QAction(keys, self)
        action.setShortcut(QKeySequence(keys))
        action.triggered.connect(callback)
        self.addAction(action)

    def _page(self, name: str, explanation: str) -> QVBoxLayout:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        summary = QLabel(explanation)
        summary.setWordWrap(True)
        summary.setObjectName("muted")
        layout.addWidget(summary)
        self.pages.addWidget(page)
        page.setAccessibleName(f"{name} workspace")
        return layout

    def _build_pages(self) -> None:
        layout = self._page("Dashboard", "Start with a research question. Your work stays local.")
        self.dashboard = QLabel("Choose a project or create a new one.")
        self.dashboard.setWordWrap(True)
        layout.addWidget(self.dashboard)
        layout.addWidget(button("Create research project", self.create_project, primary=True))
        layout.addWidget(button("Add a source", self.import_source))
        layout.addWidget(button("Build a research protocol", lambda: self.navigate("Protocol")))
        self.tutorial = QLabel("First steps: create project → add source → notes → export")
        layout.addWidget(self.tutorial)
        layout.addStretch()

        layout = self._page(
            "Search",
            "Search local sources, coded passages, manuscript, notes and protocol. "
            "The results are literal matches, not verified research conclusions.",
        )
        self.global_query = QLineEdit()
        self.global_query.setPlaceholderText("Search the complete current project")
        named(self.global_query, "Global research search")
        self.global_query.returnPressed.connect(self.search_global)
        layout.addWidget(self.global_query)
        self.global_kind = QComboBox()
        self.global_kind.addItems([
            "All", "source", "annotation", "protocol", "manuscript", "notebook"
        ])
        named(self.global_kind, "Global search category filter")
        layout.addWidget(self.global_kind)
        layout.addWidget(button("Search project", self.search_global, primary=True))
        self.global_results = QListWidget()
        named(self.global_results, "Project-wide search results")
        self.global_results.itemActivated.connect(lambda item: self.open_search_result(item))
        layout.addWidget(self.global_results)
        layout.addWidget(button("Open selected result", self.open_selected_search))
        self.global_summary = QLabel("All searches remain inside the current project.")
        self.global_summary.setWordWrap(True)
        layout.addWidget(self.global_summary)

        layout = self._page(
            "Protocol",
            "Choose an editable research design; no real data or ethics approvals are assumed.",
        )
        self.template_picker = QComboBox()
        named(self.template_picker, "Research design template")
        layout.addWidget(self.template_picker)
        layout.addWidget(button("Start protocol from template", self.start_protocol,
                                primary=True))
        self.protocol_summary = QLabel(
            "Choose a template, then save each field. Protocols require human review."
        )
        self.protocol_summary.setWordWrap(True)
        layout.addWidget(self.protocol_summary)
        self.protocol_content = QWidget()
        self.protocol_form = QFormLayout(self.protocol_content)
        self.protocol_content.setAccessibleName("Editable protocol fields")
        self.protocol_scroll = QScrollArea()
        self.protocol_scroll.setWidgetResizable(True)
        self.protocol_scroll.setWidget(self.protocol_content)
        named(self.protocol_scroll, "Research protocol form")
        layout.addWidget(self.protocol_scroll)
        layout.addWidget(button("Save protocol draft", self.save_protocol))
        layout.addWidget(button("Check required fields", self.validate_protocol))
        self._refresh_templates()

        layout = self._page("Library", "Search local sources; sample records are always labeled.")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search title, source text or tags")
        named(self.search, "Search this project's sources")
        self.search.textChanged.connect(self.search_sources)
        layout.addWidget(self.search)
        layout.addWidget(button("Import source text", self.import_source, primary=True))
        self.library_list = QListWidget()
        named(self.library_list, "Sources in current project")
        self.library_list.itemSelectionChanged.connect(self.select_source)
        layout.addWidget(self.library_list)

        layout = self._page("Reader", "Read selected source text and inspect its provenance.")
        self.reader_meta = QLabel("Choose an item from Library.")
        layout.addWidget(self.reader_meta)
        self.reader_text = QPlainTextEdit()
        self.reader_text.setReadOnly(True)
        named(self.reader_text, "Read-only source content")
        layout.addWidget(self.reader_text)
        layout.addWidget(button("Code selected text", self.annotate_selection))

        layout = self._page("Review", "Screen included and excluded sources with a reason.")
        self.review_summary = QLabel("No screening decisions.")
        layout.addWidget(self.review_summary)
        self.review_filter = QComboBox()
        self.review_filter.addItems(["All", "pending", "include", "exclude", "unsure"])
        named(self.review_filter, "Review queue decision filter")
        self.review_filter.currentTextChanged.connect(self.refresh_review)
        layout.addWidget(self.review_filter)
        self.review_queue = QListWidget()
        named(self.review_queue, "Select a source to review")
        self.review_queue.currentItemChanged.connect(self._select_review_source)
        layout.addWidget(self.review_queue)
        self.review_reason = QLineEdit()
        self.review_reason.setPlaceholderText("Exclusion reason (required to exclude)")
        named(self.review_reason, "Screening exclusion reason")
        layout.addWidget(self.review_reason)
        for status in ("include", "exclude", "unsure"):
            layout.addWidget(button(f"Screen: {status.title()}",
                                    lambda _checked=False, choice=status: self.vote(choice)))
        layout.addStretch()

        layout = self._page("Data View", "Import a small local CSV; cells stay in a virtual table.")
        layout.addWidget(button("Import CSV text", self.import_csv, primary=True))
        self.dataset_picker = QComboBox()
        named(self.dataset_picker, "Active dataset")
        self.dataset_picker.currentIndexChanged.connect(self._selected_dataset)
        layout.addWidget(self.dataset_picker)
        self.data_table = QTableView()
        named(self.data_table, "Dataset grid with labeled column and row headers")
        self.data_model = ResearchTableModel()
        self.data_table.setModel(self.data_model)
        layout.addWidget(self.data_table)
        pager = QHBoxLayout()
        pager.addWidget(button("Previous data page", self.previous_data_page))
        self.data_page_status = QLabel("No dataset loaded")
        pager.addWidget(self.data_page_status)
        pager.addWidget(button("Next data page", self.next_data_page))
        layout.addLayout(pager)
        self.data_offset = 0
        self.data_total = 0
        self.data_page_size = 250

        layout = self._page("Variable View", "Choose a column and inspect its raw values.")
        self.variable_list = QListWidget()
        named(self.variable_list, "Variables available for descriptive statistics")
        layout.addWidget(self.variable_list)

        layout = self._page("Statistics", "Descriptive summaries; missing values are reported.")
        self.variable_picker = QComboBox()
        named(self.variable_picker, "Numeric column for descriptive summary")
        layout.addWidget(self.variable_picker)
        layout.addWidget(button("Compute descriptive summary", self.run_summary, primary=True))
        self.stats_result = QPlainTextEdit()
        self.stats_result.setReadOnly(True)
        named(self.stats_result, "Text alternative for numeric summary")
        layout.addWidget(self.stats_result)

        layout = self._page("Qualitative", "Code Unicode spans with original source offsets.")
        layout.addWidget(button("Code selection in Reader", self.annotate_selection))
        self.annotation_list = QListWidget()
        named(self.annotation_list, "Saved text annotations")
        layout.addWidget(self.annotation_list)

        layout = self._page("Manuscript", "Verify each manuscript claim against its source.")
        self.manuscript_editor = QPlainTextEdit()
        named(self.manuscript_editor, "Editable manuscript draft")
        layout.addWidget(self.manuscript_editor)
        layout.addWidget(button("Save manuscript · Ctrl+S", lambda: self.save_text("manuscript")))

        layout = self._page("Notebook", "Record observations, questions and source checks.")
        self.notebook_editor = QPlainTextEdit()
        named(self.notebook_editor, "Editable research notes")
        layout.addWidget(self.notebook_editor)
        layout.addWidget(button("Save notes · Ctrl+S", lambda: self.save_text("notebook")))

        layout = self._page("Agent", "Model plans are suggestions; no unapproved changes can run.")
        self.agent_proposal = QPlainTextEdit()
        self.agent_proposal.setPlaceholderText("Paste a proposed action to review locally")
        named(self.agent_proposal, "Untrusted agent proposal")
        layout.addWidget(self.agent_proposal)
        self.risk_picker = QComboBox()
        self.risk_picker.addItems(["read", "local-write", "external-network", "irreversible"])
        named(self.risk_picker, "Proposed action risk class")
        layout.addWidget(self.risk_picker)
        layout.addWidget(button("Preview proposal", self.preview_agent))
        layout.addWidget(button("Deny proposed change", self.deny_agent))
        self.agent_status = QLabel("No provider configured; manual work remains available.")
        self.agent_status.setWordWrap(True)
        layout.addWidget(self.agent_status)

        layout = self._page("Privacy", "Offline mode is on. The demo never contacts a server.")
        self.privacy_status = QLabel("Local data only · no telemetry · no accounts required")
        self.privacy_status.setWordWrap(True)
        layout.addWidget(self.privacy_status)
        layout.addStretch()

        layout = self._page("Exports", "Preview file hashes before saving a local export.")
        self.export_name = QLineEdit("research-notes.md")
        named(self.export_name, "Export filename")
        layout.addWidget(self.export_name)
        layout.addWidget(button("Inspect export", self.preview_export))
        layout.addWidget(button("Save local export", self.export_file, primary=True))
        self.export_receipt = QLabel("No export yet.")
        self.export_receipt.setWordWrap(True)
        layout.addWidget(self.export_receipt)
        layout.addStretch()

        layout = self._page(
            "Backups",
            "Create a verified local snapshot. Restoration copies data to a new project.",
        )
        layout.addWidget(button("Preview backup for this project", self.preview_backup))
        layout.addWidget(button("Create verified backup", self.create_backup, primary=True))
        layout.addWidget(button("Refresh backup list", self.refresh_backups))
        self.backup_list = QListWidget()
        named(self.backup_list, "Local project backup archives")
        self.backup_list.currentItemChanged.connect(self.inspect_backup)
        layout.addWidget(self.backup_list)
        layout.addWidget(button("Restore selected backup as new project",
                                self.restore_backup))
        self.backup_receipt = QLabel("Backups are local, immutable ZIP data archives.")
        self.backup_receipt.setWordWrap(True)
        layout.addWidget(self.backup_receipt)

        layout = self._page("Jobs", "Long operations use cancellable supervised Qt tasks.")
        self.job_list = QListWidget()
        named(self.job_list, "Background job statuses")
        layout.addWidget(self.job_list)
        layout.addWidget(button("Cancel selected job", self.cancel_job))
        self.jobs.changed.connect(lambda key, state: self.job_list.addItem(f"{key}: {state}"))

        layout = self._page(
            "Guidance", "Plain-language definitions and limitations for research methods."
        )
        self.help_query = QLineEdit()
        self.help_query.setPlaceholderText("Search sample, variable, evidence, missingness")
        named(self.help_query, "Search research definitions")
        self.help_query.textChanged.connect(self.refresh_guidance)
        layout.addWidget(self.help_query)
        self.help_list = QListWidget()
        named(self.help_list, "Research guidance topics")
        self.help_list.currentItemChanged.connect(self._select_guidance)
        layout.addWidget(self.help_list)
        self.help_detail = QPlainTextEdit()
        self.help_detail.setReadOnly(True)
        named(self.help_detail, "Method definition, example and limitations")
        layout.addWidget(self.help_detail)
        self.refresh_guidance()

        layout = self._page("Preferences", "Theme, density and text size are saved locally.")
        form = QFormLayout()
        self.theme_picker = QComboBox()
        self.theme_picker.addItems(["light", "dark", "contrast"])
        self.theme_picker.setCurrentText(self.prefs.theme)
        named(self.theme_picker, "Application color theme")
        form.addRow("Theme", self.theme_picker)
        self.density_picker = QComboBox()
        self.density_picker.addItems(["comfortable", "compact"])
        self.density_picker.setCurrentText(self.prefs.density)
        named(self.density_picker, "Workspace information density")
        form.addRow("Density", self.density_picker)
        self.scale_picker = QComboBox()
        self.scale_picker.addItems(["100%", "150%", "200%"])
        self.scale_picker.setCurrentText(f"{round(self.prefs.scale * 100)}%")
        named(self.scale_picker, "Text scaling factor")
        form.addRow("Text scaling", self.scale_picker)
        layout.addLayout(form)
        layout.addWidget(button("Apply and save preferences", self.save_preferences, primary=True))
        layout.addStretch()

        layout = self._page("Activity", "Local operation history for the current project.")
        self.activity_list = QListWidget()
        named(self.activity_list, "Project activity audit")
        layout.addWidget(self.activity_list)

        layout = self._page("About", "Original, free and open-source research workspace.")
        layout.addWidget(QLabel("ResearchWeave UI V2 · GPL-3.0-only · local demo"))
        layout.addWidget(QLabel("Prototype screens use local services with explicit limitations."))
        layout.addStretch()

    def _set_status(self, message: str) -> None:
        status = self.statusBar()
        if status is not None:
            status.showMessage(message)

    def _call(self, operation: str, **values: Any) -> dict[str, Any] | None:
        if operation not in ("ui.project.list", "ui.project.create", "ui.project.open",
                             "ui.templates.list", "ui.guidance.search",
                             "ui.backup.list", "ui.backup.inspect", "ui.backup.restore",
                             "ui.preferences.read", "ui.preferences.update", "ui.agent.propose",
                             "ui.agent.deny"):
            if not self.project_id:
                self._set_status("Create or select a project first.")
                return None
            values.setdefault("project_id", self.project_id)
        if operation in {
            "ui.project.update", "ui.source.add", "ui.review.vote", "ui.qual.annotate",
            "ui.dataset.import", "ui.manuscript.save", "ui.notebook.save", "ui.tutorial.step",
            "ui.protocol.start", "ui.protocol.update",
        }:
            values.setdefault("expected_revision", self.revision)
        result = self.facade.execute(operation, values)
        if result["status"] != "ok":
            error = result["error"]
            self._set_status(f"{error['message']} {error['recovery']}")
            return None
        payload = result["data"]
        if "revision" in payload:
            self.revision = payload["revision"]
        return cast(dict[str, Any], payload)

    def navigate(self, name: str) -> None:
        if name not in SCREENS:
            return
        index = SCREENS.index(name)
        self.pages.setCurrentIndex(index)
        self.page_heading.setText(name)
        if self.nav.currentRow() != index:
            self.nav.setCurrentRow(index)
        if name == "Library":
            self.search_sources()
        elif name == "Review":
            self.refresh_review()
        elif name == "Qualitative":
            self.refresh_annotations()
        elif name == "Activity":
            self.refresh_activity()
        elif name == "Protocol":
            self.refresh_protocol()
        elif name == "Guidance":
            self.refresh_guidance()
        elif name == "Backups":
            self.refresh_backups()
        elif name in ("Data View", "Variable View", "Statistics"):
            self.refresh_datasets()
        self.prefs.selected_screen = name

    def show_palette(self) -> None:
        dialog = CommandPalette(self)
        dialog.query.setFocus()
        dialog.exec()

    def focus_search(self) -> None:
        self.navigate("Search")
        self.global_query.setFocus()

    def search_global(self) -> None:
        self.global_results.clear()
        if not self.project_id:
            self.global_summary.setText("Open a local project to search.")
            return
        query = self.global_query.text().strip()
        if not query:
            self.global_summary.setText("Type a word or phrase, then search.")
            return
        kind = self.global_kind.currentText()
        response = self._call(
            "ui.search.global", query=query,
            kind="" if kind == "All" else kind, limit=500,
        )
        if response is None:
            return
        for hit in response["hits"]:
            item = QListWidgetItem(
                f"{hit['kind'].upper()} · {hit['title']}\n{hit['snippet']}"
            )
            item.setData(Qt.ItemDataRole.UserRole, hit)
            self.global_results.addItem(item)
        self.global_summary.setText(
            f"{response['total']} matching artifacts · "
            f"{response['search_method']}.\n"
            "Excerpts are unverified until checked against their original record."
        )

    def open_selected_search(self) -> None:
        selected = self.global_results.currentItem()
        if selected is not None:
            self.open_search_result(selected)

    def open_search_result(self, item: QListWidgetItem) -> None:
        hit = item.data(Qt.ItemDataRole.UserRole)
        if hit["kind"] in ("source", "annotation"):
            source_id = hit["source_id"]
            response = self._call("ui.source.get", source_id=source_id)
            if response is None:
                return
            source = response["source"]
            self.current_source_id = source_id
            self.reader_text.setPlainText(source["text"])
            self.reader_meta.setText(
                f"{source['title']} · {source['source_label']}\n"
                f"Verified: {source['verified']} · hash: {source['content_hash']}"
            )
            self.navigate("Reader")
        elif hit["kind"] == "protocol":
            self.navigate("Protocol")
        elif hit["kind"] == "notebook":
            self.navigate("Notebook")
        elif hit["kind"] == "manuscript":
            self.navigate("Manuscript")

    def refresh_projects(self) -> None:
        value = self._call("ui.project.list")
        if value is None:
            return
        self.project_picker.blockSignals(True)
        self.project_picker.clear()
        self.project_picker.addItem("Choose a project", "")
        for project in value["projects"]:
            self.project_picker.addItem(project["title"], project["id"])
        if self.project_id:
            index = self.project_picker.findData(self.project_id)
            if index >= 0:
                self.project_picker.setCurrentIndex(index)
        self.project_picker.blockSignals(False)

    def _selected_project(self, index: int) -> None:
        project_id = self.project_picker.itemData(index)
        if project_id:
            if project_id != self.project_id and not self._confirm_leave_project():
                self.refresh_projects()
                return
            self.open_project(project_id)

    def _writing_dirty(self) -> bool:
        return any(
            document is not None and document.isModified()
            for document in (
                self.manuscript_editor.document(), self.notebook_editor.document(),
                *(editor.document() for editor in self.protocol_fields.values()),
            )
        )

    def _confirm_leave_project(self) -> bool:
        """Protect draft text before project switching and application shutdown."""
        if not self.project_id or not self._writing_dirty():
            return True
        outcome = QMessageBox.question(
            self, "Unsaved research writing",
            "Save manuscript and notes before leaving this project?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if outcome == QMessageBox.StandardButton.Cancel:
            return False
        if outcome == QMessageBox.StandardButton.Save:
            if not self._save_both():
                QMessageBox.warning(
                    self, "Save failed",
                    "Your changes could not be saved. The project remains open. "
                    "Check the status message and retry.",
                )
                return False
        return True

    def _save_both(self) -> bool:
        """Do not declare a successful save after a failed optimistic revision check."""
        if not self.project_id:
            return False
        for operation, editor in (
            ("ui.manuscript.save", self.manuscript_editor),
            ("ui.notebook.save", self.notebook_editor),
        ):
            result = self._call(operation, **{
                operation.split(".")[1]: editor.toPlainText()
            })
            if result is None:
                return False
        if self.protocol_fields:
            values = {key: editor.toPlainText()
                      for key, editor in self.protocol_fields.items()}
            if self._call("ui.protocol.update", values=values) is None:
                return False
            for editor in self.protocol_fields.values():
                document = editor.document()
                if document is not None:
                    document.setModified(False)
        return True

    def create_project(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("New research project")
        named(dialog, "Create local research project")
        form = QFormLayout(dialog)
        title = QLineEdit()
        title.setPlaceholderText("e.g. Reading and attention")
        question = QLineEdit()
        question.setPlaceholderText("What do you want to understand?")
        study = QComboBox()
        study.addItems(["literature", "qualitative", "quantitative", "mixed"])
        for label, field in (("Project title", title), ("Research question", question),
                             ("Study type", study)):
            field.setAccessibleName(label)
            form.addRow(label, field)
        actions = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        actions.accepted.connect(dialog.accept)
        actions.rejected.connect(dialog.reject)
        form.addRow(actions)
        title.setFocus()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = self._call("ui.project.create", title=title.text(),
                            question=question.text(), study_type=study.currentText())
        if result:
            self.project_id = result["project_id"]
            self.refresh_projects()
            self.open_project(self.project_id)
            self.navigate("Dashboard")

    def open_project(self, project_id: str) -> None:
        response = self._call("ui.project.open", project_id=project_id)
        if response is None:
            return
        self.jobs.invalidate()
        project = response["project"]
        self.project_id = project["id"]
        self.revision = project["revision"]
        self.current_source_id = ""
        self.current_dataset_id = ""
        self.dashboard.setText(
            f"{project['title']}\n\nResearch question: {project['question']}\n"
            f"Study approach: {project['study_type']}\n"
            f"{len(project['sources'])} sources · {len(project['datasets'])} datasets"
        )
        self._editor_loading = True
        self.manuscript_editor.setPlainText(project["manuscript"])
        self.notebook_editor.setPlainText(project["notebook"])
        self._editor_loading = False
        self.tutorial.setText(
            f"Learning progress: {', '.join(project['tutorial_steps']) or 'create a source'}"
        )
        self.prefs.last_project_id = self.project_id
        self.facade.settings.save(self.prefs)
        self.search_sources()
        self.refresh_review()
        self.refresh_datasets()
        self.refresh_protocol()
        self._set_status(f"Opened {project['title']}")

    def _text_dialog(self, label: str) -> tuple[str, bool]:
        content, accepted = QInputDialog.getMultiLineText(self, label, label, "")
        return content, bool(accepted)

    def import_source(self) -> None:
        if not self.project_id:
            self._set_status("Create a project before importing a source.")
            return
        title, accepted = QInputDialog.getText(self, "Source title", "Title or identifier")
        if not accepted:
            return
        text, accepted = self._text_dialog("Source text")
        if not accepted:
            return
        data = self._call("ui.source.add", title=title, text=text)
        if data:
            self.search_sources()
            self.navigate("Library")

    def search_sources(self, query: str = "") -> None:
        if not self.project_id:
            return
        value = self._call("ui.source.search", query=self.search.text(), limit=500)
        if value is None:
            return
        self.library_list.clear()
        for source in value["sources"]:
            from PyQt6.QtWidgets import QListWidgetItem

            item = QListWidgetItem(f"{source['title']} · {source['source_label']}")
            item.setData(Qt.ItemDataRole.UserRole, source["id"])
            self.library_list.addItem(item)
        self._set_status(f"{value['total']} matching sources")

    def select_source(self) -> None:
        selected = self.library_list.currentItem()
        if selected is None:
            return
        source_id = selected.data(Qt.ItemDataRole.UserRole)
        value = self._call("ui.source.get", source_id=source_id)
        if value is None:
            return
        source = value["source"]
        self.current_source_id = source_id
        self.reader_meta.setText(
            f"{source['title']} · {source['source_label']} · "
            f"{'verified' if source['verified'] else 'unverified'}\n"
            f"SHA-256: {source['content_hash']}"
        )
        self.reader_text.setPlainText(source["text"])

    def vote(self, decision: str) -> None:
        selected = self.review_queue.currentItem()
        if selected is None:
            self._set_status("Select a source in the review queue first.")
            return
        selected_id = selected.data(Qt.ItemDataRole.UserRole)
        if self._call("ui.review.vote", source_id=selected_id,
                      decision=decision, reason=self.review_reason.text()):
            self.current_source_id = selected_id
            self.refresh_review()

    def _select_review_source(self, current: QListWidgetItem | None,
                              previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        self.current_source_id = current.data(Qt.ItemDataRole.UserRole)
        response = self._call("ui.source.get", source_id=self.current_source_id)
        if response:
            source = response["source"]
            self.reader_meta.setText(
                f"{source['title']} · {source['source_label']} · "
                f"{'verified' if source['verified'] else 'unverified'}"
            )
            self.reader_text.setPlainText(source["text"])

    def refresh_review(self, unused: str = "") -> None:
        if not self.project_id:
            return
        counts = self._call("ui.review.counts")
        if counts:
            self.review_summary.setText(
                f"Records: {counts['total']}; screened: {counts['screened']}; "
                f"include: {counts['include']}; exclude: {counts['exclude']}; "
                f"uncertain: {counts['unsure']}; pending: {counts['pending']}\n"
                f"{counts['note']}"
            )
        decision = self.review_filter.currentText()
        filtered = self._call(
            "ui.review.queue", limit=500,
            decision="" if decision == "All" else decision,
        )
        if filtered is None:
            return
        selected = self.review_queue.currentItem()
        previous_selection = selected.data(Qt.ItemDataRole.UserRole) if selected else ""
        self.review_queue.blockSignals(True)
        self.review_queue.clear()
        for source in filtered["records"]:
            item = QListWidgetItem(
                f"{source['status'].upper()} · {source['title']} · {source['source_label']}"
            )
            item.setData(Qt.ItemDataRole.UserRole, source["source_id"])
            self.review_queue.addItem(item)
            if source["source_id"] == previous_selection:
                self.review_queue.setCurrentItem(item)
        self.review_queue.blockSignals(False)
        self.review_reason.clear()

    def annotate_selection(self) -> None:
        if not self.current_source_id:
            self._set_status("Select a source in Library first.")
            return
        cursor = self.reader_text.textCursor()
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        if start == end:
            self._set_status("Highlight a passage in Reader before coding.")
            return
        code, accepted = QInputDialog.getText(self, "Code selected source text", "Code label")
        if accepted and self._call("ui.qual.annotate", source_id=self.current_source_id,
                                   start=start, end=end, code=code):
            self.refresh_annotations()

    def refresh_annotations(self) -> None:
        self.annotation_list.clear()
        if not self.project_id:
            return
        value = self._call("ui.qual.list")
        if value:
            for item in value["annotations"]:
                self.annotation_list.addItem(f"{item['code']}: {item['quote'][:120]}")

    def import_csv(self) -> None:
        if not self.project_id:
            self._set_status("Create a project first.")
            return
        name, accepted = QInputDialog.getText(self, "Dataset", "Dataset name")
        if not accepted:
            return
        csv_text, accepted = self._text_dialog("CSV with header row")
        if accepted and self._call("ui.dataset.import", name=name, csv_text=csv_text):
            self.refresh_datasets()

    def refresh_datasets(self) -> None:
        if not self.project_id:
            return
        response = self._call("ui.dataset.list")
        if response is None:
            return
        datasets = response["datasets"]
        self.variable_list.clear()
        self.variable_picker.clear()
        self.dataset_picker.blockSignals(True)
        self.dataset_picker.clear()
        if not datasets:
            self.data_model.set_records([], [])
            self.dataset_picker.blockSignals(False)
            self.data_page_status.setText("No dataset imported")
            return
        for dataset in datasets:
            self.dataset_picker.addItem(dataset["name"], dataset["id"])
        current = self.dataset_picker.findData(self.current_dataset_id)
        self.dataset_picker.setCurrentIndex(current if current >= 0 else 0)
        self.dataset_picker.blockSignals(False)
        self._selected_dataset(self.dataset_picker.currentIndex())

    def _selected_dataset(self, index: int) -> None:
        if index < 0:
            return
        self.current_dataset_id = self.dataset_picker.itemData(index)
        self.data_offset = 0
        self.load_data_page()
        self.variable_list.clear()
        self.variable_picker.clear()
        response = self._call("ui.dataset.variables", dataset_id=self.current_dataset_id)
        if response is not None:
            for variable in response["variables"]:
                self.variable_list.addItem(
                    f"{variable['name']} · {variable['inferred_type']} · "
                    f"missing {variable['missing_n']} / {response['total_rows']}"
                )
                self.variable_picker.addItem(variable["name"])

    def load_data_page(self) -> None:
        if not self.current_dataset_id:
            self.data_model.set_records([], [])
            return
        response = self._call(
            "ui.dataset.page", dataset_id=self.current_dataset_id,
            offset=self.data_offset, limit=self.data_page_size,
        )
        if response is None:
            return
        self.data_total = response["total"]
        self.data_model.set_records(response["columns"], response["rows"])
        beginning = self.data_offset + 1 if self.data_total else 0
        last = min(self.data_offset + len(response["rows"]), self.data_total)
        self.data_page_status.setText(
            f"Rows {beginning}–{last} of {self.data_total} · synthetic or imported data"
        )

    def previous_data_page(self) -> None:
        if self.data_offset > 0:
            self.data_offset = max(0, self.data_offset - self.data_page_size)
            self.load_data_page()

    def next_data_page(self) -> None:
        if self.data_offset + self.data_page_size < self.data_total:
            self.data_offset += self.data_page_size
            self.load_data_page()

    def run_summary(self) -> None:
        if not self.current_dataset_id:
            self._set_status("Import CSV data in Data View first.")
            return
        result = self._call("ui.dataset.describe", dataset_id=self.current_dataset_id,
                            column=self.variable_picker.currentText())
        if result is not None:
            self.stats_result.setPlainText("\n".join(
                f"{key}: {value}" for key, value in result.items()
            ))

    def save_text(self, which: str) -> None:
        if not self.project_id:
            self._set_status("Select a project first.")
            return
        editor = self.manuscript_editor if which == "manuscript" else self.notebook_editor
        if self._call(f"ui.{which}.save", **{which: editor.toPlainText()}):
            self._set_status(f"Saved {which} locally")

    def save_active(self) -> None:
        screen = SCREENS[self.pages.currentIndex()]
        if screen in ("Manuscript", "Notebook"):
            self.save_text(screen.lower())
        else:
            self._set_status("Project records save automatically after each operation.")

    def preview_agent(self) -> None:
        result = self._call("ui.agent.propose",
                            summary=self.agent_proposal.toPlainText(),
                            risk=self.risk_picker.currentText())
        if result:
            self.agent_status.setText(
                f"Review needed · {result['effect']}\n"
                f"Nothing executed. Proposal: {result['proposal']}"
            )

    def deny_agent(self) -> None:
        result = self._call("ui.agent.deny",
                            summary=self.agent_proposal.toPlainText())
        if result:
            self.agent_status.setText(result["message"])

    def preview_export(self) -> None:
        result = self._call("ui.export.preview", filename=self.export_name.text())
        if result:
            self.export_receipt.setText(
                f"{result['filename']} · {result['bytes']} bytes\n"
                f"SHA-256: {result['sha256']}\nDestination: {result['destination']}"
            )

    def export_file(self) -> None:
        preview = self._call("ui.export.preview", filename=self.export_name.text())
        if preview is None:
            return
        outcome = QMessageBox.question(
            self, "Approve local export",
            f"Write {preview['filename']} ({preview['bytes']} bytes) to your local export folder?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if outcome != QMessageBox.StandardButton.Yes:
            self._set_status("Export cancelled. No file was written.")
            return
        # Trusted UI approval exists only within this synchronous user action.
        previous = self.facade.export_authorizer
        self.facade.export_authorizer = lambda filename: filename == preview["filename"]
        try:
            receipt = self._call("ui.export.write", filename=self.export_name.text())
        finally:
            self.facade.export_authorizer = previous
        if receipt:
            self.export_receipt.setText(
                f"Exported: {receipt['path']}\nSHA-256: {receipt['sha256']}"
            )

    def preview_backup(self) -> None:
        if not self.project_id:
            self._set_status("Create or select a project first.")
            return
        result = self._call("ui.backup.plan")
        if result is not None:
            self.backup_receipt.setText(
                f"Preview only · {result['title']} · revision {result['revision']}\n"
                f"{result['source_count']} sources · {result['dataset_count']} datasets\n"
                f"Content SHA-256: {result['content_sha256']}\n"
                f"Destination: {result['destination']}\n"
                "Passwords and AI credentials are excluded."
            )

    def create_backup(self) -> None:
        if not self.project_id:
            self._set_status("Choose a project before backing it up.")
            return
        plan = self._call("ui.backup.plan")
        if plan is None:
            return
        if QMessageBox.question(
            self, "Approve local snapshot",
            f"Write a new immutable backup for {plan['title']}, revision "
            f"{plan['revision']}? Existing backups will be preserved.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            self._set_status("Backup canceled. No data was written.")
            return
        old = self.facade.backup_authorizer
        self.facade.backup_authorizer = (
            lambda action, identifier: action == "create"
            and identifier == self.project_id
        )
        try:
            result = self._call(
                "ui.backup.create", expected_revision=plan["revision"]
            )
        finally:
            self.facade.backup_authorizer = old
        if result is not None:
            self.backup_receipt.setText(
                f"Verified snapshot: {result['backup_id']}\n"
                f"SHA-256: {result['sha256']}\n"
                f"{result['bytes']} bytes written."
            )
            self.refresh_backups()

    def refresh_backups(self) -> None:
        response = self._call("ui.backup.list")
        if response is None:
            return
        self.backup_list.clear()
        for record in response["backups"]:
            name = record["backup_id"]
            status = record["integrity"]
            item = QListWidgetItem(f"{name} · {status}")
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.backup_list.addItem(item)

    def inspect_backup(self, current: QListWidgetItem | None,
                       previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        name = current.data(Qt.ItemDataRole.UserRole)
        response = self._call("ui.backup.inspect", backup_id=name)
        if response is not None:
            self.backup_receipt.setText(
                f"{response['title']} · revision {response['revision']}\n"
                f"Verified SHA-256: {response['sha256']}\n"
                f"{response['source_count']} sources · "
                f"{response['dataset_count']} datasets\n"
                f"{response['effect']}"
            )

    def restore_backup(self) -> None:
        item = self.backup_list.currentItem()
        if item is None:
            self._set_status("Select a valid backup in the list first.")
            return
        backup_id = item.data(Qt.ItemDataRole.UserRole)
        verified = self._call("ui.backup.inspect", backup_id=backup_id)
        if verified is None:
            return
        if QMessageBox.question(
            self, "Approve recovery",
            f"Restore {verified['title']} from this verified archive "
            "as an additional project? No existing project will be overwritten.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            self._set_status("Restore cancelled.")
            return
        if not self._confirm_leave_project():
            return
        previous = self.facade.backup_authorizer
        self.facade.backup_authorizer = (
            lambda action, identifier: action == "restore" and identifier == backup_id
        )
        try:
            restored = self._call(
                "ui.backup.restore", backup_id=backup_id,
                expected_sha256=verified["sha256"],
            )
        finally:
            self.facade.backup_authorizer = previous
        if restored is not None:
            self.refresh_projects()
            self.open_project(restored["restored_project_id"])
            self.navigate("Dashboard")
            self._set_status("Verified snapshot restored to a separate local project.")

    def cancel_job(self) -> None:
        selected = self.job_list.currentItem()
        if selected:
            self.jobs.cancel(selected.text().split(": ", 1)[0])

    def save_preferences(self) -> None:
        values = {
            "theme": self.theme_picker.currentText(),
            "density": self.density_picker.currentText(),
            "scale": float(self.scale_picker.currentText().rstrip("%")) / 100,
            "sidebar_width": self.splitter.sizes()[0],
        }
        response = self._call("ui.preferences.update", **values)
        if response:
            self.prefs = Preferences(**response["preferences"])
            app = QApplication.instance()
            if isinstance(app, QApplication):
                apply_theme(app, self.prefs)
            self._set_status("Preferences saved.")

    def refresh_activity(self) -> None:
        self.activity_list.clear()
        if self.project_id:
            value = self._call("ui.activity.list")
            if value:
                for event in value["events"]:
                    self.activity_list.addItem(
                        f"{event['sequence']} · {event['operation']} · {event['timestamp']}"
                    )

    def _refresh_templates(self) -> None:
        response = self._call("ui.templates.list")
        if response is None:
            return
        self.template_picker.clear()
        for template in response["templates"]:
            self.template_picker.addItem(
                f"{template['title']} · {template['family']}", template["id"]
            )

    def start_protocol(self) -> None:
        if not self.project_id:
            self._set_status("Create a project before starting a protocol.")
            return
        template_id = self.template_picker.currentData()
        if not template_id:
            return
        response = self._call("ui.protocol.start", template_id=template_id)
        if response is not None:
            self.refresh_protocol()
            self._set_status("Protocol draft started. Edit the fields before validation.")

    def _clear_protocol_form(self) -> None:
        self.protocol_fields.clear()
        while self.protocol_form.count():
            child = self.protocol_form.takeAt(0)
            if child is None:
                break
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

    def refresh_protocol(self) -> None:
        if self.protocol_fields and any(
            bool(document and document.isModified())
            for document in (editor.document() for editor in self.protocol_fields.values())
        ):
            if not self._confirm_leave_project():
                return
        self._clear_protocol_form()
        if not self.project_id:
            self.protocol_summary.setText("Create a project to start a protocol.")
            return
        response = self._call("ui.protocol.read")
        if response is None:
            return
        record = response["protocol"]
        if not record:
            self.protocol_summary.setText(
                "No protocol draft yet. Select a research design and start a template."
            )
            return
        self.protocol_summary.setText(
            f"Draft · {record['template_title']}\n"
            f"Steps: {' → '.join(record['guidance'])}\n"
            f"Cautions: {'; '.join(record['cautions'])}"
        )
        templates = self._call("ui.templates.list")
        if templates is None:
            return
        matched = next(
            (template for template in templates["templates"]
             if template["id"] == record["template_id"]), None
        )
        if matched is None:
            self._set_status("Protocol template is missing; preserve existing draft.")
            return
        for spec in matched["fields"]:
            editor = QPlainTextEdit()
            editor.setMinimumHeight(65)
            editor.setMaximumHeight(125)
            editor.setPlainText(record["values"].get(spec["name"], ""))
            editor.setPlaceholderText(spec["help_text"])
            named(editor, f"{spec['label']} {'required' if spec['required'] else 'optional'}",
                  spec["help_text"])
            self.protocol_form.addRow(
                f"{spec['label']} {'*' if spec['required'] else ''}", editor,
            )
            self.protocol_fields[spec["name"]] = editor

    def save_protocol(self) -> None:
        if not self.protocol_fields:
            self._set_status("Start a protocol draft first.")
            return
        values = {key: editor.toPlainText() for key, editor in self.protocol_fields.items()}
        response = self._call("ui.protocol.update", values=values)
        if response is not None:
            progress = response["completion"]
            for editor in self.protocol_fields.values():
                document = editor.document()
                if document is not None:
                    document.setModified(False)
            self.protocol_summary.setText(
                f"Draft saved · {progress['filled_count']}/{progress['total_fields']} "
                "fields with content.\n"
                "Required incomplete: "
                f"{', '.join(progress['required_missing']) or 'none'}\n"
                "Completion is not ethics approval or scientific validation."
            )

    def validate_protocol(self) -> None:
        self.save_protocol()
        if not self.protocol_fields:
            return
        response = self._call("ui.protocol.complete")
        if response is not None:
            self.protocol_summary.setText(
                f"{response['template']}: required fields are complete.\n"
                f"{response['note']}"
            )

    def refresh_guidance(self, unused: str = "") -> None:
        response = self._call("ui.guidance.search", query=self.help_query.text())
        if response is None:
            return
        self.help_list.clear()
        for item in response["guidance"]:
            record = QListWidgetItem(item["heading"])
            record.setData(Qt.ItemDataRole.UserRole, item)
            self.help_list.addItem(record)
        if self.help_list.count():
            self.help_list.setCurrentRow(0)
        else:
            self.help_detail.setPlainText(
                "No matching topic. Try a general term such as source or variable."
            )

    def _select_guidance(self, current: QListWidgetItem | None,
                         previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        item = current.data(Qt.ItemDataRole.UserRole)
        self.help_detail.setPlainText(
            f"{item['heading']}\n\n"
            f"Definition: {item['summary']}\n\n"
            f"Example: {item['example']}\n\n"
            f"Limitations: {item['caveat']}\n\n"
            f"Next action: {item['next_action']}"
        )

    def closeEvent(self, event: QCloseEvent | None) -> None:
        if event is None:
            return
        if not self._confirm_leave_project():
            event.ignore()
            return
        self.jobs.invalidate()
        self.prefs.sidebar_width = max(150, min(480, self.splitter.sizes()[0]))
        self.facade.settings.save(self.prefs)
        event.accept()

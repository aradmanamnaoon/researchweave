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
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
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
    "Dashboard", "Library", "Reader", "Review", "Data View", "Variable View",
    "Statistics", "Qualitative", "Manuscript", "Notebook", "Agent", "Privacy",
    "Exports", "Jobs", "Preferences", "Activity", "About",
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
        self.tutorial = QLabel("First steps: create project → add source → notes → export")
        layout.addWidget(self.tutorial)
        layout.addStretch()

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
        self.data_table = QTableView()
        named(self.data_table, "Dataset grid with labeled column and row headers")
        self.data_model = ResearchTableModel()
        self.data_table.setModel(self.data_model)
        layout.addWidget(self.data_table)

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

        layout = self._page("Jobs", "Long operations use cancellable supervised Qt tasks.")
        self.job_list = QListWidget()
        named(self.job_list, "Background job statuses")
        layout.addWidget(self.job_list)
        layout.addWidget(button("Cancel selected job", self.cancel_job))
        self.jobs.changed.connect(lambda key, state: self.job_list.addItem(f"{key}: {state}"))

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
        form.addRow("Density", self.density_picker)
        self.scale_picker = QComboBox()
        self.scale_picker.addItems(["100%", "150%", "200%"])
        self.scale_picker.setCurrentText(f"{round(self.prefs.scale * 100)}%")
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
                             "ui.preferences.read", "ui.preferences.update", "ui.agent.propose",
                             "ui.agent.deny"):
            if not self.project_id:
                self._set_status("Create or select a project first.")
                return None
            values.setdefault("project_id", self.project_id)
        if operation in {
            "ui.project.update", "ui.source.add", "ui.review.vote", "ui.qual.annotate",
            "ui.dataset.import", "ui.manuscript.save", "ui.notebook.save", "ui.tutorial.step",
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
        elif name in ("Data View", "Variable View", "Statistics"):
            self.refresh_datasets()
        self.prefs.selected_screen = name

    def show_palette(self) -> None:
        dialog = CommandPalette(self)
        dialog.query.setFocus()
        dialog.exec()

    def focus_search(self) -> None:
        self.navigate("Library")
        self.search.setFocus()

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
            self.open_project(project_id)

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
        if not self.current_source_id:
            self._set_status("Select a source in Library before screening.")
            return
        if self._call("ui.review.vote", source_id=self.current_source_id,
                      decision=decision, reason=self.review_reason.text()):
            self.refresh_review()

    def refresh_review(self) -> None:
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
        response = self._call("ui.project.open")
        if response is None:
            return
        datasets = response["project"]["datasets"]
        self.variable_list.clear()
        self.variable_picker.clear()
        if not datasets:
            self.data_model.set_records([], [])
            return
        dataset = datasets[0]
        self.current_dataset_id = dataset["id"]
        self.data_model.set_records(dataset["columns"], dataset["rows"])
        self.variable_list.addItems(dataset["columns"])
        self.variable_picker.addItems(dataset["columns"])

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

    def closeEvent(self, event: QCloseEvent | None) -> None:
        if event is None:
            return
        manuscript_doc = self.manuscript_editor.document()
        notebook_doc = self.notebook_editor.document()
        dirty = (self.project_id and
                 ((manuscript_doc is not None and manuscript_doc.isModified()) or
                  (notebook_doc is not None and notebook_doc.isModified())))
        if dirty:
            outcome = QMessageBox.question(
                self, "Unsaved writing",
                "Save changes to your manuscript and notebook before closing?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save,
            )
            if outcome == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if outcome == QMessageBox.StandardButton.Save:
                self.save_text("manuscript")
                self.save_text("notebook")
        self.jobs.invalidate()
        self.prefs.sidebar_width = max(150, min(480, self.splitter.sizes()[0]))
        self.facade.settings.save(self.prefs)
        event.accept()

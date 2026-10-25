"""Functional PyQt6 desktop shell; every enabled action routes to a local service."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from threading import Event
from typing import Any, cast

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QAction, QCloseEvent, QFont, QIcon, QKeySequence, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
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
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .analysis_compatibility import COMPATIBILITY_COLUMNS, build_compatibility_rows
from .analysis_forms import FieldSpec, build_field_specs, parse_form_values
from .assets import asset_path
from .contracts import Preferences, UIError
from .design import apply_theme, named
from .facade import UIFacade
from .i18n import Localizer
from .jobs import JobManager
from .models import ResearchTableModel
from .pdf_reader import PDFReader
from .presets import WORKSPACE_SCREENS
from .result_presentation import format_result_record
from .text_offsets import codepoint_range_to_qt, qt_range_to_codepoints
from .visualization import Bin, ChartSpec, HistogramWidget

SCREENS = WORKSPACE_SCREENS

NAVIGATION_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Start", ("Welcome", "Dashboard", "Question", "Search", "Protocol")),
    ("Evidence", ("Library", "Reader", "PDF Reader", "Evidence", "Review", "PRISMA", "Extraction")),
    (
        "Analyze",
        (
            "Data View",
            "Variable View",
            "Statistics",
            "Analysis Results",
            "Qualitative",
            "Codebook",
            "Mixed Methods",
        ),
    ),
    ("Write", ("Manuscript", "References", "Notebook", "Publishing")),
    ("Assist", ("Agent", "Providers", "Privacy", "Integrations")),
    (
        "Project",
        ("Exports", "Backups", "Recovery", "Diagnostics", "Jobs", "Notifications", "Activity"),
    ),
    ("Learn & settings", ("Tutorials", "Guidance", "Shortcuts", "Preferences", "About")),
)
NAV_GROUP_BY_SCREEN = {screen: group for group, screens in NAVIGATION_GROUPS for screen in screens}


def button(text: str, callback: Callable[..., Any], *, primary: bool = False) -> QPushButton:
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


def surface(
    title: str = "",
    description: str = "",
    *,
    kind: str = "surface",
) -> tuple[QFrame, QVBoxLayout]:
    """Create a consistent content surface with optional heading and helper copy."""

    frame = QFrame()
    frame.setObjectName(kind)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(10)
    if title:
        label = QLabel(title)
        label.setObjectName("surfaceTitle")
        layout.addWidget(label)
    if description:
        helper = QLabel(description)
        helper.setWordWrap(True)
        helper.setObjectName("pageLead")
        layout.addWidget(helper)
    return frame, layout


def metric_card(label: str, value: str = "—", detail: str = "") -> tuple[QFrame, QLabel, QLabel]:
    """Create a compact dashboard metric card with accessible text labels."""

    frame = QFrame()
    frame.setObjectName("metricCard")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(3)
    label_widget = QLabel(label.upper())
    label_widget.setObjectName("metricLabel")
    value_widget = QLabel(value)
    value_widget.setObjectName("metricValue")
    detail_widget = QLabel(detail)
    detail_widget.setObjectName("metricDetail")
    detail_widget.setWordWrap(True)
    layout.addWidget(label_widget)
    layout.addWidget(value_widget)
    layout.addWidget(detail_widget)
    return frame, value_widget, detail_widget


def empty_list_item(text: str) -> QListWidgetItem:
    """Return explanatory list content that cannot be mistaken for project data."""

    item = QListWidgetItem(text)
    item.setFlags(Qt.ItemFlag.ItemIsEnabled)
    item.setData(Qt.ItemDataRole.UserRole, None)
    return item


def display_local_path(path: Path) -> str:
    """Render common private path prefixes without exposing the local account name."""

    resolved = path.resolve()
    anchors = (
        (Path(tempfile.gettempdir()).resolve(), "%TEMP%"),
        (Path.home().resolve(), "~"),
    )
    for anchor, label in anchors:
        try:
            relative = resolved.relative_to(anchor)
        except ValueError:
            continue
        suffix = str(relative)
        return label if not suffix else f"{label}\\{suffix}"
    return str(resolved)


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
        parent = self.parent()
        if not isinstance(parent, ResearchWindow):
            return
        entries = parent.command_entries()
        exact_screen = next(
            (
                entry
                for entry in entries
                if entry["kind"] == "screen"
                and entry["value"].casefold() == query.strip().casefold()
            ),
            None,
        )
        if exact_screen is not None:
            entries = [exact_screen]
        for entry in entries:
            searchable = f"{entry['label']} {entry.get('summary', '')}".casefold()
            if query.casefold() not in searchable:
                continue
            suffix = "" if entry["enabled"] else f" · disabled: {entry['reason']}"
            item = QListWidgetItem(f"{entry['label']}{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, entry)
            item.setToolTip(entry.get("summary", "") or entry.get("reason", ""))
            self.results.addItem(item)
        if self.results.count():
            self.results.setCurrentRow(0)

    def activate(self) -> None:
        current = self.results.currentItem()
        if current is None:
            return
        parent = self.parent()
        if not isinstance(parent, ResearchWindow):
            return
        entry = current.data(Qt.ItemDataRole.UserRole)
        if not entry["enabled"]:
            parent._set_status(entry["reason"])
            return
        self.accept()
        parent.execute_palette_entry(entry)


class ResearchWindow(QMainWindow):
    def __init__(self, facade: UIFacade) -> None:
        super().__init__()
        self.facade = facade
        self.prefs = self.facade.settings.load()
        self.project_id = self.prefs.last_project_id
        self.revision = 0
        self.current_source_id = ""
        self.current_dataset_id = ""
        self.project_title = ""
        self.assistant_conversation_id: str | None = None
        self.assistant_pending_tool: dict[str, Any] | None = None
        self.assistant_model_available = False
        self._editor_loading = False
        self._screen_focus: dict[str, QWidget] = {}
        self.protocol_fields: dict[str, QPlainTextEdit] = {}
        self.extraction_pending_fields: list[dict[str, Any]] = []
        self.extraction_value_widgets: dict[str, QWidget] = {}
        self.jobs = JobManager()
        self.jobs.error.connect(lambda _key, message: self._set_status(message))
        self.jobs.changed.connect(lambda key, state: self._set_status(f"{key}: {state}"))
        self.jobs.changed.connect(lambda _key, _state: self._refresh_dashboard_if_visible())
        self.jobs.progress.connect(lambda _key, _value: self._refresh_dashboard_if_visible())
        self.jobs.chunk.connect(self._assistant_chunk)
        self.jobs.result.connect(self._assistant_job_result)
        self.jobs.error.connect(self._assistant_job_error)
        self.jobs.changed.connect(self._assistant_job_changed)
        self.setWindowTitle("ResearchWeave · Local research desktop")
        self.base_window_title = "ResearchWeave"
        self.setMinimumSize(760, 490)
        self.resize(max(760, self.prefs.window_width), max(490, self.prefs.window_height))
        self._build()
        self._draft_timers: dict[str, QTimer] = {}
        for field, editor in (
            ("manuscript", self.manuscript_editor),
            ("notebook", self.notebook_editor),
        ):
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(250)
            timer.timeout.connect(lambda which=field: self._journal_editor(which))
            editor.textChanged.connect(lambda which=field: self._schedule_journal(which))
            self._draft_timers[field] = timer
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, self.prefs)
        self.refresh_projects()
        if self.project_id:
            self.open_project(self.project_id)
        if not self.prefs.onboarding_complete:
            self.navigate("Welcome")
        else:
            self.navigate(
                self.prefs.selected_screen if self.prefs.selected_screen in SCREENS else "Dashboard"
            )
        self._set_status("Offline-ready · no AI credentials required")

    def _build(self) -> None:
        root = QWidget()
        row = QHBoxLayout(root)
        row.setContentsMargins(14, 14, 14, 8)
        row.setSpacing(12)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        row.addWidget(self.splitter)
        self.setCentralWidget(root)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 16, 14, 14)
        side.setSpacing(8)
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        mark = QLabel()
        mark.setFixedSize(36, 36)
        mark_icon = QIcon(str(asset_path("researchweave-mark.svg")))
        if not mark_icon.isNull():
            mark.setPixmap(mark_icon.pixmap(QSize(34, 34)))
        mark.setAccessibleName("ResearchWeave mark")
        brand_row.addWidget(mark, 0, Qt.AlignmentFlag.AlignTop)
        brand_copy = QVBoxLayout()
        brand_copy.setSpacing(0)
        brand = QLabel("researchweave")
        brand.setObjectName("brandTitle")
        brand_context = QLabel("LOCAL RESEARCH WORKSPACE")
        brand_context.setObjectName("eyebrow")
        brand_copy.addWidget(brand)
        brand_copy.addWidget(brand_context)
        brand_row.addLayout(brand_copy, 1)
        side.addLayout(brand_row)
        project_label = QLabel("PROJECT")
        project_label.setObjectName("eyebrow")
        side.addWidget(project_label)
        self.project_search = QLineEdit()
        self.project_search.setPlaceholderText("Find local projects")
        named(self.project_search, "Search recent local projects")
        self.project_search.textChanged.connect(self.refresh_projects)
        side.addWidget(self.project_search)
        self.project_picker = QComboBox()
        named(self.project_picker, "Current project")
        self.project_picker.currentIndexChanged.connect(self._selected_project)
        side.addWidget(self.project_picker)
        side.addWidget(button("＋ New project", self.create_project, primary=True))
        workflow_label = QLabel("WORKFLOW")
        workflow_label.setObjectName("eyebrow")
        side.addWidget(workflow_label)
        self.nav = QTreeWidget()
        self.nav.setObjectName("workspaceNav")
        self.nav.setHeaderHidden(True)
        self.nav.setIndentation(14)
        self.nav.setRootIsDecorated(True)
        named(
            self.nav,
            "Workspace navigation",
            "Use arrow keys to move through grouped research workspaces and Enter to activate.",
        )
        self._nav_items: dict[str, QTreeWidgetItem] = {}
        self._nav_groups: dict[str, QTreeWidgetItem] = {}
        for group_name, screens in NAVIGATION_GROUPS:
            group_item = QTreeWidgetItem([group_name])
            group_item.setExpanded(False)
            group_font = QFont(self.font())
            group_font.setBold(True)
            group_font.setPointSizeF(max(8.0, group_font.pointSizeF() * 0.88))
            group_item.setFont(0, group_font)
            self.nav.addTopLevelItem(group_item)
            self._nav_groups[group_name] = group_item
            for screen in screens:
                item = QTreeWidgetItem([screen])
                item.setData(0, Qt.ItemDataRole.UserRole, screen)
                group_item.addChild(item)
                self._nav_items[screen] = item
        self.nav.currentItemChanged.connect(
            lambda current, _previous: (
                self.navigate(str(current.data(0, Qt.ItemDataRole.UserRole)))
                if current is not None and current.data(0, Qt.ItemDataRole.UserRole)
                else None
            )
        )
        side.addWidget(self.nav)
        palette_button = button("Commands  ·  Ctrl+K", self.show_palette)
        palette_button.setObjectName("quiet")
        side.addWidget(palette_button)
        self.splitter.addWidget(sidebar)
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 2, 0, 0)
        center_layout.setSpacing(10)
        header_surface = QFrame()
        header_surface.setObjectName("headerSurface")
        header_surface_layout = QHBoxLayout(header_surface)
        header_surface_layout.setContentsMargins(16, 10, 12, 10)
        header = header_surface_layout
        header.setSpacing(16)
        header_titles = QVBoxLayout()
        header_titles.setSpacing(1)
        self.page_context = QLabel("START")
        self.page_context.setObjectName("eyebrow")
        self.page_heading = heading("Dashboard")
        header_titles.addWidget(self.page_context)
        header_titles.addWidget(self.page_heading)
        header.addLayout(header_titles, 1)
        self.project_context = QLabel("No project selected · local only")
        self.project_context.setObjectName("projectContext")
        self.project_context.setAccessibleName("Current project and privacy status")
        header.addWidget(self.project_context, 0, Qt.AlignmentFlag.AlignVCenter)
        header_command = button("Commands · Ctrl+K", self.show_palette)
        header_command.setObjectName("quiet")
        header.addWidget(header_command, 0, Qt.AlignmentFlag.AlignVCenter)
        center_layout.addWidget(header_surface)
        self.pages = QStackedWidget()
        self.pages.setAccessibleName("Active research workspace")
        center_layout.addWidget(self.pages)
        self.splitter.addWidget(center)
        self.splitter.setSizes([max(248, self.prefs.sidebar_width), 930])
        self._build_pages()
        self._set_status("Ready")
        self._shortcut("Ctrl+K", self.show_palette)
        self._shortcut("Ctrl+N", self.create_project)
        self._shortcut("Ctrl+F", self.focus_search)
        self._shortcut("Ctrl+S", self.save_active)
        self._shortcut("Ctrl+Shift+A", self.annotate_selection)
        self._shortcut("Ctrl+1", lambda: self.navigate("Dashboard"))
        self._shortcut("Ctrl+2", lambda: self.navigate("Library"))
        self._shortcut("Ctrl+L", self.focus_library_search)
        self._shortcut("Ctrl+Shift+E", self.focus_export)
        self._shortcut("F1", self.open_context_help)

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
        intro = QHBoxLayout()
        intro.setSpacing(12)
        summary = QLabel(explanation)
        summary.setWordWrap(True)
        summary.setObjectName("pageLead")
        intro.addWidget(summary, 1)
        if name not in ("Guidance", "Shortcuts"):
            help_button = button(
                "Help",
                lambda _checked=False, screen=name: self.open_context_help(screen),
            )
            help_button.setObjectName("quiet")
            help_button.setToolTip(f"Open contextual help for {name}")
            intro.addWidget(help_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(intro)
        scroll = QScrollArea()
        scroll.setObjectName("pageScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        named(scroll, f"{name} workspace")
        page.setAccessibleName(f"{name} workspace content")
        self.pages.addWidget(scroll)
        return layout

    def _build_pages(self) -> None:
        layout = self._page(
            "Welcome",
            "ResearchWeave works locally without an account, API key or AI provider. "
            "Start with your own question or open a clearly labeled synthetic demo.",
        )
        self.welcome_status = QLabel(
            "Beginner path: create project → structure question → add a source → "
            "screen/capture evidence → write notes → preview export."
        )
        self.welcome_status.setWordWrap(True)
        self.welcome_status.setObjectName("pageLead")
        hero = QFrame()
        hero.setObjectName("heroSurface")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(20, 20, 20, 20)
        hero_layout.setSpacing(22)
        hero_copy = QVBoxLayout()
        hero_copy.setSpacing(10)
        hero_title = QLabel("Build a research trail you can inspect and reproduce.")
        hero_title.setObjectName("sectionTitle")
        hero_title.setWordWrap(True)
        hero_copy.addWidget(hero_title)
        hero_copy.addWidget(self.welcome_status)
        welcome_actions = QHBoxLayout()
        welcome_actions.addWidget(button("Create project", self.create_project, primary=True))
        welcome_actions.addWidget(button("Explore synthetic demo", self.create_local_demo))
        welcome_actions.addStretch(1)
        hero_copy.addLayout(welcome_actions)
        welcome_secondary = QHBoxLayout()
        welcome_secondary.addWidget(
            button("Research-question guide", lambda: self.navigate("Question"))
        )
        finish_button = button("Finish onboarding", self.finish_onboarding)
        finish_button.setObjectName("quiet")
        welcome_secondary.addWidget(finish_button)
        welcome_secondary.addStretch(1)
        hero_copy.addLayout(welcome_secondary)
        self.welcome_privacy = QLabel(
            "No provider is required. Demo content is synthetic and is not a research finding."
        )
        self.welcome_privacy.setWordWrap(True)
        self.welcome_privacy.setObjectName("muted")
        hero_copy.addWidget(self.welcome_privacy)
        hero_layout.addLayout(hero_copy, 1)
        layout.addWidget(hero)
        layout.addStretch()

        layout = self._page("Dashboard", "Start with a research question. Your work stays local.")
        dashboard_surface, dashboard_layout = surface(
            "Project pulse",
            "A compact view of the current project, active work and research-state warnings.",
        )
        self.dashboard = QLabel("Choose a project or create a new one.")
        self.dashboard.setWordWrap(True)
        self.dashboard.setObjectName("pageLead")
        dashboard_layout.addWidget(self.dashboard)
        refresh_dashboard = button("Refresh", self.refresh_dashboard)
        refresh_dashboard.setObjectName("quiet")
        dashboard_layout.addWidget(refresh_dashboard, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(dashboard_surface)
        metric_row = QHBoxLayout()
        metric_row.setSpacing(10)
        source_card, self.dashboard_sources_value, self.dashboard_sources_detail = metric_card(
            "Sources", "—", "Local evidence inputs"
        )
        dataset_card, self.dashboard_datasets_value, self.dashboard_datasets_detail = metric_card(
            "Datasets", "—", "Structured analysis inputs"
        )
        (
            screening_card,
            self.dashboard_screening_value,
            self.dashboard_screening_detail,
        ) = metric_card("Screening", "—", "Pending / conflict / final")
        writing_card, self.dashboard_writing_value, self.dashboard_writing_detail = metric_card(
            "Writing", "—", "Manuscript + notes"
        )
        for card in (source_card, dataset_card, screening_card, writing_card):
            metric_row.addWidget(card, 1)
        layout.addLayout(metric_row)
        action_surface, dashboard_actions = surface(
            "Continue your workflow",
            "Keep the next common actions close without crowding every research screen.",
            kind="toolbarSurface",
        )
        quick_actions = QHBoxLayout()
        quick_actions.addWidget(button("New project", self.create_project, primary=True))
        quick_actions.addWidget(button("Add source", self.import_source))
        quick_actions.addWidget(button("Research protocol", lambda: self.navigate("Protocol")))
        quick_actions.addWidget(button("Open notebook", lambda: self.navigate("Notebook")))
        quick_actions.addWidget(button("Preview export", lambda: self.navigate("Exports")))
        quick_actions.addStretch(1)
        dashboard_actions.addLayout(quick_actions)
        self.tutorial = QLabel("First steps: create project → add source → notes → export")
        self.tutorial.setObjectName("muted")
        dashboard_actions.addWidget(self.tutorial)
        layout.addWidget(action_surface)
        layout.addStretch()

        layout = self._page(
            "Question",
            "Build an editable research question from explicit user-entered components. "
            "The structure guides planning and does not certify scientific validity.",
        )
        self.question_topic = QLineEdit()
        self.question_population = QLineEdit()
        self.question_exposure = QLineEdit()
        self.question_outcome = QLineEdit()
        self.question_type = QComboBox()
        self.question_type.addItems(
            [
                "descriptive",
                "association",
                "causal",
                "prediction",
                "qualitative",
                "systematic-review",
                "mixed-methods",
            ]
        )
        self.question_editable = QPlainTextEdit()
        self.question_editable.setMaximumHeight(110)
        question_surface, question_surface_layout = surface(
            "Question structure",
            "Capture the research intent explicitly before choosing methods or analyses.",
            kind="toolbarSurface",
        )
        question_form = QFormLayout()
        for label, widget in (
            ("Topic", self.question_topic),
            ("Population / context", self.question_population),
            ("Exposure / intervention / phenomenon", self.question_exposure),
            ("Outcome / target", self.question_outcome),
            ("Question type", self.question_type),
        ):
            named(widget, label)
            question_form.addRow(label, widget)
        question_surface_layout.addLayout(question_form)
        layout.addWidget(question_surface)
        draft_surface, draft_layout = surface(
            "Editable research question",
            "Write the final wording you want to carry into protocol, evidence and analysis work.",
        )
        named(self.question_editable, "Editable question")
        draft_layout.addWidget(self.question_editable)
        draft_layout.addWidget(button("Save structured question", self.save_question, primary=True))
        self.question_status = QLabel("Open a project to structure its research question.")
        self.question_status.setWordWrap(True)
        self.question_status.setObjectName("muted")
        draft_layout.addWidget(self.question_status)
        layout.addWidget(draft_surface)
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
        self.global_kind.addItems(
            [
                "All",
                "source",
                "evidence",
                "annotation",
                "claim",
                "protocol",
                "manuscript",
                "notebook",
            ]
        )
        named(self.global_kind, "Global search category filter")
        layout.addWidget(self.global_kind)
        layout.addWidget(button("Search project", self.search_global, primary=True))
        self.global_results = QListWidget()
        named(self.global_results, "Project-wide search results")
        self.global_results.itemActivated.connect(lambda item: self.open_search_result(item))
        layout.addWidget(self.global_results)
        global_actions = QHBoxLayout()
        global_actions.addWidget(button("Previous search page", self.previous_global_page))
        global_actions.addWidget(button("Open selected result", self.open_selected_search))
        global_actions.addWidget(button("Next search page", self.next_global_page))
        layout.addLayout(global_actions)
        self.global_summary = QLabel("All searches remain inside the current project.")
        self.global_summary.setWordWrap(True)
        layout.addWidget(self.global_summary)
        self.global_offset = 0
        self.global_page_size = 100
        self.global_total = 0

        layout = self._page(
            "Protocol",
            "Choose an editable research design; no real data or ethics approvals are assumed.",
        )
        self.template_picker = QComboBox()
        named(self.template_picker, "Research design template")
        layout.addWidget(self.template_picker)
        layout.addWidget(button("Start protocol from template", self.start_protocol, primary=True))
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
        protocol_actions = QHBoxLayout()
        protocol_actions.addWidget(button("Save protocol draft", self.save_protocol))
        protocol_actions.addWidget(button("Check required fields", self.validate_protocol))
        protocol_actions.addWidget(
            button("Preview protocol JSON export", self.preview_protocol_export)
        )
        layout.addLayout(protocol_actions)
        self.protocol_history = QListWidget()
        named(self.protocol_history, "Protocol amendment history")
        layout.addWidget(self.protocol_history)
        deviation_form = QFormLayout()
        self.protocol_deviation = QLineEdit()
        self.protocol_deviation_reason = QLineEdit()
        self.protocol_deviation_impact = QLineEdit()
        named(self.protocol_deviation, "Protocol deviation description")
        named(self.protocol_deviation_reason, "Protocol deviation reason")
        named(self.protocol_deviation_impact, "Protocol deviation impact")
        deviation_form.addRow("Deviation", self.protocol_deviation)
        deviation_form.addRow("Reason", self.protocol_deviation_reason)
        deviation_form.addRow("Impact", self.protocol_deviation_impact)
        layout.addLayout(deviation_form)
        layout.addWidget(button("Record protocol deviation", self.add_protocol_deviation))
        self._refresh_templates()

        layout = self._page("Library", "Search local sources; sample records are always labeled.")
        library_toolbar, library_toolbar_layout = surface(
            "Find and organize sources",
            "Search stays inside this project. Import remains explicit and local.",
            kind="toolbarSurface",
        )
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search title, source text or tags")
        named(self.search, "Search this project's sources")
        self.search.textChanged.connect(self.search_sources)
        library_toolbar_layout.addWidget(self.search)
        library_controls = QHBoxLayout()
        self.library_sort = QComboBox()
        self.library_sort.addItem("Title", "title")
        self.library_sort.addItem("Source label", "source_label")
        self.library_sort.addItem("Verification", "verified")
        named(self.library_sort, "Library sort field")
        self.library_sort_desc = QCheckBox("Descending")
        library_controls.addWidget(self.library_sort)
        library_controls.addWidget(self.library_sort_desc)
        library_controls.addWidget(button("Apply library sort", self.reset_library_page))
        library_controls.addStretch(1)
        library_controls.addWidget(button("Import source text", self.import_source, primary=True))
        library_toolbar_layout.addLayout(library_controls)
        layout.addWidget(library_toolbar)
        list_surface, list_surface_layout = surface("Project sources")
        self.library_list = QListWidget()
        self.library_list.setAlternatingRowColors(True)
        named(self.library_list, "Sources in current project")
        self.library_list.itemSelectionChanged.connect(self.select_source)
        list_surface_layout.addWidget(self.library_list)
        library_pager = QHBoxLayout()
        library_pager.addWidget(button("Previous source page", self.previous_library_page))
        self.library_status = QLabel("No sources loaded")
        library_pager.addWidget(self.library_status)
        library_pager.addStretch(1)
        library_pager.addWidget(button("Next source page", self.next_library_page))
        list_surface_layout.addLayout(library_pager)
        layout.addWidget(list_surface)
        self.library_offset = 0
        self.library_page_size = 100
        self.library_total = 0

        layout = self._page("Reader", "Read selected source text and inspect its provenance.")
        self.reader_meta = QLabel("Choose an item from Library.")
        layout.addWidget(self.reader_meta)
        self.reader_text = QPlainTextEdit()
        self.reader_text.setReadOnly(True)
        named(self.reader_text, "Read-only source content")
        layout.addWidget(self.reader_text)
        layout.addWidget(button("Code selected text", self.annotate_selection))
        layout.addWidget(
            button("Capture selected text as evidence", self.capture_evidence, primary=True)
        )

        layout = self._page(
            "PDF Reader",
            "Read an explicitly selected local PDF in QtPdf. Verify quoted text "
            "and page references against the source before citing.",
        )
        self.pdf_reader = PDFReader(self)
        layout.addWidget(self.pdf_reader)

        layout = self._page(
            "Evidence",
            "Source-linked quotations remain inspectable. A matching quotation "
            "does not by itself establish scientific truth.",
        )
        layout.addWidget(button("Capture selection from Reader", self.capture_evidence))
        self.evidence_list = QListWidget()
        named(self.evidence_list, "Anchored excerpts with integrity status")
        self.evidence_list.currentItemChanged.connect(self.inspect_selected_evidence)
        self.evidence_list.itemActivated.connect(self.open_selected_evidence_source)
        layout.addWidget(self.evidence_list)
        layout.addWidget(
            button("Open selected passage in Reader", self.open_selected_evidence_source)
        )
        self.evidence_detail = QPlainTextEdit()
        self.evidence_detail.setReadOnly(True)
        named(self.evidence_detail, "Selected evidence passage and source checks")
        layout.addWidget(self.evidence_detail)
        self.claim_entry = QPlainTextEdit()
        self.claim_entry.setPlaceholderText("Write a draft claim to link to the passage")
        self.claim_entry.setMaximumHeight(90)
        named(self.claim_entry, "New source-linked claim draft")
        layout.addWidget(self.claim_entry)
        layout.addWidget(
            button("Create claim from selected evidence", self.create_evidence_claim, primary=True)
        )
        self.claim_list = QListWidget()
        named(self.claim_list, "Draft claims and evidence linkage")
        self.claim_list.currentItemChanged.connect(self.inspect_selected_claim)
        layout.addWidget(self.claim_list)
        self.claim_details = QPlainTextEdit()
        self.claim_details.setReadOnly(True)
        named(self.claim_details, "Claim support limitations and verification warnings")
        layout.addWidget(self.claim_details)

        layout = self._page(
            "Review",
            "Record independent reviewer decisions. Local aliases separate sessions but do not "
            "authenticate reviewer identity.",
        )
        reviewer_surface, reviewer_layout = surface(
            "Review session",
            "Choose the local reviewer label and narrow the queue without exposing peer decisions.",
            kind="toolbarSurface",
        )
        reviewer_row = QHBoxLayout()
        self.reviewer_alias = QLineEdit("Reviewer 1")
        named(
            self.reviewer_alias,
            "Local reviewer alias",
            "A local session label only; this is not authenticated identity.",
        )
        reviewer_row.addWidget(QLabel("Reviewer alias"))
        reviewer_row.addWidget(self.reviewer_alias, 1)
        self.review_summary = QLabel("No screening decisions.")
        self.review_summary.setWordWrap(True)
        self.review_summary.setObjectName("pageLead")
        self.review_filter = QComboBox()
        self.review_filter.addItems(
            [
                "All",
                "pending",
                "needs-your-review",
                "awaiting-second",
                "conflict",
                "agreed",
                "adjudicated",
            ]
        )
        named(self.review_filter, "Review queue decision filter")
        self.review_filter.currentTextChanged.connect(self.refresh_review)
        self.reviewer_alias.textChanged.connect(self.refresh_review)
        reviewer_row.addWidget(QLabel("Queue"))
        reviewer_row.addWidget(self.review_filter)
        reviewer_layout.addLayout(reviewer_row)
        reviewer_layout.addWidget(self.review_summary)
        layout.addWidget(reviewer_surface)
        queue_surface, queue_layout = surface(
            "Screen sources",
            "Select one source, record an exclusion reason when needed, then choose a decision.",
        )
        self.review_queue = QListWidget()
        named(self.review_queue, "Select a source to review")
        self.review_queue.currentItemChanged.connect(self._select_review_source)
        queue_layout.addWidget(self.review_queue)
        self.review_reason = QLineEdit()
        self.review_reason.setPlaceholderText("Exclusion reason (required to exclude)")
        named(self.review_reason, "Screening exclusion reason")
        queue_layout.addWidget(self.review_reason)
        decision_row = QHBoxLayout()
        for status in ("include", "exclude", "unsure"):
            decision = button(
                status.title(),
                lambda _checked=False, choice=status: self.vote(choice),
                primary=status == "include",
            )
            decision.setToolTip(f"Record {status} for the selected source")
            decision_row.addWidget(decision)
        decision_row.addStretch(1)
        queue_layout.addLayout(decision_row)
        layout.addWidget(queue_surface)
        adjudication_surface, adjudication_layout = surface(
            "Resolve conflicts",
            "Adjudication is a separate local decision and should include an explicit rationale.",
        )
        self.adjudicator_alias = QLineEdit()
        self.adjudicator_alias.setPlaceholderText("Independent adjudicator alias")
        named(self.adjudicator_alias, "Independent adjudicator alias")
        self.adjudication_choice = QComboBox()
        self.adjudication_choice.addItems(["include", "exclude", "unsure"])
        named(self.adjudication_choice, "Final adjudication decision")
        self.adjudication_reason = QLineEdit()
        self.adjudication_reason.setPlaceholderText("Adjudication rationale")
        named(self.adjudication_reason, "Adjudication rationale")
        adjudication_form = QFormLayout()
        adjudication_form.addRow("Adjudicator", self.adjudicator_alias)
        adjudication_form.addRow("Decision", self.adjudication_choice)
        adjudication_form.addRow("Rationale", self.adjudication_reason)
        adjudication_layout.addLayout(adjudication_form)
        adjudication_layout.addWidget(
            button("Adjudicate selected conflict", self.adjudicate_selected, primary=True)
        )
        layout.addWidget(adjudication_surface)
        layout.addStretch()

        layout = self._page(
            "PRISMA",
            "Record only review-flow counts you actually know. Unknown stages remain unknown "
            "and are never inferred from unrelated screening events.",
        )
        self.prisma_fields: dict[str, QLineEdit] = {}
        prisma_form = QFormLayout()
        for key, label in (
            ("records_identified", "Records identified"),
            ("duplicates_removed", "Duplicates removed"),
            ("records_screened", "Records screened"),
            ("records_excluded", "Records excluded"),
            ("reports_sought", "Reports sought"),
            ("reports_not_retrieved", "Reports not retrieved"),
            ("reports_assessed", "Reports assessed for eligibility"),
            ("reports_excluded", "Reports excluded"),
            ("studies_included", "Studies included"),
        ):
            field = QLineEdit()
            field.setPlaceholderText("Unknown")
            named(field, f"PRISMA {label}")
            self.prisma_fields[key] = field
            prisma_form.addRow(label, field)
        layout.addLayout(prisma_form)
        self.prisma_reasons = QLineEdit()
        self.prisma_reasons.setPlaceholderText("Reason=3; Other reason=1")
        named(self.prisma_reasons, "PRISMA exclusion reason counts")
        layout.addWidget(self.prisma_reasons)
        layout.addWidget(button("Save measured review-flow events", self.save_prisma, primary=True))
        prisma_actions = QHBoxLayout()
        prisma_actions.addWidget(button("Refresh PRISMA state", self.refresh_prisma))
        prisma_actions.addWidget(
            button("Preview structured PRISMA export", self.preview_prisma_export)
        )
        layout.addLayout(prisma_actions)
        self.prisma_summary = QPlainTextEdit()
        self.prisma_summary.setReadOnly(True)
        named(self.prisma_summary, "Grounded PRISMA flow summary")
        layout.addWidget(self.prisma_summary)

        layout = self._page(
            "Extraction",
            "Build a versioned extraction form, then record validated values against an "
            "imported source.",
        )
        self.extraction_title = QLineEdit("Study extraction")
        named(self.extraction_title, "Extraction form title")
        layout.addWidget(self.extraction_title)
        extraction_builder = QFormLayout()
        self.extraction_field_name = QLineEdit()
        self.extraction_field_type = QComboBox()
        self.extraction_field_type.addItems(
            ["text", "integer", "float", "categorical", "boolean", "date", "source-passage"]
        )
        self.extraction_required = QCheckBox("Required")
        self.extraction_categories = QLineEdit()
        self.extraction_categories.setPlaceholderText("category A, category B")
        for label, widget in (
            ("Field name", self.extraction_field_name),
            ("Field type", self.extraction_field_type),
            ("Categories", self.extraction_categories),
        ):
            named(widget, f"Extraction {label.lower()}")
            extraction_builder.addRow(label, widget)
        extraction_builder.addRow("", self.extraction_required)
        layout.addLayout(extraction_builder)
        layout.addWidget(button("Add field to form", self.add_extraction_field))
        self.extraction_fields_list = QListWidget()
        named(self.extraction_fields_list, "Pending extraction form fields")
        layout.addWidget(self.extraction_fields_list)
        layout.addWidget(
            button("Save versioned extraction form", self.save_extraction_schema, primary=True)
        )
        self.extraction_source = QComboBox()
        named(self.extraction_source, "Source for extraction record")
        layout.addWidget(self.extraction_source)
        self.extraction_record_widget = QWidget()
        self.extraction_record_form = QFormLayout(self.extraction_record_widget)
        named(self.extraction_record_widget, "Extraction record fields")
        layout.addWidget(self.extraction_record_widget)
        layout.addWidget(button("Save extraction record", self.save_extraction_record))
        self.extraction_records = QListWidget()
        named(self.extraction_records, "Saved extraction records")
        layout.addWidget(self.extraction_records)

        layout = self._page("Data View", "Import a small local CSV; cells stay in a virtual table.")
        data_toolbar, data_toolbar_layout = surface(
            "Dataset controls",
            "Choose the active dataset, filter/sort the view, or import CSV text into this "
            "local project.",
            kind="toolbarSurface",
        )
        data_actions = QHBoxLayout()
        data_actions.addWidget(button("Import CSV text", self.import_csv, primary=True))
        self.data_mode = QLabel(
            "Read-only preview · edits are disabled until provenance-preserving editing exists."
        )
        self.data_mode.setWordWrap(True)
        self.data_mode.setObjectName("muted")
        named(self.data_mode, "Dataset editing mode")
        data_actions.addWidget(self.data_mode, 1)
        data_toolbar_layout.addLayout(data_actions)
        self.dataset_picker = QComboBox()
        named(self.dataset_picker, "Active dataset")
        self.dataset_picker.currentIndexChanged.connect(self._selected_dataset)
        data_toolbar_layout.addWidget(self.dataset_picker)
        data_controls = QHBoxLayout()
        self.data_filter = QLineEdit()
        self.data_filter.setPlaceholderText("Filter dataset rows")
        named(self.data_filter, "Dataset text filter")
        self.data_sort = QComboBox()
        self.data_sort.addItem("No sort", "")
        named(self.data_sort, "Dataset sort column")
        self.data_sort_desc = QCheckBox("Descending")
        data_controls.addWidget(self.data_filter)
        data_controls.addWidget(self.data_sort)
        data_controls.addWidget(self.data_sort_desc)
        data_controls.addWidget(button("Apply data view", self.apply_data_view))
        data_toolbar_layout.addLayout(data_controls)
        layout.addWidget(data_toolbar)
        data_surface, data_surface_layout = surface("Data preview")
        self.data_table = QTableView()
        self.data_table.setAlternatingRowColors(True)
        named(self.data_table, "Dataset grid with labeled column and row headers")
        self.data_model = ResearchTableModel()
        self.data_table.setModel(self.data_model)
        data_surface_layout.addWidget(self.data_table)
        pager = QHBoxLayout()
        pager.addWidget(button("Previous data page", self.previous_data_page))
        self.data_page_status = QLabel("No dataset loaded")
        pager.addWidget(self.data_page_status)
        pager.addStretch(1)
        pager.addWidget(button("Next data page", self.next_data_page))
        data_surface_layout.addLayout(pager)
        layout.addWidget(data_surface)
        self.data_offset = 0
        self.data_total = 0
        self.data_page_size = 250

        layout = self._page(
            "Variable View",
            "Inspect inferred structure and save explicit variable type, role, units and "
            "missing-code metadata.",
        )
        self.variable_list = QListWidget()
        named(self.variable_list, "Variables available for descriptive statistics")
        self.variable_list.currentItemChanged.connect(self.load_variable_metadata)
        layout.addWidget(self.variable_list)
        variable_form = QFormLayout()
        self.variable_type = QComboBox()
        self.variable_type.addItems(["numeric", "categorical", "boolean", "date", "text"])
        self.variable_role = QComboBox()
        self.variable_role.addItems(
            ["outcome", "predictor", "group", "confounder", "identifier", "weight", "other"]
        )
        self.variable_units = QLineEdit()
        self.variable_levels = QLineEdit()
        self.variable_levels.setPlaceholderText("level A, level B")
        self.variable_missing = QLineEdit()
        self.variable_missing.setPlaceholderText("NA, -99")
        self.variable_description = QLineEdit()
        for label, widget in (
            ("Type", self.variable_type),
            ("Role", self.variable_role),
            ("Units", self.variable_units),
            ("Categorical levels", self.variable_levels),
            ("Missing codes", self.variable_missing),
            ("Description", self.variable_description),
        ):
            named(widget, f"Variable metadata {label.lower()}")
            variable_form.addRow(label, widget)
        layout.addLayout(variable_form)
        layout.addWidget(button("Save variable metadata", self.save_variable_metadata))

        layout = self._page("Statistics", "Descriptive summaries; missing values are reported.")
        summary_surface, summary_layout = surface(
            "Descriptive summary",
            "Start with a numeric variable; missing values remain explicit in the result.",
            kind="toolbarSurface",
        )
        self.variable_picker = QComboBox()
        named(self.variable_picker, "Numeric column for descriptive summary")
        summary_actions = QHBoxLayout()
        summary_actions.addWidget(self.variable_picker, 1)
        summary_actions.addWidget(button("Compute summary", self.run_summary, primary=True))
        summary_layout.addLayout(summary_actions)
        layout.addWidget(summary_surface)
        automatic_surface, automatic_layout = surface(
            "Automatic statistical analysis",
            "Run a deterministic, offline analysis workflow. ResearchWeave uses only explicit "
            "design and variable roles for inferential choices; it never asks an LLM to compute "
            "or select statistical results.",
            kind="toolbarSurface",
        )
        automatic_form = QFormLayout()
        self.auto_mode = QComboBox()
        for label, mode_value in (
            ("Explore my data", "explore"),
            ("Compare groups", "compare-groups"),
            ("Study relationships", "relationships"),
            ("Analyze a questionnaire", "questionnaire"),
            ("Predict an outcome", "predict-outcome"),
            ("Comprehensive exploratory analysis", "comprehensive"),
        ):
            self.auto_mode.addItem(label, mode_value)
        self.auto_design = QComboBox()
        for label, design_value in (
            ("Descriptive / no inferential design", "descriptive"),
            ("Independent groups", "independent"),
            ("Paired observations", "paired"),
            ("Observational model", "observational"),
            ("Repeated measures · requires more design metadata", "repeated"),
            ("Complex survey · requires more design metadata", "survey"),
        ):
            self.auto_design.addItem(label, design_value)
        self.auto_outcome = QComboBox()
        self.auto_group = QComboBox()
        self.auto_paired = QComboBox()
        self.auto_outcome_type = QComboBox()
        for label, outcome_value in (
            ("Continuous", "continuous"),
            ("Binary", "binary"),
            ("Count", "count"),
            ("Categorical", "categorical"),
            ("Ordinal", "ordinal"),
        ):
            self.auto_outcome_type.addItem(label, outcome_value)
        self.auto_levels = QLineEdit()
        self.auto_levels.setPlaceholderText("Group levels, e.g. control, treatment")
        self.auto_predictors = QLineEdit()
        self.auto_predictors.setPlaceholderText("Predictors, comma-separated")
        self.auto_variables = QLineEdit()
        self.auto_variables.setPlaceholderText("Variables for exploration/relationships")
        self.auto_items = QLineEdit()
        self.auto_items.setPlaceholderText("Questionnaire items, comma-separated")
        for label, widget in (
            ("Goal", self.auto_mode),
            ("Study design", self.auto_design),
            ("Outcome", self.auto_outcome),
            ("Outcome type", self.auto_outcome_type),
            ("Group", self.auto_group),
            ("Comparison levels", self.auto_levels),
            ("Paired variable", self.auto_paired),
            ("Predictors", self.auto_predictors),
            ("Variables", self.auto_variables),
            ("Questionnaire items", self.auto_items),
        ):
            named(widget, f"Automatic analysis {label.lower()}")
            automatic_form.addRow(label, widget)
        automatic_layout.addLayout(automatic_form)
        self.auto_analysis_status = QLabel(
            "Exploratory modes can run with no inferential design. Group comparisons, paired "
            "tests and prediction require the corresponding explicit design information."
        )
        self.auto_analysis_status.setWordWrap(True)
        self.auto_analysis_status.setObjectName("pageLead")
        automatic_layout.addWidget(self.auto_analysis_status)
        automatic_layout.addWidget(
            button("Run automatic analysis", self.run_automatic_analysis, primary=True)
        )
        layout.addWidget(automatic_surface)
        plot_surface, plot_surface_layout = surface(
            "Plot builder",
            "Configure a reproducible plot, preview file receipts, and write only after explicit "
            "approval.",
        )
        plot_form = QFormLayout()
        self.plot_type = QComboBox()
        self.plot_type.addItems(["histogram", "bar"])
        self.plot_title = QLineEdit()
        self.plot_x_label = QLineEdit()
        self.plot_y_label = QLineEdit()
        self.plot_unit = QLineEdit()
        self.plot_config_name = QLineEdit()
        self.plot_config_name.setPlaceholderText("Saved plot configuration name")
        self.plot_export_name = QLineEdit("plot.svg")
        for label, widget in (
            ("Plot type", self.plot_type),
            ("Title", self.plot_title),
            ("X-axis label", self.plot_x_label),
            ("Y-axis label", self.plot_y_label),
            ("Units", self.plot_unit),
            ("Config name", self.plot_config_name),
            ("Export filename", self.plot_export_name),
        ):
            named(widget, f"Plot {label.lower()}")
            plot_form.addRow(label, widget)
        plot_surface_layout.addLayout(plot_form)
        plot_actions = QHBoxLayout()
        plot_actions.addWidget(button("Render configured plot", self.render_configured_plot))
        plot_actions.addWidget(button("Preview SVG + PNG receipts", self.preview_plot_exports))
        plot_actions.addWidget(button("Save plot config", self.save_plot_config))
        plot_actions.addWidget(button("Write approved plot file", self.export_plot_file))
        plot_surface_layout.addLayout(plot_actions)
        self.plot_configs = QListWidget()
        named(self.plot_configs, "Saved descriptive plot configurations")
        self.plot_configs.itemActivated.connect(self.restore_plot_config)
        plot_surface_layout.addWidget(self.plot_configs)
        self.histogram_chart = HistogramWidget()
        named(self.histogram_chart, "Observed value histogram")
        plot_surface_layout.addWidget(self.histogram_chart)
        layout.addWidget(plot_surface)
        result_surface, result_surface_layout = surface("Result and advanced analysis")
        self.stats_result = QPlainTextEdit()
        self.stats_result.setReadOnly(True)
        self.stats_result.setMaximumHeight(120)
        self.stats_result.setPlaceholderText(
            "Run an analysis to see a concise summary here. Full numerical output is saved in "
            "Analysis Results."
        )
        named(self.stats_result, "Text alternative for numeric summary")
        result_surface_layout.addWidget(self.stats_result)
        self.analysis_method = QComboBox()
        named(self.analysis_method, "Scientific analysis method")
        self.analysis_method.currentIndexChanged.connect(self.prepare_analysis_arguments)
        result_surface_layout.addWidget(self.analysis_method)
        self.analysis_guided_form = QFormLayout()
        self.analysis_guided_widgets: dict[str, QWidget] = {}
        self.analysis_guided_specs: tuple[FieldSpec, ...] = ()
        self.analysis_guided_supported = False
        result_surface_layout.addLayout(self.analysis_guided_form)
        self.analysis_arguments = QPlainTextEdit()
        self.analysis_arguments.setPlaceholderText(
            "Advanced methods: enter operation arguments as a JSON object. "
            "Current dataset and variable are inserted when the selected schema supports them."
        )
        self.analysis_arguments.setMaximumHeight(120)
        named(self.analysis_arguments, "Advanced scientific analysis JSON arguments")
        result_surface_layout.addWidget(self.analysis_arguments)
        result_surface_layout.addWidget(button("Run selected analysis", self.run_analysis))
        layout.addWidget(result_surface)
        compatibility_surface, compatibility_layout = surface(
            "SPSS-style procedure coverage",
            "Coverage describes current ResearchWeave workflows, not IBM SPSS equivalence. "
            "Python replay is broad; mapped base-R syntax covers descriptives, t tests, "
            "correlation, one-way ANOVA and ordinary least squares. Other R workflows use "
            "the optional local Rscript runtime and remain explicitly marked as unmapped.",
        )
        self.analysis_compatibility_model = ResearchTableModel(COMPATIBILITY_COLUMNS, [])
        self.analysis_compatibility_table = QTableView()
        self.analysis_compatibility_table.setModel(self.analysis_compatibility_model)
        self.analysis_compatibility_table.setAlternatingRowColors(True)
        self.analysis_compatibility_table.setSortingEnabled(False)
        self.analysis_compatibility_table.setMaximumHeight(270)
        self.analysis_compatibility_table.setColumnHidden(3, True)
        self.analysis_compatibility_table.setColumnHidden(4, True)
        compatibility_header = self.analysis_compatibility_table.horizontalHeader()
        if compatibility_header is not None:
            compatibility_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            compatibility_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            compatibility_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.analysis_compatibility_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        named(self.analysis_compatibility_table, "Statistical procedure compatibility matrix")
        selection_model = self.analysis_compatibility_table.selectionModel()
        if selection_model is not None:
            selection_model.currentChanged.connect(self.inspect_analysis_compatibility)
        compatibility_layout.addWidget(self.analysis_compatibility_table)
        self.analysis_compatibility_detail = QLabel(
            "Select a procedure family to inspect backend/reproducibility support and limits."
        )
        self.analysis_compatibility_detail.setWordWrap(True)
        self.analysis_compatibility_detail.setObjectName("pageLead")
        named(self.analysis_compatibility_detail, "Selected statistical procedure compatibility")
        compatibility_layout.addWidget(self.analysis_compatibility_detail)
        layout.addWidget(compatibility_surface)

        layout = self._page(
            "Analysis Results",
            "Review versioned scientific results with method, inputs, assumptions, warnings, "
            "uncertainty, diagnostics and provenance.",
        )
        self.analysis_results_list = QListWidget()
        named(self.analysis_results_list, "Versioned analysis results")
        self.analysis_results_list.currentItemChanged.connect(self.inspect_analysis_result)
        layout.addWidget(self.analysis_results_list)
        self.analysis_result_model = ResearchTableModel()
        self.analysis_result_table = QTableView()
        self.analysis_result_table.setModel(self.analysis_result_model)
        self.analysis_result_table.setAlternatingRowColors(True)
        self.analysis_result_table.setSortingEnabled(False)
        named(self.analysis_result_table, "Structured analysis result table")
        layout.addWidget(self.analysis_result_table)
        self.analysis_result_detail = QPlainTextEdit()
        self.analysis_result_detail.setReadOnly(True)
        named(
            self.analysis_result_detail,
            "Selected analysis assumptions warnings and reproducibility",
        )
        layout.addWidget(self.analysis_result_detail)

        layout = self._page("Qualitative", "Code Unicode spans with original source offsets.")
        layout.addWidget(button("Code selection in Reader", self.annotate_selection))
        self.annotation_list = QListWidget()
        named(self.annotation_list, "Saved text annotations")
        self.annotation_list.currentItemChanged.connect(self.load_annotation_for_edit)
        self.annotation_list.itemActivated.connect(self.open_selected_annotation_source)
        layout.addWidget(self.annotation_list)
        annotation_form = QFormLayout()
        self.annotation_code = QLineEdit()
        self.annotation_memo = QLineEdit()
        named(self.annotation_code, "Selected annotation code")
        named(self.annotation_memo, "Selected annotation memo")
        annotation_form.addRow("Code", self.annotation_code)
        annotation_form.addRow("Memo", self.annotation_memo)
        layout.addLayout(annotation_form)
        layout.addWidget(button("Update selected annotation", self.update_annotation))

        layout = self._page(
            "Codebook",
            "Manage qualitative codes and preserve recoding history when codes are merged.",
        )
        self.codebook_list = QListWidget()
        named(self.codebook_list, "Qualitative codebook")
        layout.addWidget(self.codebook_list)
        code_form = QFormLayout()
        self.code_name = QLineEdit()
        self.code_description = QLineEdit()
        self.code_inclusion = QLineEdit()
        self.code_exclusion = QLineEdit()
        self.code_marker = QLineEdit("●")
        for label, widget in (
            ("Name", self.code_name),
            ("Description", self.code_description),
            ("Inclusion rule", self.code_inclusion),
            ("Exclusion rule", self.code_exclusion),
            ("Text marker", self.code_marker),
        ):
            named(widget, f"Codebook {label.lower()}")
            code_form.addRow(label, widget)
        layout.addLayout(code_form)
        layout.addWidget(button("Create code", self.save_code, primary=True))
        self.code_merge_sources = QLineEdit()
        self.code_merge_sources.setPlaceholderText("source code IDs separated by commas")
        self.code_merge_target = QLineEdit()
        self.code_merge_target.setPlaceholderText("target code ID")
        self.code_merge_note = QLineEdit()
        self.code_merge_note.setPlaceholderText("why this merge is appropriate")
        named(self.code_merge_sources, "Code IDs to merge")
        named(self.code_merge_target, "Target code ID for merge")
        named(self.code_merge_note, "Code merge conflict resolution note")
        layout.addWidget(self.code_merge_sources)
        layout.addWidget(self.code_merge_target)
        layout.addWidget(self.code_merge_note)
        layout.addWidget(button("Merge codes with trace", self.merge_codes_ui))

        layout = self._page(
            "Mixed Methods",
            "Link qualitative and quantitative evidence while preserving units, groups and "
            "method-specific limitations.",
        )
        mixed_form = QFormLayout()
        self.mixed_qual_refs = QLineEdit()
        self.mixed_quant_refs = QLineEdit()
        self.mixed_relation = QComboBox()
        self.mixed_relation.addItems(["converges", "diverges", "complements", "uncertain"])
        self.mixed_units = QLineEdit()
        self.mixed_groups = QLineEdit()
        self.mixed_origin = QLineEdit()
        self.mixed_interpretation = QLineEdit()
        for label, widget in (
            ("Qualitative refs", self.mixed_qual_refs),
            ("Quantitative refs", self.mixed_quant_refs),
            ("Relation", self.mixed_relation),
            ("Units", self.mixed_units),
            ("Group definition", self.mixed_groups),
            ("Evidence origin", self.mixed_origin),
            ("Interpretation", self.mixed_interpretation),
        ):
            named(widget, f"Mixed methods {label.lower()}")
            mixed_form.addRow(label, widget)
        layout.addLayout(mixed_form)
        layout.addWidget(button("Add mixed-method link", self.add_mixed_link, primary=True))
        self.mixed_links = QListWidget()
        named(self.mixed_links, "Mixed-method evidence links")
        layout.addWidget(self.mixed_links)

        layout = self._page("Manuscript", "Verify each manuscript claim against its source.")
        manuscript_sections = QHBoxLayout()
        self.manuscript_section_list = QListWidget()
        named(self.manuscript_section_list, "Structured manuscript sections")
        self.manuscript_section_list.currentItemChanged.connect(self.load_manuscript_section)
        manuscript_sections.addWidget(self.manuscript_section_list)
        section_editor = QVBoxLayout()
        self.manuscript_section_title = QLineEdit()
        self.manuscript_section_body = QPlainTextEdit()
        named(self.manuscript_section_title, "Manuscript section title")
        named(self.manuscript_section_body, "Manuscript section body")
        section_editor.addWidget(self.manuscript_section_title)
        section_editor.addWidget(self.manuscript_section_body)
        section_editor.addWidget(button("Add / update section", self.upsert_manuscript_section))
        section_editor.addWidget(button("Remove selected section", self.remove_manuscript_section))
        manuscript_sections.addLayout(section_editor)
        layout.addLayout(manuscript_sections)
        self.manuscript_editor = QPlainTextEdit()
        named(self.manuscript_editor, "Editable manuscript draft")
        layout.addWidget(self.manuscript_editor)
        manuscript_actions = QHBoxLayout()
        manuscript_actions.addWidget(
            button("Save manuscript · Ctrl+S", lambda: self.save_text("manuscript"))
        )
        manuscript_actions.addWidget(
            button("Save structured sections", self.save_manuscript_sections)
        )
        layout.addLayout(manuscript_actions)

        layout = self._page(
            "References",
            "Maintain source-linked citation metadata manually. Missing fields stay visible and "
            "no DOI or bibliography entry is invented.",
        )
        self.reference_list = QListWidget()
        named(self.reference_list, "Manuscript references")
        self.reference_list.currentItemChanged.connect(self.inspect_reference)
        layout.addWidget(self.reference_list)
        reference_form = QFormLayout()
        self.reference_title = QLineEdit()
        self.reference_authors = QLineEdit()
        self.reference_year = QLineEdit()
        self.reference_container = QLineEdit()
        self.reference_doi = QLineEdit()
        self.reference_url = QLineEdit()
        self.reference_verified = QCheckBox("Metadata manually verified")
        for label, widget in (
            ("Title", self.reference_title),
            ("Authors", self.reference_authors),
            ("Year", self.reference_year),
            ("Journal / container", self.reference_container),
            ("DOI", self.reference_doi),
            ("URL", self.reference_url),
        ):
            named(widget, f"Reference {label.lower()}")
            reference_form.addRow(label, widget)
        reference_form.addRow("", self.reference_verified)
        layout.addLayout(reference_form)
        layout.addWidget(button("Save reference", self.save_reference, primary=True))
        layout.addWidget(
            button("Insert selected citation into manuscript", self.insert_selected_citation)
        )
        self.reference_detail = QLabel("Select a reference to inspect its verification state.")
        self.reference_detail.setWordWrap(True)
        layout.addWidget(self.reference_detail)

        layout = self._page("Notebook", "Record observations, questions and source checks.")
        self.notebook_editor = QPlainTextEdit()
        named(self.notebook_editor, "Editable research notes")
        layout.addWidget(self.notebook_editor)
        layout.addWidget(button("Save notes · Ctrl+S", lambda: self.save_text("notebook")))
        layout.addWidget(button("Inspect code execution safety", self.refresh_code_execution))
        self.code_execution_status = QLabel(
            "Code execution is disabled until an isolated execution host is integrated."
        )
        self.code_execution_status.setWordWrap(True)
        named(self.code_execution_status, "Code execution safety status")
        layout.addWidget(self.code_execution_status)

        layout = self._page(
            "Publishing",
            "Review manuscript readiness and unresolved requirements. "
            "No approval or journal compliance can be inferred automatically.",
        )
        layout.addWidget(
            button("Inspect submission draft gates", self.preview_publishing, primary=True)
        )
        layout.addWidget(button("Generate review packet preview", self.preview_submission_markdown))
        self.publication_summary = QLabel(
            "Write a draft and link original evidence before checking submission readiness."
        )
        self.publication_summary.setWordWrap(True)
        layout.addWidget(self.publication_summary)
        self.release_gates = QListWidget()
        named(self.release_gates, "Manuscript publication checklist and human review gates")
        self.release_gates.currentItemChanged.connect(self.inspect_release_gate)
        layout.addWidget(self.release_gates)
        self.release_detail = QPlainTextEdit()
        self.release_detail.setReadOnly(True)
        named(self.release_detail, "Detailed release checklist and Markdown preview")
        layout.addWidget(self.release_detail)

        layout = self._page("Agent", "Model plans are suggestions; no unapproved changes can run.")
        assistant_surface, assistant_layout = surface(
            "Research assistant",
            "Uses the model selected in Providers. Read-only research tools may run automatically; "
            "any future write or destructive tool pauses for exact approval here.",
        )
        self.assistant_transcript = QPlainTextEdit()
        self.assistant_transcript.setReadOnly(True)
        self.assistant_transcript.setPlaceholderText(
            "Configure a model in Providers, then ask a project-scoped research question."
        )
        self.assistant_transcript.setMinimumHeight(190)
        named(self.assistant_transcript, "Project research assistant conversation")
        assistant_layout.addWidget(self.assistant_transcript)
        self.assistant_prompt = QPlainTextEdit()
        self.assistant_prompt.setPlaceholderText(
            "Ask about this project's evidence or research work"
        )
        self.assistant_prompt.setMaximumHeight(105)
        named(self.assistant_prompt, "Research assistant prompt")
        assistant_layout.addWidget(self.assistant_prompt)
        assistant_actions = QHBoxLayout()
        self.assistant_send_button = button(
            "Send to selected model", self.send_assistant, primary=True
        )
        assistant_actions.addWidget(self.assistant_send_button)
        self.assistant_cancel_button = button("Cancel request", self.cancel_assistant)
        assistant_actions.addWidget(self.assistant_cancel_button)
        assistant_actions.addStretch()
        assistant_layout.addLayout(assistant_actions)
        self.assistant_tool_status = QLabel(
            "No model is active. Manual ResearchWeave workflows remain available."
        )
        self.assistant_tool_status.setWordWrap(True)
        named(self.assistant_tool_status, "Assistant model and tool activity status")
        assistant_layout.addWidget(self.assistant_tool_status)
        self.assistant_usage_status = QLabel("Model usage: no calls recorded for this project.")
        self.assistant_usage_status.setWordWrap(True)
        named(self.assistant_usage_status, "Assistant provider usage summary")
        assistant_layout.addWidget(self.assistant_usage_status)
        self.assistant_pending = QPlainTextEdit()
        self.assistant_pending.setReadOnly(True)
        self.assistant_pending.setMaximumHeight(120)
        self.assistant_pending.setPlaceholderText("No tool approval is pending.")
        named(self.assistant_pending, "Pending assistant tool approval")
        assistant_layout.addWidget(self.assistant_pending)
        pending_actions = QHBoxLayout()
        self.assistant_approve_button = button(
            "Approve exact tool call",
            self.approve_assistant_tool,
        )
        self.assistant_deny_button = button("Deny tool call", self.deny_assistant_tool)
        pending_actions.addWidget(self.assistant_approve_button)
        pending_actions.addWidget(self.assistant_deny_button)
        pending_actions.addStretch()
        assistant_layout.addLayout(pending_actions)
        layout.addWidget(assistant_surface)
        layout.addWidget(heading("Manual proposal review"))
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
        agent_form = QFormLayout()
        self.agent_operation = QLineEdit()
        self.agent_target = QLineEdit()
        self.agent_arguments = QPlainTextEdit()
        self.agent_arguments.setPlaceholderText('{"query": "memory", "limit": 5}')
        self.agent_arguments.setMaximumHeight(90)
        self.agent_files = QLineEdit()
        self.agent_network = QLineEdit()
        self.agent_egress = QCheckBox("Proposal sends selected data to this destination")
        self.agent_destructive = QCheckBox("Proposal has a destructive effect")
        for label, widget in (
            ("Exact operation", self.agent_operation),
            ("Exact target", self.agent_target),
            ("Affected files", self.agent_files),
            ("Network destination", self.agent_network),
        ):
            named(widget, f"Agent action {label.lower()}")
            agent_form.addRow(label, widget)
        named(self.agent_arguments, "Agent action JSON arguments")
        agent_form.addRow("Operation arguments (JSON)", self.agent_arguments)
        agent_form.addRow("", self.agent_egress)
        agent_form.addRow("", self.agent_destructive)
        layout.addLayout(agent_form)
        layout.addWidget(
            button("Create scope-bound proposal", self.create_agent_action, primary=True)
        )
        self.agent_timeline = QListWidget()
        named(self.agent_timeline, "Persistent agent action timeline")
        self.agent_timeline.currentItemChanged.connect(self.inspect_agent_action)
        layout.addWidget(self.agent_timeline)
        action_row = QHBoxLayout()
        action_row.addWidget(button("Approve exact selected proposal", self.approve_agent_action))
        action_row.addWidget(button("Execute approved action", self.execute_agent_action))
        action_row.addWidget(button("Deny selected proposal", self.deny_agent_action))
        layout.addLayout(action_row)
        self.agent_status = QLabel("No provider configured; manual work remains available.")
        self.agent_status.setWordWrap(True)
        layout.addWidget(self.agent_status)

        layout = self._page(
            "Providers",
            "Configure manual, local or supported cloud-API metadata. Credentials are not stored "
            "by this UI workstream, and consumer subscriptions are never assumed.",
        )
        provider_form = QFormLayout()
        self.provider_mode = QComboBox()
        self.provider_mode.addItems(["manual", "local", "cloud-api"])
        self.provider_id = QLineEdit("manual")
        self.provider_protocol = QComboBox()
        self.provider_protocol.addItems(["openai-compatible", "ollama", "anthropic", "gemini"])
        self.provider_protocol.currentTextChanged.connect(self._provider_protocol_changed)
        self.provider_endpoint = QLineEdit()
        self.provider_endpoint.setPlaceholderText("http://127.0.0.1:1234/v1 or https://host/v1")
        self.provider_model = QLineEdit()
        self.provider_model.setPlaceholderText("Exact model identifier")
        self.provider_credential_env = QLineEdit()
        self.provider_credential_env.setPlaceholderText(
            "OPENAI_API_KEY (name only, never the secret)"
        )
        self.provider_tool_calling = QCheckBox("Model supports native tool calling")
        self.provider_enabled = QCheckBox("Enabled")
        self.provider_credential = QCheckBox("Supported credential configured externally")
        self.provider_egress = QCheckBox("I reviewed and accept the selected data egress")
        self.provider_scope = QLineEdit()
        self.provider_scope.setPlaceholderText("source-text, evidence")
        for label, widget in (
            ("Mode", self.provider_mode),
            ("Provider identifier", self.provider_id),
            ("Protocol", self.provider_protocol),
            ("Endpoint", self.provider_endpoint),
            ("Model", self.provider_model),
            ("Credential env var", self.provider_credential_env),
            ("Selected data scope", self.provider_scope),
        ):
            named(widget, f"Provider {label.lower()}")
            provider_form.addRow(label, widget)
        provider_form.addRow("", self.provider_enabled)
        provider_form.addRow("", self.provider_tool_calling)
        provider_form.addRow("", self.provider_credential)
        provider_form.addRow("", self.provider_egress)
        layout.addLayout(provider_form)
        layout.addWidget(button("Save provider configuration", self.save_provider, primary=True))
        self.provider_usage_status = QLabel("Model usage: no calls recorded for this project.")
        self.provider_usage_status.setWordWrap(True)
        named(self.provider_usage_status, "Provider usage and cost summary")
        layout.addWidget(self.provider_usage_status)
        self.provider_status = QPlainTextEdit()
        self.provider_status.setReadOnly(True)
        named(self.provider_status, "Provider availability and egress status")
        layout.addWidget(self.provider_status)

        layout = self._page(
            "Privacy",
            "Inspect offline mode, telemetry, provider egress, selected data scope, backup and "
            "sync destinations, retention and deletion impact.",
        )
        self.offline_toggle = QCheckBox("Offline mode")
        self.offline_toggle.setChecked(self.prefs.offline)
        named(self.offline_toggle, "Offline mode network gate")
        layout.addWidget(self.offline_toggle)
        layout.addWidget(button("Save offline mode", self.save_offline_mode))
        layout.addWidget(button("Refresh privacy report", self.refresh_privacy, primary=True))
        self.privacy_status = QPlainTextEdit()
        self.privacy_status.setReadOnly(True)
        named(self.privacy_status, "Privacy and data egress report")
        layout.addWidget(self.privacy_status)
        layout.addStretch()

        layout = self._page(
            "Integrations",
            "Optional adapters are disabled by default. This local UI remains usable without "
            "connecting any external service.",
        )
        self.integration_list = QListWidget()
        named(self.integration_list, "Optional integration adapters")
        layout.addWidget(self.integration_list)
        layout.addWidget(button("Refresh integration catalog", self.refresh_integrations))
        layout.addWidget(
            button("Disconnect selected integration", self.disconnect_integration, primary=True)
        )
        self.integration_status = QLabel("No external integration is required.")
        self.integration_status.setWordWrap(True)
        layout.addWidget(self.integration_status)

        layout = self._page("Exports", "Preview file hashes before saving a local export.")
        export_surface, export_surface_layout = surface(
            "Local export",
            "Choose a filename, inspect the exact payload/hash first, then explicitly approve the "
            "write.",
        )
        export_location = QHBoxLayout()
        self.export_directory = QLineEdit(display_local_path(self.facade.export_root))
        self.export_directory.setReadOnly(True)
        self.export_directory.setToolTip(str(self.facade.export_root.resolve()))
        named(self.export_directory, "Selected local export directory")
        export_location.addWidget(self.export_directory)
        export_location.addWidget(button("Choose export folder", self.choose_export_folder))
        export_surface_layout.addLayout(export_location)
        self.export_name = QLineEdit("research-notes.md")
        named(self.export_name, "Export filename")
        export_surface_layout.addWidget(self.export_name)
        export_actions = QHBoxLayout()
        export_actions.addWidget(button("Inspect export", self.preview_export))
        export_actions.addWidget(button("Save local export", self.export_file, primary=True))
        export_actions.addStretch(1)
        export_surface_layout.addLayout(export_actions)
        layout.addWidget(export_surface)
        receipt_surface, receipt_layout = surface("Export receipt", kind="calloutSurface")
        self.export_receipt = QLabel("No export yet.")
        self.export_receipt.setWordWrap(True)
        self.export_receipt.setObjectName("pageLead")
        receipt_layout.addWidget(self.export_receipt)
        layout.addWidget(receipt_surface)
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
        layout.addWidget(button("Restore selected backup as new project", self.restore_backup))
        self.backup_receipt = QLabel("Backups are local, immutable ZIP data archives.")
        self.backup_receipt.setWordWrap(True)
        layout.addWidget(self.backup_receipt)

        layout = self._page(
            "Recovery",
            "Inspect unsaved editor copies after an interrupted session. "
            "Restoring into an editor never overwrites saved project files.",
        )
        layout.addWidget(button("Refresh recovery drafts", self.refresh_recovery))
        self.recovery_list = QListWidget()
        named(self.recovery_list, "Available journaled research drafts")
        layout.addWidget(self.recovery_list)
        layout.addWidget(
            button("Restore selected into editor", self.restore_recovery, primary=True)
        )
        self.recovery_receipt = QLabel("No recovery draft selected.")
        self.recovery_receipt.setWordWrap(True)
        layout.addWidget(self.recovery_receipt)

        layout = self._page(
            "Diagnostics",
            "Audit local source hashes, research links, screening decisions and "
            "table structure. Passing this audit does not certify research validity.",
        )
        layout.addWidget(button("Run project integrity audit", self.run_diagnostics, primary=True))
        self.audit_summary = QLabel("No integrity audit has been run.")
        self.audit_summary.setWordWrap(True)
        layout.addWidget(self.audit_summary)
        self.audit_findings = QListWidget()
        named(self.audit_findings, "Project integrity findings")
        self.audit_findings.currentItemChanged.connect(self.inspect_finding)
        layout.addWidget(self.audit_findings)
        self.audit_detail = QPlainTextEdit()
        self.audit_detail.setReadOnly(True)
        named(self.audit_detail, "Selected finding and corrective action")
        layout.addWidget(self.audit_detail)

        layout = self._page("Jobs", "Long operations use cancellable supervised Qt tasks.")
        self.job_list = QListWidget()
        named(self.job_list, "Background job statuses")
        layout.addWidget(self.job_list)
        job_actions = QHBoxLayout()
        job_actions.addWidget(button("Cancel selected job", self.cancel_job))
        job_actions.addWidget(button("Retry selected failed/cancelled job", self.retry_job))
        layout.addLayout(job_actions)
        self.jobs.changed.connect(lambda key, state: self.job_list.addItem(f"{key}: {state}"))
        self.jobs.progress.connect(
            lambda key, percent: self.job_list.addItem(f"{key}: progress {percent}%")
        )

        layout = self._page(
            "Notifications",
            "Persistent, actionable local diagnostics. Secret-looking content is rejected from "
            "the stored error log.",
        )
        self.notification_list = QListWidget()
        named(self.notification_list, "Persistent notification and error center")
        layout.addWidget(self.notification_list)
        layout.addWidget(button("Refresh notifications", self.refresh_notifications))
        layout.addWidget(button("Dismiss selected notification", self.dismiss_notification))
        layout.addWidget(button("Retry selected safe local action", self.retry_notification))

        layout = self._page(
            "Tutorials",
            "Work through synthetic, local-only exercises for the main research workflow. "
            "Completion records actions; it does not certify methodological competence.",
        )
        self.tutorial_list = QListWidget()
        named(self.tutorial_list, "Research tutorial progress")
        layout.addWidget(self.tutorial_list)
        layout.addWidget(
            button(
                "Mark selected tutorial action complete", self.complete_tutorial_step, primary=True
            )
        )
        layout.addWidget(button("Refresh tutorial progress", self.refresh_tutorials))

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

        layout = self._page(
            "Shortcuts",
            "Current keyboard bindings. Escape closes modal dialogs and standard tab navigation "
            "moves between controls without trapping focus.",
        )
        self.shortcut_help = QPlainTextEdit()
        self.shortcut_help.setReadOnly(True)
        self.shortcut_help.setPlainText(
            "Ctrl+K  Commands\n"
            "Ctrl+N  New project\n"
            "Ctrl+F  Global project search\n"
            "Ctrl+S  Save active writing/protocol\n"
            "Ctrl+Shift+A  Code selected Reader passage\n"
            "Ctrl+Shift+E  Open export studio and focus filename\n"
            "Ctrl+1  Dashboard\n"
            "Ctrl+2  Library\n"
            "F1      Shortcut help\n"
            "Escape  Close the active modal dialog"
        )
        named(self.shortcut_help, "Keyboard shortcut help")
        layout.addWidget(self.shortcut_help)

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
        self.locale_entry = QLineEdit(self.prefs.locale)
        named(self.locale_entry, "Interface locale")
        form.addRow("Locale", self.locale_entry)
        layout.addLayout(form)
        layout.addWidget(button("Apply and save preferences", self.save_preferences, primary=True))
        self.localization_status = QLabel()
        self.localization_status.setWordWrap(True)
        layout.addWidget(self.localization_status)
        preset_row = QHBoxLayout()
        self.preset_name = QLineEdit()
        self.preset_name.setPlaceholderText("Preset name")
        named(self.preset_name, "Workspace preset name")
        preset_row.addWidget(self.preset_name)
        preset_row.addWidget(button("Save workspace preset", self.save_workspace_preset))
        layout.addLayout(preset_row)
        self.preset_list = QListWidget()
        named(self.preset_list, "Saved workspace presets")
        layout.addWidget(self.preset_list)
        preset_actions = QHBoxLayout()
        preset_actions.addWidget(button("Restore selected preset", self.restore_workspace_preset))
        preset_actions.addWidget(button("Delete selected preset", self.delete_workspace_preset))
        preset_actions.addWidget(button("Reset layout", self.reset_workspace_layout))
        layout.addLayout(preset_actions)
        self.refresh_localization()
        self.refresh_workspace_presets()

        layout = self._page(
            "Activity",
            "Local operation history for the current project. Actor labels are not authenticated "
            "identities.",
        )
        activity_controls = QHBoxLayout()
        self.activity_operation = QLineEdit()
        self.activity_operation.setPlaceholderText("Exact operation filter, e.g. ui.source.add")
        named(self.activity_operation, "Activity operation filter")
        self.activity_limit = QComboBox()
        for value in (25, 50, 100, 250):
            self.activity_limit.addItem(str(value), value)
        self.activity_limit.setCurrentText("100")
        named(self.activity_limit, "Activity result limit")
        activity_controls.addWidget(self.activity_operation)
        activity_controls.addWidget(self.activity_limit)
        activity_controls.addWidget(button("Apply activity filter", self.refresh_activity))
        layout.addLayout(activity_controls)
        self.activity_list = QListWidget()
        named(self.activity_list, "Project activity audit")
        self.activity_list.itemActivated.connect(self.open_activity_event)
        layout.addWidget(self.activity_list)
        self.activity_status = QLabel("Activity records are local provenance, not authentication.")
        self.activity_status.setWordWrap(True)
        layout.addWidget(self.activity_status)

        layout = self._page("About", "Original, free and open-source research workspace.")
        layout.addWidget(QLabel("ResearchWeave UI V2 · GPL-3.0-only · local demo"))
        layout.addWidget(QLabel("Prototype screens use local services with explicit limitations."))
        layout.addStretch()

    def _set_status(self, message: str) -> None:
        status = self.statusBar()
        if status is not None:
            status.showMessage(message)

    def _call(self, operation: str, **values: Any) -> dict[str, Any] | None:
        if operation not in (
            "ui.project.list",
            "ui.project.create",
            "ui.project.open",
            "ui.templates.list",
            "ui.guidance.search",
            "ui.backup.list",
            "ui.backup.inspect",
            "ui.backup.restore",
            "ui.preferences.read",
            "ui.preferences.update",
            "ui.agent.propose",
            "ui.agent.deny",
            "ui.localization.read",
            "ui.workspace.preset.list",
            "ui.workspace.preset.save",
            "ui.workspace.preset.delete",
        ):
            if not self.project_id:
                self._set_status("Create or select a project first.")
                return None
            values.setdefault("project_id", self.project_id)
        if operation in {
            "ui.project.update",
            "ui.source.add",
            "ui.review.vote",
            "ui.qual.annotate",
            "ui.qual.annotation.update",
            "ui.screening.vote",
            "ui.screening.adjudicate",
            "ui.dataset.import",
            "ui.manuscript.save",
            "ui.manuscript.sections.update",
            "ui.notebook.save",
            "ui.tutorial.step",
            "ui.protocol.start",
            "ui.protocol.update",
            "ui.protocol.deviation.add",
            "ui.evidence.capture",
            "ui.claim.create",
            "ui.question.update",
            "ui.prisma.update",
            "ui.extraction.schema.update",
            "ui.extraction.record.save",
            "ui.variable.metadata.update",
            "ui.analysis.run",
            "ui.chart.config.save",
            "ui.codebook.upsert",
            "ui.codebook.merge",
            "ui.mixed.add",
            "ui.reference.upsert",
            "ui.agent.action.propose",
            "ui.agent.action.approve",
            "ui.agent.action.deny",
            "ui.agent.action.record",
            "ui.provider.update",
            "ui.integration.disconnect",
            "ui.notification.add",
            "ui.notification.dismiss",
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
        current_name = self.page_heading.text()
        focused = QApplication.focusWidget()
        if (
            current_name in SCREENS
            and isinstance(focused, QWidget)
            and self.isAncestorOf(focused)
            and focused is not self.nav
        ):
            self._screen_focus[current_name] = focused
        index = SCREENS.index(name)
        self.pages.setCurrentIndex(index)
        self.page_heading.setText(name)
        self.page_context.setText(NAV_GROUP_BY_SCREEN.get(name, "WORKSPACE").upper())
        nav_item = self._nav_items.get(name)
        if nav_item is not None:
            parent = nav_item.parent()
            if parent is not None:
                for group_item in self._nav_groups.values():
                    group_item.setExpanded(group_item is parent)
            if self.nav.currentItem() is not nav_item:
                self.nav.setCurrentItem(nav_item)
        if name == "Library":
            self.search_sources()
        elif name == "Question":
            self.refresh_question()
        elif name == "Review":
            self.refresh_review()
        elif name == "PRISMA":
            self.refresh_prisma()
        elif name == "Extraction":
            self.refresh_extraction()
        elif name == "Qualitative":
            self.refresh_annotations()
        elif name == "Codebook":
            self.refresh_codebook()
        elif name == "Mixed Methods":
            self.refresh_mixed_links()
        elif name == "Evidence":
            self.refresh_evidence()
        elif name == "References":
            self.refresh_references()
        elif name == "Notebook":
            self.refresh_code_execution()
        elif name == "Analysis Results":
            self.refresh_analysis_results()
        elif name == "Agent":
            self.refresh_agent_timeline()
        elif name == "Providers":
            self.refresh_provider()
        elif name == "Privacy":
            self.refresh_privacy()
        elif name == "Integrations":
            self.refresh_integrations()
        elif name == "Notifications":
            self.refresh_notifications()
        elif name == "Tutorials":
            self.refresh_tutorials()
        elif name == "Activity":
            self.refresh_activity()
        elif name == "Protocol":
            self.refresh_protocol()
        elif name == "Manuscript":
            self.refresh_manuscript_sections()
        elif name == "Guidance":
            self.refresh_guidance()
        elif name == "Backups":
            self.refresh_backups()
        elif name == "Diagnostics":
            self.run_diagnostics()
        elif name == "Recovery":
            self.refresh_recovery()
        elif name == "Publishing":
            self.preview_publishing()
        elif name in ("Data View", "Variable View", "Statistics"):
            self.refresh_datasets()
            if name == "Statistics":
                self.refresh_plot_configs()
        self.prefs.selected_screen = name
        QTimer.singleShot(0, lambda screen=name: self._restore_screen_focus(screen))

    def _restore_screen_focus(self, screen: str) -> None:
        widget = self._screen_focus.get(screen)
        if widget is not None and widget.isEnabled():
            widget.setFocus(Qt.FocusReason.OtherFocusReason)

    def _refresh_dashboard_if_visible(self) -> None:
        if self.page_heading.text() == "Dashboard" and self.project_id:
            self.refresh_dashboard()

    def show_palette(self) -> None:
        dialog = CommandPalette(self)
        dialog.query.setFocus()
        dialog.exec()

    def open_context_help(self, screen: str | None = None) -> None:
        current = screen or self.page_heading.text()
        query_map = {
            "Question": "research question",
            "Protocol": "research question",
            "Library": "primary source",
            "Reader": "primary source",
            "PDF": "primary source",
            "Evidence": "evidence",
            "Review": "screening",
            "PRISMA": "screening",
            "Extraction": "variable",
            "Data View": "sample",
            "Variable View": "variable",
            "Statistics": "confidence interval",
            "Analysis Results": "confidence interval",
            "Qualitative": "qualitative",
            "Codebook": "qualitative",
            "Mixed Methods": "mixed",
            "Manuscript": "evidence",
            "References": "primary source",
            "Privacy": "privacy",
            "Exports": "evidence",
            "Recovery": "recovery",
        }
        self.navigate("Guidance")
        self.help_query.setText(query_map.get(current, current))
        self.refresh_guidance()
        self.help_query.setFocus()

    def command_entries(self) -> list[dict[str, Any]]:
        project_required = bool(self.project_id)
        entries: list[dict[str, Any]] = [
            {
                "label": f"Open {screen}",
                "kind": "screen",
                "value": screen,
                "enabled": True,
                "reason": "",
                "summary": f"Navigate to the {screen} workspace.",
            }
            for screen in SCREENS
        ]
        entries.extend(
            [
                {
                    "label": "Create project",
                    "kind": "action",
                    "value": "create-project",
                    "enabled": True,
                    "reason": "",
                    "summary": "Create a new local research project.",
                },
                {
                    "label": "Import text source",
                    "kind": "action",
                    "value": "import-source",
                    "enabled": project_required,
                    "reason": "Open or create a project first.",
                    "summary": "Add user-supplied source text to the current project.",
                },
                {
                    "label": "Search library",
                    "kind": "action",
                    "value": "search-library",
                    "enabled": project_required,
                    "reason": "Open or create a project first.",
                    "summary": "Focus the current project's local source search.",
                },
                {
                    "label": "Preview export",
                    "kind": "action",
                    "value": "export-preview",
                    "enabled": project_required,
                    "reason": "Open or create a project first.",
                    "summary": "Open the local export preview without writing a file.",
                },
            ]
        )
        surfaced = {
            "ui.project.create",
            "ui.source.add",
            "ui.search.global",
            "ui.export.preview",
        }
        for capability in self.facade.capability_manifest():
            operation = str(capability["operation"])
            if operation in surfaced:
                continue
            entries.append(
                {
                    "label": operation,
                    "kind": "capability",
                    "value": operation,
                    "enabled": False,
                    "reason": "Use its workspace screen to provide the required structured inputs.",
                    "summary": str(capability["summary"]),
                }
            )
        return entries

    def execute_palette_entry(self, entry: Mapping[str, Any]) -> None:
        kind = entry.get("kind")
        value = str(entry.get("value", ""))
        if kind == "screen" and value in SCREENS:
            self.navigate(value)
            return
        if kind != "action":
            self._set_status(
                "This capability requires structured inputs from its workspace screen."
            )
            return
        if value == "create-project":
            self.create_project()
        elif value == "import-source":
            self.import_source()
        elif value == "search-library":
            self.navigate("Library")
            QTimer.singleShot(20, self.search.setFocus)
        elif value == "export-preview":
            self.navigate("Exports")
            QTimer.singleShot(20, self.export_name.setFocus)

    def focus_search(self) -> None:
        self.navigate("Search")
        QTimer.singleShot(0, self.global_query.setFocus)

    def focus_library_search(self) -> None:
        self.navigate("Library")
        QTimer.singleShot(0, self.search.setFocus)

    def focus_export(self) -> None:
        self.navigate("Exports")
        QTimer.singleShot(0, self.export_name.setFocus)

    def search_global(self) -> None:
        self.global_offset = 0
        self._load_global_page()

    def _load_global_page(self) -> None:
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
            "ui.search.global",
            query=query,
            kind="" if kind == "All" else kind,
            offset=self.global_offset,
            limit=self.global_page_size,
        )
        if response is None:
            return
        for hit in response["hits"]:
            item = QListWidgetItem(f"{hit['kind'].upper()} · {hit['title']}\n{hit['snippet']}")
            item.setData(Qt.ItemDataRole.UserRole, hit)
            self.global_results.addItem(item)
        self.global_total = response["total"]
        start = self.global_offset + 1 if self.global_total else 0
        end = min(self.global_offset + len(response["hits"]), self.global_total)
        self.global_summary.setText(
            f"Showing {start}–{end} of {response['total']} matching artifacts · "
            f"{response['search_method']}.\n"
            "Excerpts are unverified until checked against their original record."
        )

    def previous_global_page(self) -> None:
        if self.global_offset > 0:
            self.global_offset = max(0, self.global_offset - self.global_page_size)
            self._load_global_page()

    def next_global_page(self) -> None:
        if self.global_offset + self.global_page_size < self.global_total:
            self.global_offset += self.global_page_size
            self._load_global_page()

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
        elif hit["kind"] in ("evidence", "claim"):
            self.navigate("Evidence")
            self.refresh_evidence()
        elif hit["kind"] == "protocol":
            self.navigate("Protocol")
        elif hit["kind"] == "notebook":
            self.navigate("Notebook")
        elif hit["kind"] == "manuscript":
            self.navigate("Manuscript")

    def refresh_projects(self, query: str = "") -> None:
        value = self._call("ui.project.list")
        if value is None:
            return
        query = query.strip().casefold()
        self.project_picker.blockSignals(True)
        self.project_picker.clear()
        self.project_picker.addItem("Choose a project", "")
        for project in value["projects"]:
            haystack = f"{project['title']} {project['question']} {project['id']}".casefold()
            if query and query not in haystack:
                continue
            updated = str(project["updated_at"])[:10]
            self.project_picker.addItem(
                f"{project['title']} · {updated}",
                project["id"],
            )
            index = self.project_picker.count() - 1
            self.project_picker.setItemData(
                index,
                f"Local project ID: {project['id']}",
                Qt.ItemDataRole.ToolTipRole,
            )
        if self.project_id:
            index = self.project_picker.findData(self.project_id)
            if index >= 0:
                self.project_picker.setCurrentIndex(index)
        self.project_picker.blockSignals(False)

    def finish_onboarding(self) -> None:
        response = self._call("ui.preferences.update", onboarding_complete=True)
        if response is None:
            return
        self.prefs = Preferences(**response["preferences"])
        self.welcome_status.setText(
            "First-run guide completed. You can reopen tutorials from the Tutorials screen."
        )
        self.navigate("Dashboard")

    def create_local_demo(self) -> None:
        created = self._call(
            "ui.project.create",
            title="Synthetic attention demo",
            question="How is a synthetic distraction described in this local fixture?",
            study_type="literature",
        )
        if created is None:
            return
        self.project_id = created["project_id"]
        self.revision = created["revision"]
        source = self._call(
            "ui.source.add",
            title="Synthetic demonstration source",
            text=(
                "This is synthetic demonstration text. It contains no real participant, "
                "publication, effect, or scientific finding. A learner can select passages, "
                "screen the record, and practice evidence linkage safely."
            ),
            source_label="Synthetic local tutorial fixture",
        )
        if source is None:
            self.open_project(self.project_id)
            return
        note = self._call(
            "ui.notebook.save",
            notebook=(
                "Tutorial note: this project contains synthetic content only. "
                "Any interpretation must remain labeled as practice."
            ),
        )
        if note is not None:
            for step in ("create-project", "add-source", "write-note"):
                self._call("ui.tutorial.step", step=step)
        self.refresh_projects()
        self.open_project(self.project_id)
        self.welcome_status.setText(
            "Synthetic demo created locally. No network call or AI provider was used."
        )
        self.navigate("Dashboard")

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
                self.manuscript_editor.document(),
                self.notebook_editor.document(),
                *(editor.document() for editor in self.protocol_fields.values()),
            )
        )

    def _schedule_journal(self, field: str) -> None:
        if not self._editor_loading and self.project_id:
            self._draft_timers[field].start()

    def _journal_editor(self, field: str) -> None:
        if not self.project_id or self._editor_loading:
            return
        editor = self.manuscript_editor if field == "manuscript" else self.notebook_editor
        self._call(
            "ui.recovery.save",
            field=field,
            text=editor.toPlainText(),
            expected_revision=self.revision,
        )

    def _confirm_leave_project(self) -> bool:
        """Protect draft text before project switching and application shutdown."""
        if not self.project_id or not self._writing_dirty():
            return True
        outcome = QMessageBox.question(
            self,
            "Unsaved research writing",
            "Save manuscript and notes before leaving this project?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if outcome == QMessageBox.StandardButton.Cancel:
            return False
        if outcome == QMessageBox.StandardButton.Save:
            if not self._save_both():
                QMessageBox.warning(
                    self,
                    "Save failed",
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
            document = editor.document()
            if document is None or not document.isModified():
                continue
            result = self._call(operation, **{operation.split(".")[1]: editor.toPlainText()})
            if result is None:
                return False
            document.setModified(False)
            self._draft_timers[operation.split(".")[1]].stop()
        if self.protocol_fields and any(
            bool(document and document.isModified())
            for document in (editor.document() for editor in self.protocol_fields.values())
        ):
            values = {key: editor.toPlainText() for key, editor in self.protocol_fields.items()}
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
        for label, field in (
            ("Project title", title),
            ("Research question", question),
            ("Study type", study),
        ):
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
        result = self._call(
            "ui.project.create",
            title=title.text(),
            question=question.text(),
            study_type=study.currentText(),
        )
        if result:
            self.project_id = result["project_id"]
            self.refresh_projects()
            self.open_project(self.project_id)
            self.navigate("Dashboard")

    def open_project(self, project_id: str) -> None:
        for timer in self._draft_timers.values():
            timer.stop()
        response = self._call("ui.project.open", project_id=project_id)
        if response is None:
            return
        self.jobs.invalidate()
        project = response["project"]
        self.project_id = project["id"]
        self.project_title = project["title"]
        self.project_context.setText(f"{self.project_title} · local only")
        self.setWindowTitle(f"{self.base_window_title} · {self.project_title}")
        self.revision = project["revision"]
        self.current_source_id = ""
        self.current_dataset_id = ""
        self.assistant_conversation_id = None
        self.assistant_pending_tool = None
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
        self.refresh_dashboard()
        self.refresh_question()
        self.refresh_review()
        self.refresh_prisma()
        self.refresh_extraction()
        self.refresh_datasets()
        self.refresh_protocol()
        self.refresh_codebook()
        self.refresh_mixed_links()
        self.refresh_references()
        self.refresh_analysis_results()
        self.refresh_agent_timeline()
        self.refresh_provider()
        self.refresh_assistant()
        self.refresh_privacy()
        self.refresh_integrations()
        self.refresh_notifications()
        self.refresh_tutorials()
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
        self.library_offset = 0
        self._load_library_page()

    def _load_library_page(self) -> None:
        if not self.project_id:
            return
        value = self._call(
            "ui.source.search",
            query=self.search.text(),
            offset=self.library_offset,
            limit=self.library_page_size,
            sort_by=str(self.library_sort.currentData() or "title"),
            sort_desc=self.library_sort_desc.isChecked(),
        )
        if value is None:
            return
        self.library_total = value["total"]
        self.library_list.clear()
        for source in value["sources"]:
            item = QListWidgetItem(f"{source['title']} · {source['source_label']}")
            item.setData(Qt.ItemDataRole.UserRole, source["id"])
            self.library_list.addItem(item)
        if not value["sources"]:
            message = (
                "No matching sources. Clear the search or import source text."
                if self.search.text().strip()
                else "No sources yet. Import source text to begin building evidence."
            )
            self.library_list.addItem(empty_list_item(message))
        start = self.library_offset + 1 if self.library_total else 0
        end = min(self.library_offset + len(value["sources"]), self.library_total)
        self.library_status.setText(
            f"Sources {start}–{end} of {self.library_total} · sorted by {value['sort_by']}"
        )
        self._set_status(f"{value['total']} matching sources")

    def reset_library_page(self) -> None:
        self.library_offset = 0
        self._load_library_page()

    def previous_library_page(self) -> None:
        if self.library_offset > 0:
            self.library_offset = max(0, self.library_offset - self.library_page_size)
            self._load_library_page()

    def next_library_page(self) -> None:
        if self.library_offset + self.library_page_size < self.library_total:
            self.library_offset += self.library_page_size
            self._load_library_page()

    def select_source(self) -> None:
        selected = self.library_list.currentItem()
        if selected is None:
            return
        source_id = selected.data(Qt.ItemDataRole.UserRole)
        if not isinstance(source_id, str) or not source_id:
            return
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
        if not isinstance(selected_id, str) or not selected_id:
            self._set_status("No reviewable source is selected.")
            return
        reviewer = self.reviewer_alias.text().strip()
        if not reviewer:
            self._set_status("Enter a local reviewer alias before screening.")
            self.reviewer_alias.setFocus()
            return
        if self._call(
            "ui.screening.vote",
            source_id=selected_id,
            reviewer=reviewer,
            decision=decision,
            reason=self.review_reason.text(),
        ):
            self.current_source_id = selected_id
            self.refresh_review()

    def adjudicate_selected(self) -> None:
        selected = self.review_queue.currentItem()
        if selected is None:
            self._set_status("Select a screening conflict first.")
            return
        selected_id = selected.data(Qt.ItemDataRole.UserRole)
        if not isinstance(selected_id, str) or not selected_id:
            self._set_status("No screening conflict is selected.")
            return
        response = self._call(
            "ui.screening.adjudicate",
            source_id=selected_id,
            adjudicator=self.adjudicator_alias.text(),
            final_decision=self.adjudication_choice.currentText(),
            rationale=self.adjudication_reason.text(),
        )
        if response is not None:
            self.adjudication_reason.clear()
            self.refresh_review()

    def _select_review_source(
        self, current: QListWidgetItem | None, previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        source_id = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(source_id, str) or not source_id:
            return
        self.current_source_id = source_id
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
        counts = self._call("ui.screening.flow")
        if counts:
            states = counts["status_counts"]
            self.review_summary.setText(
                f"Sources: {counts['local_source_records']} · decisions: "
                f"{counts['decision_events']} · adjudications: {counts['adjudication_events']}\n"
                f"Pending: {states['pending']} · awaiting second: {states['awaiting-second']} · "
                f"conflict: {states['conflict']} · agreed: {states['agreed']} · "
                f"adjudicated: {states['adjudicated']}\n"
                f"Final include: {counts['included']} · exclude: {counts['excluded']} · "
                f"unsure: {counts['unsure_after_adjudication']}\n"
                f"{counts['note']}"
            )
        reviewer = self.reviewer_alias.text().strip()
        filtered = self._call("ui.screening.queue", reviewer=reviewer)
        if filtered is None:
            return
        selected = self.review_queue.currentItem()
        previous_selection = selected.data(Qt.ItemDataRole.UserRole) if selected else ""
        self.review_queue.blockSignals(True)
        self.review_queue.clear()
        for source in filtered["records"]:
            selection = self.review_filter.currentText()
            if selection != "All" and source["status"] != selection:
                continue
            outcome = (
                "peer decision hidden"
                if source["computed_status"] == "blinded"
                else source["final_decision"] or "no final outcome"
            )
            item = QListWidgetItem(f"{source['status'].upper()} · {source['title']} · {outcome}")
            item.setData(Qt.ItemDataRole.UserRole, source["source_id"])
            item.setToolTip(f"{source['title']}; screening status {source['status']}")
            self.review_queue.addItem(item)
            if source["source_id"] == previous_selection:
                self.review_queue.setCurrentItem(item)
        self.review_queue.blockSignals(False)
        if self.review_queue.count() == 0:
            self.review_queue.addItem(
                empty_list_item("No sources match this review queue and reviewer context.")
            )
        self.review_reason.clear()

    @staticmethod
    def _comma_values(text: str) -> list[str]:
        return [item.strip() for item in text.split(",") if item.strip()]

    def refresh_question(self) -> None:
        if not self.project_id:
            self.question_status.setText("Create or open a project first.")
            return
        response = self._call("ui.question.read")
        if response is None:
            return
        record = response["question_structure"]
        self.question_topic.setText(record.get("topic", ""))
        self.question_population.setText(record.get("population_context", ""))
        self.question_exposure.setText(record.get("exposure_phenomenon", ""))
        self.question_outcome.setText(record.get("outcome_target", ""))
        self.question_type.setCurrentText(record.get("question_type", "descriptive"))
        self.question_editable.setPlainText(
            record.get("editable_question", response["fallback_question"])
        )
        self.question_status.setText(
            "Saved structured question loaded."
            if record
            else "No structured question yet. Existing free-text question is shown for editing."
        )

    def save_question(self) -> None:
        response = self._call(
            "ui.question.update",
            topic=self.question_topic.text(),
            population_context=self.question_population.text(),
            exposure_phenomenon=self.question_exposure.text(),
            outcome_target=self.question_outcome.text(),
            question_type=self.question_type.currentText(),
            editable_question=self.question_editable.toPlainText(),
        )
        if response is not None:
            self.question_status.setText(
                "Structured question saved. Methodological validity still requires human review."
            )
            self.refresh_dashboard()

    def refresh_dashboard(self) -> None:
        if not self.project_id:
            self.dashboard.setText("Choose a project or create a new one.")
            self.dashboard_sources_value.setText("—")
            self.dashboard_datasets_value.setText("—")
            self.dashboard_screening_value.setText("—")
            self.dashboard_writing_value.setText("—")
            return
        self.dashboard.setText("Loading local project state…")
        response = self._call("ui.project.dashboard")
        if response is None:
            self.dashboard.setText(
                "Dashboard could not load. Review the status message, then use Refresh dashboard."
            )
            return
        screening = response["screening"]
        states = screening["status_counts"]
        jobs = [f"{job.task_id}: {job.state} ({job.progress}%)" for job in self.jobs.jobs.values()]
        manuscript_chars = int(response["draft"]["manuscript_characters"])
        notebook_chars = int(response["draft"]["notebook_characters"])
        self.dashboard_sources_value.setText(str(response["source_count"]))
        self.dashboard_sources_detail.setText("Local source records")
        self.dashboard_datasets_value.setText(str(response["dataset_count"]))
        self.dashboard_datasets_detail.setText("Structured datasets")
        self.dashboard_screening_value.setText(str(screening["screened_with_final_outcome"]))
        self.dashboard_screening_detail.setText(
            f"{states['pending']} pending · {states['conflict']} conflicts"
        )
        self.dashboard_writing_value.setText(f"{manuscript_chars + notebook_chars:,}")
        self.dashboard_writing_detail.setText(
            f"{manuscript_chars:,} manuscript · {notebook_chars:,} notes"
        )
        self.dashboard.setText(
            f"{response['title']}\n\nResearch question: {response['question']}\n"
            f"Sources: {response['source_count']} · datasets: {response['dataset_count']}\n"
            f"Screening: {states['pending']} pending · {states['conflict']} conflicts · "
            f"{screening['screened_with_final_outcome']} final outcomes\n"
            f"Writing: {manuscript_chars} manuscript characters · "
            f"{notebook_chars} note characters\n\n"
            f"Jobs: {'; '.join(jobs) if jobs else 'none running or retained'}\n"
            f"Next: {'; '.join(response['next_steps'])}\n"
            f"Warnings: {'; '.join(response['warnings']) or 'none'}"
        )

    def _parse_prisma_count(self, key: str) -> int | None:
        text = self.prisma_fields[key].text().strip()
        if not text:
            return None
        try:
            value = int(text)
        except ValueError:
            self._set_status(f"{key.replace('_', ' ')} must be a nonnegative integer or blank.")
            return -1
        if value < 0:
            self._set_status(f"{key.replace('_', ' ')} cannot be negative.")
            return -1
        return value

    def save_prisma(self) -> None:
        flow: dict[str, Any] = {}
        for key in self.prisma_fields:
            value = self._parse_prisma_count(key)
            if value == -1:
                return
            flow[key] = value
        reasons: dict[str, int] = {}
        for part in self.prisma_reasons.text().split(";"):
            if not part.strip():
                continue
            label, separator, raw = part.partition("=")
            if not separator:
                self._set_status(
                    "Exclusion reasons use Reason=number entries separated by semicolons."
                )
                return
            try:
                count = int(raw.strip())
            except ValueError:
                self._set_status("Each PRISMA exclusion reason needs an integer count.")
                return
            if count < 0:
                self._set_status("PRISMA exclusion reason counts cannot be negative.")
                return
            reasons[label.strip()] = count
        flow["exclusion_reasons"] = reasons
        if self._call("ui.prisma.update", flow=flow) is not None:
            self.refresh_prisma()

    def refresh_prisma(self) -> None:
        if not self.project_id:
            self.prisma_summary.setPlainText("Open a project to inspect review-flow evidence.")
            return
        response = self._call("ui.prisma.read")
        if response is None:
            return
        flow = response["flow"]
        lines = []
        for key in self.prisma_fields:
            value = flow.get(key)
            shown = "unknown" if value is None else str(value)
            lines.append(f"{key.replace('_', ' ').title()}: {shown}")
            self.prisma_fields[key].setText("" if value is None else str(value))
        lines.append(f"Exclusion reasons: {flow['exclusion_reasons'] or 'none recorded'}")
        lines.append(flow["warning"])
        self.prisma_summary.setPlainText("\n".join(lines))

    def preview_prisma_export(self) -> None:
        response = self._call("ui.prisma.export")
        if response is None:
            return
        unknown = ", ".join(response["unknown_fields"]) or "none"
        self.prisma_summary.appendPlainText(
            "\n\nStructured export preview:\n"
            f"SHA-256: {response['sha256']}\n"
            f"Unknown fields preserved: {unknown}\n"
            "No missing flow count was synthesized."
        )

    def add_extraction_field(self) -> None:
        name = self.extraction_field_name.text().strip()
        if not name:
            self._set_status("Enter an extraction field name.")
            return
        field_type = self.extraction_field_type.currentText()
        record: dict[str, Any] = {
            "name": name,
            "label": name.replace("_", " ").title(),
            "field_type": field_type,
            "required": self.extraction_required.isChecked(),
            "description": "",
        }
        if field_type == "categorical":
            record["categories"] = self._comma_values(self.extraction_categories.text())
        self.extraction_pending_fields.append(record)
        self.extraction_fields_list.addItem(
            f"{name} · {field_type} · {'required' if record['required'] else 'optional'}"
        )
        self.extraction_field_name.clear()
        self.extraction_categories.clear()
        self.extraction_required.setChecked(False)

    def save_extraction_schema(self) -> None:
        if not self.extraction_pending_fields:
            self._set_status("Add at least one extraction field.")
            return
        response = self._call(
            "ui.extraction.schema.update",
            title=self.extraction_title.text(),
            fields=self.extraction_pending_fields,
        )
        if response is not None:
            self.extraction_pending_fields.clear()
            self.refresh_extraction()

    def _clear_extraction_record_form(self) -> None:
        self.extraction_value_widgets.clear()
        while self.extraction_record_form.count():
            child = self.extraction_record_form.takeAt(0)
            if child is None:
                break
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

    def refresh_extraction(self) -> None:
        self._clear_extraction_record_form()
        self.extraction_records.clear()
        self.extraction_source.clear()
        if not self.project_id:
            return
        sources = self._call("ui.source.search", query="", limit=500)
        if sources is not None:
            for source in sources["sources"]:
                self.extraction_source.addItem(source["title"], source["id"])
        response = self._call("ui.extraction.list")
        if response is None:
            return
        schema = response["schema"]
        if not schema:
            self.extraction_fields_list.clear()
            self.extraction_fields_list.addItem("No extraction form saved yet.")
            return
        self.extraction_title.setText(schema["title"])
        self.extraction_fields_list.clear()
        for field in schema["fields"]:
            self.extraction_fields_list.addItem(
                f"v{schema['version']} · {field['name']} · {field['field_type']} · "
                f"{'required' if field['required'] else 'optional'}"
            )
            if field["field_type"] == "categorical":
                combo = QComboBox()
                combo.addItems(field.get("categories", []))
                widget: QWidget = combo
            elif field["field_type"] == "boolean":
                combo = QComboBox()
                combo.addItems(["", "true", "false"])
                widget = combo
            else:
                widget = QLineEdit()
            named(widget, f"Extraction value {field['label']}")
            self.extraction_record_form.addRow(
                f"{field['label']} {'*' if field['required'] else ''}", widget
            )
            widget.setProperty("field_type", field["field_type"])
            self.extraction_value_widgets[field["name"]] = widget
        for record in response["records"]:
            self.extraction_records.addItem(
                f"{record['id']} · source {record['source_id']} · "
                f"schema v{record['schema_version']}"
            )

    def _extraction_widget_value(self, widget: QWidget) -> Any:
        field_type = str(widget.property("field_type"))
        if isinstance(widget, QComboBox):
            text = widget.currentText().strip()
        elif isinstance(widget, QLineEdit):
            text = widget.text().strip()
        else:
            return None
        if not text:
            return None
        if field_type == "integer":
            try:
                return int(text)
            except ValueError:
                return text
        if field_type == "float":
            try:
                return float(text)
            except ValueError:
                return text
        if field_type == "boolean":
            return text == "true"
        return text

    def save_extraction_record(self) -> None:
        source_id = self.extraction_source.currentData()
        if not source_id:
            self._set_status("Choose a source for the extraction record.")
            return
        values = {
            name: self._extraction_widget_value(widget)
            for name, widget in self.extraction_value_widgets.items()
        }
        if self._call("ui.extraction.record.save", source_id=source_id, values=values) is not None:
            self.refresh_extraction()

    def annotate_selection(self) -> None:
        if not self.current_source_id:
            self._set_status("Select a source in Library first.")
            return
        cursor = self.reader_text.textCursor()
        if not cursor.hasSelection():
            self._set_status("Highlight a passage in Reader before coding.")
            return
        try:
            start, end = qt_range_to_codepoints(
                self.reader_text.toPlainText(), cursor.selectionStart(), cursor.selectionEnd()
            )
        except UIError as exc:
            self._set_status(f"{exc.message} {exc.recovery}")
            return
        code, accepted = QInputDialog.getText(self, "Code selected source text", "Code label")
        if accepted and self._call(
            "ui.qual.annotate", source_id=self.current_source_id, start=start, end=end, code=code
        ):
            self.refresh_annotations()

    def refresh_annotations(self) -> None:
        self.annotation_list.clear()
        if not self.project_id:
            return
        value = self._call("ui.qual.list")
        if value:
            for item in value["annotations"]:
                overlap = (
                    f" · overlaps {item['overlap_count']}" if item.get("overlap_count") else ""
                )
                row = QListWidgetItem(f"{item['code']}: {item['quote'][:120]}{overlap}")
                row.setData(Qt.ItemDataRole.UserRole, item)
                if item.get("overlap_ids"):
                    row.setToolTip(
                        "Overlapping annotation IDs: "
                        + ", ".join(str(value) for value in item["overlap_ids"])
                    )
                self.annotation_list.addItem(row)

    def _open_source_span(self, source_id: str, start: int, end: int, label: str) -> None:
        response = self._call("ui.source.get", source_id=source_id)
        if response is None:
            return
        source = response["source"]
        try:
            qt_start, qt_end = codepoint_range_to_qt(source["text"], start, end)
        except UIError as exc:
            self._set_status(f"{exc.message} {exc.recovery}")
            return
        self.current_source_id = source_id
        self.reader_meta.setText(
            f"{source['title']} · {source['source_label']} · "
            f"SHA-256 {source['content_hash']}\n{label}"
        )
        self.reader_text.setPlainText(source["text"])
        cursor = self.reader_text.textCursor()
        cursor.setPosition(qt_start)
        cursor.setPosition(qt_end, QTextCursor.MoveMode.KeepAnchor)
        self.reader_text.setTextCursor(cursor)
        self.reader_text.ensureCursorVisible()
        self.navigate("Reader")

    def open_selected_annotation_source(self, item: QListWidgetItem | bool | None = None) -> None:
        selected = item if isinstance(item, QListWidgetItem) else self.annotation_list.currentItem()
        if selected is None:
            self._set_status("Select an annotation first.")
            return
        record = selected.data(Qt.ItemDataRole.UserRole)
        if not isinstance(record, dict):
            return
        self._open_source_span(
            str(record["source_id"]),
            int(record["start"]),
            int(record["end"]),
            f"Annotation {record['id']} · code {record['code']}",
        )

    def load_annotation_for_edit(
        self, current: QListWidgetItem | None, previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            self.annotation_code.clear()
            self.annotation_memo.clear()
            return
        record = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(record, dict):
            return
        self.annotation_code.setText(str(record.get("code", "")))
        self.annotation_memo.setText(str(record.get("memo", "")))

    def update_annotation(self) -> None:
        current = self.annotation_list.currentItem()
        if current is None:
            self._set_status("Select an annotation to edit.")
            return
        record = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(record, dict):
            return
        response = self._call(
            "ui.qual.annotation.update",
            annotation_id=str(record["id"]),
            code=self.annotation_code.text(),
            memo=self.annotation_memo.text(),
        )
        if response is not None:
            annotation_id = str(response["annotation"]["id"])
            self.refresh_annotations()
            for row in range(self.annotation_list.count()):
                item = self.annotation_list.item(row)
                if item is None:
                    continue
                record = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(record, dict) and str(record.get("id", "")) == annotation_id:
                    self.annotation_list.setCurrentItem(item)
                    break
            self._set_status("Updated annotation code and memo without changing its source span.")

    def refresh_codebook(self) -> None:
        self.codebook_list.clear()
        if not self.project_id:
            return
        response = self._call("ui.codebook.list")
        if response is None:
            return
        for code in response["codes"]:
            item = QListWidgetItem(
                f"{code['marker']} {code['name']} · {code['description'] or 'no description'}"
            )
            item.setData(Qt.ItemDataRole.UserRole, code)
            self.codebook_list.addItem(item)
        for trace in response["recoding_trace"][-10:]:
            self.codebook_list.addItem(
                f"TRACE · merged {len(trace['source_ids'])} code(s) into {trace['target_id']} · "
                f"{trace['affected_annotations']} annotations recoded"
            )

    def save_code(self) -> None:
        response = self._call(
            "ui.codebook.upsert",
            code_id="",
            name=self.code_name.text(),
            description=self.code_description.text(),
            inclusion_rule=self.code_inclusion.text(),
            exclusion_rule=self.code_exclusion.text(),
            marker=self.code_marker.text() or "●",
        )
        if response is not None:
            self.code_name.clear()
            self.code_description.clear()
            self.code_inclusion.clear()
            self.code_exclusion.clear()
            self.refresh_codebook()

    def merge_codes_ui(self) -> None:
        response = self._call(
            "ui.codebook.merge",
            source_ids=self._comma_values(self.code_merge_sources.text()),
            target_id=self.code_merge_target.text().strip(),
            conflict_note=self.code_merge_note.text(),
        )
        if response is not None:
            self.code_merge_sources.clear()
            self.code_merge_target.clear()
            self.code_merge_note.clear()
            self.refresh_codebook()
            self.refresh_annotations()

    def refresh_mixed_links(self) -> None:
        self.mixed_links.clear()
        if not self.project_id:
            return
        response = self._call("ui.mixed.list")
        if response is None:
            return
        for record in response["links"]:
            item = QListWidgetItem(
                f"{record['relation'].upper()} · {len(record['qualitative_refs'])} qualitative ↔ "
                f"{len(record['quantitative_refs'])} quantitative · {record['evidence_origin']}"
            )
            item.setToolTip(record["warning"])
            self.mixed_links.addItem(item)

    def add_mixed_link(self) -> None:
        response = self._call(
            "ui.mixed.add",
            link={
                "qualitative_refs": self._comma_values(self.mixed_qual_refs.text()),
                "quantitative_refs": self._comma_values(self.mixed_quant_refs.text()),
                "relation": self.mixed_relation.currentText(),
                "units": self.mixed_units.text(),
                "group_definition": self.mixed_groups.text(),
                "evidence_origin": self.mixed_origin.text(),
                "interpretation": self.mixed_interpretation.text(),
            },
        )
        if response is not None:
            self.refresh_mixed_links()
            self._set_status(response["link"]["warning"])

    def refresh_references(self) -> None:
        self.reference_list.clear()
        if not self.project_id:
            return
        response = self._call("ui.reference.list")
        if response is None:
            return
        for record in response["references"]:
            state = "verified" if record["verified"] else "unverified"
            item = QListWidgetItem(f"{state.upper()} · {record['title']}")
            item.setData(Qt.ItemDataRole.UserRole, record)
            self.reference_list.addItem(item)

    def save_reference(self) -> None:
        response = self._call(
            "ui.reference.upsert",
            reference={
                "title": self.reference_title.text(),
                "authors": self._comma_values(self.reference_authors.text()),
                "year": self.reference_year.text(),
                "container": self.reference_container.text(),
                "doi": self.reference_doi.text(),
                "url": self.reference_url.text(),
                "verified": self.reference_verified.isChecked(),
                "verification_note": (
                    "Manually verified by local user."
                    if self.reference_verified.isChecked()
                    else "Metadata remains unverified."
                ),
            },
        )
        if response is not None:
            self.refresh_references()

    def inspect_reference(
        self, current: QListWidgetItem | None, previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        record = current.data(Qt.ItemDataRole.UserRole)
        citation = self._call("ui.reference.citation", reference_id=record["id"])
        if citation is None:
            return
        self.reference_detail.setText(
            f"{citation['text']}\nVerified: {citation['verified']} · "
            f"missing: {', '.join(citation['missing_fields']) or 'none'}\n"
            f"{citation['warning']}"
        )

    def insert_selected_citation(self) -> None:
        current = self.reference_list.currentItem()
        if current is None:
            self._set_status("Select a reference first.")
            return
        record = current.data(Qt.ItemDataRole.UserRole)
        citation = self._call("ui.reference.citation", reference_id=record["id"])
        if citation is None:
            return
        if citation["missing_fields"]:
            self._set_status(
                "Citation has missing metadata; correct it before manuscript insertion."
            )
            return
        cursor = self.manuscript_editor.textCursor()
        cursor.insertText(citation["text"])
        document = self.manuscript_editor.document()
        if document is not None:
            document.setModified(True)
        self.navigate("Manuscript")

    def refresh_manuscript_sections(self) -> None:
        self.manuscript_section_list.clear()
        if not self.project_id:
            return
        response = self._call("ui.manuscript.sections.read")
        if response is None:
            return
        for section in response["sections"]:
            item = QListWidgetItem(f"{section['order'] + 1}. {section['title']}")
            item.setData(Qt.ItemDataRole.UserRole, section)
            self.manuscript_section_list.addItem(item)

    def load_manuscript_section(
        self, current: QListWidgetItem | None, previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            self.manuscript_section_title.clear()
            self.manuscript_section_body.clear()
            return
        section = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(section, dict):
            return
        self.manuscript_section_title.setText(str(section.get("title", "")))
        self.manuscript_section_body.setPlainText(str(section.get("body", "")))

    def upsert_manuscript_section(self) -> None:
        title = self.manuscript_section_title.text().strip()
        if not title:
            self._set_status("Enter a manuscript section title.")
            return
        current = self.manuscript_section_list.currentItem()
        section = (
            dict(current.data(Qt.ItemDataRole.UserRole))
            if current is not None and isinstance(current.data(Qt.ItemDataRole.UserRole), dict)
            else {"id": "", "order": self.manuscript_section_list.count()}
        )
        section["title"] = title
        section["body"] = self.manuscript_section_body.toPlainText()
        if current is None:
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, section)
            self.manuscript_section_list.addItem(item)
            self.manuscript_section_list.setCurrentItem(item)
        else:
            current.setText(title)
            current.setData(Qt.ItemDataRole.UserRole, section)
        self._set_status("Section staged locally; save structured sections to persist it.")

    def remove_manuscript_section(self) -> None:
        row = self.manuscript_section_list.currentRow()
        if row < 0:
            self._set_status("Select a manuscript section to remove.")
            return
        self.manuscript_section_list.takeItem(row)
        self.manuscript_section_title.clear()
        self.manuscript_section_body.clear()
        self._set_status("Section removed locally; save structured sections to persist the change.")

    def save_manuscript_sections(self) -> None:
        sections: list[dict[str, Any]] = []
        for row in range(self.manuscript_section_list.count()):
            item = self.manuscript_section_list.item(row)
            if item is None:
                continue
            section = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(section, dict):
                continue
            sections.append(
                {
                    "id": str(section.get("id", "")),
                    "title": str(section.get("title", "")),
                    "body": str(section.get("body", "")),
                }
            )
        response = self._call("ui.manuscript.sections.update", sections=sections)
        if response is not None:
            project = self._call("ui.project.open", project_id=self.project_id)
            if project is not None:
                self.manuscript_editor.setPlainText(project["project"]["manuscript"])
                document = self.manuscript_editor.document()
                if document is not None:
                    document.setModified(False)
            self.refresh_manuscript_sections()
            self._set_status("Saved structured manuscript sections and regenerated the draft.")

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
        for selector in (self.auto_outcome, self.auto_group, self.auto_paired):
            selector.clear()
            selector.addItem("Not set", "")
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
        self.data_filter.clear()
        self.data_sort.blockSignals(True)
        self.data_sort.clear()
        self.data_sort.addItem("No sort", "")
        self.load_data_page()
        self.variable_list.clear()
        self.variable_picker.clear()
        response = self._call("ui.dataset.variables", dataset_id=self.current_dataset_id)
        if response is not None:
            for variable in response["variables"]:
                self.data_sort.addItem(variable["name"], variable["name"])
                item = QListWidgetItem(
                    f"{variable['name']} · {variable['inferred_type']} · "
                    f"missing {variable['missing_n']} / {response['total_rows']}"
                )
                item.setData(Qt.ItemDataRole.UserRole, variable["name"])
                self.variable_list.addItem(item)
                self.variable_picker.addItem(variable["name"])
                self.auto_outcome.addItem(variable["name"], variable["name"])
                self.auto_group.addItem(variable["name"], variable["name"])
                self.auto_paired.addItem(variable["name"], variable["name"])
        self.data_sort.blockSignals(False)
        methods = self._call("ui.analysis.methods")
        if methods is not None:
            self.analysis_method.clear()
            for method in methods["methods"]:
                label = method["label"]
                if not method.get("available", False):
                    label += " · unavailable"
                self.analysis_method.addItem(label, method)
            self.analysis_compatibility_model.set_records(
                COMPATIBILITY_COLUMNS,
                build_compatibility_rows(methods["methods"]),
            )
            if self.analysis_compatibility_model.rowCount():
                self.analysis_compatibility_table.setCurrentIndex(
                    self.analysis_compatibility_model.index(0, 0)
                )
            self.prepare_analysis_arguments()

    def inspect_analysis_compatibility(self, current: Any, previous: Any) -> None:
        del previous
        if current is None or not current.isValid():
            return
        row = current.row()
        if row < 0 or row >= len(self.analysis_compatibility_model.rows):
            return
        values = self.analysis_compatibility_model.rows[row]
        if len(values) < 5:
            return
        self.analysis_compatibility_detail.setText(
            f"Reproducibility: {values[3]}\nLimits: {values[4]}"
        )

    def prepare_analysis_arguments(self) -> None:
        while self.analysis_guided_form.rowCount():
            self.analysis_guided_form.removeRow(0)
        self.analysis_guided_widgets.clear()
        self.analysis_guided_specs = ()
        self.analysis_guided_supported = False
        method = self.analysis_method.currentData()
        if not isinstance(method, dict):
            return
        if method.get("id") in {"descriptive", "analysis.statistics.describe"}:
            self.analysis_arguments.setPlainText("{}")
            self.analysis_arguments.setReadOnly(True)
            self.analysis_arguments.setVisible(False)
            return
        schema = method.get("arguments_schema", {})
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        defaults: dict[str, object] = {}
        if isinstance(properties, dict):
            if "dataset_id" in properties and self.current_dataset_id:
                defaults["dataset_id"] = self.current_dataset_id
            if "column" in properties and self.variable_picker.currentText():
                defaults["column"] = self.variable_picker.currentText()
        self.analysis_arguments.setPlainText(json.dumps(defaults, indent=2))
        if not isinstance(schema, dict) or not isinstance(properties, dict) or not properties:
            self.analysis_arguments.setReadOnly(False)
            self.analysis_arguments.setVisible(True)
            return
        try:
            specs = build_field_specs(schema)
        except ValueError:
            self.analysis_arguments.setReadOnly(False)
            self.analysis_arguments.setVisible(True)
            return
        self.analysis_guided_specs = specs
        self.analysis_guided_supported = True
        self.analysis_arguments.setReadOnly(True)
        self.analysis_arguments.setVisible(False)
        for spec in specs:
            widget: QWidget
            if spec.kind == "string" and spec.variable:
                picker = QComboBox()
                picker.addItem("Select variable", "")
                for index in range(self.variable_picker.count()):
                    name = self.variable_picker.itemText(index)
                    picker.addItem(name, name)
                if spec.name in {"column", "outcome"} and self.variable_picker.currentText():
                    selected = picker.findData(self.variable_picker.currentText())
                    if selected >= 0:
                        picker.setCurrentIndex(selected)
                widget = picker
            elif spec.choices or spec.kind == "boolean":
                picker = QComboBox()
                picker.addItem("Not set", "")
                choices = spec.choices if spec.choices else ("true", "false")
                for choice in choices:
                    picker.addItem(choice, choice)
                widget = picker
            elif spec.kind == "json":
                editor = QPlainTextEdit()
                editor.setMaximumHeight(70)
                editor.setPlaceholderText("JSON object or array")
                widget = editor
            else:
                editor_line = QLineEdit()
                if spec.kind == "string-array":
                    editor_line.setPlaceholderText("Comma-separated variable names")
                widget = editor_line
            friendly_labels = {
                "column": "Variable",
                "columns": "Variables",
                "x": "First variable",
                "y": "Second variable",
                "first": "First variable",
                "second": "Second variable",
                "group": "Grouping variable",
                "levels": "Group levels",
                "outcome": "Outcome",
                "predictors": "Predictors",
                "covariates": "Covariates",
                "factor": "Factor",
                "factors": "Factors",
                "subject": "Subject identifier",
                "within": "Within-subject factor",
                "duration": "Duration variable",
                "event": "Event indicator",
                "time_column": "Time variable",
                "value_column": "Value variable",
            }
            label_text = friendly_labels.get(spec.name, spec.name.replace("_", " ").title())
            label = f"{label_text}{' *' if spec.required else ''}"
            widget.setAccessibleName(f"Analysis {label}")
            widget.setAccessibleDescription(spec.description or f"Input for {spec.name}")
            self.analysis_guided_form.addRow(label, widget)
            self.analysis_guided_widgets[spec.name] = widget
            if isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._preview_guided_analysis)
            elif isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._preview_guided_analysis)
            elif isinstance(widget, QPlainTextEdit):
                widget.textChanged.connect(self._preview_guided_analysis)
        self._preview_guided_analysis()

    def _guided_analysis_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for name, widget in self.analysis_guided_widgets.items():
            if isinstance(widget, QComboBox):
                values[name] = str(widget.currentData() or "")
            elif isinstance(widget, QLineEdit):
                values[name] = widget.text()
            elif isinstance(widget, QPlainTextEdit):
                values[name] = widget.toPlainText()
        return values

    def _preview_guided_analysis(self) -> None:
        if not self.analysis_guided_supported:
            return
        method = self.analysis_method.currentData()
        schema = method.get("arguments_schema", {}) if isinstance(method, dict) else {}
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        preview: dict[str, object] = {}
        if isinstance(properties, dict) and "dataset_id" in properties and self.current_dataset_id:
            preview["dataset_id"] = self.current_dataset_id
        try:
            preview.update(
                parse_form_values(self.analysis_guided_specs, self._guided_analysis_values())
            )
        except ValueError:
            pass
        self.analysis_arguments.setPlainText(json.dumps(preview, indent=2))

    def load_data_page(self) -> None:
        if not self.current_dataset_id:
            self.data_model.set_records([], [])
            return
        response = self._call(
            "ui.dataset.page",
            dataset_id=self.current_dataset_id,
            offset=self.data_offset,
            limit=self.data_page_size,
            filter_text=self.data_filter.text(),
            sort_column=str(self.data_sort.currentData() or ""),
            sort_desc=self.data_sort_desc.isChecked(),
        )
        if response is None:
            return
        self.data_total = response["total"]
        self.data_model.set_records(response["columns"], response["rows"])
        beginning = self.data_offset + 1 if self.data_total else 0
        last = min(self.data_offset + len(response["rows"]), self.data_total)
        filter_note = (
            f" · filtered from {response['dataset_total']}"
            if response["dataset_total"] != response["total"]
            else ""
        )
        self.data_page_status.setText(
            f"Rows {beginning}–{last} of {self.data_total}{filter_note} · read-only · "
            "synthetic or imported data"
        )

    def apply_data_view(self) -> None:
        self.data_offset = 0
        self.load_data_page()

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
        result = self._call(
            "ui.dataset.describe",
            dataset_id=self.current_dataset_id,
            column=self.variable_picker.currentText(),
        )
        if result is not None:
            self.stats_result.setPlainText(
                "\n".join(f"{key}: {value}" for key, value in result.items())
            )
            chart_response = self._call(
                "ui.chart.histogram",
                dataset_id=self.current_dataset_id,
                column=self.variable_picker.currentText(),
                bins=10,
            )
            if chart_response is not None:
                data = chart_response["chart"]
                spec = ChartSpec(
                    title=data["title"],
                    column=data["column"],
                    kind=data["kind"],
                    x_label=data["x_label"],
                    y_label=data["y_label"],
                    bins=tuple(Bin(**item) for item in data["bins"]),
                    n=data["n"],
                    missing_n=data["missing_n"],
                    min_value=data["min_value"],
                    max_value=data["max_value"],
                    mean=data["mean"],
                    source_label=data["source_label"],
                    description=data["description"],
                )
                self.histogram_chart.set_chart(spec)
                self.stats_result.appendPlainText(
                    "\nHistogram table (accessible alternative):\n"
                    + "\n".join(
                        f"{item['interval']}: {item['count']} observations"
                        for item in data["accessibility_data"]
                    )
                )

    def _configured_plot_args(self) -> dict[str, Any]:
        return {
            "dataset_id": self.current_dataset_id,
            "column": self.variable_picker.currentText(),
            "plot_type": self.plot_type.currentText(),
            "unit": self.plot_unit.text(),
            "title": self.plot_title.text(),
            "x_label": self.plot_x_label.text(),
            "y_label": self.plot_y_label.text(),
            "bins": 10,
        }

    def render_configured_plot(self) -> None:
        if not self.current_dataset_id or not self.variable_picker.currentText():
            self._set_status("Choose a dataset and variable before plotting.")
            return
        operation = (
            "ui.chart.bar" if self.plot_type.currentText() == "bar" else "ui.chart.histogram"
        )
        args = self._configured_plot_args()
        args.pop("plot_type", None)
        response = self._call(operation, **args)
        if response is None:
            return
        data = response["chart"]
        spec = ChartSpec(
            title=data["title"],
            column=data["column"],
            kind=data["kind"],
            x_label=data["x_label"],
            y_label=data["y_label"],
            bins=tuple(Bin(**item) for item in data["bins"]),
            n=data["n"],
            missing_n=data["missing_n"],
            min_value=data["min_value"],
            max_value=data["max_value"],
            mean=data["mean"],
            source_label=data["source_label"],
            description=data["description"],
        )
        self.histogram_chart.set_chart(spec)
        self.stats_result.setPlainText(
            f"{spec.title}\nType: {spec.kind}\nN: {spec.n}\n"
            f"Missing: {spec.missing_n}\nX label: {spec.x_label}\n"
            f"Y label: {spec.y_label}\nSource: {spec.source_label}\n\n"
            "Accessible table:\n"
            + "\n".join(
                f"{item['interval']}: {item['count']} observations"
                for item in data["accessibility_data"]
            )
        )

    def preview_plot_exports(self) -> None:
        if not self.current_dataset_id or not self.variable_picker.currentText():
            self._set_status("Choose a dataset and variable before exporting a plot.")
            return
        args = self._configured_plot_args()
        svg = self._call("ui.chart.svg", **args, width=900, height=500)
        png = self._call("ui.chart.png", **args, width=900, height=500)
        if svg is None or png is None:
            return
        self.stats_result.appendPlainText(
            "\n\nExport receipts (preview only):\n"
            f"SVG SHA-256: {svg['sha256']}\n"
            f"PNG SHA-256: {png['sha256']} · {png['bytes']} bytes\n"
            "Both outputs represent the same descriptive configuration; "
            "no inferential result is added."
        )

    def save_plot_config(self) -> None:
        if not self.current_dataset_id or not self.variable_picker.currentText():
            self._set_status("Choose a dataset and variable before saving a plot config.")
            return
        name = self.plot_config_name.text().strip()
        if not name:
            self._set_status("Enter a plot configuration name.")
            return
        response = self._call("ui.chart.config.save", name=name, **self._configured_plot_args())
        if response is not None:
            self.refresh_plot_configs()
            self._set_status(f"Saved plot configuration {response['config']['name']}.")

    def refresh_plot_configs(self) -> None:
        self.plot_configs.clear()
        if not self.project_id:
            return
        response = self._call("ui.chart.config.list")
        if response is None:
            return
        for config in response["configs"]:
            item = QListWidgetItem(f"{config['name']} · {config['plot_type']} · {config['column']}")
            item.setData(Qt.ItemDataRole.UserRole, config)
            self.plot_configs.addItem(item)

    def restore_plot_config(self, item: QListWidgetItem) -> None:
        config = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(config, dict):
            return
        dataset_index = self.dataset_picker.findData(config["dataset_id"])
        if dataset_index >= 0:
            self.dataset_picker.setCurrentIndex(dataset_index)
        variable_index = self.variable_picker.findText(config["column"])
        if variable_index >= 0:
            self.variable_picker.setCurrentIndex(variable_index)
        self.plot_type.setCurrentText(config["plot_type"])
        self.plot_title.setText(config["title"])
        self.plot_x_label.setText(config["x_label"])
        self.plot_y_label.setText(config["y_label"])
        self.plot_unit.setText(config["unit"])
        self.plot_config_name.setText(config["name"])
        self.render_configured_plot()

    def export_plot_file(self) -> None:
        if not self.current_dataset_id or not self.variable_picker.currentText():
            self._set_status("Choose a dataset and variable before exporting a plot.")
            return
        filename = self.plot_export_name.text().strip()
        requested = "png" if filename.lower().endswith(".png") else "svg"
        args = self._configured_plot_args()
        preview_operation = "ui.chart.png" if requested == "png" else "ui.chart.svg"
        preview = self._call(preview_operation, **args, width=900, height=500)
        if preview is None:
            return
        outcome = QMessageBox.question(
            self,
            "Approve local plot export",
            f"Write {filename} to the local export folder?\nSHA-256: {preview['sha256']}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if outcome != QMessageBox.StandardButton.Yes:
            self._set_status("Plot export cancelled. No file was written.")
            return
        previous = self.facade.export_authorizer
        self.facade.export_authorizer = lambda approved: approved == filename
        try:
            receipt = self._call(
                "ui.chart.export.write",
                filename=filename,
                format=requested,
                width=900,
                height=500,
                **args,
            )
        finally:
            self.facade.export_authorizer = previous
        if receipt is not None:
            self.stats_result.appendPlainText(
                f"\n\nPlot file written: {receipt['path']}\n"
                f"SHA-256: {receipt['sha256']}\n"
                "Descriptive display only."
            )

    def refresh_code_execution(self) -> None:
        if not self.project_id:
            self.code_execution_status.setText(
                "Open a project to inspect the code-execution safety contract."
            )
            return
        response = self._call("ui.code.execution.status")
        if response is None:
            return
        requirements = response["required_integration"]
        self.code_execution_status.setText(
            f"Enabled: {response['enabled']} · Python: {response['python']} · "
            f"R: {response['r']}\n{response['reason']}\n"
            f"Required integration: {requirements}"
        )

    def load_variable_metadata(
        self, current: QListWidgetItem | None, previous: QListWidgetItem | None
    ) -> None:
        if current is None or not self.current_dataset_id:
            return
        variable = str(current.data(Qt.ItemDataRole.UserRole))
        response = self._call("ui.variable.metadata", dataset_id=self.current_dataset_id)
        record = None
        if response is not None:
            record = next(
                (item for item in response["records"] if item["variable"] == variable), None
            )
        if record is None:
            self.variable_type.setCurrentText("numeric")
            self.variable_role.setCurrentText("other")
            self.variable_units.clear()
            self.variable_levels.clear()
            self.variable_missing.clear()
            self.variable_description.clear()
            return
        self.variable_type.setCurrentText(record["type"])
        self.variable_role.setCurrentText(record["role"])
        self.variable_units.setText(record["units"])
        self.variable_levels.setText(", ".join(record["levels"]))
        self.variable_missing.setText(", ".join(record["missing_codes"]))
        self.variable_description.setText(record["description"])

    def save_variable_metadata(self) -> None:
        current = self.variable_list.currentItem()
        if current is None or not self.current_dataset_id:
            self._set_status("Select a variable from the active dataset.")
            return
        variable = str(current.data(Qt.ItemDataRole.UserRole))
        response = self._call(
            "ui.variable.metadata.update",
            dataset_id=self.current_dataset_id,
            variable=variable,
            metadata={
                "type": self.variable_type.currentText(),
                "role": self.variable_role.currentText(),
                "units": self.variable_units.text(),
                "levels": self._comma_values(self.variable_levels.text()),
                "missing_codes": self._comma_values(self.variable_missing.text()),
                "description": self.variable_description.text(),
            },
        )
        if response is not None:
            self._set_status(f"Saved metadata for {variable}.")

    def run_analysis(self) -> None:
        method = self.analysis_method.currentData()
        if not isinstance(method, dict):
            self._set_status("Choose an analysis method.")
            return
        if not method.get("available"):
            self.stats_result.setPlainText(
                f"{method['label']} is unavailable.\n{method.get('blocker', '')}\n"
                "No statistical result was fabricated."
            )
            return
        method_id = str(method.get("id", ""))
        if method_id in {"descriptive", "analysis.statistics.describe"} and (
            not self.current_dataset_id or not self.variable_picker.currentText()
        ):
            self._set_status("Choose a dataset and variable.")
            return
        if method_id in {"descriptive", "analysis.statistics.describe"}:
            inputs: dict[str, object] = {
                "dataset_id": self.current_dataset_id,
                "column": self.variable_picker.currentText(),
            }
        else:
            if self.analysis_guided_supported:
                try:
                    inputs = parse_form_values(
                        self.analysis_guided_specs, self._guided_analysis_values()
                    )
                except ValueError as exc:
                    self._set_status(str(exc))
                    return
                schema = method.get("arguments_schema", {})
                properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
                if isinstance(properties, dict) and "dataset_id" in properties:
                    if not self.current_dataset_id:
                        self._set_status("Choose a dataset before running this analysis.")
                        return
                    inputs["dataset_id"] = self.current_dataset_id
                self.analysis_arguments.setPlainText(json.dumps(inputs, indent=2))
            else:
                raw_arguments = self.analysis_arguments.toPlainText().strip() or "{}"
                try:
                    parsed_arguments = json.loads(raw_arguments)
                except json.JSONDecodeError:
                    self._set_status("Advanced analysis arguments must be valid JSON.")
                    return
                if not isinstance(parsed_arguments, dict):
                    self._set_status("Advanced analysis arguments must be a JSON object.")
                    return
                inputs = parsed_arguments
        response = self._call(
            "ui.analysis.run",
            method=method_id,
            inputs=inputs,
        )
        if response is not None:
            self.refresh_analysis_results()
            self.navigate("Analysis Results")

    def run_automatic_analysis(self) -> None:
        if not self.current_dataset_id:
            self._set_status("Choose a dataset before running automatic analysis.")
            return
        mode = str(self.auto_mode.currentData())
        design = str(self.auto_design.currentData())
        inputs: dict[str, object] = {
            "dataset_id": self.current_dataset_id,
            "mode": mode,
            "design": design,
        }
        outcome = str(self.auto_outcome.currentData() or "")
        group = str(self.auto_group.currentData() or "")
        paired_with = str(self.auto_paired.currentData() or "")
        if outcome:
            inputs["outcome"] = outcome
            inputs["outcome_type"] = str(self.auto_outcome_type.currentData())
        if group:
            inputs["group"] = group
        if paired_with:
            inputs["paired_with"] = paired_with
        levels = self._comma_values(self.auto_levels.text())
        predictors = self._comma_values(self.auto_predictors.text())
        variables = self._comma_values(self.auto_variables.text())
        items = self._comma_values(self.auto_items.text())
        if levels:
            inputs["levels"] = levels
        if predictors:
            inputs["predictors"] = predictors
        if variables:
            inputs["variables"] = variables
        if items:
            inputs["items"] = items
        response = self._call(
            "ui.analysis.run",
            method="analysis.statistics.auto_analyze",
            inputs=inputs,
        )
        if response is None:
            return
        result = response.get("result", {})
        estimates = result.get("estimates", {}) if isinstance(result, dict) else {}
        report = estimates.get("report", {}) if isinstance(estimates, dict) else {}
        manifest = estimates.get("execution_manifest", {}) if isinstance(estimates, dict) else {}
        selected = report.get("selected_methods", []) if isinstance(report, dict) else []
        failures = estimates.get("failures", []) if isinstance(estimates, dict) else []
        self.stats_result.setPlainText(
            "Automatic analysis completed without an LLM.\n"
            f"Mode: {mode} · Design: {design}\n"
            f"Selected procedures: {', '.join(str(value) for value in selected) or 'none'}\n"
            f"Successful operations: {manifest.get('successful_operations', '—')} · "
            f"Failed operations: {manifest.get('failed_operations', len(failures))}\n"
            "Open Analysis Results to inspect numerical outputs, selection rules, warnings and "
            "the reproducibility manifest."
        )
        self.refresh_analysis_results()
        self.navigate("Analysis Results")

    def refresh_analysis_results(self) -> None:
        self.analysis_results_list.clear()
        self.analysis_result_model.set_records([], [])
        self.analysis_result_detail.clear()
        if not self.project_id:
            return
        response = self._call("ui.analysis.results")
        if response is None:
            return
        for record in reversed(response["results"]):
            item = QListWidgetItem(
                f"{record['method']} · {record['method_version']} · {record['created_at']}"
            )
            item.setData(Qt.ItemDataRole.UserRole, record)
            self.analysis_results_list.addItem(item)
        if response["results"]:
            self.analysis_results_list.setCurrentRow(0)
        else:
            self.analysis_results_list.addItem(
                empty_list_item("No analysis results yet. Run an analysis from Statistics first.")
            )

    def inspect_analysis_result(
        self, current: QListWidgetItem | None, previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        record = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(record, dict):
            return
        presentation = format_result_record(record)
        self.analysis_result_model.set_records(
            list(presentation.columns),
            [list(row) for row in presentation.rows],
        )
        self.analysis_result_table.resizeColumnsToContents()
        self.analysis_result_detail.setPlainText(presentation.detail)

    def save_text(self, which: str) -> None:
        if not self.project_id:
            self._set_status("Select a project first.")
            return
        editor = self.manuscript_editor if which == "manuscript" else self.notebook_editor
        if self._call(f"ui.{which}.save", **{which: editor.toPlainText()}):
            document = editor.document()
            if document is not None:
                document.setModified(False)
            if which in self._draft_timers:
                self._draft_timers[which].stop()
            self._set_status(f"Saved {which} locally")

    def save_active(self) -> None:
        screen = SCREENS[self.pages.currentIndex()]
        if screen in ("Manuscript", "Notebook"):
            self.save_text(screen.lower())
        else:
            self._set_status("Project records save automatically after each operation.")

    @staticmethod
    def _assistant_error_payload(exc: Exception) -> dict[str, Any]:
        code = getattr(exc, "code", None)
        if isinstance(code, str) and code:
            message = str(exc).strip() or "Assistant request failed."
            if code == "CANCELLED":
                return {"status": "cancelled", "data": {}}
            return {
                "status": "failed",
                "error": {"code": code, "message": message[:1_000]},
            }
        return {
            "status": "failed",
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Assistant request failed without changing approved project data.",
            },
        }

    def _assistant_runtime_flags(self) -> tuple[bool, bool]:
        offline = self.facade.settings.load().offline
        provider = self._call("ui.provider.read") if self.project_id else None
        acknowledged = bool(provider and provider.get("egress_acknowledged"))
        return offline, acknowledged

    def _assistant_running(self) -> bool:
        job = self.jobs.jobs.get("assistant")
        return job is not None and job.state in ("queued", "running", "cancelling")

    def _sync_assistant_controls(self) -> None:
        backend_available = self.facade.ai_backend is not None
        ready = bool(self.project_id) and backend_available and self.assistant_model_available
        running = self._assistant_running()
        pending = self.assistant_pending_tool is not None
        self.assistant_send_button.setEnabled(ready and not running and not pending)
        self.assistant_cancel_button.setEnabled(running)
        self.assistant_prompt.setEnabled(ready and not running and not pending)
        self.assistant_approve_button.setEnabled(backend_available and pending and not running)
        self.assistant_deny_button.setEnabled(backend_available and pending and not running)

    def _set_assistant_pending(self, pending: Mapping[str, Any] | None) -> None:
        self.assistant_pending_tool = dict(pending) if pending is not None else None
        if pending is None:
            self.assistant_pending.clear()
        else:
            arguments = pending.get("arguments", {})
            self.assistant_pending.setPlainText(
                f"Operation: {pending.get('operation', 'unknown')}\n"
                f"Risk: {pending.get('risk', 'unknown')}\n"
                f"Effect: {pending.get('effect', 'unknown')}\n"
                f"Arguments: {json.dumps(arguments, ensure_ascii=False, sort_keys=True)}\n"
                f"Model profile: {pending.get('profile_id') or 'active profile'}"
            )
        self._sync_assistant_controls()

    def _render_assistant_history(self, payload: Mapping[str, Any]) -> None:
        raw_messages = payload.get("messages", [])
        messages = raw_messages if isinstance(raw_messages, list) else []
        lines: list[str] = []
        for raw in messages[-100:]:
            if not isinstance(raw, Mapping):
                continue
            role = str(raw.get("role", "message"))
            content = str(raw.get("content", ""))
            if len(content) > 4_000:
                content = content[:4_000] + "…"
            if role == "tool":
                metadata = raw.get("metadata", {})
                operation = (
                    str(metadata.get("operation", "tool"))
                    if isinstance(metadata, Mapping)
                    else "tool"
                )
                label = f"Tool · {operation}"
            else:
                label = {
                    "user": "You",
                    "assistant": "Assistant",
                    "system": "System",
                    "evidence": "Evidence",
                }.get(role, role.title())
            lines.append(f"{label}\n{content}")
        self.assistant_transcript.setPlainText("\n\n".join(lines))
        pending = payload.get("pending_tool")
        self._set_assistant_pending(pending if isinstance(pending, Mapping) else None)
        usage = payload.get("usage")
        if isinstance(usage, Mapping):
            self.assistant_usage_status.setText(self._format_ai_usage(usage))

    @staticmethod
    def _format_ai_usage(summary: Mapping[str, Any]) -> str:
        raw_providers = summary.get("providers", {})
        providers = raw_providers if isinstance(raw_providers, Mapping) else {}
        requests = 0
        failed = 0
        cancelled = 0
        input_tokens = 0
        output_tokens = 0
        tokens_known = True
        weighted_latency = 0.0
        for raw in providers.values():
            if not isinstance(raw, Mapping):
                continue
            count = int(raw.get("requests", 0))
            requests += count
            failed += int(raw.get("failed", 0))
            cancelled += int(raw.get("cancelled", 0))
            input_tokens += int(raw.get("input_tokens", 0))
            output_tokens += int(raw.get("output_tokens", 0))
            tokens_known = tokens_known and bool(raw.get("tokens_known", False))
            weighted_latency += float(raw.get("mean_latency_ms", 0.0)) * count
        if requests == 0:
            return "Model usage: no calls recorded for this project. Monetary cost: unknown."
        token_text = (
            f"{input_tokens:,} input + {output_tokens:,} output tokens"
            if tokens_known
            else "token totals incomplete"
        )
        mean_latency = weighted_latency / requests
        failure_text = f" · {failed} failed" if failed else ""
        cancelled_text = f" · {cancelled} cancelled" if cancelled else ""
        return (
            f"Model usage: {requests:,} logical model call{'s' if requests != 1 else ''} · "
            f"{token_text} · "
            f"mean latency {mean_latency:.0f} ms{failure_text}{cancelled_text}. "
            "Monetary cost: unknown (provider pricing is not configured)."
        )

    def refresh_assistant(self) -> None:
        self.assistant_model_available = False
        backend = self.facade.ai_backend
        if not self.project_id or backend is None:
            self.assistant_conversation_id = None
            self.assistant_transcript.setPlainText(
                "The integrated AI host is unavailable. Manual ResearchWeave workflows "
                "remain usable."
            )
            self.assistant_tool_status.setText("No integrated model runtime is connected.")
            self.assistant_usage_status.setText("Model usage is unavailable without the AI host.")
            self._set_assistant_pending(None)
            return
        try:
            model_state = backend.model_config()
            self.assistant_model_available = bool(model_state.get("active_profile"))
            conversations = backend.assistant_conversations(self.project_id).get(
                "conversations", []
            )
            if isinstance(conversations, list) and conversations:
                first = conversations[0]
                if isinstance(first, Mapping):
                    self.assistant_conversation_id = str(first.get("conversation_id", "")) or None
            if self.assistant_conversation_id:
                history = backend.assistant_history(self.project_id, self.assistant_conversation_id)
                self._render_assistant_history(history)
            else:
                self.assistant_transcript.clear()
                self._set_assistant_pending(None)
                self.assistant_usage_status.setText(
                    self._format_ai_usage(backend.usage_summary(self.project_id))
                )
            if self.assistant_model_available:
                self.assistant_tool_status.setText(
                    f"Active model: {model_state.get('active_profile')} · assistant ready."
                )
            else:
                self.assistant_tool_status.setText(
                    "No model is active. Configure a local or hosted profile in Providers."
                )
        except Exception:
            self.assistant_tool_status.setText(
                "Assistant history or model configuration could not be loaded."
            )
        self._sync_assistant_controls()

    def cancel_assistant(self) -> None:
        if not self._assistant_running():
            self._set_status("No assistant request is currently running.")
            return
        self.jobs.cancel("assistant")
        self.assistant_tool_status.setText("Cancelling assistant request…")
        self._sync_assistant_controls()

    def send_assistant(self) -> None:
        backend = self.facade.ai_backend
        if not self.project_id or backend is None:
            self._set_status(
                "Open a project with the integrated AI host before using the assistant."
            )
            return
        if not self.assistant_model_available:
            self._set_status("Configure and enable a model in Providers before sending a message.")
            return
        if self.assistant_pending_tool is not None:
            self._set_status(
                "Approve or deny the pending tool request before sending another message."
            )
            return
        prompt = self.assistant_prompt.toPlainText().strip()
        if not prompt:
            self._set_status("Enter a research question for the assistant.")
            return
        project_id = self.project_id
        conversation_id = self.assistant_conversation_id
        offline, egress_acknowledged = self._assistant_runtime_flags()

        def work(stop: Event, emit: Callable[[str], None]) -> Mapping[str, Any]:
            if stop.is_set():
                return {"status": "cancelled", "data": {}}
            try:
                data = backend.assistant_send(
                    project_id,
                    prompt,
                    conversation_id=conversation_id,
                    offline=offline,
                    egress_acknowledged=egress_acknowledged,
                    on_delta=emit,
                    is_cancelled=stop.is_set,
                )
                return {"status": "ok", "data": dict(data)}
            except Exception as exc:
                return ResearchWindow._assistant_error_payload(exc)

        if not self.jobs.submit_stream("assistant", work):
            self._set_status("The assistant is already processing a request.")
            return
        if self.assistant_transcript.toPlainText().strip():
            self.assistant_transcript.appendPlainText("")
        self.assistant_transcript.appendPlainText(f"You\n{prompt}\n\nAssistant\n")
        self.assistant_prompt.clear()
        self.assistant_tool_status.setText("Assistant is generating with the selected model…")
        self._sync_assistant_controls()

    def _assistant_chunk(self, task_id: str, value: str) -> None:
        if task_id != "assistant" or not value:
            return
        cursor = self.assistant_transcript.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(value)
        self.assistant_transcript.setTextCursor(cursor)

    def _assistant_job_result(self, task_id: str, value: object) -> None:
        if task_id != "assistant" or not isinstance(value, Mapping):
            return
        status = value.get("status")
        if status == "cancelled":
            self.assistant_tool_status.setText("Assistant request was cancelled.")
            self._sync_assistant_controls()
            return
        if status != "ok":
            error = value.get("error", {})
            code = (
                str(error.get("code", "INTERNAL_ERROR"))
                if isinstance(error, Mapping)
                else "INTERNAL_ERROR"
            )
            message = (
                str(error.get("message", "Assistant request failed."))
                if isinstance(error, Mapping)
                else "Assistant request failed."
            )
            self.assistant_tool_status.setText(f"{code}: {message}")
            self.refresh_assistant()
            self._set_status(f"Assistant: {message}")
            return
        data = value.get("data", {})
        if not isinstance(data, Mapping):
            self.assistant_tool_status.setText("Assistant returned an invalid host response.")
            self._sync_assistant_controls()
            return
        conversation_id = data.get("conversation_id")
        if isinstance(conversation_id, str) and conversation_id:
            self.assistant_conversation_id = conversation_id
        usage = data.get("usage")
        if isinstance(usage, Mapping):
            self.assistant_usage_status.setText(self._format_ai_usage(usage))
        events = data.get("tool_events", [])
        tool_names = (
            [
                str(item.get("operation"))
                for item in events
                if isinstance(item, Mapping) and item.get("operation")
            ]
            if isinstance(events, list)
            else []
        )
        self.refresh_assistant()
        if self.assistant_pending_tool is not None:
            self.assistant_tool_status.setText(
                "Assistant paused before a non-read tool. Review the exact request below."
            )
        elif tool_names:
            self.assistant_tool_status.setText(
                "Assistant completed · tools used: " + ", ".join(tool_names)
            )
        else:
            self.assistant_tool_status.setText("Assistant completed with the selected model.")
        self._sync_assistant_controls()

    def _assistant_job_error(self, task_id: str, message: str) -> None:
        if task_id != "assistant":
            return
        self.assistant_tool_status.setText(message)
        self._sync_assistant_controls()

    def _assistant_job_changed(self, task_id: str, state: str) -> None:
        if task_id != "assistant":
            return
        if state == "running":
            self.assistant_tool_status.setText("Assistant is running…")
        elif state == "cancelled":
            self.assistant_tool_status.setText("Assistant request was cancelled.")
        self._sync_assistant_controls()

    def approve_assistant_tool(self) -> None:
        pending = self.assistant_pending_tool
        backend = self.facade.ai_backend
        conversation_id = self.assistant_conversation_id
        if pending is None or backend is None or not self.project_id or not conversation_id:
            self._set_status("No assistant tool request is waiting for approval.")
            return
        summary = (
            f"Operation: {pending.get('operation', 'unknown')}\n"
            f"Risk: {pending.get('risk', 'unknown')}\n"
            f"Effect: {pending.get('effect', 'unknown')}\n"
            "Arguments: "
            f"{json.dumps(pending.get('arguments', {}), ensure_ascii=False, sort_keys=True)}\n\n"
            "Execute exactly this persisted tool call and then let the model continue?"
        )
        answer = QMessageBox.question(
            self,
            "Approve exact assistant tool call",
            summary,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        project_id = self.project_id
        offline, egress_acknowledged = self._assistant_runtime_flags()

        def work(stop: Event, emit: Callable[[str], None]) -> Mapping[str, Any]:
            if stop.is_set():
                return {"status": "cancelled", "data": {}}
            try:
                data = backend.assistant_approve(
                    project_id,
                    conversation_id,
                    offline=offline,
                    egress_acknowledged=egress_acknowledged,
                    on_delta=emit,
                    is_cancelled=stop.is_set,
                )
                return {"status": "ok", "data": dict(data)}
            except Exception as exc:
                return ResearchWindow._assistant_error_payload(exc)

        if not self.jobs.submit_stream("assistant", work):
            self._set_status("The assistant is already processing a request.")
            return
        self.assistant_transcript.appendPlainText(
            f"\nApproved tool · {pending.get('operation', 'unknown')}\n\nAssistant\n"
        )
        self.assistant_tool_status.setText("Executing the exact approved tool call…")
        self._sync_assistant_controls()

    def deny_assistant_tool(self) -> None:
        pending = self.assistant_pending_tool
        backend = self.facade.ai_backend
        conversation_id = self.assistant_conversation_id
        if pending is None or backend is None or not self.project_id or not conversation_id:
            self._set_status("No assistant tool request is waiting for denial.")
            return
        try:
            backend.assistant_deny(self.project_id, conversation_id)
        except Exception:
            self._set_status("The pending assistant tool request could not be denied.")
            return
        operation = str(pending.get("operation", "tool"))
        self.refresh_assistant()
        self.assistant_tool_status.setText(f"Denied {operation}. The tool was not executed.")
        self._set_status("Assistant tool request denied; no tool side effect was executed.")

    def preview_agent(self) -> None:
        result = self._call(
            "ui.agent.propose",
            summary=self.agent_proposal.toPlainText(),
            risk=self.risk_picker.currentText(),
        )
        if result:
            self.agent_status.setText(
                f"Review needed · {result['effect']}\n"
                f"Nothing executed. Proposal: {result['proposal']}"
            )

    def deny_agent(self) -> None:
        result = self._call("ui.agent.deny", summary=self.agent_proposal.toPlainText())
        if result:
            self.agent_status.setText(result["message"])

    def create_agent_action(self) -> None:
        raw_arguments = self.agent_arguments.toPlainText().strip() or "{}"
        try:
            parsed_arguments = json.loads(raw_arguments)
        except json.JSONDecodeError:
            self._set_status("Operation arguments must be valid JSON.")
            return
        if not isinstance(parsed_arguments, dict):
            self._set_status("Operation arguments must be a JSON object.")
            return
        proposal = {
            "operation": self.agent_operation.text(),
            "target": self.agent_target.text(),
            "arguments": parsed_arguments,
            "changed_fields": {"proposal_text": self.agent_proposal.toPlainText()},
            "files": self._comma_values(self.agent_files.text()),
            "network_destination": self.agent_network.text(),
            "data_egress": self.agent_egress.isChecked(),
            "destructive_effect": self.agent_destructive.isChecked(),
            "provider": "manual",
            "model": "",
            "input_refs": [],
        }
        response = self._call("ui.agent.action.propose", proposal=proposal)
        if response is not None:
            self.agent_status.setText(
                "Scope-bound proposal saved. Nothing executed; select it to approve or deny."
            )
            self.refresh_agent_timeline()

    def refresh_agent_timeline(self) -> None:
        self.agent_timeline.clear()
        if not self.project_id:
            return
        response = self._call("ui.agent.timeline")
        if response is None:
            return
        for record in reversed(response["events"]):
            item = QListWidgetItem(
                f"{record['event'].upper()} · {record['operation']} · {record['target']} · "
                f"{record['timestamp']}"
            )
            item.setData(Qt.ItemDataRole.UserRole, record)
            self.agent_timeline.addItem(item)

    def inspect_agent_action(
        self, current: QListWidgetItem | None, previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        record = current.data(Qt.ItemDataRole.UserRole)
        self.agent_status.setText(
            f"Event: {record['event']}\nOperation: {record['operation']}\n"
            f"Target: {record['target']}\nArguments: {record.get('arguments', {})}\n"
            f"Changed fields: {record['changed_fields']}\n"
            f"Files: {record['files']}\nNetwork: {record['network_destination'] or 'none'}\n"
            f"Data egress: {record['data_egress']} · destructive: "
            f"{record['destructive_effect']}\nFingerprint: {record['fingerprint']}\n"
            f"Approval ID: {record['approval_id'] or 'none'}\n{record['message']}"
        )

    def approve_agent_action(self) -> None:
        current = self.agent_timeline.currentItem()
        if current is None:
            self._set_status("Select a proposed action to review.")
            return
        record = current.data(Qt.ItemDataRole.UserRole)
        if record["event"] != "proposed":
            self._set_status("Only a pending proposal can be approved.")
            return
        preview = (
            f"Operation: {record['operation']}\nTarget: {record['target']}\n"
            f"Arguments: {record.get('arguments', {})}\n"
            f"Changed fields: {record['changed_fields']}\nFiles: {record['files']}\n"
            f"Network destination: {record['network_destination'] or 'none'}\n"
            f"Data egress: {record['data_egress']}\n"
            f"Destructive effect: {record['destructive_effect']}\n"
            f"Fingerprint: {record['fingerprint']}\n\n"
            "Approval is bound to exactly this fingerprint and does not execute the action."
        )
        answer = QMessageBox.question(
            self,
            "Approve exact proposed action",
            preview,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        response = self._call(
            "ui.agent.action.approve",
            action_id=record["id"],
            expected_fingerprint=record["fingerprint"],
        )
        if response is not None:
            self.refresh_agent_timeline()
            self.agent_status.setText(
                "Exact scope approved. Use Execute approved action for a separate host-routed step."
            )

    def execute_agent_action(self) -> None:
        current = self.agent_timeline.currentItem()
        if current is None:
            self._set_status("Select an approved action to execute.")
            return
        record = current.data(Qt.ItemDataRole.UserRole)
        if record["event"] != "approved":
            self._set_status("Only an approved action can be executed.")
            return
        summary = (
            f"Operation: {record['operation']}\nArguments: {record.get('arguments', {})}\n"
            f"Network destination: {record['network_destination'] or 'none'}\n"
            f"Data egress: {record['data_egress']}\n\nExecute this exact approved action now?"
        )
        answer = QMessageBox.question(
            self,
            "Execute approved action",
            summary,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        response = self._call("ui.agent.action.execute", action_id=record["id"])
        if response is None:
            return
        execution = response["execution"]
        if execution.get("status") == "ok":
            self.agent_status.setText(
                "Approved AI action completed through the shared command bus.\n"
                + json.dumps(execution.get("data", {}), ensure_ascii=False, indent=2)[:4_000]
            )
        else:
            error = execution.get("error") or {}
            self.agent_status.setText(
                f"AI action failed: {error.get('code', 'INTERNAL_ERROR')} · "
                f"{error.get('message', 'Unknown error')}"
            )
        self.refresh_agent_timeline()

    def deny_agent_action(self) -> None:
        current = self.agent_timeline.currentItem()
        if current is None:
            self._set_status("Select a proposed action to deny.")
            return
        record = current.data(Qt.ItemDataRole.UserRole)
        reason, accepted = QInputDialog.getText(self, "Deny proposed action", "Reason for denial")
        if not accepted:
            return
        response = self._call("ui.agent.action.deny", action_id=record["id"], reason=reason)
        if response is not None:
            self.refresh_agent_timeline()
            self.agent_status.setText(
                "Proposal denied. No write or network execution was performed."
            )

    def refresh_provider(self) -> None:
        if not self.project_id:
            self.provider_status.setPlainText("Open a project to configure provider metadata.")
            return
        response = self._call("ui.provider.read")
        if response is None:
            return
        self.provider_mode.setCurrentText(response["mode"])
        self.provider_id.setText(response["provider_id"])
        self.provider_protocol.setCurrentText(response.get("protocol", "openai-compatible"))
        self.provider_endpoint.setText(response.get("endpoint", ""))
        self.provider_model.setText(response.get("model", ""))
        self.provider_credential_env.setText(response.get("credential_env", ""))
        self.provider_tool_calling.setChecked(bool(response.get("tool_calling", False)))
        self.provider_enabled.setChecked(bool(response["enabled"]))
        self.provider_credential.setChecked(bool(response["credential_present"]))
        self.provider_egress.setChecked(bool(response["egress_acknowledged"]))
        self.provider_scope.setText(", ".join(response["permission_scope"]))
        runtime_state = "Integrated AI host is not connected."
        usage_state = "Model usage: unavailable without the integrated AI host."
        backend = self.facade.ai_backend
        if backend is not None:
            try:
                model_state = backend.model_config()
                runtime_state = (
                    f"Active model profile: {model_state.get('active_profile') or 'none'}"
                )
                usage_state = self._format_ai_usage(backend.usage_summary(self.project_id))
            except Exception:
                runtime_state = "Model runtime configuration could not be read."
                usage_state = "Model usage diagnostics could not be read."
        self.provider_usage_status.setText(usage_state)
        self.provider_status.setPlainText(
            f"Mode: {response['mode']}\nProvider: {response['provider_id']}\n"
            f"Protocol: {response.get('protocol', 'openai-compatible')}\n"
            f"Endpoint: {response.get('endpoint') or 'none'}\n"
            f"Model: {response.get('model') or 'none'}\n"
            f"Credential env var: {response.get('credential_env') or 'none'}\n"
            f"Native tool calling: {response.get('tool_calling', False)}\n"
            f"Availability: {response['effective_availability']}\n"
            f"Credential present: {response['credential_present']}\n"
            f"Permission scope: {response['permission_scope']}\n"
            f"Data-egress acknowledged: {response['egress_acknowledged']}\n"
            f"Observed network calls: {response['network_calls_observed']}\n"
            f"{runtime_state}\n{response['note']}"
        )

    def _provider_protocol_changed(self, protocol: str) -> None:
        native_ollama = protocol == "ollama"
        if native_ollama:
            self.provider_mode.setCurrentText("local")
            if not self.provider_endpoint.text().strip():
                self.provider_endpoint.setText("http://127.0.0.1:11434")
            self.provider_credential_env.clear()
            self.provider_credential.setChecked(False)
            self.provider_egress.setChecked(False)
            self.provider_tool_calling.setChecked(False)
        self.provider_credential_env.setEnabled(not native_ollama)
        self.provider_credential.setEnabled(not native_ollama)
        self.provider_egress.setEnabled(not native_ollama)
        self.provider_tool_calling.setEnabled(not native_ollama)
        if native_ollama:
            self.provider_model.setPlaceholderText("Installed Ollama tag, for example llama3.2:3b")
        else:
            self.provider_model.setPlaceholderText("Exact model identifier")

    def save_provider(self) -> None:
        mode = self.provider_mode.currentText()
        profile = {
            "identifier": self.provider_id.text().strip(),
            "kind": self.provider_protocol.currentText(),
            "endpoint": self.provider_endpoint.text().strip(),
            "model": self.provider_model.text().strip(),
            "local": mode == "local",
            "credential_env": self.provider_credential_env.text().strip() or None,
            "tool_calling": self.provider_tool_calling.isChecked(),
            "enabled": self.provider_enabled.isChecked(),
        }
        backend = self.facade.ai_backend
        if mode != "manual" and backend is not None:
            try:
                backend.validate_model_profile(profile)
            except Exception:
                self._set_status(
                    "Model configuration is invalid. Check the endpoint, model and credential "
                    "environment-variable name."
                )
                return
        response = self._call(
            "ui.provider.update",
            provider={
                "mode": mode,
                "provider_id": self.provider_id.text(),
                "protocol": self.provider_protocol.currentText(),
                "endpoint": self.provider_endpoint.text(),
                "model": self.provider_model.text(),
                "credential_env": self.provider_credential_env.text(),
                "tool_calling": self.provider_tool_calling.isChecked(),
                "enabled": self.provider_enabled.isChecked(),
                "credential_present": self.provider_credential.isChecked(),
                "availability": "not-checked",
                "permission_scope": self._comma_values(self.provider_scope.text()),
                "egress_acknowledged": self.provider_egress.isChecked(),
            },
        )
        if response is not None:
            if backend is not None:
                try:
                    if mode == "manual":
                        backend.activate_model(None)
                    else:
                        backend.save_model_profile(
                            profile,
                            activate=self.provider_enabled.isChecked(),
                        )
                        if not self.provider_enabled.isChecked():
                            backend.activate_model(None)
                except Exception:
                    self._set_status(
                        "Provider metadata was saved, but the model runtime configuration could "
                        "not be persisted. Review the provider fields and retry."
                    )
                    return
            self.refresh_provider()
            self.refresh_assistant()

    def save_offline_mode(self) -> None:
        response = self._call("ui.preferences.update", offline=self.offline_toggle.isChecked())
        if response is not None:
            self.prefs = Preferences(**response["preferences"])
            self.refresh_privacy()
            self.refresh_provider()
            self.refresh_assistant()

    def refresh_privacy(self) -> None:
        if not self.project_id:
            self.privacy_status.setPlainText("Open a project to inspect privacy state.")
            return
        self.offline_toggle.setChecked(self.facade.settings.load().offline)
        response = self._call("ui.privacy.read")
        if response is None:
            return
        deletion = response["deletion_preview"]
        self.privacy_status.setPlainText(
            f"Offline mode: {response['offline_mode']}\n"
            f"Telemetry enabled: {response['telemetry_enabled']}\n"
            f"Provider egress enabled: {response['provider_egress_enabled']}\n"
            f"Selected data scope: {response['selected_data_scope']}\n"
            f"Backup destination: {response['backup_destination']}\n"
            f"Sync destinations: {response['sync_destinations']}\n"
            f"Retention: {response['retention']}\n"
            f"Credential handling: {response['credential_storage']}\n"
            f"Audit events: {response['audit_events']}\n"
            f"Deletion preview: {deletion['sources']} sources, "
            f"{deletion['datasets']} datasets · {deletion['warning']}\n"
            f"Observed network calls: {response['network_calls_observed']}"
        )

    def refresh_integrations(self) -> None:
        self.integration_list.clear()
        if not self.project_id:
            return
        response = self._call("ui.integration.list")
        if response is None:
            return
        for record in response["integrations"]:
            item = QListWidgetItem(
                f"{record['id']} · {record['status']} · {', '.join(record['capabilities'])}"
            )
            item.setData(Qt.ItemDataRole.UserRole, record)
            self.integration_list.addItem(item)

    def disconnect_integration(self) -> None:
        current = self.integration_list.currentItem()
        if current is None:
            self._set_status("Select an integration adapter.")
            return
        record = current.data(Qt.ItemDataRole.UserRole)
        response = self._call(
            "ui.integration.disconnect",
            integration_id=record["id"],
            permissions=record["permissions"],
        )
        if response is not None:
            self.integration_status.setText(
                f"{record['id']} is disconnected. No network connection was attempted."
            )
            self.refresh_integrations()

    def refresh_notifications(self) -> None:
        self.notification_list.clear()
        if not self.project_id:
            return
        response = self._call("ui.notification.list")
        if response is None:
            return
        for record in response["notifications"]:
            item = QListWidgetItem(
                f"{record['severity'].upper()} · {record['code']} · {record['message']} · "
                f"diagnostic {record['diagnostic_id']}"
            )
            item.setData(Qt.ItemDataRole.UserRole, record)
            item.setToolTip(f"Recovery: {record['recovery']} · linkage: {record['linkage']}")
            self.notification_list.addItem(item)

    def dismiss_notification(self) -> None:
        current = self.notification_list.currentItem()
        if current is None:
            return
        record = current.data(Qt.ItemDataRole.UserRole)
        if self._call("ui.notification.dismiss", notification_id=record["id"]) is not None:
            self.refresh_notifications()

    def retry_notification(self) -> None:
        current = self.notification_list.currentItem()
        if current is None:
            self._set_status("Select a notification with a safe retry action.")
            return
        record = current.data(Qt.ItemDataRole.UserRole)
        response = self._call("ui.notification.retry", notification_id=record["id"])
        if response is not None:
            self._set_status(
                f"Retried {response['retried_operation']} locally with no network or writes."
            )

    def refresh_tutorials(self) -> None:
        self.tutorial_list.clear()
        if not self.project_id:
            return
        response = self._call("ui.tutorial.status")
        if response is None:
            return
        completed = set(response["completed"])
        for step in (
            "research-question",
            "source-import",
            "screening",
            "data",
            "evidence",
            "writing",
            "export",
            "privacy",
        ):
            item = QListWidgetItem(
                f"{'DONE' if step in completed else 'NEXT'} · {step.replace('-', ' ')}"
            )
            item.setData(Qt.ItemDataRole.UserRole, step)
            self.tutorial_list.addItem(item)
        self.tutorial.setText(
            f"Learning progress: {len(completed)} actions recorded · "
            f"{len(response['remaining'])} core tutorial actions remaining"
        )

    def complete_tutorial_step(self) -> None:
        current = self.tutorial_list.currentItem()
        if current is None:
            self._set_status("Select a tutorial action.")
            return
        step = current.data(Qt.ItemDataRole.UserRole)
        if self._call("ui.tutorial.step", step=step) is not None:
            self.refresh_tutorials()

    def preview_export(self) -> None:
        result = self._call("ui.export.preview", filename=self.export_name.text())
        if result:
            destination = display_local_path(Path(result["destination"]))
            self.export_receipt.setText(
                f"{result['filename']} · {result['bytes']} bytes\n"
                f"SHA-256: {result['sha256']}\nDestination: {destination}"
            )

    def choose_export_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Choose local export folder",
            str(self.facade.export_root),
        )
        if not selected:
            return
        destination = Path(selected)
        if destination.is_symlink() or not destination.is_dir():
            self._set_status("Choose an existing ordinary local directory.")
            return
        self.facade.export_root = destination.resolve()
        self.export_directory.setText(display_local_path(self.facade.export_root))
        self.export_directory.setToolTip(str(self.facade.export_root))
        self._set_status("Local export folder selected. Each write still requires approval.")

    def export_file(self) -> None:
        preview = self._call("ui.export.preview", filename=self.export_name.text())
        if preview is None:
            return
        outcome = QMessageBox.question(
            self,
            "Approve local export",
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
        if (
            QMessageBox.question(
                self,
                "Approve local snapshot",
                f"Write a new immutable backup for {plan['title']}, revision "
                f"{plan['revision']}? Existing backups will be preserved.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            self._set_status("Backup canceled. No data was written.")
            return
        old = self.facade.backup_authorizer
        self.facade.backup_authorizer = lambda action, identifier: (
            action == "create" and identifier == self.project_id
        )
        try:
            result = self._call("ui.backup.create", expected_revision=plan["revision"])
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

    def inspect_backup(
        self, current: QListWidgetItem | None, previous: QListWidgetItem | None
    ) -> None:
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
        if (
            QMessageBox.question(
                self,
                "Approve recovery",
                f"Restore {verified['title']} from this verified archive "
                "as an additional project? No existing project will be overwritten.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            self._set_status("Restore cancelled.")
            return
        if not self._confirm_leave_project():
            return
        previous = self.facade.backup_authorizer
        self.facade.backup_authorizer = lambda action, identifier: (
            action == "restore" and identifier == backup_id
        )
        try:
            restored = self._call(
                "ui.backup.restore",
                backup_id=backup_id,
                expected_sha256=verified["sha256"],
            )
        finally:
            self.facade.backup_authorizer = previous
        if restored is not None:
            self.refresh_projects()
            self.open_project(restored["restored_project_id"])
            self.navigate("Dashboard")
            self._set_status("Verified snapshot restored to a separate local project.")

    def refresh_recovery(self) -> None:
        self.recovery_list.clear()
        if not self.project_id:
            return
        result = self._call("ui.recovery.list")
        if result is not None:
            for draft in result["drafts"]:
                item = QListWidgetItem(
                    f"{draft['field']} · {'conflict' if draft.get('conflict') else 'ready'}"
                )
                item.setData(Qt.ItemDataRole.UserRole, draft["field"])
                self.recovery_list.addItem(item)

    def restore_recovery(self) -> None:
        item = self.recovery_list.currentItem()
        if item is None:
            self._set_status("Select a recovery draft first.")
            return
        field = item.data(Qt.ItemDataRole.UserRole)
        result = self._call("ui.recovery.inspect", field=field)
        if result is None:
            return
        target = self.manuscript_editor if field == "manuscript" else self.notebook_editor
        if result["conflict"]:
            answer = QMessageBox.question(
                self,
                "Review changed project",
                "The saved project changed since this draft. Load the recovery text "
                "into the editor for comparison? Saved files stay unchanged.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        target.setPlainText(result["text"])
        document = target.document()
        if document is not None:
            document.setModified(True)
        self.navigate("Manuscript" if field == "manuscript" else "Notebook")
        self._set_status("Recovery text loaded into editor. Review and save explicitly.")

    def run_diagnostics(self) -> None:
        self.audit_findings.clear()
        if not self.project_id:
            self.audit_summary.setText("Select a project before running an audit.")
            return
        report = self._call("ui.project.audit")
        if report is None:
            return
        totals = report["summary"]
        self.audit_summary.setText(
            f"{report['status']} · project revision {report['project_revision']}\n"
            f"Errors: {totals['errors']} · warnings: {totals['warnings']} · "
            f"information: {totals['information']}\n"
            "The audit detects structural integrity issues only."
        )
        for finding in report["findings"]:
            item = QListWidgetItem(
                f"{finding['severity'].upper()} · {finding['title']} · {finding['location']}"
            )
            item.setData(Qt.ItemDataRole.UserRole, finding)
            self.audit_findings.addItem(item)

    def inspect_finding(
        self, current: QListWidgetItem | None, previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        finding = current.data(Qt.ItemDataRole.UserRole)
        self.audit_detail.setPlainText(
            f"{finding['severity'].upper()} · {finding['code']}\n"
            f"Location: {finding['location']}\n\n"
            f"Finding: {finding['message']}\n\n"
            f"Next action: {finding['recovery']}"
        )

    def preview_publishing(self) -> None:
        self.release_gates.clear()
        if not self.project_id:
            self.publication_summary.setText("Select a project before reviewing a manuscript.")
            return
        result = self._call("ui.release.preview")
        if result is None:
            return
        self.publication_summary.setText(
            f"Status: {result['structural_status']}\n"
            f"Saved manuscript: {result['manuscript_characters']} characters\n"
            f"Blocked checks: {len(result['blocking_gates'])}; "
            f"manual review: {len(result['manual_gates'])}\n"
            "Publication approval: No · Ethics approval: Not verified"
        )
        for gate in result["gates"]:
            item = QListWidgetItem(f"{gate['state'].upper()} · {gate['heading']}")
            item.setData(Qt.ItemDataRole.UserRole, gate)
            self.release_gates.addItem(item)

    def inspect_release_gate(
        self, current: QListWidgetItem | None, previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        item = current.data(Qt.ItemDataRole.UserRole)
        self.release_detail.setPlainText(
            f"{item['heading']}\nState: {item['state']}\n\n"
            f"{item['rationale']}\n\nAction: {item['next_action']}\n"
            "Only a human can verify scientific methods, data permissions and ethics."
        )

    def preview_submission_markdown(self) -> None:
        response = self._call("ui.release.markdown")
        if response is not None:
            self.release_detail.setPlainText(
                f"Preview only · {response['filename_suggestion']}\n"
                f"SHA-256: {response['sha256']}\n\n{response['content']}"
            )
            self._set_status(
                "Review packet preview generated locally. No publication was submitted."
            )

    def cancel_job(self) -> None:
        selected = self.job_list.currentItem()
        if selected:
            self.jobs.cancel(selected.text().split(": ", 1)[0])

    def retry_job(self) -> None:
        selected = self.job_list.currentItem()
        if selected is None:
            self._set_status("Select a failed or cancelled job first.")
            return
        task_id = selected.text().split(": ", 1)[0]
        if self.jobs.retry(task_id):
            self._set_status(f"{task_id}: retry started")
        else:
            self._set_status("Only failed or cancelled jobs with a retained callback can retry.")

    def save_preferences(self) -> None:
        try:
            locale = Localizer(self.locale_entry.text()).normalized_locale
        except UIError as exc:
            self._set_status(f"{exc.message} {exc.recovery}")
            return
        values = {
            "theme": self.theme_picker.currentText(),
            "density": self.density_picker.currentText(),
            "scale": float(self.scale_picker.currentText().rstrip("%")) / 100,
            "sidebar_width": self.splitter.sizes()[0],
            "window_width": self.width(),
            "window_height": self.height(),
            "panel_visibility": {"sidebar": self.splitter.sizes()[0] > 0},
            "panel_sizes": {"sidebar": self.splitter.sizes()[0]},
            "locale": locale,
        }
        response = self._call("ui.preferences.update", **values)
        if response:
            self.prefs = Preferences(**response["preferences"])
            app = QApplication.instance()
            if isinstance(app, QApplication):
                apply_theme(app, self.prefs)
                direction = Localizer(self.prefs.locale).direction
                app.setLayoutDirection(
                    Qt.LayoutDirection.RightToLeft
                    if direction == "rtl"
                    else Qt.LayoutDirection.LeftToRight
                )
            self.refresh_localization()
            self._set_status("Preferences saved.")

    def refresh_localization(self) -> None:
        response = self._call("ui.localization.read")
        if response is None:
            return
        state = response["localization"]
        self.localization_status.setText(
            f"Requested locale: {state['requested_locale']} · direction: {state['direction']} · "
            f"translated catalog: {state['translated']} · "
            f"fallback: {state['fallback_locale'] or 'none'}\n"
            f"Complete catalogs: {', '.join(state['complete_catalogs'])}. "
            "English is the only complete translation shipped in this workstream."
        )

    def refresh_workspace_presets(self) -> None:
        self.preset_list.clear()
        response = self._call("ui.workspace.preset.list")
        if response is None:
            return
        for preset in response["presets"]:
            item = QListWidgetItem(
                f"{preset['name']} · {preset['active_screen']} · "
                f"{round(float(preset['scale']) * 100)}%"
            )
            item.setData(Qt.ItemDataRole.UserRole, preset)
            self.preset_list.addItem(item)
        if response["warnings"]:
            self._set_status("; ".join(response["warnings"]))

    def save_workspace_preset(self) -> None:
        name = self.preset_name.text().strip()
        if not name:
            self._set_status("Enter a workspace preset name.")
            return
        sizes = self.splitter.sizes()
        response = self._call(
            "ui.workspace.preset.save",
            preset={
                "name": name,
                "project_id": self.project_id,
                "active_screen": SCREENS[self.pages.currentIndex()],
                "panel_visibility": {"sidebar": bool(sizes and sizes[0] > 0)},
                "panel_sizes": {"sidebar": sizes[0] if sizes else self.prefs.sidebar_width},
                "theme": self.theme_picker.currentText(),
                "density": self.density_picker.currentText(),
                "scale": float(self.scale_picker.currentText().rstrip("%")) / 100,
                "table_settings": {"page_size": self.data_page_size},
                "window_width": self.width(),
                "window_height": self.height(),
            },
        )
        if response is not None:
            self.refresh_workspace_presets()
            self._set_status(f"Saved workspace preset {response['preset']['name']}.")

    def restore_workspace_preset(self) -> None:
        current = self.preset_list.currentItem()
        if current is None:
            self._set_status("Select a workspace preset.")
            return
        preset = current.data(Qt.ItemDataRole.UserRole)
        self.theme_picker.setCurrentText(preset["theme"])
        self.density_picker.setCurrentText(preset["density"])
        self.scale_picker.setCurrentText(f"{round(float(preset['scale']) * 100)}%")
        self.resize(int(preset["window_width"]), int(preset["window_height"]))
        sidebar = int(preset["panel_sizes"].get("sidebar", self.prefs.sidebar_width))
        self.splitter.setSizes([sidebar, max(400, self.width() - sidebar)])
        table_size = preset.get("table_settings", {}).get("page_size")
        if isinstance(table_size, int) and 1 <= table_size <= 5000:
            self.data_page_size = table_size
        project_id = str(preset.get("project_id", ""))
        if project_id and project_id != self.project_id:
            available = {
                project["id"]
                for project in (self._call("ui.project.list") or {}).get("projects", [])
            }
            if project_id in available:
                if not self._confirm_leave_project():
                    return
                self.open_project(project_id)
            else:
                self._set_status(
                    "Preset project no longer exists; restored layout without switching project."
                )
        self.navigate(str(preset["active_screen"]))
        self.save_preferences()
        self._set_status(f"Restored workspace preset {preset['name']}.")

    def delete_workspace_preset(self) -> None:
        current = self.preset_list.currentItem()
        if current is None:
            return
        preset = current.data(Qt.ItemDataRole.UserRole)
        if self._call("ui.workspace.preset.delete", preset_id=preset["id"]) is not None:
            self.refresh_workspace_presets()

    def reset_workspace_layout(self) -> None:
        self.resize(1260, 780)
        self.splitter.setSizes([214, 1046])
        self.theme_picker.setCurrentText("light")
        self.density_picker.setCurrentText("comfortable")
        self.scale_picker.setCurrentText("100%")
        self.locale_entry.setText("en")
        self.data_page_size = 250
        self.navigate("Dashboard")
        self.save_preferences()
        self._set_status("Workspace layout reset to safe defaults.")

    def refresh_activity(self) -> None:
        self.activity_list.clear()
        if self.project_id:
            value = self._call(
                "ui.activity.list",
                operation_filter=self.activity_operation.text().strip(),
                limit=int(self.activity_limit.currentData() or 100),
            )
            if value:
                for event in value["events"]:
                    target = (
                        f" · {event['target_kind']}:{event['target_id']}"
                        if event.get("target_id")
                        else f" · {event.get('target_kind', 'project')}"
                    )
                    item = QListWidgetItem(
                        f"{event['sequence']} · {event['operation']}{target} · {event['timestamp']}"
                    )
                    item.setData(Qt.ItemDataRole.UserRole, event)
                    fields = ", ".join(event.get("changed_fields", [])) or "none"
                    item.setToolTip(f"Changed fields: {fields}")
                    self.activity_list.addItem(item)
                self.activity_status.setText(
                    f"Showing {len(value['events'])} of {value['total']} matching local events. "
                    f"{value['limitation']}"
                )

    def open_activity_event(self, item: QListWidgetItem) -> None:
        event = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(event, dict):
            return
        target_kind = str(event.get("target_kind", ""))
        target_id = str(event.get("target_id", ""))
        screen_by_kind = {
            "source": "Library",
            "qual": "Qualitative",
            "dataset": "Data View",
            "variable": "Variable View",
            "chart": "Statistics",
            "protocol": "Protocol",
            "prisma": "PRISMA",
            "manuscript": "Manuscript",
            "reference": "References",
            "analysis": "Analysis Results",
            "screening": "Review",
        }
        screen = screen_by_kind.get(target_kind)
        if screen is None:
            self._set_status("This activity record has no specialized navigation target.")
            return
        self.navigate(screen)
        if target_kind == "source" and target_id:
            response = self._call("ui.source.get", source_id=target_id)
            if response is not None:
                source = response["source"]
                self.current_source_id = target_id
                self.reader_meta.setText(
                    f"{source['title']} · {source['source_label']} · "
                    f"SHA-256 {source['content_hash']}"
                )
                self.reader_text.setPlainText(source["text"])
                self.navigate("Reader")

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
        self.protocol_history.clear()
        history = self._call("ui.protocol.history")
        if history is not None:
            for entry in history["entries"][-100:]:
                self.protocol_history.addItem(
                    f"{entry['timestamp']} · {entry['action']} · "
                    f"{', '.join(entry.get('changed_fields', [])) or 'no field diff'}"
                )
            for deviation in history.get("deviations", [])[-100:]:
                item = QListWidgetItem(
                    f"DEVIATION · {deviation['created_at']} · {deviation['description']}"
                )
                item.setToolTip(
                    f"Reason: {deviation['reason']} · Impact: "
                    f"{deviation['impact'] or 'not specified'}"
                )
                self.protocol_history.addItem(item)
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
            (
                template
                for template in templates["templates"]
                if template["id"] == record["template_id"]
            ),
            None,
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
            named(
                editor,
                f"{spec['label']} {'required' if spec['required'] else 'optional'}",
                spec["help_text"],
            )
            self.protocol_form.addRow(
                f"{spec['label']} {'*' if spec['required'] else ''}",
                editor,
            )
            self.protocol_fields[spec["name"]] = editor

    def preview_protocol_export(self) -> None:
        response = self._call("ui.protocol.export")
        if response is None:
            return
        self.protocol_summary.setText(
            self.protocol_summary.text()
            + "\n\nStructured export preview:"
            + f" {response['entries']} history entries · "
            + f"{response['deviations']} deviations · SHA-256 {response['sha256']}\n"
            + "Export preserves user-authored protocol/history without certifying validity."
        )

    def add_protocol_deviation(self) -> None:
        response = self._call(
            "ui.protocol.deviation.add",
            description=self.protocol_deviation.text(),
            reason=self.protocol_deviation_reason.text(),
            impact=self.protocol_deviation_impact.text(),
        )
        if response is not None:
            self.protocol_deviation.clear()
            self.protocol_deviation_reason.clear()
            self.protocol_deviation_impact.clear()
            self.refresh_protocol()
            self._set_status("Recorded protocol deviation with protocol revision hash.")

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
                f"{response['template']}: required fields are complete.\n{response['note']}"
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

    def _select_guidance(
        self, current: QListWidgetItem | None, previous: QListWidgetItem | None
    ) -> None:
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

    def capture_evidence(self) -> None:
        if not self.current_source_id:
            self._set_status("Choose a local source in Library before capturing evidence.")
            return
        cursor = self.reader_text.textCursor()
        if not cursor.hasSelection():
            self._set_status("Highlight an exact passage in Reader first.")
            return
        try:
            start, end = qt_range_to_codepoints(
                self.reader_text.toPlainText(), cursor.selectionStart(), cursor.selectionEnd()
            )
        except UIError as exc:
            self._set_status(f"{exc.message} {exc.recovery}")
            return
        note, accepted = QInputDialog.getText(
            self, "Evidence interpretation", "Optional context note (not a verified claim)"
        )
        if not accepted:
            return
        result = self._call(
            "ui.evidence.capture",
            source_id=self.current_source_id,
            start=start,
            end=end,
            note=note,
        )
        if result is not None:
            self.navigate("Evidence")
            self._set_status(
                f"Evidence anchor saved; integrity: {result['integrity']['integrity']}"
            )

    def refresh_evidence(self) -> None:
        if not self.project_id:
            return
        saved = self._call("ui.evidence.list", limit=500)
        if saved is not None:
            self.evidence_list.clear()
            for record in saved["records"]:
                item = QListWidgetItem(f"{record['integrity'].upper()} · {record['quote'][:100]}")
                item.setData(Qt.ItemDataRole.UserRole, record["id"])
                self.evidence_list.addItem(item)
        claims = self._call("ui.claim.list")
        if claims is not None:
            self.claim_list.clear()
            for claim in claims["claims"]:
                item = QListWidgetItem(
                    f"{claim['status']} · {claim['text'][:90]} · "
                    f"{claim['supporting_count']} source links"
                )
                item.setData(Qt.ItemDataRole.UserRole, claim["id"])
                self.claim_list.addItem(item)

    def inspect_selected_evidence(
        self, current: QListWidgetItem | None, previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        response = self._call(
            "ui.evidence.inspect", evidence_id=current.data(Qt.ItemDataRole.UserRole)
        )
        if response is not None:
            self.evidence_detail.setPlainText(
                f"Source: {response['source_title']}\n"
                f"Label: {response['source_label']}\n"
                f"Text: {response['quote']}\n"
                f"Span: {response['span_start']}–{response['span_end']}\n"
                f"Source SHA-256: {response['source_sha256']}\n"
                f"Integrity: {response['integrity']}\n"
                f"Checks: {response['checks']}\n\n{response['note']}"
            )

    def open_selected_evidence_source(self, item: QListWidgetItem | bool | None = None) -> None:
        selected = item if isinstance(item, QListWidgetItem) else self.evidence_list.currentItem()
        if selected is None:
            self._set_status("Select an evidence passage first.")
            return
        response = self._call(
            "ui.evidence.inspect",
            evidence_id=selected.data(Qt.ItemDataRole.UserRole),
        )
        if response is None:
            return
        self._open_source_span(
            str(response["source_id"]),
            int(response["span_start"]),
            int(response["span_end"]),
            f"Evidence anchor · integrity {response['integrity']}",
        )

    def create_evidence_claim(self) -> None:
        item = self.evidence_list.currentItem()
        if item is None:
            self._set_status("Select the evidence passage that supports the draft.")
            return
        created = self._call(
            "ui.claim.create",
            text=self.claim_entry.toPlainText(),
            supporting_evidence=[item.data(Qt.ItemDataRole.UserRole)],
            challenging_evidence=[],
        )
        if created is not None:
            self.claim_entry.clear()
            self.refresh_evidence()
            self._set_status("Claim draft saved; independent scientific review is required.")

    def inspect_selected_claim(
        self, current: QListWidgetItem | None, previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        claim_id = current.data(Qt.ItemDataRole.UserRole)
        assessment = self._call("ui.claim.inspect", claim_id=claim_id)
        reference = self._call("ui.claim.reference", claim_id=claim_id)
        if assessment is None:
            return
        text = (
            f"Draft: {assessment['claim']['text']}\n"
            f"Evidence integrity: {assessment['integrity']}\n"
            f"Supporting excerpts: {len(assessment['supporting'])}\n"
            f"Challenging excerpts: {len(assessment['challenging'])}\n"
            f"Scientific review required: {assessment['human_assessment_required']}\n"
            f"Warnings: {assessment['warnings']}\n"
        )
        if reference is not None:
            text += (
                f"\n{reference['citation_placeholder']}\n"
                f"Source IDs: {reference['source_ids']}\n"
                f"{reference['note']}"
            )
        self.claim_details.setPlainText(text)

    def closeEvent(self, event: QCloseEvent | None) -> None:
        if event is None:
            return
        if not self._confirm_leave_project():
            event.ignore()
            return
        if self.project_id:
            for field, editor in (
                ("manuscript", self.manuscript_editor),
                ("notebook", self.notebook_editor),
            ):
                document = editor.document()
                if document is not None and document.isModified():
                    self._call(
                        "ui.recovery.save",
                        field=field,
                        text=editor.toPlainText(),
                        expected_revision=self.revision,
                    )
        for timer in self._draft_timers.values():
            timer.stop()
        self.jobs.invalidate()
        self.prefs.sidebar_width = max(150, min(480, self.splitter.sizes()[0]))
        self.prefs.window_width = self.width()
        self.prefs.window_height = self.height()
        self.facade.settings.save(self.prefs)
        event.accept()

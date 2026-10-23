"""Accessible visual tokens and reusable Qt styling primitives."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication, QWidget

from .contracts import Preferences


@dataclass(frozen=True)
class Colors:
    background: str
    surface: str
    text: str
    muted: str
    accent: str
    border: str
    focus: str
    error: str


THEMES = {
    "light": Colors("#F7F8FB", "#FFFFFF", "#182339", "#445269", "#315FAC",
                    "#DCE3ED", "#235BC4", "#A9243E"),
    "dark": Colors("#111823", "#1A2635", "#EFF4FB", "#B9C9DF", "#8EB5FF",
                   "#39485D", "#BDD6FF", "#FF9FAD"),
    "contrast": Colors("#000000", "#111111", "#FFFFFF", "#FFFFFF", "#FFFF00",
                       "#FFFFFF", "#00FFFF", "#FF8899"),
}


def apply_theme(app: QApplication, preferences: Preferences) -> None:
    """Apply real QPalette colors and keyboard-visible focus styles."""
    color = THEMES[preferences.theme]
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(color.background))
    palette.setColor(QPalette.ColorRole.Base, QColor(color.surface))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(color.background))
    palette.setColor(QPalette.ColorRole.Button, QColor(color.surface))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(color.text))
    palette.setColor(QPalette.ColorRole.Text, QColor(color.text))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(color.text))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(color.accent))
    palette.setColor(QPalette.ColorRole.HighlightedText,
                     QColor("#000000" if preferences.theme == "contrast" else "#FFFFFF"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(color.muted))
    app.setPalette(palette)
    font = QFont("Segoe UI")
    font.setPointSizeF(10 * preferences.scale)
    app.setFont(font)
    padding = 6 if preferences.density == "compact" else 10
    app.setStyleSheet(
        f"QMainWindow, QWidget {{ background: {color.background}; color: {color.text}; }}"
        f"QWidget#page, QWidget#readingSurface, QFrame#surface {{"
        f"background: {color.surface}; border: 1px solid {color.border};"
        f"border-radius: 9px; }}"
        f"QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QTableView, QListWidget, "
        f"QTreeView, QSpinBox {{background: {color.surface}; color: {color.text};"
        f"border: 1px solid {color.border}; border-radius: 5px;"
        f"padding: {padding // 2}px; selection-background-color: {color.accent}; }}"
        f"QPushButton {{background: {color.surface}; color: {color.text};"
        f"border: 1px solid {color.border}; border-radius: 7px;"
        f"padding: {padding}px; min-height: 18px; }}"
        f"QPushButton:hover {{border-color: {color.accent};}}"
        f"QPushButton:focus, QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,"
        f"QComboBox:focus, QListWidget:focus, QTableView:focus {{"
        f"border: 2px solid {color.focus}; }}"
        f"QPushButton#primary {{background: {color.accent}; color:"
        f"{'#000000' if preferences.theme == 'contrast' else '#FFFFFF'};"
        f"font-weight: 600; }}"
        f"QLabel#sectionTitle {{font-size: {16 * preferences.scale:.1f}pt;"
        f"font-weight: 700;}}"
        f"QLabel#muted {{color: {color.muted};}}"
        f"QListWidget::item:selected {{background: {color.accent}; color:"
        f"{'#000000' if preferences.theme == 'contrast' else '#FFFFFF'};}}"
    )


def named(widget: QWidget, name: str, description: str = "") -> QWidget:
    widget.setAccessibleName(name)
    if description:
        widget.setAccessibleDescription(description)
    return widget

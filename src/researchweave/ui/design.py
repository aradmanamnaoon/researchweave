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
    surface_alt: str
    text: str
    muted: str
    accent: str
    accent_soft: str
    primary_text: str
    border: str
    focus: str
    error: str
    success: str
    warning: str


THEMES = {
    "light": Colors(
        "#F3F6F9",
        "#FFFFFF",
        "#EAF0F6",
        "#172033",
        "#526176",
        "#2F6092",
        "#DCE9F5",
        "#FFFFFF",
        "#D5DFE9",
        "#1F65B5",
        "#A9243E",
        "#237A57",
        "#8A5A00",
    ),
    "dark": Colors(
        "#0F1722",
        "#172232",
        "#1D2B3E",
        "#EFF4FB",
        "#BAC7D8",
        "#8EB8E8",
        "#233A54",
        "#0F1722",
        "#33465B",
        "#B8D8FF",
        "#FF9FAD",
        "#7FD4AF",
        "#F5C66A",
    ),
    "contrast": Colors(
        "#000000",
        "#111111",
        "#1B1B1B",
        "#FFFFFF",
        "#FFFFFF",
        "#FFFF00",
        "#262600",
        "#000000",
        "#FFFFFF",
        "#00FFFF",
        "#FF8899",
        "#7CFFB2",
        "#FFD166",
    ),
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
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(color.primary_text))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(color.muted))
    app.setPalette(palette)
    font = QFont("Segoe UI")
    font.setPointSizeF(10 * preferences.scale)
    app.setFont(font)
    padding = 6 if preferences.density == "compact" else 10
    row_padding = 5 if preferences.density == "compact" else 8
    app.setStyleSheet(
        f"QMainWindow, QWidget {{ background: {color.background}; color: {color.text}; }}"
        "QLabel { background: transparent; }"
        f"QMainWindow::separator {{ background: {color.border}; width: 1px; height: 1px; }}"
        f"QWidget#page, QWidget#readingSurface, QFrame#surface, QFrame#heroSurface {{"
        f"background: {color.surface}; border: 1px solid {color.border};"
        f"border-radius: 12px; }}"
        f"QFrame#sidebar {{ background: {color.surface}; border: 1px solid {color.border};"
        f"border-radius: 12px; }}"
        f"QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QTableView, QListWidget, "
        f"QTreeView, QSpinBox {{background: {color.surface}; color: {color.text};"
        f"border: 1px solid {color.border}; border-radius: 7px;"
        f"padding: {padding // 2}px; selection-background-color: {color.accent};"
        f"selection-color: {color.primary_text}; }}"
        f"QPushButton {{background: {color.surface}; color: {color.text};"
        f"border: 1px solid {color.border}; border-radius: 8px;"
        f"padding: {padding}px {padding + 4}px; min-height: 18px; }}"
        f"QPushButton:hover {{border-color: {color.accent}; background: {color.surface_alt};}}"
        f"QPushButton:pressed {{background: {color.accent_soft};}}"
        f"QPushButton:focus, QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,"
        f"QComboBox:focus, QListWidget:focus, QTreeView:focus, QTableView:focus {{"
        f"border: 2px solid {color.focus}; }}"
        f"QPushButton#primary {{background: {color.accent}; color:"
        f"{color.primary_text};"
        f"font-weight: 650; border-color: {color.accent}; }}"
        f"QPushButton#primary:hover {{background: {color.focus}; border-color: {color.focus};}}"
        f"QPushButton#quiet {{background: transparent; border-color: transparent;"
        f"color: {color.accent}; padding: {max(4, padding // 2)}px {padding}px; }}"
        f"QPushButton#quiet:hover {{background: {color.accent_soft};"
        f"border-color: {color.accent_soft};}}"
        f"QLabel#brandTitle {{font-size: {18 * preferences.scale:.1f}pt; font-weight: 750;}}"
        f"QLabel#eyebrow {{font-size: {8.5 * preferences.scale:.1f}pt; font-weight: 700;"
        f"color: {color.muted}; }}"
        f"QLabel#sectionTitle {{font-size: {20 * preferences.scale:.1f}pt;"
        f"font-weight: 750;}}"
        f"QLabel#projectContext {{background: {color.surface_alt}; color: {color.muted};"
        f"border: 1px solid {color.border}; border-radius: 9px; padding: 6px 10px;}}"
        f"QLabel#pageLead {{font-size: {11 * preferences.scale:.1f}pt; color: {color.muted};}}"
        f"QLabel#muted {{color: {color.muted};}}"
        "QTreeWidget#workspaceNav {background: transparent; border: none;"
        "outline: none; padding: 2px;}"
        f"QTreeWidget#workspaceNav::item {{border: none; border-radius: 7px;"
        f"padding: {row_padding}px 7px; margin: 1px 1px;}}"
        f"QTreeWidget#workspaceNav::item:hover {{background: {color.surface_alt};}}"
        f"QTreeWidget#workspaceNav::item:selected {{background: {color.accent_soft};"
        f"color: {color.text};"
        f"font-weight: 650;}}"
        f"QListWidget::item:selected {{background: {color.accent_soft}; color: {color.text};}}"
        f"QStatusBar {{background: {color.background}; color: {color.muted};"
        f"border-top: 1px solid {color.border};}}"
    )


def named(widget: QWidget, name: str, description: str = "") -> QWidget:
    widget.setAccessibleName(name)
    if description:
        widget.setAccessibleDescription(description)
    return widget

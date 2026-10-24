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
    padding = 6 if preferences.density == "compact" else 9
    row_padding = 4 if preferences.density == "compact" else 7
    card_padding = 10 if preferences.density == "compact" else 14
    app.setStyleSheet(
        f"QMainWindow, QWidget {{ background: {color.background}; color: {color.text}; }}"
        "QLabel { background: transparent; }"
        "QScrollArea#pageScroll { background: transparent; border: none; }"
        "QScrollArea#pageScroll > QWidget > QWidget { background: transparent; }"
        f"QMainWindow::separator {{ background: {color.border}; width: 1px; height: 1px; }}"
        f"QWidget#page, QWidget#readingSurface {{"
        f"background: {color.surface}; border: 1px solid {color.border};"
        f"border-radius: 12px; }}"
        f"QFrame#surface, QFrame#heroSurface, QFrame#toolbarSurface, QFrame#metricCard, "
        f"QFrame#headerSurface, QFrame#calloutSurface {{background: {color.surface};"
        f"border: 1px solid {color.border}; border-radius: 10px;}}"
        f"QFrame#heroSurface {{background: {color.surface_alt};}}"
        f"QFrame#toolbarSurface {{background: {color.surface_alt};}}"
        f"QFrame#metricCard {{min-width: 132px;}}"
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
        f"QLabel#brandTitle {{font-size: {17 * preferences.scale:.1f}pt; font-weight: 750;}}"
        f"QLabel#eyebrow {{font-size: {8.5 * preferences.scale:.1f}pt; font-weight: 700;"
        f"color: {color.muted}; letter-spacing: 0.8px;}}"
        f"QLabel#sectionTitle {{font-size: {19 * preferences.scale:.1f}pt;"
        f"font-weight: 750;}}"
        f"QLabel#surfaceTitle {{font-size: {11.5 * preferences.scale:.1f}pt;"
        f"font-weight: 700; color: {color.text};}}"
        f"QLabel#metricValue {{font-size: {18 * preferences.scale:.1f}pt;"
        f"font-weight: 750; color: {color.text};}}"
        f"QLabel#metricLabel {{font-size: {8.5 * preferences.scale:.1f}pt;"
        f"font-weight: 700; color: {color.muted}; letter-spacing: 0.5px;}}"
        f"QLabel#metricDetail {{font-size: {8.5 * preferences.scale:.1f}pt;"
        f"color: {color.muted};}}"
        f"QLabel#projectContext {{background: {color.surface_alt}; color: {color.muted};"
        f"border: 1px solid {color.border}; border-radius: 9px; padding: 6px 10px;}}"
        f"QLabel#pageLead {{font-size: {11 * preferences.scale:.1f}pt; color: {color.muted};}}"
        f"QLabel#muted {{color: {color.muted};}}"
        f"QLabel#statusGood {{color: {color.success}; font-weight: 650;}}"
        f"QLabel#statusWarn {{color: {color.warning}; font-weight: 650;}}"
        f"QFrame#surface QLabel#pageLead, QFrame#toolbarSurface QLabel#pageLead {{"
        f"font-size: {9.5 * preferences.scale:.1f}pt;}}"
        "QTreeWidget#workspaceNav {background: transparent; border: none;"
        "outline: none; padding: 4px 1px;}"
        f"QTreeWidget#workspaceNav::item {{border: none; border-radius: 7px;"
        f"padding: {row_padding}px 7px; margin: 1px 1px;}}"
        f"QTreeWidget#workspaceNav::item:hover {{background: {color.surface_alt};}}"
        f"QTreeWidget#workspaceNav::item:selected {{background: {color.accent_soft};"
        f"color: {color.text};"
        f"font-weight: 650;}}"
        f"QListWidget::item:selected {{background: {color.accent_soft}; color: {color.text};}}"
        f"QTableView {{gridline-color: {color.border};"
        f"alternate-background-color: {color.surface_alt};}}"
        f"QHeaderView::section {{background: {color.surface_alt}; color: {color.text};"
        f"border: none; border-right: 1px solid {color.border};"
        f"border-bottom: 1px solid {color.border};"
        f"padding: {max(5, card_padding // 2)}px; font-weight: 650;}}"
        f"QScrollBar:vertical {{background: transparent; width: 10px; margin: 1px;}}"
        f"QScrollBar::handle:vertical {{background: {color.border}; border-radius: 4px;"
        f"min-height: 28px;}}"
        f"QScrollBar::handle:vertical:hover {{background: {color.muted};}}"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height: 0px;}"
        f"QToolTip {{background: {color.surface}; color: {color.text};"
        f"border: 1px solid {color.border};"
        f"padding: 5px;}}"
        f"QStatusBar {{background: {color.background}; color: {color.muted};"
        f"border-top: 1px solid {color.border};}}"
    )


def named(widget: QWidget, name: str, description: str = "") -> QWidget:
    widget.setAccessibleName(name)
    if description:
        widget.setAccessibleDescription(description)
    return widget

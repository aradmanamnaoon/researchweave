"""Programmatic accessibility checks and measurable theme contrast.

These checks supplement, but cannot replace, real assistive technology tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QComboBox,
    QHeaderView,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
    QWidget,
)

from .design import THEMES, Colors


def _rgb(color: str) -> tuple[int, int, int]:
    if len(color) != 7 or not color.startswith("#"):
        raise ValueError("Expected a six-digit hexadecimal color")
    try:
        values = tuple(int(color[index : index + 2], 16) for index in (1, 3, 5))
    except ValueError as exc:
        raise ValueError("Invalid hexadecimal color") from exc
    return values  # type: ignore[return-value]


def _linear(channel: int) -> float:
    number = channel / 255
    return number / 12.92 if number <= 0.04045 else ((number + 0.055) / 1.055) ** 2.4


def luminance(color: str) -> float:
    red, green, blue = _rgb(color)
    return 0.2126 * _linear(red) + 0.7152 * _linear(green) + 0.0722 * _linear(blue)


def contrast_ratio(first: str, second: str) -> float:
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def contrast_audit(colors: Colors) -> dict[str, float]:
    """Compare text roles to their default canvas/surface backgrounds."""
    return {
        "body-on-window": round(contrast_ratio(colors.text, colors.background), 3),
        "body-on-surface": round(contrast_ratio(colors.text, colors.surface), 3),
        "muted-on-window": round(contrast_ratio(colors.muted, colors.background), 3),
        "muted-on-surface": round(contrast_ratio(colors.muted, colors.surface), 3),
        "focus-on-window": round(contrast_ratio(colors.focus, colors.background), 3),
        "focus-on-surface": round(contrast_ratio(colors.focus, colors.surface), 3),
        "primary-text-on-accent": round(contrast_ratio(colors.primary_text, colors.accent), 3),
        "primary-text-on-hover": round(contrast_ratio(colors.primary_text, colors.focus), 3),
    }


def check_theme_contrast(*, normal_threshold: float = 4.5) -> list[str]:
    """Report any failing default text role; do not silently drop bad tokens."""
    issues = []
    for theme_name, palette in THEMES.items():
        audits = contrast_audit(palette)
        for role, ratio in audits.items():
            if role.startswith(("body", "muted", "primary-text")) and ratio < normal_threshold:
                issues.append(f"{theme_name}/{role}: {ratio:.2f}:1")
    return issues


@dataclass(frozen=True)
class AccessibleIssue:
    widget_type: str
    object_name: str
    problem: str
    severity: str = "medium"


def inspect_widgets(parent: QWidget) -> list[AccessibleIssue]:
    """Inspect keyboard-focus controls without mutating focus or user settings."""
    issue_list: list[AccessibleIssue] = []
    classes = (QAbstractButton, QAbstractItemView, QLineEdit, QPlainTextEdit, QTextEdit, QComboBox)
    for widget in parent.findChildren(QWidget):
        if not isinstance(widget, classes):
            continue
        # The Qt implementation owns popup QListViews and table headers. Their
        # accessible container is the named combo box / table view, so do not
        # report them as separate first-class controls.
        if isinstance(widget, QHeaderView):
            continue
        if isinstance(widget, QAbstractItemView):
            owner = widget.parent()
            while owner is not None and owner is not parent:
                if isinstance(owner, QComboBox):
                    break
                owner = owner.parent()
            if isinstance(owner, QComboBox):
                continue
        if type(widget).__name__ == "QAbstractButton":
            continue
        if not widget.isEnabled():
            continue
        if not widget.accessibleName().strip():
            # Text buttons have native spoken labels; still require names for icon-only controls.
            if isinstance(widget, QAbstractButton) and widget.text().strip():
                continue
            issue_list.append(
                AccessibleIssue(
                    type(widget).__name__,
                    widget.objectName(),
                    "Focusable control lacks an accessible name",
                )
            )
        if widget.focusPolicy().value == 0:
            issue_list.append(
                AccessibleIssue(
                    type(widget).__name__,
                    widget.objectName(),
                    "Enabled interactive control does not accept keyboard focus",
                )
            )
    return issue_list


def contrast_report() -> dict[str, Any]:
    return {
        "standard": "WCAG 2.x text-contrast heuristic applied to theme tokens",
        "normal_text_minimum": 4.5,
        "reports": {name: contrast_audit(colors) for name, colors in THEMES.items()},
        "failures": check_theme_contrast(),
        "limitations": (
            "Programmatic checks cannot certify native screen reader support, "
            "layout reflow, animation reduction or legal compliance."
        ),
    }

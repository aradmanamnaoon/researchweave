"""Theme contrast, high DPI and accessible-name regression."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from researchweave.ui import build_ui_facade, build_ui_shell
from researchweave.ui.accessibility import (
    check_theme_contrast,
    contrast_audit,
    contrast_ratio,
    inspect_widgets,
)
from researchweave.ui.design import THEMES, apply_theme


def test_contrast_reference_values() -> None:
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert contrast_ratio("#FFFFFF", "#FFFFFF") == pytest.approx(1.0)
    with pytest.raises(ValueError):
        contrast_ratio("red", "#FFFFFF")


def test_default_palette_minimums() -> None:
    assert check_theme_contrast() == []
    for palette in THEMES.values():
        audits = contrast_audit(palette)
        assert audits["primary-text-on-accent"] >= 4.5
        assert audits["primary-text-on-hover"] >= 4.5


def test_scaled_accessibility_inspection(tmp_path: Path) -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    facade = build_ui_facade(tmp_path)
    window = build_ui_shell(fake_services=facade)
    for theme in ("light", "dark", "contrast"):
        for scale in (1.0, 1.5, 2.0):
            preferences = facade.settings.load()
            preferences.theme = theme
            preferences.scale = scale
            apply_theme(app, preferences)
            window.resize(1280, 720)
            app.processEvents()
            assert window.pages.count() >= 15
            assert window.page_heading.text()
            assert window.nav.accessibleName()
            assert window.project_picker.accessibleName()
    issues = inspect_widgets(window)
    assert not issues, issues
    window.close()

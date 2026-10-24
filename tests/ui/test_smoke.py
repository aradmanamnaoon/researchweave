import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from researchweave.app.config import AppConfig  # noqa: E402
from researchweave.app.main import create_window  # noqa: E402


def test_window_starts_offscreen(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = create_window(AppConfig(data_directory=tmp_path))
    window.show()
    app.processEvents()
    assert window.windowTitle() == "ResearchWeave"
    assert not window.windowIcon().isNull()
    assert window.isVisible()
    window.close()


def test_custom_application_title_survives_project_open(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = create_window(AppConfig(application_title="Research Desk", data_directory=tmp_path))
    window.show()
    app.processEvents()
    assert hasattr(window, "create_local_demo")
    window.create_local_demo()  # type: ignore[attr-defined]
    app.processEvents()
    assert window.windowTitle().startswith("Research Desk · Synthetic attention demo")
    window.close()

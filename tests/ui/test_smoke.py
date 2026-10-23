import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from researchweave.app.config import load_config  # noqa: E402
from researchweave.app.main import create_window  # noqa: E402


def test_window_starts_offscreen() -> None:
    app = QApplication.instance() or QApplication([])
    window = create_window(load_config())
    window.show()
    app.processEvents()
    assert window.windowTitle() == "ResearchWeave"
    assert window.isVisible()
    window.close()

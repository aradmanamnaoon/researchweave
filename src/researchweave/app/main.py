"""Start a minimal accessible Qt shell; no network access or credentials required."""

import sys

from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget

from researchweave.app.config import AppConfig, load_config


def create_window(config: AppConfig) -> QMainWindow:
    window = QMainWindow()
    window.setWindowTitle(config.application_title)
    window.setMinimumSize(760, 480)
    content = QWidget()
    content.setAccessibleName("ResearchWeave welcome screen")
    layout = QVBoxLayout(content)
    heading = QLabel("ResearchWeave")
    heading.setObjectName("welcomeHeading")
    heading.setAccessibleName("ResearchWeave")
    heading.setStyleSheet("font-size: 26px; font-weight: 600;")
    summary = QLabel("A research workspace is taking shape.")
    summary.setWordWrap(True)
    layout.addWidget(heading)
    layout.addWidget(summary)
    layout.addStretch()
    window.setCentralWidget(content)
    return window


def main() -> int:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    if not isinstance(app, QApplication):
        raise RuntimeError("Expected QApplication instance")
    window = create_window(load_config())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

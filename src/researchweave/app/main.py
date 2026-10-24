"""Start the integrated ResearchWeave desktop with offline-safe production services."""

from __future__ import annotations

import sys
from typing import cast

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMainWindow

from researchweave.app.composition import AppServices, build_services
from researchweave.app.config import AppConfig, load_config
from researchweave.app.desktop_gateway import DesktopCommandGateway
from researchweave.ui import build_ui_shell
from researchweave.ui.assets import asset_path
from researchweave.ui.facade import UIFacade


def create_window(config: AppConfig, *, services: AppServices | None = None) -> QMainWindow:
    """Build the real V2 desktop shell without starting a second QApplication."""

    integrated = services or build_services(config.data_directory)
    gateway = DesktopCommandGateway(integrated.ui, integrated.bus)
    window = build_ui_shell(fake_services=cast(UIFacade, gateway))
    icon = QIcon(str(asset_path("researchweave-mark.svg")))
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.base_window_title = config.application_title
    project_title = getattr(window, "project_title", "")
    if project_title:
        window.setWindowTitle(f"{config.application_title} · {project_title}")
    else:
        window.setWindowTitle(config.application_title)
    return window


def main() -> int:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    if not isinstance(app, QApplication):
        raise RuntimeError("Expected QApplication instance")
    icon = QIcon(str(asset_path("researchweave-mark.svg")))
    if not icon.isNull():
        app.setWindowIcon(icon)
    services = build_services(load_config().data_directory)
    app.aboutToQuit.connect(services.close)
    window = create_window(load_config(), services=services)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

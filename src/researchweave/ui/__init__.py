"""ResearchWeave's offline desktop UI and independently testable command facade.

The integration composition root will inject real domain facades. The included
local demonstration service uses only synthetic, explicitly labeled material.
"""

from typing import TYPE_CHECKING

from .facade import UIFacade, build_ui_facade

if TYPE_CHECKING:
    from .shell import ResearchWindow

__all__ = ["UIFacade", "build_ui_facade", "build_ui_shell"]


def build_ui_shell(*, fake_services: UIFacade | None = None) -> "ResearchWindow":
    """Build a configured QMainWindow without starting a second QApplication."""
    from .shell import ResearchWindow

    return ResearchWindow(fake_services or build_ui_facade())

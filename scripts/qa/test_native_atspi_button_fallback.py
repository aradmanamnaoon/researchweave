"""Isolated regression for native AT-SPI Slint push-button activation fallback.

Compiles only the real activate() function AST; does not import pyatspi,
spawn an X11 desktop, or fabricate an installed UI acceptance result.
"""
from __future__ import annotations

import ast
import pathlib
import types
import unittest
from typing import Any


class FakeNode:
    def __init__(self, name: str, role: str, y: int = 310, actions: int = 0) -> None:
        self.name = name
        self.role = role
        self.y = y
        self.actions = actions

    def queryAction(self) -> Any:
        return types.SimpleNamespace(nActions=self.actions, doAction=lambda index: True)

    def getRoleName(self) -> str:
        return self.role

    def queryComponent(self) -> Any:
        return self

    def getExtents(self, coords: Any) -> Any:
        return types.SimpleNamespace(x=390, y=self.y, width=100, height=32)


class ButtonFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        source = pathlib.Path(__file__).with_name("mission-atspi-navigation.py")
        parsed = ast.parse(source.read_text(encoding="utf-8"))
        function = next(
            item for item in parsed.body
            if isinstance(item, ast.FunctionDef) and item.name == "activate"
        )
        self.calls: list[list[str]] = []
        self.nodes: list[FakeNode] = []

        def recorded_run(command: list[str], **kwargs: Any) -> None:
            self.calls.append(command)

        namespace: dict[str, Any] = {
            "Any": Any,
            "nodes_named": lambda app, name: self.nodes,
            "subprocess": types.SimpleNamespace(run=recorded_run),
            "pyatspi": types.SimpleNamespace(DESKTOP_COORDS=0),
        }
        isolated = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
        exec(compile(isolated, str(source), "exec"), namespace)
        self.activate = namespace["activate"]

    def test_actual_slint_accesskit_push_button_role_can_click_exact_visible_node(self) -> None:
        name = "Load manuscript section revision history"
        self.nodes = [FakeNode(name, "push button")]
        self.assertTrue(self.activate(None, name))
        self.assertEqual(self.calls, [["xdotool", "mousemove", "--sync", "440", "326", "click", "1"]])

    def test_unrelated_role_or_name_cannot_be_clicked(self) -> None:
        name = "Load manuscript section revision history"
        for node in (FakeNode(name, "label"), FakeNode("Another button", "push button")):
            self.nodes = [node]
            self.assertFalse(self.activate(None, name))
            self.assertEqual(self.calls, [])

    def test_offscreen_node_below_persistent_jobs_tray_is_rejected(self) -> None:
        name = "Load manuscript section revision history"
        self.nodes = [FakeNode(name, "push button", y=730)]
        self.assertFalse(self.activate(None, name))
        self.assertEqual(self.calls, [])

    def test_actual_native_accessibility_action_precedes_any_mouse_fallback(self) -> None:
        name = "Load manuscript section revision history"
        self.nodes = [FakeNode(name, "push button", actions=1)]
        self.assertTrue(self.activate(None, name))
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()

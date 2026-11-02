"""Fail-closed contract tests for actual native editor clipboard readback.

These tests use isolated stand-ins for native X11 commands and must not be
reported as a passing installed Xvfb/AT-SPI GUI acceptance.
"""
from __future__ import annotations

import ast
import pathlib
import types
import unittest
import uuid
from typing import Any


class FakeEditor:
    name = "Analysis dataset ID"

    def __init__(self, y: int = 312) -> None:
        self.y = y

    def queryComponent(self) -> "FakeEditor":
        return self

    def getExtents(self, coords: Any) -> Any:
        return types.SimpleNamespace(x=390, y=self.y, width=250, height=32)

    def grabFocus(self) -> bool:
        return True


class ClipboardReadbackTests(unittest.TestCase):
    def setUp(self) -> None:
        source = pathlib.Path(__file__).with_name("mission-atspi-navigation.py")
        parsed = ast.parse(source.read_text(encoding="utf-8"))
        function = next(
            statement for statement in parsed.body
            if isinstance(statement, ast.FunctionDef)
            and statement.name == "read_visible_field_keyboard"
        )
        self.clipboard = ""
        self.native_value: str | None = None
        self.calls: list[list[str]] = []
        self.ats_read_count = 0
        self.editor = FakeEditor()

        def native_run(command: list[str], **kwargs: Any) -> Any:
            self.calls.append(command)
            if command[:3] == ["xdotool", "search", "--name"]:
                return types.SimpleNamespace(stdout="12345\n")
            if command == ["xclip", "-selection", "clipboard", "-i"]:
                self.clipboard = kwargs["input"]
            elif command == ["xdotool", "key", "--clearmodifiers", "ctrl+a", "ctrl+c"]:
                if self.native_value is not None:
                    self.clipboard = self.native_value
            elif command == ["xclip", "-selection", "clipboard", "-o"]:
                return types.SimpleNamespace(stdout=self.clipboard)
            return types.SimpleNamespace(stdout="")

        def fake_read_field(app: Any, name: str) -> str:
            self.ats_read_count += 1
            # The point of force_clipboard is to reject false empty text from
            # broken AT-SPI on an actually populated native LineEdit.
            return ""

        namespace: dict[str, Any] = {
            "Any": Any,
            "nodes_named": lambda app, name: [self.editor],
            "read_field": fake_read_field,
            "subprocess": types.SimpleNamespace(run=native_run),
            "pyatspi": types.SimpleNamespace(DESKTOP_COORDS=0),
            "uuid": uuid,
            "print": lambda *args, **kwargs: None,
        }
        module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
        exec(compile(module, str(source), "exec"), namespace)
        self.readback = namespace["read_visible_field_keyboard"]

    def test_forced_clipboard_rejects_misleading_empty_accessibility_text(self) -> None:
        self.native_value = "persisted-identity-from-older-project"
        self.assertEqual(
            self.readback(None, "Analysis dataset ID", allow_empty=True, force_clipboard=True),
            self.native_value,
        )
        self.assertEqual(self.ats_read_count, 0)
        self.assertIn(
            ["xdotool", "key", "--clearmodifiers", "ctrl+a", "ctrl+c"],
            self.calls,
        )

    def test_fresh_sentinel_may_represent_empty_only_with_explicit_opt_in(self) -> None:
        self.native_value = None
        self.assertEqual(
            self.readback(None, "Analysis dataset ID", allow_empty=True, force_clipboard=True),
            "",
        )
        self.assertEqual(self.ats_read_count, 0)
        with self.assertRaises(RuntimeError):
            self.readback(None, "Analysis dataset ID", allow_empty=False, force_clipboard=True)

    def test_offscreen_editor_cannot_be_trusted_as_empty(self) -> None:
        self.editor = FakeEditor(y=730)
        with self.assertRaises(RuntimeError):
            self.readback(None, "Analysis dataset ID", allow_empty=True, force_clipboard=True)
        self.assertFalse(self.calls)

    def test_f05_citation_reads_require_actual_native_field_not_database_value(self) -> None:
        source = pathlib.Path(__file__).with_name("mission-atspi-navigation.py")
        tree = ast.parse(source.read_text(encoding="utf-8"))
        procedure = next(
            statement for statement in tree.body
            if isinstance(statement, ast.FunctionDef)
            and statement.name == "exercise_f05_project_citation"
        )
        native_reads = [
            call for call in ast.walk(procedure)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "read_visible_field_keyboard"
            and len(call.args) >= 2
            and isinstance(call.args[1], ast.Constant)
            and call.args[1].value == "Manuscript citations"
        ]
        self.assertEqual(len(native_reads), 2)
        self.assertTrue(any(
            any(keyword.arg == "force_clipboard" for keyword in call.keywords)
            for call in native_reads
        ))
        self.assertFalse(any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "read_field"
            and len(call.args) >= 2
            and isinstance(call.args[1], ast.Constant)
            and call.args[1].value == "Manuscript citations"
            for call in ast.walk(procedure)
        ))


if __name__ == "__main__":
    unittest.main()

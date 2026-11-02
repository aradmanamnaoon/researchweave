"""Fail-closed regression checks for strict native editor readback fallback.

These are isolated stand-ins; they do not establish installed Linux acceptance.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import unittest


SOURCE = Path(__file__).with_name("mission-atspi-navigation.py")


class NativeEditor:
    name = "Manuscript find text"

    def queryEditableText(self) -> Any:
        raise NotImplementedError("Slint AT-SPI EditableText unsupported")

    def queryComponent(self) -> "NativeEditor":
        return self

    def grabFocus(self) -> bool:
        return True

    def queryText(self) -> Any:
        raise NotImplementedError("Slint AT-SPI Text unsupported")


class StrictEditClipboardContract(unittest.TestCase):
    def setUp(self) -> None:
        parsed = ast.parse(SOURCE.read_text(encoding="utf-8"))
        func = next(
            node for node in parsed.body
            if isinstance(node, ast.FunctionDef) and node.name == "edit_text"
        )
        self.native_value = ""
        self.clipboard_override: str | None = None
        self.revealed = 0
        self.native_commands: list[list[str]] = []
        self.editor = NativeEditor()

        def run(command: list[str], **_: Any) -> SimpleNamespace:
            self.native_commands.append(command)
            if command[:3] == ["xdotool", "search", "--name"]:
                return SimpleNamespace(stdout="123456\n")
            if command[:2] == ["xdotool", "type"]:
                self.native_value = command[-1]
            return SimpleNamespace(stdout="")

        def reveal(_: Any, name: str, **__: Any) -> None:
            self.assertEqual(name, self.editor.name)
            self.revealed += 1

        def clipboard(_: Any, name: str, **kwargs: Any) -> str:
            self.assertEqual(name, self.editor.name)
            self.assertTrue(kwargs.get("force_clipboard"))
            return (
                self.native_value
                if self.clipboard_override is None
                else self.clipboard_override
            )

        namespace: dict[str, Any] = {
            "Any": Any,
            "nodes_named": lambda app, name: [self.editor] if name == self.editor.name else [],
            "subprocess": SimpleNamespace(run=run),
            "time": SimpleNamespace(sleep=lambda _: None),
            "print": lambda *args, **kwargs: None,
            "reveal_bounded_control": reveal,
            "read_visible_field_keyboard": clipboard,
        }
        module = ast.fix_missing_locations(ast.Module(body=[func], type_ignores=[]))
        exec(compile(module, str(SOURCE), "exec"), namespace)
        self.edit = namespace["edit_text"]

    def test_really_typed_and_exactly_copied_native_value_can_pass(self) -> None:
        self.edit(None, "Manuscript find text", "Synthetic")
        self.assertEqual(self.native_value, "Synthetic")
        self.assertEqual(self.revealed, 1)
        self.assertIn(
            ["xdotool", "type", "--clearmodifiers", "--delay", "12", "Synthetic"],
            self.native_commands,
        )

    def test_wrong_native_clipboard_value_fails_even_after_typing(self) -> None:
        self.clipboard_override = "Wrong value in actual field"
        with self.assertRaisesRegex(RuntimeError, "Text never appeared"):
            self.edit(None, "Manuscript find text", "Synthetic")
        self.assertEqual(self.revealed, 1)

    def test_empty_native_clipboard_must_not_count_as_entered_text(self) -> None:
        self.clipboard_override = ""
        with self.assertRaisesRegex(RuntimeError, "Text never appeared"):
            self.edit(None, "Manuscript find text", "Synthetic")
        self.assertEqual(self.revealed, 1)


if __name__ == "__main__":
    unittest.main()

"""Fail-closed parser contracts for a real GUI Protocol inspector readback."""

from __future__ import annotations

import ast
import json
import pathlib
import unittest
from typing import Any


SCRIPT = pathlib.Path(__file__).with_name("mission-atspi-navigation.py")


def load_parser():
    # The installed Windows QA host has no Linux-only pyatspi dependency.
    # Compile only the pure production validator; do not mock the GUI surface.
    syntax = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
    function = next(
        node for node in syntax.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "parse_native_protocol_receipt"
    )
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    namespace: dict[str, Any] = {"json": json, "Any": Any}
    exec(compile(module, str(SCRIPT), "exec"), namespace)
    return namespace[function.name]


class ProtocolInspectorReceiptTests(unittest.TestCase):
    def test_only_matching_visible_json_is_accepted(self):
        parse = load_parser()
        identity = "12345678-1234-1234-1234-123456789abc"
        payload = {
            "protocol_id": identity,
            "frozen": False,
            "local_only": True,
            "external_registration_verified": False,
        }
        self.assertEqual(parse(json.dumps(payload), identity, frozen=False), payload)
        with self.assertRaisesRegex(RuntimeError, "invalid JSON"):
            parse("", identity, frozen=False)
        with self.assertRaisesRegex(RuntimeError, "invalid JSON"):
            parse("{", identity, frozen=False)
        for changed in (
            {"protocol_id": "other"},
            {"frozen": True},
            {"local_only": False},
            {"external_registration_verified": True},
        ):
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(RuntimeError, "identity/state"):
                    parse(json.dumps(payload | changed), identity, frozen=False)

    def test_frozen_receipt_requires_exact_boolean_and_identity(self):
        parse = load_parser()
        identity = "12345678-1234-1234-1234-123456789abc"
        payload = {
            "protocol_id": identity,
            "frozen": True,
            "local_only": True,
            "external_registration_verified": False,
        }
        self.assertEqual(parse(json.dumps(payload), identity, frozen=True), payload)
        with self.assertRaises(RuntimeError):
            parse(json.dumps(payload | {"frozen": 1}), identity, frozen=True)


if __name__ == "__main__":
    unittest.main()

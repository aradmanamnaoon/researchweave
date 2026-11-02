"""Regression for Linux quick-card archive QA's persisted/UI readback gates.

These isolated tests deliberately do not claim that a native Xvfb app ran.
"""

from __future__ import annotations

import ast
import json
import pathlib
import sqlite3
import tempfile
import time
import types
import unittest
from contextlib import closing
from typing import Any


class QuickNoteArchiveReadbackTests(unittest.TestCase):
    def setUp(self) -> None:
        source = pathlib.Path(__file__).with_name("mission-atspi-navigation.py")
        parsed = ast.parse(source.read_text(encoding="utf-8"))
        functions = [
            node for node in parsed.body
            if isinstance(node, ast.FunctionDef) and node.name in (
                "wait_quick_note_revision", "wait_quick_note_removed_from_filter",
            )
        ]
        self.assertEqual(len(functions), 2)
        self.names: list[str] = []
        self.audits: list[str] = []

        def nodes_named(app: Any, name: str) -> list[Any]:
            return [types.SimpleNamespace(name=entry) for entry in self.names if name in entry]

        namespace: dict[str, Any] = {
            "Any": Any,
            "pathlib": pathlib,
            "sqlite3": sqlite3,
            "closing": closing,
            "json": json,
            "time": time,
            "nodes_named": nodes_named,
            "audit": lambda app, label, output: self.audits.append(label),
        }
        exec(compile(ast.fix_missing_locations(
            ast.Module(body=functions, type_ignores=[])
        ), str(source), "exec"), namespace)
        self.wait_revision = namespace["wait_quick_note_revision"]
        self.wait_removed = namespace["wait_quick_note_removed_from_filter"]
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = pathlib.Path(self.temporary.name)
        (self.project / "data").mkdir()
        self.card_id = "card:00000000-0000-4000-8000-000000000001"
        with closing(sqlite3.connect(self.project / "data/project.sqlite")) as db:
            db.execute("CREATE TABLE notebook_entries(id TEXT,revision INTEGER,body TEXT)")
            db.commit()
        self.append_revision(1, pinned=False, archived=False)

    def append_revision(self, revision: int, *, pinned: bool, archived: bool) -> None:
        with closing(sqlite3.connect(self.project / "data/project.sqlite")) as db:
            db.execute(
                "INSERT INTO notebook_entries(id,revision,body) VALUES(?,?,?)",
                (self.card_id, revision, json.dumps({"pinned": pinned, "archived": archived})),
            )
            db.commit()

    def test_pin_archive_and_restore_require_real_incremental_writes(self) -> None:
        self.append_revision(2, pinned=True, archived=False)
        self.assertEqual(
            self.wait_revision(self.project, self.card_id, 1,
                               pinned=True, archived=False, timeout=0), 2,
        )
        self.append_revision(3, pinned=True, archived=True)
        self.assertEqual(
            self.wait_revision(self.project, self.card_id, 2,
                               pinned=True, archived=True, timeout=0), 3,
        )
        self.append_revision(4, pinned=True, archived=False)
        self.assertEqual(
            self.wait_revision(self.project, self.card_id, 3,
                               pinned=True, archived=False, timeout=0), 4,
        )

    def test_atspi_acceptance_without_db_revision_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "did not append"):
            self.wait_revision(self.project, self.card_id, 1,
                               pinned=True, archived=True, timeout=0)

    def test_wrong_state_or_skipped_revision_fails_closed(self) -> None:
        self.append_revision(2, pinned=True, archived=False)
        with self.assertRaisesRegex(RuntimeError, "unexpected revision"):
            self.wait_revision(self.project, self.card_id, 1,
                               pinned=True, archived=True, timeout=0)
        self.append_revision(4, pinned=True, archived=True)
        with self.assertRaisesRegex(RuntimeError, "unexpected revision"):
            self.wait_revision(self.project, self.card_id, 2,
                               pinned=True, archived=True, timeout=0)

    def test_stale_native_card_fails_even_after_persistence(self) -> None:
        self.names = ["Edit quick note Synthetic MRI memo"]
        with self.assertRaisesRegex(RuntimeError, "still exposes its Edit control"):
            self.wait_removed(None, "Synthetic MRI memo", self.project,
                              filter_name="pinned", timeout=0)
        self.assertEqual(self.audits, ["quick-note-stale-pinned-filter"])
        self.names = []
        self.wait_removed(None, "Synthetic MRI memo", self.project,
                          filter_name="archived", timeout=0)


if __name__ == "__main__":
    unittest.main()

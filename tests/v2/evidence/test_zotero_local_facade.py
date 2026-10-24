from __future__ import annotations

import json
from pathlib import Path

from researchweave.evidence import build_evidence_facade


class _LocalZotero:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, bytes | None]] = []

    def request(self, method: str, path: str, body: bytes | None = None) -> tuple[int, bytes]:
        self.calls.append((method, path, body))
        return 200, json.dumps([{"key": "ITEM1", "title": "Local item"}]).encode()


def test_facade_exposes_read_only_authorized_zotero_local_bridge(tmp_path: Path) -> None:
    transport = _LocalZotero()
    facade = build_evidence_facade(tmp_path, zotero_transport=transport)
    result = facade.execute("migration.zotero_local_read", {"path": "/api/users/0/items"}, {})
    assert result["status"] == "ok"
    assert result["data"]["read_only"] is True
    assert result["data"]["data"][0]["key"] == "ITEM1"
    assert transport.calls == [("GET", "/api/users/0/items", None)]


def test_zotero_local_facade_is_denied_without_injected_transport(tmp_path: Path) -> None:
    facade = build_evidence_facade(tmp_path)
    result = facade.execute("migration.zotero_local_read", {"path": "/api/users/0/items"}, {})
    assert result["status"] == "failed"
    assert result["error"]["code"] == "OFFLINE_DENIED"

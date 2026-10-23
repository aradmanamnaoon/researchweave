from __future__ import annotations

import hashlib
import json
from pathlib import Path

from defusedxml import ElementTree as ET

ASSET_ROOT = Path("workstreams/v2/ui/assets")


def test_asset_manifest_hashes_and_accessible_svg_metadata() -> None:
    manifest = json.loads((ASSET_ROOT / "ASSET_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["license"] == "GPL-3.0-only"
    assert len(manifest["assets"]) >= 2
    for record in manifest["assets"]:
        path = ASSET_ROOT / record["path"]
        content = path.read_bytes()
        assert hashlib.sha256(content).hexdigest() == record["sha256"]
        root = ET.fromstring(content)
        namespace = "{http://www.w3.org/2000/svg}"
        title = root.find(f"{namespace}title")
        description = root.find(f"{namespace}desc")
        assert title is not None and title.text == record["title"]
        assert description is not None and description.text == record["description"]
        assert root.attrib.get("role") == "img"
        assert "title" in root.attrib.get("aria-labelledby", "")
        assert "description" in root.attrib.get("aria-labelledby", "")
        lowered = content.lower()
        assert b"<script" not in lowered
        assert b"http://" not in lowered.replace(b"http://www.w3.org/2000/svg", b"")
        assert b"https://" not in lowered
        assert b"xlink:href" not in lowered
        assert b"href=" not in lowered
        assert record["license"] == "GPL-3.0-only"
        assert "Original" in record["provenance"]

"""Validated workspace preset records independent from Qt widgets."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from .contracts import UIError, new_id, utc_now

THEMES = frozenset({"light", "dark", "contrast"})
DENSITIES = frozenset({"comfortable", "compact"})
MIN_WIDTH = 760
MAX_WIDTH = 7680
MIN_HEIGHT = 490
MAX_HEIGHT = 4320
MIN_PANEL = 120
MAX_PANEL = 4000
MAX_PRESETS = 50
WORKSPACE_SCREENS = (
    "Welcome", "Dashboard", "Question", "Search", "Protocol", "Library", "Reader",
    "PDF Reader", "Evidence", "Review", "PRISMA", "Extraction", "Data View",
    "Variable View", "Statistics", "Analysis Results", "Qualitative", "Codebook",
    "Mixed Methods", "Manuscript", "References", "Notebook", "Publishing", "Agent",
    "Providers", "Privacy", "Integrations", "Exports", "Backups", "Recovery",
    "Diagnostics", "Jobs", "Notifications", "Tutorials", "Guidance", "Shortcuts",
    "Preferences", "Activity", "About",
)


@dataclass
class WorkspacePreset:
    id: str
    name: str
    project_id: str = ""
    active_screen: str = "Dashboard"
    panel_visibility: dict[str, bool] = field(default_factory=dict)
    panel_sizes: dict[str, int] = field(default_factory=dict)
    theme: str = "light"
    density: str = "comfortable"
    scale: float = 1.0
    table_settings: dict[str, Any] = field(default_factory=dict)
    window_width: int = 1260
    window_height: int = 780
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


def _text(value: Any, name: str, maximum: int, *, required: bool = True) -> str:
    if not isinstance(value, str) or len(value) > maximum:
        raise UIError("INVALID_INPUT", f"{name} is invalid.",
                      "Review the workspace preset fields.")
    cleaned = value.strip()
    if required and not cleaned:
        raise UIError("INVALID_INPUT", f"{name} is required.",
                      "Enter a value before saving the preset.")
    return cleaned


def _clamp_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return max(minimum, min(maximum, int(value)))


def sanitize_workspace(raw: dict[str, Any], *, known_screens: tuple[str, ...]) -> WorkspacePreset:
    name = _text(raw.get("name", "Workspace"), "Preset name", 100)
    theme = raw.get("theme", "light")
    density = raw.get("density", "comfortable")
    scale = raw.get("scale", 1.0)
    if theme not in THEMES:
        theme = "light"
    if density not in DENSITIES:
        density = "comfortable"
    if isinstance(scale, bool) or not isinstance(scale, (int, float)):
        scale = 1.0
    scale = max(1.0, min(2.0, float(scale)))
    screen = raw.get("active_screen", "Dashboard")
    if not isinstance(screen, str) or screen not in known_screens:
        screen = "Dashboard"
    visibility_raw = raw.get("panel_visibility", {})
    sizes_raw = raw.get("panel_sizes", {})
    visibility = (
        {str(key): bool(value) for key, value in visibility_raw.items()}
        if isinstance(visibility_raw, dict) else {}
    )
    sizes = (
        {
            str(key): _clamp_int(value, MIN_PANEL, MAX_PANEL, MIN_PANEL)
            for key, value in sizes_raw.items()
        }
        if isinstance(sizes_raw, dict) else {}
    )
    table_raw = raw.get("table_settings", {})
    table = json.loads(json.dumps(table_raw)) if isinstance(table_raw, dict) else {}
    return WorkspacePreset(
        id=_text(raw.get("id", new_id()), "Preset id", 60),
        name=name,
        project_id=_text(raw.get("project_id", ""), "Project id", 60, required=False),
        active_screen=screen,
        panel_visibility=visibility,
        panel_sizes=sizes,
        theme=theme,
        density=density,
        scale=scale,
        table_settings=table,
        window_width=_clamp_int(raw.get("window_width"), MIN_WIDTH, MAX_WIDTH, 1260),
        window_height=_clamp_int(raw.get("window_height"), MIN_HEIGHT, MAX_HEIGHT, 780),
        created_at=_text(raw.get("created_at", utc_now()), "Created timestamp", 80),
        updated_at=utc_now(),
    )


def decode_presets(
    raw: Any, *, known_screens: tuple[str, ...],
) -> tuple[list[WorkspacePreset], list[str]]:
    if not isinstance(raw, list):
        return [], ["Preset collection was corrupt and was ignored."]
    presets: list[WorkspacePreset] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(raw[:MAX_PRESETS]):
        if not isinstance(item, dict):
            warnings.append(f"Preset {index + 1} was not an object and was ignored.")
            continue
        if not isinstance(item.get("name"), str) or not item["name"].strip():
            warnings.append(f"Preset {index + 1} had no valid name and was ignored.")
            continue
        try:
            preset = sanitize_workspace(item, known_screens=known_screens)
        except UIError:
            warnings.append(f"Preset {index + 1} was invalid and was ignored.")
            continue
        if preset.id in seen:
            warnings.append(f"Duplicate preset {preset.id} was ignored.")
            continue
        seen.add(preset.id)
        presets.append(preset)
    return presets, warnings


def save_preset(
    raw_presets: Any, raw_preset: dict[str, Any], *, known_screens: tuple[str, ...],
) -> tuple[list[dict[str, Any]], WorkspacePreset, list[str]]:
    presets, warnings = decode_presets(raw_presets, known_screens=known_screens)
    preset = sanitize_workspace(raw_preset, known_screens=known_screens)
    replaced = False
    for index, current in enumerate(presets):
        if current.id == preset.id or current.name.casefold() == preset.name.casefold():
            preset.id = current.id
            preset.created_at = current.created_at
            presets[index] = preset
            replaced = True
            break
    if not replaced:
        if len(presets) >= MAX_PRESETS:
            raise UIError("RESOURCE_LIMIT", "Workspace preset limit reached.",
                          "Delete an old preset before saving another.")
        presets.append(preset)
    return [asdict(item) for item in presets], preset, warnings


def delete_preset(
    raw_presets: Any, preset_id: str, *, known_screens: tuple[str, ...],
) -> tuple[list[dict[str, Any]], bool, list[str]]:
    presets, warnings = decode_presets(raw_presets, known_screens=known_screens)
    remaining = [item for item in presets if item.id != preset_id]
    return [asdict(item) for item in remaining], len(remaining) != len(presets), warnings

from researchweave.ui.i18n import Localizer, validate_catalog
from researchweave.ui.presets import decode_presets, delete_preset, save_preset

SCREENS = ("Dashboard", "Library", "Data View")


def test_i18n_english_fallback_plural_and_rtl_metadata() -> None:
    assert validate_catalog()["valid"] is True
    english = Localizer("en-US")
    assert english.translate("app.title").startswith("ResearchWeave")
    assert english.plural("count.source", 1) == "1 source"
    assert english.plural("count.source", 2) == "2 sources"
    persian = Localizer("fa-IR")
    assert persian.direction == "rtl"
    assert persian.translated is False
    assert persian.fallback_used is True
    assert persian.translate("screen.dashboard") == "Dashboard"
    assert persian.metadata()["fallback_locale"] == "en"


def test_workspace_preset_sanitizes_geometry_and_corrupt_state() -> None:
    raw, saved, warnings = save_preset(
        [{"broken": True}, "bad"],
        {
            "name": "Analysis",
            "active_screen": "Data View",
            "theme": "dark",
            "density": "compact",
            "scale": 9.0,
            "window_width": 99999,
            "window_height": 1,
            "panel_sizes": {"sidebar": 12},
            "table_settings": {"page_size": 250},
        },
        known_screens=SCREENS,
    )
    assert warnings
    assert saved.scale == 2.0
    assert saved.window_width == 7680
    assert saved.window_height == 490
    assert saved.panel_sizes["sidebar"] == 120
    decoded, decode_warnings = decode_presets(raw, known_screens=SCREENS)
    assert not decode_warnings
    assert decoded[0].active_screen == "Data View"
    remaining, deleted, _ = delete_preset(
        raw, saved.id, known_screens=SCREENS
    )
    assert deleted is True
    assert remaining == []

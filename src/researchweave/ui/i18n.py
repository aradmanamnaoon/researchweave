"""Small, explicit localization layer for the desktop UI.

English is the only complete shipped catalog. Other locale codes fall back to
English while still exposing correct layout direction metadata; this avoids
misrepresenting an untranslated interface as localized.
"""

from __future__ import annotations

from dataclasses import dataclass
from string import Formatter
from typing import Final

from .contracts import UIError

RTL_LANGUAGES: Final[frozenset[str]] = frozenset({"ar", "fa", "he", "ur"})

EN: Final[dict[str, str]] = {
    "app.title": "ResearchWeave · Local research desktop",
    "app.tagline": "Private by default · local workspace",
    "status.offline_ready": "Offline-ready · no AI credentials required",
    "status.no_project": "Open or create a project first.",
    "screen.welcome": "Welcome",
    "screen.dashboard": "Dashboard",
    "screen.question": "Question",
    "screen.search": "Search",
    "screen.protocol": "Protocol",
    "screen.library": "Library",
    "screen.reader": "Reader",
    "screen.pdf_reader": "PDF Reader",
    "screen.evidence": "Evidence",
    "screen.review": "Review",
    "screen.prisma": "PRISMA",
    "screen.extraction": "Extraction",
    "screen.data_view": "Data View",
    "screen.variable_view": "Variable View",
    "screen.statistics": "Statistics",
    "screen.analysis_results": "Analysis Results",
    "screen.qualitative": "Qualitative",
    "screen.codebook": "Codebook",
    "screen.mixed_methods": "Mixed Methods",
    "screen.manuscript": "Manuscript",
    "screen.references": "References",
    "screen.notebook": "Notebook",
    "screen.publishing": "Publishing",
    "screen.agent": "Agent",
    "screen.providers": "Providers",
    "screen.privacy": "Privacy",
    "screen.integrations": "Integrations",
    "screen.exports": "Exports",
    "screen.backups": "Backups",
    "screen.recovery": "Recovery",
    "screen.diagnostics": "Diagnostics",
    "screen.jobs": "Jobs",
    "screen.notifications": "Notifications",
    "screen.tutorials": "Tutorials",
    "screen.guidance": "Guidance",
    "screen.shortcuts": "Shortcuts",
    "screen.preferences": "Preferences",
    "screen.activity": "Activity",
    "screen.about": "About",
    "count.project.one": "{count} project",
    "count.project.other": "{count} projects",
    "count.source.one": "{count} source",
    "count.source.other": "{count} sources",
}

SCREEN_KEYS: Final[dict[str, str]] = {
    value: f"screen.{value.lower().replace(' ', '_')}"
    for value in (
        "Welcome",
        "Dashboard",
        "Question",
        "Search",
        "Protocol",
        "Library",
        "Reader",
        "PDF Reader",
        "Evidence",
        "Review",
        "PRISMA",
        "Extraction",
        "Data View",
        "Variable View",
        "Statistics",
        "Analysis Results",
        "Qualitative",
        "Codebook",
        "Mixed Methods",
        "Manuscript",
        "References",
        "Notebook",
        "Publishing",
        "Agent",
        "Providers",
        "Privacy",
        "Integrations",
        "Exports",
        "Backups",
        "Recovery",
        "Diagnostics",
        "Jobs",
        "Notifications",
        "Tutorials",
        "Guidance",
        "Shortcuts",
        "Preferences",
        "Activity",
        "About",
    )
}


def normalize_locale(value: str) -> str:
    if not isinstance(value, str) or len(value) > 40:
        raise UIError(
            "INVALID_INPUT",
            "Locale identifier is invalid.",
            "Use a language tag such as en, en-US or fa-IR.",
        )
    cleaned = value.strip().replace("_", "-")
    if not cleaned:
        return "en"
    parts = cleaned.split("-")
    if not all(part.isalnum() and 1 <= len(part) <= 8 for part in parts):
        raise UIError(
            "INVALID_INPUT",
            "Locale identifier is invalid.",
            "Use a language tag such as en, en-US or fa-IR.",
        )
    language = parts[0].lower()
    tail = [part.upper() if len(part) == 2 else part.title() for part in parts[1:]]
    return "-".join([language, *tail])


def _placeholders(template: str) -> set[str]:
    return {field_name for _, field_name, _, _ in Formatter().parse(template) if field_name}


@dataclass(frozen=True)
class Localizer:
    locale: str = "en"

    @property
    def normalized_locale(self) -> str:
        return normalize_locale(self.locale)

    @property
    def language(self) -> str:
        return self.normalized_locale.split("-", 1)[0]

    @property
    def direction(self) -> str:
        return "rtl" if self.language in RTL_LANGUAGES else "ltr"

    @property
    def translated(self) -> bool:
        return self.language == "en"

    @property
    def fallback_used(self) -> bool:
        return not self.translated

    def translate(self, key: str, **values: object) -> str:
        template = EN.get(key)
        if template is None:
            raise UIError(
                "NOT_FOUND",
                f"Translation key {key!r} is not defined.",
                "Use an existing interface translation key.",
            )
        expected = _placeholders(template)
        supplied = set(values)
        if supplied != expected:
            raise UIError(
                "INVALID_INPUT",
                f"Translation values for {key!r} do not match its placeholders.",
                f"Expected: {sorted(expected)}.",
            )
        return template.format(**values)

    def plural(self, base_key: str, count: int) -> str:
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise UIError(
                "INVALID_INPUT",
                "Plural count must be a nonnegative integer.",
                "Provide a measured item count.",
            )
        suffix = "one" if count == 1 else "other"
        return self.translate(f"{base_key}.{suffix}", count=count)

    def metadata(self) -> dict[str, object]:
        return {
            "requested_locale": self.normalized_locale,
            "language": self.language,
            "direction": self.direction,
            "translated": self.translated,
            "fallback_locale": None if self.translated else "en",
            "complete_catalogs": ["en"],
        }


def validate_catalog() -> dict[str, object]:
    missing_screen_keys = [screen for screen, key in SCREEN_KEYS.items() if key not in EN]
    return {
        "english_keys": len(EN),
        "screens": len(SCREEN_KEYS),
        "missing_screen_keys": missing_screen_keys,
        "valid": not missing_screen_keys,
    }

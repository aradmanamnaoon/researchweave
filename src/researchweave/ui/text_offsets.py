"""Map Qt UTF-16 cursor positions onto Python Unicode codepoint positions.

Qt QTextCursor counts UTF-16 code units, whereas persisted research excerpts
use Python codepoint offsets. An uncorrected supplementary symbol before an
excerpt shifts every subsequent annotation or citation.
"""

from __future__ import annotations

from .contracts import UIError


def qt_range_to_codepoints(text: str, start: int, end: int) -> tuple[int, int]:
    """Translate a QTextCursor selection, rejecting split surrogate pairs.

    Runs in O(len(text)) time and constant auxiliary memory. A valid span maps
    to the exact Python slice saved in the project and verified by SHA-256.
    """
    if (
        not isinstance(text, str)
        or type(start) is not int
        or type(end) is not int
        or start < 0
        or start >= end
    ):
        raise UIError("INVALID_INPUT", "Invalid Qt selection.",
                      "Highlight a complete source passage.")
    utf16_index = 0
    first: int | None = None
    last: int | None = None
    for index, char in enumerate(text):
        if utf16_index == start:
            first = index
        if utf16_index == end:
            last = index
            break
        advance = 2 if ord(char) > 0xFFFF else 1
        if utf16_index < start < utf16_index + advance:
            raise UIError("INVALID_INPUT", "Selection splits a Unicode symbol.",
                          "Select the complete symbol and retry.")
        if utf16_index < end < utf16_index + advance:
            raise UIError("INVALID_INPUT", "Selection splits a Unicode symbol.",
                          "Select the complete symbol and retry.")
        utf16_index += advance
    if utf16_index == start and first is None:
        first = len(text)
    if utf16_index == end and last is None:
        last = len(text)
    if first is None or last is None or first >= last:
        raise UIError("INVALID_INPUT", "Selection is outside the source text.",
                      "Highlight existing source text before coding.")
    return first, last


def codepoint_range_to_qt(text: str, start: int, end: int) -> tuple[int, int]:
    """Translate persisted Python codepoint offsets into Qt UTF-16 cursor offsets."""
    if (
        not isinstance(text, str)
        or type(start) is not int
        or type(end) is not int
        or start < 0
        or start >= end
        or end > len(text)
    ):
        raise UIError(
            "INVALID_INPUT",
            "Invalid persisted source span.",
            "Inspect the saved evidence or annotation before navigating to it.",
        )
    qt_start = len(text[:start].encode("utf-16-le")) // 2
    qt_end = len(text[:end].encode("utf-16-le")) // 2
    return qt_start, qt_end

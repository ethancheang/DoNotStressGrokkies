"""The basic crisis-language check run on the optional reflection."""

from __future__ import annotations

import re


class SafetyCheck:
    """Keyword patterns that highlight support contacts.

    The same patterns go to the browser for an immediate prompt. Keywords
    can give false positives and negatives; this never assesses safety.
    """

    def __init__(self, patterns: tuple[str, ...]) -> None:
        self.__patterns: tuple[str, ...] = patterns
        self.__compiled: tuple[re.Pattern[str], ...] = tuple(
            re.compile(pattern) for pattern in patterns)

    @property
    def patterns(self) -> tuple[str, ...]:
        return self.__patterns

    def fired(self, text: object) -> bool:
        """True when the reflection matches any crisis pattern."""
        normalised = str(text or "").lower().replace("’", "'")
        return any(pattern.search(normalised) for pattern in self.__compiled)

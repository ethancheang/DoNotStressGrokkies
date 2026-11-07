"""Proof that a browser has checked in as a Student ID."""

from __future__ import annotations

import hashlib
import hmac


class HistoryPass:
    """Which Student IDs have checked in from this browser.

    The cookie holds keyed HMAC digests, never the IDs themselves, and a
    digest cannot be made without the server's secret key. Without a
    login this is what stops one student reading another's history by
    typing their Student ID.
    """

    COOKIE_NAME: str = "dns_history"
    MAX_AGE_SECONDS: int = 180 * 24 * 60 * 60
    MAX_IDS: int = 8
    DIGEST_LENGTH: int = 32

    def __init__(self, secret_key: str) -> None:
        self.__secret: bytes = secret_key.encode("utf-8")

    def allows(self, cookie: str | None, student_id: str) -> bool:
        """True when this browser has checked in as student_id."""
        wanted = self.__digest(student_id)
        return any(hmac.compare_digest(wanted, held)
                   for held in self.__digests(cookie))

    def grant(self, cookie: str | None, student_id: str) -> str:
        """The cookie value after adding student_id (newest kept)."""
        wanted = self.__digest(student_id)
        held = [digest for digest in self.__digests(cookie)
                if digest != wanted]
        return ".".join((held + [wanted])[-self.MAX_IDS:])

    def __digests(self, cookie: str | None) -> list[str]:
        parts = (cookie or "").split(".")
        return [part for part in parts
                if len(part) == self.DIGEST_LENGTH and part.isalnum()]

    def __digest(self, student_id: str) -> str:
        mac = hmac.new(self.__secret, student_id.strip().encode("utf-8"),
                       hashlib.sha256)
        return mac.hexdigest()[:self.DIGEST_LENGTH]

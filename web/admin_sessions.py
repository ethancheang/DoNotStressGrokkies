"""Server-side admin sign-in for the fixed coursework account."""

from __future__ import annotations

import secrets
import threading
import time

from werkzeug.security import check_password_hash


class AdminSessions:
    """Admin tokens kept on the server, plus a sign-in throttle.

    Only a token lives in the session cookie, so signing out or expiry
    revokes access even if an old cookie is replayed. No role is ever
    trusted from client input.
    """

    USERNAME: str = "admin"
    # Only the hash is in code; the password is in the README for the demo.
    PASSWORD_HASH: str = (
        "scrypt:32768:8:1$zoikUrXAJEAJCQlR$83ec3b2a32cedeb5721031e22f7fed"
        "c19ed5eea40c5995aa11d2c2ea1cc40845b393de85d68cda54706b5714293fc49"
        "ec360a477913186f00b46be7a6c31e8c1")
    MAX_PASSWORD_LENGTH: int = 256

    def __init__(self, session_seconds: float = 1800,
                 max_attempts: int = 5,
                 window_seconds: float = 300) -> None:
        self.__session_seconds: float = session_seconds
        self.__max_attempts: int = max_attempts
        self.__window_seconds: float = window_seconds
        self.__tokens: dict[str, float] = {}
        self.__attempts: dict[str, list[float]] = {}
        self.__lock: threading.Lock = threading.Lock()

    @property
    def session_seconds(self) -> float:
        return self.__session_seconds

    @session_seconds.setter
    def session_seconds(self, value: float) -> None:
        self.__session_seconds = value

    @property
    def window_seconds(self) -> float:
        return self.__window_seconds

    @window_seconds.setter
    def window_seconds(self, value: float) -> None:
        self.__window_seconds = value

    @property
    def active_count(self) -> int:
        with self.__lock:
            return len(self.__tokens)

    def record_attempt(self, address: str) -> bool:
        """Count a sign-in attempt. False when this address is throttled."""
        now = time.monotonic()
        with self.__lock:
            recent = [stamp for stamp in self.__attempts.get(address, [])
                      if stamp > now - self.__window_seconds]
            if len(recent) >= self.__max_attempts:
                self.__attempts[address] = recent
                return False
            self.__attempts[address] = recent + [now]
            return True

    def credentials_match(self, username: object, password: object) -> bool:
        if not isinstance(password, str) or (
                len(password) > self.MAX_PASSWORD_LENGTH):
            return False
        valid = check_password_hash(self.PASSWORD_HASH, password)
        return username == self.USERNAME and valid

    def issue(self, address: str) -> str:
        """A new admin token; the address's failed attempts are cleared."""
        token = secrets.token_urlsafe(32)
        with self.__lock:
            self.__tokens[token] = time.monotonic()
            self.__attempts.pop(address, None)
        return token

    def is_valid(self, token: str | None) -> bool:
        if not token:
            return False
        with self.__lock:
            issued = self.__tokens.get(token)
            if issued is not None and self.__fresh(issued):
                return True
            self.__tokens.pop(token, None)
            return False

    def revoke(self, token: str | None) -> None:
        if token:
            with self.__lock:
                self.__tokens.pop(token, None)

    def expire(self) -> None:
        """Drop expired tokens and attempts outside the throttle window."""
        cutoff = time.monotonic() - self.__window_seconds
        with self.__lock:
            self.__tokens = {token: issued
                             for token, issued in self.__tokens.items()
                             if self.__fresh(issued)}
            self.__attempts = {
                address: [stamp for stamp in stamps if stamp > cutoff]
                for address, stamps in self.__attempts.items()
                if any(stamp > cutoff for stamp in stamps)}

    def __fresh(self, issued: float) -> bool:
        return time.monotonic() - issued < self.__session_seconds

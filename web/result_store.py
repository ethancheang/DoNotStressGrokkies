"""Finished results kept briefly in server memory for /result."""

from __future__ import annotations

import secrets
import threading
import time

from json_types import JSONObject


class ResultStore:
    """Results keyed by an opaque token, never by the session cookie.

    Answers stay on the server; the cookie only holds the token. A result
    expires after ttl_seconds; the saved record is separate and stays.
    """

    def __init__(self, ttl_seconds: float = 1800) -> None:
        self.__ttl_seconds: float = ttl_seconds
        self.__results: dict[str, tuple[float, JSONObject]] = {}
        self.__lock: threading.Lock = threading.Lock()

    @property
    def ttl_seconds(self) -> float:
        return self.__ttl_seconds

    @ttl_seconds.setter
    def ttl_seconds(self, value: float) -> None:
        self.__ttl_seconds = value

    @property
    def count(self) -> int:
        with self.__lock:
            return len(self.__results)

    def put(self, result: JSONObject) -> str:
        token = secrets.token_urlsafe(32)
        with self.__lock:
            self.__results[token] = (time.monotonic(), dict(result))
        return token

    def get(self, token: str | None) -> JSONObject | None:
        """The result for this token, or None when unknown or expired."""
        if not token:
            return None
        with self.__lock:
            entry = self.__results.get(token)
            if entry is None or not self.__fresh(entry[0]):
                self.__results.pop(token, None)
                return None
            return dict(entry[1])

    def drop(self, token: str | None) -> None:
        if token:
            with self.__lock:
                self.__results.pop(token, None)

    def expire(self) -> None:
        with self.__lock:
            self.__results = {token: entry
                              for token, entry in self.__results.items()
                              if self.__fresh(entry[0])}

    def __fresh(self, created: float) -> bool:
        return time.monotonic() - created < self.__ttl_seconds

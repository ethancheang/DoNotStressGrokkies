"""A structured reason why the AI step did not finish."""

from __future__ import annotations


class AIFailure:
    """An AI failure code plus a secret-free detail for the logs.

    The codes match the error copy in the I/O layer. An unknown code is
    stored as "unavailable" so no caller ever sees an invented outcome.
    """

    MISSING_API_KEY: str = "missing_api_key"
    TIMEOUT: str = "timeout"
    INVALID_RESPONSE: str = "invalid_response"
    RETRIES_EXHAUSTED: str = "retries_exhausted"
    RATE_LIMITED: str = "rate_limited"
    UNAVAILABLE: str = "unavailable"
    CODES: tuple[str, ...] = (
        MISSING_API_KEY, TIMEOUT, INVALID_RESPONSE,
        RETRIES_EXHAUSTED, RATE_LIMITED, UNAVAILABLE,
    )
    SOURCE: str = "gemini"

    def __init__(self, code: str, detail: str = "") -> None:
        self.__code: str = code if code in self.CODES else self.UNAVAILABLE
        self.__detail: str = detail

    @property
    def code(self) -> str:
        return self.__code

    @property
    def detail(self) -> str:
        return self.__detail

    @property
    def source(self) -> str:
        return self.SOURCE

    def as_dict(self) -> dict[str, str]:
        return {"error_code": self.__code, "detail": self.__detail,
                "source": self.SOURCE}

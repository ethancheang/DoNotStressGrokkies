"""Maps a provider error onto one AIFailure code."""

from __future__ import annotations

from ai.ai_failure import AIFailure


class ErrorClassifier:
    """Reads an exception or message and names the kind of failure."""

    MISSING_KEY_MARKERS: tuple[str, ...] = (
        "missing_api_key", "gemini_api_key is not set", "api key is not set",
        "api_key is not set",
    )
    RATE_LIMIT_MARKERS: tuple[str, ...] = (
        "429", "resource exhausted", "resourceexhausted", "too many requests",
        "toomanyrequests", "rate limit", "ratelimit", "quota",
    )
    TIMEOUT_MARKERS: tuple[str, ...] = (
        "timeout", "timed out", "timed_out", "deadlineexceeded",
        "deadline exceeded",
    )
    SCHEMA_MARKERS: tuple[str, ...] = (
        "schema validation", "not valid json", "jsondecode", "malformed",
        "missing required fields", "must be a json object",
        "empty ai response", "allow-list", "invalid json",
    )

    def classify(self, error: Exception | str | None) -> str:
        """One AIFailure code. Unknown errors map to "unavailable"."""
        kind = type(error).__name__ if isinstance(error, Exception) else ""
        text = f"{kind} {error or ''}".strip().lower()
        if not text:
            return AIFailure.UNAVAILABLE
        if self.__mentions(text, self.MISSING_KEY_MARKERS) or (
                "gemini_api_key" in text
                and self.__mentions(text, ("not set", "missing", "blank"))):
            return AIFailure.MISSING_API_KEY
        status = (getattr(error, "code", None),
                  getattr(error, "status_code", None))
        if 429 in status or self.__mentions(text, self.RATE_LIMIT_MARKERS):
            return AIFailure.RATE_LIMITED
        if self.__mentions(text, self.TIMEOUT_MARKERS):
            return AIFailure.TIMEOUT
        if self.__mentions(text, self.SCHEMA_MARKERS):
            return AIFailure.INVALID_RESPONSE
        if "retries" in text and "exhaust" in text:
            return AIFailure.RETRIES_EXHAUSTED
        return AIFailure.UNAVAILABLE

    def __mentions(self, text: str, markers: tuple[str, ...]) -> bool:
        return any(marker in text for marker in markers)

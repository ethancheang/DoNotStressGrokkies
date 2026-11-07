"""The outcome of one AI step: validated fields, or a failure."""

from __future__ import annotations

from ai.ai_failure import AIFailure
from json_types import JSONObject


class AIResult:
    """Validated Gemini fields, or the AIFailure that stopped them."""

    def __init__(self, fields: JSONObject | None = None,
                 failure: AIFailure | None = None) -> None:
        self.__fields: JSONObject | None = fields
        self.__failure: AIFailure | None = failure

    @property
    def fields(self) -> JSONObject | None:
        return self.__fields

    @property
    def failure(self) -> AIFailure | None:
        return self.__failure

    @property
    def ok(self) -> bool:
        return self.__failure is None and self.__fields is not None

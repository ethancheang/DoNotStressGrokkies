"""A text answer that must be one of a fixed set of choices."""

from __future__ import annotations

from ai.validators.response_validator import ResponseValidator
from json_types import JSONObject, JSONValue


class ChoiceValidator(ResponseValidator):
    """One of a fixed set of strings; surrounding spaces are ignored."""

    def __init__(self, field: str, choices: tuple[str, ...],
                 description: str = "") -> None:
        super().__init__(field)
        self.__choices: tuple[str, ...] = choices
        self.__description: str = description

    def validate(self, value: object) -> tuple[bool, JSONValue]:
        problem = f"{self.field} must be {self.__quoted_choices()}."
        if not isinstance(value, str):
            return False, problem
        choice = self._normalise(value.strip())
        if choice is None:
            return False, problem
        return True, choice

    def schema(self) -> JSONObject:
        entry: JSONObject = {"type": "STRING", "enum": list(self.__choices)}
        if self.__description:
            entry["description"] = self.__description
        return entry

    def _normalise(self, text: str) -> str | None:
        """The accepted choice for text, or None. Subclasses may widen it."""
        return text if text in self.__choices else None

    def __quoted_choices(self) -> str:
        quoted = [f'"{choice}"' for choice in self.__choices]
        if len(quoted) == 1:
            return quoted[0]
        return ", ".join(quoted[:-1]) + f", or {quoted[-1]}"

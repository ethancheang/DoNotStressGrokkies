"""A finite number inside a fixed range."""

from __future__ import annotations

import math

from ai.validators.response_validator import ResponseValidator
from json_types import JSONObject, JSONValue


class RangeValidator(ResponseValidator):
    """A finite number from minimum to maximum. Booleans are rejected."""

    def __init__(self, field: str, minimum: float, maximum: float,
                 description: str = "") -> None:
        super().__init__(field)
        self.__minimum: float = minimum
        self.__maximum: float = maximum
        self.__description: str = description

    def validate(self, value: object) -> tuple[bool, JSONValue]:
        problem = (f"{self.field} must be a float between "
                   f"{self.__minimum:.1f} and {self.__maximum:.1f}.")
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return False, problem
        try:
            number = float(value)
        except (ValueError, OverflowError):
            return False, problem
        if (not math.isfinite(number)
                or not self.__minimum <= number <= self.__maximum):
            return False, problem
        return True, number

    def schema(self) -> JSONObject:
        entry: JSONObject = {
            "type": "NUMBER",
            "minimum": self.__minimum,
            "maximum": self.__maximum,
        }
        if self.__description:
            entry["description"] = self.__description
        return entry

"""The contract for checking one field of Gemini's JSON reply."""

from __future__ import annotations

from abc import ABC, abstractmethod

from json_types import JSONObject, JSONValue


class ResponseValidator(ABC):
    """Checks and normalises one field, and describes it for Gemini.

    AIManager runs a list of these in order, so a new reply field needs a
    new validator, not a change to the validation loop.
    """

    def __init__(self, field: str) -> None:
        self.__field: str = field

    @property
    def field(self) -> str:
        return self.__field

    @abstractmethod
    def validate(self, value: object) -> tuple[bool, JSONValue]:
        """(True, normalised value) or (False, message). Never raises."""

    @abstractmethod
    def schema(self) -> JSONObject:
        """This field's entry in Gemini's structured-output schema."""

"""Validator for reasoning."""

from __future__ import annotations

from ai.validators.response_validator import ResponseValidator
from json_types import JSONObject, JSONValue


class ReasoningValidator(ResponseValidator):
    """reasoning: warm, non-empty text written to the student."""

    def __init__(self) -> None:
        super().__init__("reasoning")

    def validate(self, value: object) -> tuple[bool, JSONValue]:
        if not isinstance(value, str) or not value.strip():
            return False, "reasoning must be a non-empty string."
        return True, value.strip()

    def schema(self) -> JSONObject:
        return {
            "type": "STRING",
            "description": (
                "Two or three warm, plain sentences to the student. "
                "No numbers, jargon, diagnosis, or contacts."),
        }

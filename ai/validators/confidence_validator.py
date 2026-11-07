"""Validator for confidence."""

from __future__ import annotations

from ai.validators.range_validator import RangeValidator


class ConfidenceValidator(RangeValidator):
    """confidence: Gemini's own certainty, from 0.0 to 1.0."""

    def __init__(self) -> None:
        super().__init__("confidence", 0.0, 1.0)

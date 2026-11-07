"""Validator for stress_score."""

from __future__ import annotations

from ai.validators.range_validator import RangeValidator


class ScoreValidator(RangeValidator):
    """stress_score: a number on the 1.0–5.0 scale.

    This is a schema range only. The tier cut-offs belong to Logic.
    """

    MINIMUM: float = 1.0
    MAXIMUM: float = 5.0

    def __init__(self) -> None:
        super().__init__(
            "stress_score", self.MINIMUM, self.MAXIMUM,
            "Mean of the converted values, rounded to 2 decimal places.")

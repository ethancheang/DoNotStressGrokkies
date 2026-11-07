"""Validator for primary_stressors."""

from __future__ import annotations

from ai.validators.id_list_validator import IdListValidator


class StressorsValidator(IdListValidator):
    """primary_stressors: any number of allow-listed stressor IDs.

    emotional_distress is deliberately absent: it would need the
    reflection, and that text is never sent to Gemini.
    """

    ALLOWED: frozenset[str] = frozenset({
        "sleep_deprivation",
        "high_stress",
        "academic_overload",
        "financial_pressure",
        "low_social_support",
    })

    def __init__(self) -> None:
        super().__init__("primary_stressors", self.ALLOWED)

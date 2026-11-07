"""Validator for soft_label."""

from __future__ import annotations

from ai.validators.choice_validator import ChoiceValidator


class SoftLabelValidator(ChoiceValidator):
    """soft_label, also accepting a curly apostrophe in "You’re doing ok"."""

    LABELS: tuple[str, ...] = (
        "You're doing ok",
        "Worth a check-in",
        "Please reach out",
    )
    ALIASES: dict[str, str] = {"You’re doing ok": "You're doing ok"}

    def __init__(self) -> None:
        super().__init__("soft_label", self.LABELS,
                         "Must match risk_category.")

    def _normalise(self, text: str) -> str | None:
        return super()._normalise(self.ALIASES.get(text, text))

"""Rule: the reflection safety check forces "Please reach out"."""

from __future__ import annotations

from logic.business_rule import BusinessRule
from logic.decision import Decision


class SafetyOverrideRule(BusinessRule):
    """If the safety check fired, show High / "Please reach out".

    "Talk to someone" leads the tips. The stress score is never changed,
    and the reflection text itself is never seen here.
    """

    TALK_TO_SOMEONE: str = "talk_to_someone"

    @property
    def name(self) -> str:
        return "safety_override"

    def applies(self, decision: Decision) -> bool:
        return decision.field("safety_flag") is True

    def apply(self, decision: Decision) -> None:
        decision.risk_category = "High"
        decision.soft_label = "Please reach out"
        decision.speak_prominence = "high"
        decision.lead_with(self.TALK_TO_SOMEONE)
        decision.note("safety_override: reflection safety check fired")

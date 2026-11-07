"""Rule: high stress with low social support puts talking first."""

from __future__ import annotations

from logic.business_rule import BusinessRule
from logic.decision import Decision


class SupportPriorityRule(BusinessRule):
    """A multi-condition rule on two fields of Gemini's reply.

    Fires when Gemini rated the check-in High (risk_category) AND named
    low social support as a stressor (primary_stressors). "Talk to
    someone" then leads and "keep in touch" is added if there is room.
    """

    CATEGORY: str = "High"
    STRESSOR: str = "low_social_support"
    TALK_TO_SOMEONE: str = "talk_to_someone"
    KEEP_SOCIAL_CONTACT: str = "keep_social_contact"

    @property
    def name(self) -> str:
        return "support_priority"

    def applies(self, decision: Decision) -> bool:
        stressors = decision.field("primary_stressors")
        return (decision.field("risk_category") == self.CATEGORY
                and isinstance(stressors, list)
                and self.STRESSOR in stressors)

    def apply(self, decision: Decision) -> None:
        decision.support_priority = True
        decision.lead_with(self.TALK_TO_SOMEONE)
        decision.suggest(self.KEEP_SOCIAL_CONTACT)
        decision.note("support_priority: High tier with low social support")

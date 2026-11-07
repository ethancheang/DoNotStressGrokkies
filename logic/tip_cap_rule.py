"""Rule: merge the tips in order and cap them at four."""

from __future__ import annotations

from logic.business_rule import BusinessRule
from logic.decision import Decision


class TipCapRule(BusinessRule):
    """Lead tip first, then all of Gemini's tips, then extras while room.

    Gemini gives at most three tips and at most one tip leads, so Gemini's
    own tips are never pushed out by the cap.
    """

    MAX_TIPS: int = 4

    @property
    def name(self) -> str:
        return "tip_cap"

    def applies(self, decision: Decision) -> bool:
        return True

    def apply(self, decision: Decision) -> None:
        ordered: list[str] = []
        for tip_id in decision.lead_tips + decision.gemini_tips:
            if tip_id not in ordered:
                ordered.append(tip_id)
        for tip_id in decision.extra_tips:
            if len(ordered) >= self.MAX_TIPS:
                break
            if tip_id not in ordered:
                ordered.append(tip_id)
        decision.tips = ordered[:self.MAX_TIPS]

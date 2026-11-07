"""Rule: each raised context flag suggests its matching tip."""

from __future__ import annotations

from logic.business_rule import BusinessRule
from logic.decision import Decision


class ContextFlagRule(BusinessRule):
    """Sleep, workload, money and support flags each suggest one tip.

    Flags only add tips after Gemini's own, never replace them, and never
    change the tier.
    """

    FLAG_TIPS: tuple[tuple[str, str], ...] = (
        ("sleep", "sleep_routine"),
        ("workload", "workload_chunks"),
        ("finances", "money_worries"),
        ("support", "talk_to_someone"),
    )

    @property
    def name(self) -> str:
        return "context_flags"

    def applies(self, decision: Decision) -> bool:
        return any(decision.context_flags.values())

    def apply(self, decision: Decision) -> None:
        flags = decision.context_flags
        for flag, tip_id in self.FLAG_TIPS:
            if flags.get(flag):
                decision.suggest(tip_id)

"""The contract every Logic business rule follows."""

from __future__ import annotations

from abc import ABC, abstractmethod

from logic.decision import Decision


class BusinessRule(ABC):
    """One domain rule applied to Gemini's analysis.

    LogicManager runs its rules in order on one Decision, so a new rule
    is a new subclass rather than a change to LogicManager.evaluate().
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short rule name for health checks and staff notes."""

    @abstractmethod
    def applies(self, decision: Decision) -> bool:
        """True when this rule should change the decision."""

    @abstractmethod
    def apply(self, decision: Decision) -> None:
        """Change the decision. Only called when applies() is True."""

    def run(self, decision: Decision) -> bool:
        """Apply the rule if it applies. Returns True when it fired."""
        if not self.applies(decision):
            return False
        self.apply(decision)
        return True

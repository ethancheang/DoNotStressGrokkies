"""What the AI layer needs from the scoring rules, as an interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from json_types import JSONObject


class ScoreAuditor(ABC):
    """Interface for the owner of the scoring formula.

    AIManager puts instructions() into the prompt and runs verify() on
    every reply. The Logic layer's StressScorer implements it, so the AI
    layer holds no scoring rules of its own.
    """

    @abstractmethod
    def instructions(self) -> str:
        """The scoring formula and tier rules, written for the prompt."""

    @abstractmethod
    def verify(self, ai_fields: JSONObject,
               answers: JSONObject) -> str | None:
        """A problem with the reply's arithmetic or tier, or None."""

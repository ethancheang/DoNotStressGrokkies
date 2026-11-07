"""The deterministic score of one check-in's answers."""

from __future__ import annotations


class ScoreCard:
    """Logic's own reading of the 11 answers, used to audit Gemini."""

    def __init__(self, stress_score: float, scored_items: dict[str, int],
                 support_mean: float, risk_category: str,
                 context_flags: dict[str, bool]) -> None:
        self.__stress_score: float = stress_score
        self.__scored_items: dict[str, int] = dict(scored_items)
        self.__support_mean: float = support_mean
        self.__risk_category: str = risk_category
        self.__context_flags: dict[str, bool] = dict(context_flags)

    @property
    def stress_score(self) -> float:
        """Mean of the converted answers, 1.0 to 5.0, 2 decimal places."""
        return self.__stress_score

    @property
    def scored_items(self) -> dict[str, int]:
        return dict(self.__scored_items)

    @property
    def item_count(self) -> int:
        return len(self.__scored_items)

    @property
    def support_mean(self) -> float:
        """Mean raw agreement of the friends and family answers."""
        return self.__support_mean

    @property
    def risk_category(self) -> str:
        return self.__risk_category

    @property
    def context_flags(self) -> dict[str, bool]:
        return dict(self.__context_flags)

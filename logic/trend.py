"""How a student's stress scores are moving."""

from __future__ import annotations


class Trend:
    """The latest score against the previous one, and the recent direction.

    comparison: NONE (no scores), FIRST (one score), or LOWER, SIMILAR or
    HIGHER than the previous score. direction: NOT_ENOUGH (under three
    scores), or EASING, STEADY or BUILDING across recent check-ins. Lower
    stress is better.
    """

    NONE: str = "none"
    FIRST: str = "first"
    LOWER: str = "lower"
    SIMILAR: str = "similar"
    HIGHER: str = "higher"
    NOT_ENOUGH: str = "not_enough"
    EASING: str = "easing"
    STEADY: str = "steady"
    BUILDING: str = "building"

    def __init__(self, comparison: str, direction: str,
                 latest: float | None = None,
                 previous: float | None = None,
                 average: float | None = None) -> None:
        self.__comparison: str = comparison
        self.__direction: str = direction
        self.__latest: float | None = latest
        self.__previous: float | None = previous
        self.__average: float | None = average

    @property
    def comparison(self) -> str:
        return self.__comparison

    @property
    def direction(self) -> str:
        return self.__direction

    @property
    def latest(self) -> float | None:
        return self.__latest

    @property
    def previous(self) -> float | None:
        return self.__previous

    @property
    def average(self) -> float | None:
        return self.__average

    @property
    def change(self) -> float | None:
        """latest - previous, 2 decimal places; negative means less stress."""
        if self.__latest is None or self.__previous is None:
            return None
        return round(self.__latest - self.__previous, 2)

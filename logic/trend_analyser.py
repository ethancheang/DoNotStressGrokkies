"""Reads a simple trend from a student's stress history."""

from __future__ import annotations

from logic.trend import Trend
from records.stress_history import StressHistory


class TrendAnalyser:
    """Compares the latest score with the last one and finds a direction.

    Scores within similar_within of each other count as about the same.
    The direction is the least-squares slope over the last `window`
    scores: below -slope_threshold per check-in is easing, above it is
    building, anything in between is steady. A guide, not a diagnosis.
    """

    SIMILAR_WITHIN: float = 0.25
    WINDOW: int = 5
    SLOPE_THRESHOLD: float = 0.1
    MIN_FOR_DIRECTION: int = 3

    def analyse(self, history: StressHistory) -> Trend:
        scores = history.scores
        if not scores:
            return Trend(Trend.NONE, Trend.NOT_ENOUGH)
        average = round(sum(scores) / len(scores), 2)
        if len(scores) == 1:
            return Trend(Trend.FIRST, Trend.NOT_ENOUGH, scores[0],
                         average=average)
        latest, previous = scores[-1], scores[-2]
        return Trend(self.__compare(latest, previous),
                     self.__direction(scores), latest, previous, average)

    def __compare(self, latest: float, previous: float) -> str:
        change = latest - previous
        if abs(change) <= self.SIMILAR_WITHIN:
            return Trend.SIMILAR
        return Trend.LOWER if change < 0 else Trend.HIGHER

    def __direction(self, scores: list[float]) -> str:
        if len(scores) < self.MIN_FOR_DIRECTION:
            return Trend.NOT_ENOUGH
        recent = scores[-self.WINDOW:]
        slope = self.__slope(recent)
        if slope < -self.SLOPE_THRESHOLD:
            return Trend.EASING
        if slope > self.SLOPE_THRESHOLD:
            return Trend.BUILDING
        return Trend.STEADY

    def __slope(self, values: list[float]) -> float:
        """Least-squares change per check-in."""
        count = len(values)
        mean_x = (count - 1) / 2
        mean_y = sum(values) / count
        spread = sum((index - mean_x) ** 2 for index in range(count))
        return sum((index - mean_x) * (value - mean_y)
                   for index, value in enumerate(values)) / spread

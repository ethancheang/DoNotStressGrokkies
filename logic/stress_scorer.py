"""The scoring formula: the only place that knows how answers are scored."""

from __future__ import annotations

import math

from ai.score_auditor import ScoreAuditor
from json_types import JSONObject, JSONValue
from logic.score_card import ScoreCard


class StressScorer(ScoreAuditor):
    """Scores the 11 answers and audits Gemini's arithmetic.

    Score: the mean of the 11 answers on the 1–5 stress scale, equal
    weight. Positively worded items are scored as 6 - answer. Sleep hours
    convert as 8+ h -> 1, 7 to <8 -> 2, 6 to <7 -> 3, 5 to <6 -> 4, under
    5 -> 5. Tiers: Low below 2.5, Moderate 2.5 to 3.5 inclusive, High
    above 3.5. These bands are team heuristics, not clinical cut-offs.
    """

    SCALE_MIN: int = 1
    SCALE_MAX: int = 5
    ANSWER_KEYS: tuple[str, ...] = (
        "pss_1", "pss_2", "pss_3", "pss_4", "sleep_hours_avg",
        "sleep_quality", "pas_workload", "pas_catchup", "fin_stress",
        "mspss_friends", "mspss_family",
    )
    REVERSED_KEYS: tuple[str, ...] = (
        "pss_2", "pss_3", "mspss_friends", "mspss_family")
    SUPPORT_KEYS: tuple[str, ...] = ("mspss_friends", "mspss_family")
    SLEEP_KEY: str = "sleep_hours_avg"
    SLEEP_HOURS_MIN: int = 0
    SLEEP_HOURS_MAX: int = 14
    SLEEP_HOUR_BANDS: tuple[tuple[int, int], ...] = (
        (8, 1), (7, 2), (6, 3), (5, 4))
    SLEEP_HOURS_BELOW_ALL: int = 5
    CHECK_IN_FROM: float = 2.5
    REACH_OUT_ABOVE: float = 3.5
    TOLERANCE: float = 0.01
    CATEGORY_LABELS: dict[str, str] = {
        "Low": "You're doing ok",
        "Moderate": "Worth a check-in",
        "High": "Please reach out",
    }
    CATEGORY_PROMINENCE: dict[str, str] = {
        "Low": "low", "Moderate": "medium", "High": "high"}

    # Context flags on the raw answers. They steer tips, never the tier.
    FLAG_SLEEP: str = "sleep"
    FLAG_WORKLOAD: str = "workload"
    FLAG_FINANCES: str = "finances"
    FLAG_SUPPORT: str = "support"
    SLEEP_FLAG_BELOW_HOURS: float = 6
    SLEEP_QUALITY_FLAG_MIN: float = 4
    WORKLOAD_FLAG_MIN: float = 4
    FINANCE_FLAG_MIN: float = 4
    SUPPORT_FLAG_BELOW: float = 2.5

    def score(self, answers: JSONObject) -> ScoreCard:
        """Score usable answers. Check them with answer_in_range first."""
        items = self.scored_items(answers)
        stress = round(sum(items.values()) / len(items), 2)
        support = [self.__answer(answers, key) for key in self.SUPPORT_KEYS]
        support_mean = round(sum(support) / len(support), 2)
        return ScoreCard(stress, items, support_mean,
                         self.category_for(stress),
                         self.context_flags(answers, support_mean))

    def scored_items(self, answers: JSONObject) -> dict[str, int]:
        """The answers on the 1–5 stress scale: what Gemini must return."""
        return {key: int(self.scored_value(key, self.__answer(answers, key)))
                for key in self.ANSWER_KEYS}

    def scored_value(self, key: str, answer: float) -> float:
        """Sleep hours converted; positively worded items as 6 - answer."""
        if key == self.SLEEP_KEY:
            return self.sleep_hours_stress(answer)
        if key in self.REVERSED_KEYS:
            return (self.SCALE_MIN + self.SCALE_MAX) - answer
        return answer

    def sleep_hours_stress(self, hours: float) -> int:
        for at_least, value in self.SLEEP_HOUR_BANDS:
            if hours >= at_least:
                return value
        return self.SLEEP_HOURS_BELOW_ALL

    def category_for(self, stress_score: float) -> str:
        if stress_score > self.REACH_OUT_ABOVE:
            return "High"
        if stress_score >= self.CHECK_IN_FROM:
            return "Moderate"
        return "Low"

    def label_for(self, category: str) -> str:
        return self.CATEGORY_LABELS[category]

    def prominence_for(self, category: str) -> str:
        return self.CATEGORY_PROMINENCE[category]

    def risk_score_for(self, stress_score: float) -> float:
        """The 1–5 score mapped onto 0–1. Kept for compatibility."""
        return ((stress_score - self.SCALE_MIN)
                / (self.SCALE_MAX - self.SCALE_MIN))

    def within_tolerance(self, gemini_score: float,
                         logic_score: float) -> bool:
        """True when Gemini is at most 0.01 away from Logic.

        The tiny extra allowance absorbs float error, so exactly 0.01 off
        (for example 4.63 against 4.64) is accepted.
        """
        return abs(gemini_score - logic_score) <= self.TOLERANCE + 1e-9

    def context_flags(self, answers: JSONObject,
                      support_mean: float) -> dict[str, bool]:
        sleep_short = (self.__answer(answers, self.SLEEP_KEY)
                       < self.SLEEP_FLAG_BELOW_HOURS)
        sleep_poor = (self.__answer(answers, "sleep_quality")
                      >= self.SLEEP_QUALITY_FLAG_MIN)
        return {
            self.FLAG_SLEEP: sleep_short or sleep_poor,
            self.FLAG_WORKLOAD: (self.__answer(answers, "pas_workload")
                                 >= self.WORKLOAD_FLAG_MIN),
            self.FLAG_FINANCES: (self.__answer(answers, "fin_stress")
                                 >= self.FINANCE_FLAG_MIN),
            self.FLAG_SUPPORT: support_mean < self.SUPPORT_FLAG_BELOW,
        }

    def answer_in_range(self, key: str, value: JSONValue) -> bool:
        """A number Logic can score: sleep hours 0–14, anything else 1–5."""
        number = self.number(value)
        if number is None:
            return False
        if key == self.SLEEP_KEY:
            return self.SLEEP_HOURS_MIN <= number <= self.SLEEP_HOURS_MAX
        return self.SCALE_MIN <= number <= self.SCALE_MAX

    def number(self, value: JSONValue) -> float | None:
        """value as a finite float, or None for text, bools, NaN or inf."""
        if isinstance(value, bool) or not isinstance(
                value, (int, float, str)):
            return None
        try:
            number = float(value)
        except (ValueError, OverflowError):
            return None
        return number if math.isfinite(number) else None

    def instructions(self) -> str:
        """The formula and tiers, written as instructions for Gemini."""
        reversed_keys = ", ".join(self.REVERSED_KEYS)
        sleep_bands = ", ".join(
            f"{hours:g} or more{' hours' if index == 0 else ''} -> {value}"
            for index, (hours, value) in enumerate(self.SLEEP_HOUR_BANDS))
        low, middle, high = self.CATEGORY_LABELS.values()
        scale = f"{self.SCALE_MIN} to {self.SCALE_MAX}"
        return (
            f"Convert each answer onto the {scale} stress scale:\n"
            f"- {reversed_keys} are positively worded. Convert each as "
            f"{self.SCALE_MIN + self.SCALE_MAX} - answer.\n"
            f"- sleep_hours_avg is hours from {self.SLEEP_HOURS_MIN} to "
            f"{self.SLEEP_HOURS_MAX} in half-hour steps. Convert it as: "
            f"{sleep_bands}, otherwise {self.SLEEP_HOURS_BELOW_ALL}.\n"
            f"- Every other answer is already on the {scale} scale. Use "
            "the number as answered.\n"
            f"stress_score is the mean of those {len(self.ANSWER_KEYS)} "
            "converted values, rounded to 2 decimal places. Higher stress "
            "is worse.\n"
            "Then set the tier from that stress_score:\n"
            f"- below {self.CHECK_IN_FROM:g}: risk_category Low, soft_label "
            f'"{low}", speak_prominence low\n'
            f"- {self.CHECK_IN_FROM:g} to {self.REACH_OUT_ABOVE:g} "
            f'inclusive: risk_category Moderate, soft_label "{middle}", '
            "speak_prominence medium\n"
            f"- above {self.REACH_OUT_ABOVE:g}: risk_category High, "
            f'soft_label "{high}", speak_prominence high\n'
            "These bands are a simple guide for this check-in, not clinical "
            "cut-offs.\n"
        )

    def verify(self, ai_fields: JSONObject,
               answers: JSONObject) -> str | None:
        """Check Gemini's tier, converted items and mean. Never raises.

        In order: the tier fields match the tier of Gemini's own score;
        scored_items equal the converted answers exactly; stress_score is
        within 0.01 of their mean. Returns a problem or None.
        """
        if not isinstance(ai_fields, dict) or not isinstance(answers, dict):
            return "verify needs the AI fields and the answers as dicts."
        unusable = [key for key in self.ANSWER_KEYS
                    if not self.__scorable(key, answers.get(key))]
        if unusable:
            return (f"Cannot convert {', '.join(unusable)} onto the 1-5 "
                    "stress scale.")
        gemini_score = self.number(ai_fields.get("stress_score"))
        if gemini_score is None:
            return "stress_score must be a number."
        expected = self.category_for(gemini_score)
        if ai_fields.get("risk_category") != expected:
            return (f"risk_category must be {expected} for stress_score "
                    f"{gemini_score}.")
        if ai_fields.get("soft_label") != self.label_for(expected):
            return "soft_label must match risk_category."
        if ai_fields.get("speak_prominence") != self.prominence_for(expected):
            return "speak_prominence must match risk_category."
        if ai_fields.get("scored_items") != self.scored_items(answers):
            return "scored_items does not match the converted answers."
        logic_score = self.score(answers).stress_score
        if not self.within_tolerance(gemini_score, logic_score):
            return ("stress_score must match the mean of the 11 converted "
                    f"answers (expected {logic_score}).")
        return None

    def __scorable(self, key: str, value: JSONValue) -> bool:
        """In range and, except for sleep hours, a whole number."""
        number = self.number(value)
        if number is None or not self.answer_in_range(key, value):
            return False
        return key == self.SLEEP_KEY or number.is_integer()

    def __answer(self, answers: JSONObject, key: str) -> float:
        number = self.number(answers.get(key))
        if number is None:
            raise ValueError(f"{key} is not a usable answer.")
        return number

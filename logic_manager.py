"""DoNotStress — Logic Layer (logic_manager).

LogicManager checks Gemini's analysis against the answers and applies the
team's business rules. Gemini's result is the result: Logic recomputes the
score as an audit and never substitutes its own number.

Rules (logic_rule "v3")
-----------------------
1. Cross-check — Gemini's stress_score must be within 0.01 of Logic's.
   Otherwise evaluate() returns a "score_mismatch" error and the caller
   treats the check-in as an AI failure (saved as pending, no result).
2. SafetyOverrideRule — the reflection safety check forces High /
   "Please reach out" and puts "talk to someone" first.
3. SupportPriorityRule — High tier AND low_social_support (two Gemini
   fields) puts "talk to someone" first and adds "keep in touch".
4. ContextFlagRule — sleep, workload, money and support flags each add
   their tip after Gemini's, never replacing them.
5. TipCapRule — merges the tips and caps them at four.

No terminal I/O, no Gemini calls, no file I/O, no student-facing copy.

Pipeline position:
  User → io_manager → ai_manager (must succeed) → logic_manager →
  data_manager
"""

from __future__ import annotations

from base_manager import BaseManager
from json_types import JSONObject, JSONValue
from logic.business_rule import BusinessRule
from logic.context_flag_rule import ContextFlagRule
from logic.decision import Decision
from logic.safety_override_rule import SafetyOverrideRule
from logic.stress_scorer import StressScorer
from logic.support_priority_rule import SupportPriorityRule
from logic.tip_cap_rule import TipCapRule
from logic.trend import Trend
from logic.trend_analyser import TrendAnalyser
from records.stress_history import StressHistory


class LogicManager(BaseManager):
    """Audits Gemini's score, runs the business rules, reads trends.

    The scorer, the rules and the trend analyser are created here and
    belong to this manager (composition). The scorer is also lent to
    AIManager as its ScoreAuditor, which uses it without owning it.
    """

    SOURCE: str = "ai_logic"
    RULE_VERSION: str = "v3"
    ERROR_AI_FIELDS_REQUIRED: str = "ai_fields_required"
    ERROR_SCORE_MISMATCH: str = "score_mismatch"
    REQUIRED_AI_FIELDS: tuple[str, ...] = (
        "stress_score", "risk_category", "soft_label", "speak_prominence",
        "primary_stressors", "tips", "reasoning", "confidence",
    )
    # Stored with each record for staff; the student sees tips instead.
    RECOMMENDED_SUPPORT: dict[str, str] = {
        "Low": "Internal: low stress. The UI shows tips, not this field.",
        "Moderate": ("Internal: moderate stress. The UI shows tips, not "
                     "this field."),
        "High": "Internal: high stress. The UI shows tips, not this field.",
    }

    def __init__(self) -> None:
        super().__init__("logic_manager")
        self.__scorer: StressScorer = StressScorer()
        self.__rules: list[BusinessRule] = [
            SafetyOverrideRule(),
            SupportPriorityRule(),
            ContextFlagRule(),
            TipCapRule(),
        ]
        self.__trends: TrendAnalyser = TrendAnalyser()

    @property
    def scorer(self) -> StressScorer:
        return self.__scorer

    @property
    def rule_names(self) -> list[str]:
        return [rule.name for rule in self.__rules]

    def describe(self) -> JSONObject:
        return {"rule_version": self.RULE_VERSION,
                "rules": list(self.rule_names)}

    def evaluate(self, record: JSONObject) -> JSONObject:
        """Validate Gemini's analysis and apply every business rule.

        The record must hold the 11 raw answers and Gemini's fields. On
        success the copy gains ok=True, source="ai_logic", the final tier
        and tips, logic_stress_score (audit only), logic_clamp_notes,
        support_priority, context_flags, support_mean, risk_score and
        recommended_support. On a problem it is an error dict with
        ok=False. feelings_text is always removed; the input is not
        changed.
        """
        if not isinstance(record, dict):
            return self.__error_result(
                {}, list(self.REQUIRED_AI_FIELDS + StressScorer.ANSWER_KEYS),
                ["record"])
        missing, invalid = self.__field_problems(record)
        if missing or invalid:
            return self.__error_result(record, missing, invalid)

        card = self.__scorer.score(record)
        gemini_score = self.__scorer.number(record["stress_score"])
        if gemini_score is None:
            return self.__error_result(record, [], ["stress_score"])
        if not self.__scorer.within_tolerance(gemini_score,
                                              card.stress_score):
            return self.__mismatch_result(record, gemini_score,
                                          card.stress_score)

        decision = Decision(record, card.context_flags)
        for rule in self.__rules:
            rule.run(decision)

        result = self.__without_reflection(record)
        result.update({
            "ok": True,
            "error": None,
            "source": self.SOURCE,
            "ai_ok": True,
            "logic_rule": self.RULE_VERSION,
            "logic_stress_score": card.stress_score,
            "risk_score": self.__scorer.risk_score_for(gemini_score),
            "recommended_support": self.RECOMMENDED_SUPPORT[
                decision.risk_category],
            "risk_category": decision.risk_category,
            "soft_label": decision.soft_label,
            "speak_prominence": decision.speak_prominence,
            "tips": list(decision.tips),
            "logic_clamp_notes": list(decision.notes),
            "support_priority": decision.support_priority,
            "context_flags": dict(card.context_flags),
            "support_mean": card.support_mean,
        })
        return result

    def trend(self, history: StressHistory) -> Trend:
        """How a student's scores are moving across their check-ins."""
        return self.__trends.analyse(history)

    def score(self, record: JSONObject) -> float | None:
        """Gemini's verified stress_score, or None if Logic rejects it."""
        result = self.evaluate(record)
        if not result.get("ok"):
            return None
        return self.__scorer.number(result["stress_score"])

    def route(self, decision: JSONObject) -> str:
        """"Low", "Moderate", "High", or "unavailable".

        Pass the dict evaluate() returned. The tier is only trusted when
        its soft label agrees with it.
        """
        if not isinstance(decision, dict) or not decision.get("ok"):
            return "unavailable"
        category = str(decision.get("risk_category"))
        label = StressScorer.CATEGORY_LABELS.get(category)
        if label is not None and decision.get("soft_label") == label:
            return category
        return "unavailable"

    def __field_problems(self, record: JSONObject
                         ) -> tuple[list[str], list[str]]:
        """(missing keys, unusable keys). Gemini's schema is AI's job."""
        needed = self.REQUIRED_AI_FIELDS + StressScorer.ANSWER_KEYS
        missing = [key for key in needed if key not in record]
        numbers = ("stress_score",) + StressScorer.ANSWER_KEYS
        invalid = [key for key in numbers if key in record and
                   not self.__scorer.answer_in_range(key, record[key])]
        invalid += [key for key in ("tips", "primary_stressors")
                    if key in record and not isinstance(record[key], list)]
        return missing, invalid

    def __error_result(self, record: JSONObject, missing: list[str],
                       invalid: list[str]) -> JSONObject:
        """Pass the fields through with no invented outcome."""
        result = self.__without_reflection(record)
        missing_keys: list[JSONValue] = list(missing)
        invalid_keys: list[JSONValue] = list(invalid)
        result.update({
            "ok": False,
            "error": self.ERROR_AI_FIELDS_REQUIRED,
            "missing": missing_keys,
            "invalid": invalid_keys,
            "message": ("Logic requires a successful Gemini (AI-enriched) "
                        "record and all 11 answers; it does not guess "
                        "outcomes without them."),
        })
        return result

    def __mismatch_result(self, record: JSONObject, gemini_score: float,
                          logic_score: float) -> JSONObject:
        """Gemini's score disagrees with the answers: no outcome at all."""
        result = self.__without_reflection(record)
        result.update({
            "ok": False,
            "error": self.ERROR_SCORE_MISMATCH,
            "logic_stress_score": logic_score,
            "message": (f"Gemini stress_score {gemini_score:g} does not "
                        f"match the answers ({logic_score:g}); no result "
                        "is given."),
        })
        return result

    def __without_reflection(self, record: JSONObject) -> JSONObject:
        return {key: value for key, value in record.items()
                if key != "feelings_text"}

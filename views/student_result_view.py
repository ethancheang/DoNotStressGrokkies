"""The student's result page."""

from __future__ import annotations

from json_types import JSONObject, JSONValue
from questions.questionnaire import Questionnaire
from records.record import Record
from views.student_copy import StudentCopy
from views.view import View


class StudentResultView(View):
    """Soft label, factor cards, tips and support for one check-in.

    Only allow-listed wording is sent to the browser. The raw answers and
    internal notes stay on the server.
    """

    FACTOR_COPY: tuple[tuple[str, str, str], ...] = (
        ("sleep", "Rest & recovery",
         "Sleep and stress affect each other. When sleep is short or "
         "restless, everyday tasks can feel harder, and stress can make it "
         "harder to sleep well."),
        ("workload", "Study demands",
         "A heavy workload can leave less time to rest and recharge. "
         "Feeling behind or overloaded is one of the most common sources "
         "of student stress."),
        ("finances", "Money pressures",
         "Financial worries can add to the pressure of studying. Concerns "
         "about money often weigh on focus and sleep."),
        ("support", "Support & connection",
         "Having people to turn to can make stressful times easier to "
         "handle. Strong support from friends or family helps protect "
         "against stress."),
    )
    FACTOR_FIELDS: tuple[str, ...] = (
        "sleep_hours_avg", "sleep_quality", "pas_workload", "fin_stress",
        "support_mean")

    def __init__(self, copy: StudentCopy,
                 questionnaire: Questionnaire) -> None:
        super().__init__()
        self.__copy: StudentCopy = copy
        self.__questionnaire: Questionnaire = questionnaire

    def render(self, record: Record) -> JSONObject:
        advisor = self.__copy.advisor_panel(
            str(record.get("speak_prominence") or ""))
        advisor.pop("cta", None)
        return {
            "soft": self.__copy.soft_label(str(record.get("soft_label")
                                               or "")),
            "tips": self.__copy.tips(self.__strings(record.get("tips"))),
            "advisor": advisor,
            "insights": {
                "risk_category": str(record.get("risk_category")
                                     or "Unknown"),
                "explanation": str(record.get("reasoning") or "").split(
                    " Logic adjusted:")[0],
                "stressors": self.__strings(record.get("primary_stressors")),
                "factors": self.__factor_cards(record),
                "safety_flag": record.get("safety_flag") is True,
            },
        }

    def __factor_cards(self, record: Record) -> list[JSONValue]:
        """Rest, study, money and support cards from Logic's flags."""
        found: dict[str, float] = {}
        for key in self.FACTOR_FIELDS:
            number = self.__number(record.get(key))
            if number is None:
                return []
            found[key] = number
        flags = record.get("context_flags")
        flagged = flags if isinstance(flags, dict) else {}
        workload, finances = found["pas_workload"], found["fin_stress"]
        shown = {
            "sleep": (f"{found['sleep_hours_avg']:g} hours · "
                      f"{self.__label(found, 'sleep_quality')} quality"),
            "workload": (f"{workload:g}/5 · "
                         f"{self.__label(found, 'pas_workload')}"),
            "finances": (f"{finances:g}/5 · "
                         f"{self.__label(found, 'fin_stress')}"),
            "support": (f"{found['support_mean']:g}/5 agreement across "
                        "2 answers"),
        }
        return [{"title": title, "flagged": flagged.get(flag) is True,
                 "value": shown[flag], "text": text}
                for flag, title, text in self.FACTOR_COPY]

    def __label(self, found: dict[str, float], key: str) -> str:
        """The word label for an answer, e.g. 5 -> "Very bad"."""
        question = self.__questionnaire.question(key)
        return question.option_label(int(found[key]))

    def __number(self, value: JSONValue) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)

    def __strings(self, value: JSONValue) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value]

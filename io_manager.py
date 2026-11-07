"""DoNotStress — I/O Layer (io_manager).

IOManager validates what students type into the web form and turns
records into the plain data each page shows. All wording and page shapes
live here and in the templates; no other layer writes student-facing
copy.

Student ID: seven ASCII digits beginning with 2. The reflection is checked
for crisis language and then discarded; only the safety flag remains.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from base_manager import BaseManager
from json_types import JSONObject
from logic.trend import Trend
from questions.questionnaire import Questionnaire
from records.record import Record
from records.stress_history import StressHistory
from views.admin_records_view import AdminRecordsView
from views.history_entry_view import HistoryEntryView
from views.student_copy import StudentCopy
from views.student_result_view import StudentResultView


class IOManager(BaseManager):
    """Collects and validates input; renders results, lists and errors.

    The questionnaire is passed in and shared (aggregation). The wording
    and the page views are created here and belong to this manager
    (composition).
    """

    STUDENT_ID_EXAMPLE: str = "2605581"
    REFLECTION_LIMIT: int = 2000

    def __init__(self, questionnaire: Questionnaire) -> None:
        super().__init__("io_manager")
        self.__questionnaire: Questionnaire = questionnaire
        self.__copy: StudentCopy = StudentCopy()
        self.__result_view: StudentResultView = StudentResultView(
            self.__copy, questionnaire)
        self.__admin_view: AdminRecordsView = AdminRecordsView()
        self.__history_view: HistoryEntryView = HistoryEntryView()

    @property
    def copy(self) -> StudentCopy:
        """The allow-listed student-facing wording."""
        return self.__copy

    def describe(self) -> JSONObject:
        return {"questionnaire": self.__questionnaire.version,
                "questions": len(self.__questionnaire.questions)}

    # --- Input -----------------------------------------------------------

    def validate_student_id(self, raw: object) -> tuple[bool, str]:
        """(True, the ID) or (False, a message). Seven digits from 2."""
        text = str(raw if raw is not None else "").strip()
        if (len(text) != 7 or not text.isascii() or not text.isdigit()
                or not text.startswith("2")):
            return False, ("Student ID must be exactly 7 digits and start "
                           f"with 2 (e.g. {self.STUDENT_ID_EXAMPLE}).")
        return True, text

    def validate_feelings_text(self, raw: object) -> tuple[bool, str]:
        """(True, the stripped reflection) or (False, a message)."""
        if raw is not None and not isinstance(raw, str):
            return False, "Please enter text or leave this blank."
        text = (raw or "").strip()
        if len(text) > self.REFLECTION_LIMIT:
            return False, ("Please keep your reflection within 2,000 "
                           "characters.")
        return True, text

    def validate_student_form(self, form: Mapping[str, object]
                              ) -> tuple[bool, JSONObject]:
        """(True, the check-in) or (False, a message for each bad field).

        The check-in never keeps the reflection, and never trusts a score,
        tier or flag sent by the browser.
        """
        record: JSONObject = {}
        errors: JSONObject = {}
        ok, student_id = self.validate_student_id(form.get("student_id"))
        (record if ok else errors)["student_id"] = student_id
        for question in self.__questionnaire.questions:
            ok, answer = question.validate(form.get(question.key))
            (record if ok else errors)[question.key] = answer
        ok, reflection = self.validate_feelings_text(
            form.get("feelings_text"))
        if not ok:
            errors["feelings_text"] = reflection
        if errors:
            return False, errors
        record["safety_flag"] = self.__questionnaire.safety.fired(reflection)
        record["survey_version"] = self.__questionnaire.version
        return True, record

    def validate_record_filters(self, tier: str,
                                cohort_year: str) -> str | None:
        """A message for an unknown admin filter, or None when both are ok."""
        if tier and tier not in self.__copy.SOFT_LABEL_COPY:
            return ("Choose a tier: You're doing ok, Worth a check-in, or "
                    "Please reach out.")
        if cohort_year and (len(cohort_year) not in (2, 4)
                            or not cohort_year.isascii()
                            or not cohort_year.isdigit()):
            return "Choose a valid cohort year."
        return None

    def safety_fired(self, text: object) -> bool:
        """The reflection safety check, for an immediate support prompt."""
        return self.__questionnaire.safety.fired(text)

    # --- Output ----------------------------------------------------------

    def display_record(self, record: Record) -> JSONObject:
        """The answers of one check-in as labelled values."""
        fields: list[JSONObject] = []
        if record.student_id:
            fields.append({"key": "student_id", "label": "Student ID",
                           "value": record.student_id})
        for question in self.__questionnaire.questions:
            value = record.get(question.key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            shown = f"{value:g}"
            if question.options:
                shown = f"{shown} · {question.option_label(int(value))}"
            elif question.step < 1:
                shown = f"{value:.1f}"
            fields.append({"key": question.key, "label": question.prompt,
                           "value": shown})
        return {"heading": "Your check-in", "fields": fields,
                "empty": not fields}

    def display_list(self, records: Sequence[Record]) -> list[JSONObject]:
        """Admin table rows, newest first."""
        newest = sorted(records, key=lambda record: record.saved_at,
                        reverse=True)
        return self.__admin_view.render_many(newest)

    def display_result(self, record: Record) -> JSONObject:
        """The student's result page for a finished check-in."""
        return self.__result_view.render(record)

    def display_history(self, history: StressHistory,
                        trend: Trend) -> JSONObject:
        """A student's own history page: scores, trend and support.

        Support is highlighted when stress is building or the latest
        check-in was High. Answers and reasoning are never included.
        """
        latest = history.latest
        high = latest is not None and latest.risk_category == "High"
        needs_support = high or trend.direction == Trend.BUILDING
        advisor = (self.__copy.advisor_panel("high" if high else "medium")
                   if needs_support else None)
        return {
            "student_id": history.student_id,
            "entries": self.__history_view.render_many(history.records),
            "pending": history.pending_count,
            "trend": self.__copy.trend_summary(trend),
            "advisor": advisor,
        }

    def display_error(self, code: str,
                      detail: str | None = None) -> JSONObject:
        """The page shown when the AI step could not finish."""
        return self.__copy.ai_error(code, detail)

    def advisor_panel(self, prominence: str) -> JSONObject:
        return self.__copy.advisor_panel(prominence)

    def page_config(self) -> JSONObject:
        """The questionnaire as the browser needs it."""
        return self.__questionnaire.public_config()

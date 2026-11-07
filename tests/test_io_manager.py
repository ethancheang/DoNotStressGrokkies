"""IOManager, its views and the student-facing wording."""
import json
import unittest

from base_manager import BaseManager
from io_manager import IOManager
from plain_tests import case, function_suite
from records.check_in_record import CheckInRecord
from records.pending_record import PendingRecord
from survey import QUESTIONNAIRE
from views.admin_records_view import AdminRecordsView
from views.student_copy import StudentCopy
from views.student_result_view import StudentResultView
from views.view import View

IO = IOManager(QUESTIONNAIRE)
COPY = StudentCopy()


def evaluated(**changes):
    row = {"student_id": "2605581", "stress_score": 3.0,
           "risk_category": "Moderate", "soft_label": "Worth a check-in",
           "speak_prominence": "medium", "tips": ["short_breaks"],
           "primary_stressors": ["academic_overload"],
           "reasoning": "Warm words.", "context_flags": {"sleep": True},
           "support_mean": 3.0, "pss_1": 3, "sleep_hours_avg": 5.5,
           "sleep_quality": 4, "pas_workload": 2, "fin_stress": 1,
           "saved_at": "2026-10-09T01:00:00+00:00", "safety_flag": False,
           "feelings_text": "PRIVATE"}
    row.update(changes)
    return row


def test_io_manager_is_a_manager():
    assert isinstance(IO, BaseManager)
    assert IO.health() == {"name": "io_manager",
                           "questionnaire": "evidence-v3", "questions": 11}


def test_every_view_renders_any_record_the_same_way():
    """Polymorphism: render_many never asks which view or record it has."""
    views = (StudentResultView(COPY, QUESTIONNAIRE), AdminRecordsView())
    records = [CheckInRecord(evaluated()), PendingRecord(evaluated())]
    for view in views:
        with case(view=type(view).__name__):
            assert isinstance(view, View)
            pages = view.render_many(records)
            assert len(pages) == 2
            assert "PRIVATE" not in json.dumps(pages)


def test_admin_rows_show_status_and_fill_a_missing_tier_label():
    view = AdminRecordsView()
    row = view.render(CheckInRecord(evaluated(reasoning="Secret note")))
    assert row["status"] == "Evaluated"
    assert set(row) == set(AdminRecordsView.COLUMNS) | {"status"}
    pending = view.render(PendingRecord({"risk_category": "Low"}))
    assert pending["status"] == "Pending"
    assert pending["soft_label"] == "You're doing ok"


def test_admin_list_is_newest_first():
    older = CheckInRecord(evaluated(student_id="2000001",
                                    saved_at="2026-01-01T00:00:00+00:00"))
    newer = CheckInRecord(evaluated(student_id="2000002"))
    rows = IO.display_list([older, newer])
    assert [row["student_id"] for row in rows] == ["2000002", "2000001"]


def test_result_page_holds_wording_not_raw_answers():
    page = IO.display_result(CheckInRecord(evaluated()))
    assert page["soft"]["heading"] == "Worth a check-in"
    assert page["tips"]["items"] == [
        {"id": "short_breaks", "text": StudentCopy.TIPS["short_breaks"]}]
    assert "cta" not in page["advisor"]
    assert page["advisor"]["helpline"] == "6592 2030"
    factors = {card["title"]: card for card in page["insights"]["factors"]}
    assert factors["Rest & recovery"]["value"] == (
        "5.5 hours · Fairly bad quality")
    assert factors["Rest & recovery"]["flagged"] is True
    assert factors["Study demands"]["value"] == "2/5 · Disagree"
    assert factors["Support & connection"]["value"] == (
        "3/5 agreement across 2 answers")
    assert "pss_1" not in json.dumps(page)
    assert IO.display_result(PendingRecord({}))["insights"]["factors"] == []


def test_wording_never_invents_tips_contacts_or_labels():
    assert COPY.tips(["made_up", " short_breaks", "short_breaks"])[
        "items"] == [{"id": "short_breaks",
                      "text": StudentCopy.TIPS["short_breaks"]}]
    unknown = COPY.advisor_panel("urgent")
    assert unknown["prominence"] == "medium" and unknown["error"]
    assert unknown["sos"] == "1767" and unknown["mindline"] == "1771"
    assert COPY.soft_label("Great")["error"].startswith("Unknown soft label")


def test_ai_error_copy_hides_secrets_and_handles_unknown_codes():
    page = COPY.ai_error("timeout", "slow network")
    assert page["error_code"] == "timeout" and page["error"] is None
    assert page["hint"].endswith("Detail: slow network.")
    assert page["speak_to_advisor"]["prominence"] == "high"
    secret = COPY.ai_error("timeout", "GEMINI_API_KEY=abc")
    assert secret["reason"] is None
    token = COPY.ai_error("timeout", "A" * 40)
    assert token["reason"] is None
    unknown = COPY.ai_error("exploded")
    assert unknown["error_code"] == "unavailable" and unknown["error"]


def test_reflection_and_form_validation():
    assert IO.validate_feelings_text(None) == (True, "")
    assert IO.validate_feelings_text(["x"])[0] is False
    assert IO.validate_feelings_text("x" * 2001)[0] is False
    ok, errors = IO.validate_student_form({"student_id": "1"})
    assert not ok
    assert set(errors) == {"student_id", *QUESTIONNAIRE.keys}
    assert IO.safety_fired("I want to die") is True
    assert IO.page_config()["version"] == "evidence-v3"


def test_display_record_labels_the_answers():
    shown = IO.display_record(PendingRecord(evaluated()))
    values = {field["key"]: field["value"] for field in shown["fields"]}
    assert values["student_id"] == "2605581"
    assert values["pss_1"] == "3 · Sometimes"
    assert values["sleep_hours_avg"] == "5.5"
    assert IO.display_record(PendingRecord({}))["empty"] is True


def load_tests(loader, tests, pattern):
    """Let `python -m unittest discover -s tests` run this file's tests."""
    return function_suite(globals())


if __name__ == "__main__":
    unittest.main()

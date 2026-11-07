"""Saved records for staff and the Student ID contract; synthetic data."""
import json
import unittest
from contextlib import contextmanager
from pathlib import Path

import survey
from data_manager import DataManager
from helpers import campus, login_admin, static_text
from io_manager import IOManager
from plain_tests import capture_logs, function_suite
from records.check_in_record import CheckInRecord
from records.pending_record import PendingRecord
from storage.json_storage import JSONStorage

IO = IOManager(survey.QUESTIONNAIRE)
LABELS = {"Low": "You're doing ok", "Moderate": "Worth a check-in",
          "High": "Please reach out"}


def sample_row(student_id, score, risk, saved_at):
    return dict(
        student_id=student_id, survey_version=survey.VERSION,
        stress_score=score, stress_level=5, pss_1=2, pss_2=4, pss_3=3,
        pss_4=1, sleep_hours_avg=7.5, sleep_quality=2, pas_workload=3,
        pas_catchup=2, fin_stress=4, mspss_friends=4, mspss_family=5,
        risk_category=risk, soft_label=LABELS[risk], ai_ok=True,
        source="ai_logic", saved_at=saved_at,
        feelings_text="Private response that must not appear",
        reasoning="Private explanation")


@contextmanager
def records_app():
    """A signed-in admin client and three sample rows ready to write."""
    with campus() as ctx:
        login_admin(ctx.client)
        ctx.rows = [
            sample_row("2603503", 3.1, "Moderate",
                       "2026-10-09T01:00:00+00:00"),
            sample_row("2703504", 4.2, "High", "2026-10-09T02:00:00+00:00"),
            sample_row("2000123", 1.4, "Low", "2026-10-09T03:00:00+00:00"),
        ]
        yield ctx


def write_rows(ctx, rows=None):
    """Write rows straight to the records file."""
    ctx.path.write_text(json.dumps(ctx.rows if rows is None else rows),
                        encoding="utf-8")


def records(ctx, **filters):
    return ctx.client.get("/api/records", query_string=filters)


def test_seven_digits_starting_with_two():
    for sid in ("2000000", "2200000", "2703504", "2999999", " 2603503 "):
        assert IO.validate_student_id(sid)[0], sid
    for sid in ("1200000", "3000000", "260350", "26035030", "2abc503",
                "2１２３４５６", "", None):
        assert not IO.validate_student_id(sid)[0], sid


def test_corrupt_file_is_backed_up_before_save():
    with records_app() as ctx:
        ctx.path.write_text('[{"student_id": "2603503"', encoding="utf-8")
        with capture_logs("data_manager", level="WARNING"):
            result = DataManager(JSONStorage(ctx.path)).save(
                PendingRecord({"student_id": "2000123"}), opt_in=True)
        assert result.ok
        backups = list(Path(ctx.temp).glob("records.corrupt-*.json"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == (
            '[{"student_id": "2603503"')


def test_missing_file_is_empty():
    with records_app() as ctx:
        response = records(ctx)
        assert response.status_code == 200
        assert response.json["records"] == []


def test_all_records_columns_and_privacy():
    with records_app() as ctx:
        write_rows(ctx)
        response = records(ctx)
        assert response.status_code == 200
        assert response.json["total"] == 3
        newest = response.json["records"][0]
        assert newest["student_id"] == "2000123"
        assert set(newest) == {
            "student_id", "stress_score", "risk_category", "soft_label",
            "pss_1", "pss_2", "pss_3", "pss_4", "sleep_hours_avg",
            "sleep_quality", "pas_workload", "pas_catchup", "fin_stress",
            "mspss_friends", "mspss_family", "saved_at", "survey_version",
            "status"}
        assert newest["pss_1"] == 2
        assert newest["sleep_hours_avg"] == 7.5
        assert "stress_level" not in newest
        assert "Private" not in response.get_data(as_text=True)
        assert response.headers["Cache-Control"] == "no-store"


def test_partial_id_and_combined_filters():
    with records_app() as ctx:
        write_rows(ctx)
        assert records(ctx, student_id="035").json["matching"] == 2
        result = records(ctx, student_id="035", tier="Please reach out",
                         cohort_year="2027").json
        assert result["matching"] == 1
        assert result["records"][0]["student_id"] == "2703504"
        assert result["cohorts"] == ["27", "26", "20"]
        assert records(ctx, tier="You're doing ok",
                       cohort_year="26").json["records"] == []
        assert records(ctx).json["matching"] == 3


def test_tier_filters():
    with records_app() as ctx:
        write_rows(ctx)
        for risk, tier in LABELS.items():
            rows = records(ctx, tier=tier).json["records"]
            assert len(rows) == 1
            assert rows[0]["risk_category"] == risk
            assert rows[0]["soft_label"] == tier
            assert rows[0]["status"] == "Evaluated"


def test_errors_are_not_empty_history():
    with records_app() as ctx:
        ctx.path.write_text("invalid json", encoding="utf-8")
        with capture_logs("data_manager", level="WARNING"):
            assert records(ctx).status_code == 500
        write_rows(ctx)
        assert records(ctx, tier="Critical").status_code == 400
        assert records(ctx, cohort_year="abc").status_code == 400


def test_legacy_records_are_ignored():
    with records_app() as ctx:
        write_rows(ctx, [
            {"student_id": "2600000", "survey_version": "legacy",
             "risk_category": "High"},
            {"student_id": "2700000", "survey_version": "evidence-v2",
             "ai_ok": False, "risk_category": "Low"},
            {"student_id": "2800000", "survey_version": survey.VERSION,
             "status": "pending", "risk_category": "Low"},
            {"student_id": "2900000", "survey_version": survey.VERSION,
             "ai_ok": True, "source": "ai_logic",
             "risk_category": "Moderate"},
            "not-a-record",
        ])
        payload = records(ctx).json
        assert payload["total"] == 2
        assert payload["cohorts"] == ["29", "28"]
        statuses = {row["student_id"]: row["status"]
                    for row in payload["records"]}
        assert statuses == {"2800000": "Pending", "2900000": "Evaluated"}
        pending = next(row for row in payload["records"]
                       if row["student_id"] == "2800000")
        assert pending["soft_label"] == "You're doing ok"


def test_insights_use_assessment_and_inputs():
    with records_app() as ctx:
        view = IO.display_result(CheckInRecord({
            **ctx.rows[0], "soft_label": "Worth a check-in",
            "tips": ["short_breaks"], "speak_prominence": "medium",
            "primary_stressors": ["academic_overload"],
            "reasoning": "Workload contributes. Logic adjusted: internal."}))
        assert view["insights"]["risk_category"] == "Moderate"
        assert view["insights"]["explanation"] == "Workload contributes."
        assert "snapshot" not in view["insights"]
        assert "stress_level" not in json.dumps(view)


def test_records_page():
    with records_app() as ctx:
        response = ctx.client.get("/records")
        assert response.status_code == 200
        assert '"page": "records"' in response.get_data(as_text=True)
        js = static_text("campus.js")
        css = static_text("style.css")
        for header in ("Control", "Coping", "Going well", "Piling up",
                       "Sleep (hours)", "Catch-up", "Date saved"):
            assert header in js
        for gone in ("Control (pss_1)", "Coping (pss_2)",
                     "Going well (pss_3)", "Piling up (pss_4)",
                     "Answers: 1 = lowest, 5 = highest · Sleep in hours",
                     "Cohort year uses the first two ID digits"):
            assert gone not in js
        assert ("title=\"${escape(key+': '+questions[key].prompt)}\""
                in js)
        assert "Showing ${data.matching} of ${data.total} check-ins" in js
        assert ("Answers are on a 1–5 scale, where 1 is the lowest. Sleep "
                "is shown in hours. All times are in Singapore time (SGT)."
                in js)
        assert 'role="status"' in js
        assert 'title="${escape(title)}"' in js
        for rule in ("overflow-x:auto", "max-width:75rem",
                     "text-align:center", "white-space:nowrap"):
            assert rule in css


def load_tests(loader, tests, pattern):
    """Let `python -m unittest discover -s tests` run this file's tests."""
    return function_suite(globals())


if __name__ == "__main__":
    unittest.main()

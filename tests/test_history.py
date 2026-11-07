"""The student stress-history feature: aggregate, trend, views, privacy."""
import json
import unittest

import survey
from data_manager import DataManager
from helpers import (campus, csrf_token, login_admin, make_app,
                     post_checkin, static_text)
from io_manager import IOManager
from logic.trend import Trend
from logic.trend_analyser import TrendAnalyser
from logic_manager import LogicManager
from plain_tests import capture_logs, case, function_suite
from records.check_in_record import CheckInRecord
from records.pending_record import PendingRecord
from records.stress_history import StressHistory
from storage.json_storage import JSONStorage
from views.history_entry_view import HistoryEntryView
from web.history_pass import HistoryPass

ANALYSER = TrendAnalyser()
STUDENT_A = "2605581"
STUDENT_B = "2703504"


def checked_in(score, day, student_id=STUDENT_A, **changes):
    """A finished check-in saved on 2026-10-<day>."""
    category = LogicManager().scorer.category_for(score)
    row = {"student_id": student_id, "survey_version": survey.VERSION,
           "stress_score": score, "risk_score": (score - 1) / 4,
           "risk_category": category,
           "soft_label": LogicManager().scorer.label_for(category),
           "primary_stressors": [], "recommended_support": "Internal",
           "confidence": 0.8, "reasoning": "PRIVATE reasoning",
           "source": "ai_logic", "ai_ok": True, "pss_1": 4,
           "saved_at": f"2026-10-{day:02d}T01:00:00+00:00"}
    row.update(changes)
    return row


def history(*scores):
    return StressHistory(STUDENT_A, [CheckInRecord(checked_in(score, day))
                                     for day, score in enumerate(scores, 1)])


def history_lookup(ctx, student_id, client=None):
    client = client or ctx.client
    return client.post("/api/history", json={"student_id": student_id},
                       headers={"X-CSRF-Token": csrf_token(client)})


# --- StressHistory ---------------------------------------------------------

def test_history_aggregates_records_oldest_first():
    late = CheckInRecord(checked_in(2.0, 9))
    early = CheckInRecord(checked_in(4.0, 1))
    combined = StressHistory(STUDENT_A, [late, early], pending_count=2)
    assert combined.records == [early, late]
    assert combined.scores == [4.0, 2.0]
    assert combined.latest is late and combined.previous is early
    assert combined.count == 2 and combined.pending_count == 2
    combined.records.clear()
    assert combined.count == 2
    empty = StressHistory(STUDENT_A, [])
    assert empty.latest is None and empty.previous is None


# --- TrendAnalyser ---------------------------------------------------------

def test_trend_compares_the_latest_score_with_the_previous_one():
    cases = (((), Trend.NONE, None), ((3.0,), Trend.FIRST, None),
             ((3.0, 2.5), Trend.LOWER, -0.5), ((3.0, 3.25), Trend.SIMILAR,
                                               0.25),
             ((3.0, 2.8), Trend.SIMILAR, -0.2),
             ((2.0, 3.64), Trend.HIGHER, 1.64))
    for scores, comparison, change in cases:
        with case(scores=scores):
            trend = ANALYSER.analyse(history(*scores))
            assert trend.comparison == comparison
            assert trend.change == change


def test_trend_direction_needs_three_scores_and_uses_recent_ones():
    cases = (((3.0, 2.0), Trend.NOT_ENOUGH),
             ((4.0, 3.5, 3.0), Trend.EASING),
             ((2.0, 2.05, 1.95, 2.0), Trend.STEADY),
             ((1.5, 2.0, 2.6, 3.1), Trend.BUILDING),
             # Only the last five count: an old high is forgotten.
             ((5.0, 2.0, 2.0, 2.05, 1.95, 2.0), Trend.STEADY))
    for scores, direction in cases:
        with case(scores=scores):
            assert ANALYSER.analyse(history(*scores)).direction == direction
    trend = ANALYSER.analyse(history(4.0, 3.0, 2.0))
    assert (trend.latest, trend.previous, trend.average) == (2.0, 3.0, 3.0)


def test_logic_manager_owns_the_trend_analyser():
    assert LogicManager().trend(history(3.0, 2.0)).comparison == Trend.LOWER


# --- DataManager.history_for ----------------------------------------------

def test_history_only_holds_that_student_on_this_questionnaire():
    with campus() as ctx:
        data = DataManager(JSONStorage(ctx.path))
        for row in (checked_in(3.0, 1), checked_in(4.0, 2, STUDENT_B),
                    checked_in(2.0, 3, "2605580"),
                    checked_in(2.0, 4, survey_version="evidence-v2"),
                    {"student_id": STUDENT_A,
                     "survey_version": survey.VERSION}):
            record = (CheckInRecord(row) if "stress_score" in row
                      else PendingRecord(row))
            assert data.save(record, opt_in=True).ok
        own = data.history_for(f" {STUDENT_A} ", survey.VERSION)
        assert own.student_id == STUDENT_A
        assert own.scores == [3.0]
        assert own.pending_count == 1
        assert all(record.student_id == STUDENT_A for record in own.records)


# --- Views -----------------------------------------------------------------

def test_history_entries_show_date_score_and_tier_only():
    view = HistoryEntryView()
    entry = view.render(CheckInRecord(checked_in(3.64, 5)))
    assert entry == {"saved_at": "2026-10-05T01:00:00+00:00", "score": 3.64,
                     "tier": "Please reach out", "risk": "high",
                     "status": "evaluated"}
    waiting = view.render(PendingRecord({"risk_category": "Low"}))
    assert waiting["score"] is None and waiting["status"] == "pending"
    assert waiting["tier"] == "You're doing ok"


def test_history_page_words_the_trend_and_offers_support_when_needed():
    io = IOManager(survey.QUESTIONNAIRE)
    building = history(1.5, 2.0, 2.6, 3.1)
    page = io.display_history(building, ANALYSER.analyse(building))
    assert page["trend"]["headline"] == (
        "Your latest score is 0.50 points higher than last time.")
    assert "building" in page["trend"]["detail"]
    assert page["advisor"]["prominence"] == "medium"
    assert [entry["score"] for entry in page["entries"]] == [1.5, 2.0, 2.6,
                                                             3.1]
    assert "PRIVATE" not in json.dumps(page)
    assert "pss_1" not in json.dumps(page)
    calm = history(3.0, 2.0)
    assert io.display_history(calm, ANALYSER.analyse(calm))[
        "advisor"] is None
    high = history(2.0, 4.0)
    assert io.display_history(high, ANALYSER.analyse(high))["advisor"][
        "prominence"] == "high"


# --- HistoryPass -----------------------------------------------------------

def test_history_pass_holds_digests_not_student_ids():
    issuer = HistoryPass("server-secret")
    cookie = issuer.grant(None, STUDENT_A)
    assert STUDENT_A not in cookie
    assert issuer.allows(cookie, STUDENT_A)
    assert not issuer.allows(cookie, STUDENT_B)
    assert not HistoryPass("other-secret").allows(cookie, STUDENT_A)
    assert not issuer.allows(cookie + ".forged0000000000000000000000000",
                             STUDENT_B)
    both = issuer.grant(cookie, STUDENT_B)
    assert issuer.allows(both, STUDENT_A) and issuer.allows(both, STUDENT_B)
    assert issuer.grant(both, STUDENT_A).count(".") == 1
    many = None
    for number in range(HistoryPass.MAX_IDS + 2):
        many = issuer.grant(many, f"20000{number:02d}")
    assert many.count(".") == HistoryPass.MAX_IDS - 1


# --- Web -------------------------------------------------------------------

def test_a_student_sees_their_own_history_after_checking_in():
    with campus() as ctx:
        assert post_checkin(ctx).status_code == 200
        ctx.values["pss_1"] = 5
        assert post_checkin(ctx).status_code == 200
        response = history_lookup(ctx, STUDENT_A)
        assert response.status_code == 200
        page = response.json["history"]
        assert len(page["entries"]) == 2
        assert page["trend"]["comparison"] == Trend.SIMILAR
        assert page["student_id"] == STUDENT_A
        assert response.headers["Cache-Control"] == "no-store"
        assert "feelings_text" not in json.dumps(page)


def test_student_a_cannot_see_student_b():
    with campus() as ctx:
        DataManager(JSONStorage(ctx.path)).save(
            CheckInRecord(checked_in(4.5, 1, STUDENT_B)), opt_in=True)
        assert post_checkin(ctx).status_code == 200
        response = history_lookup(ctx, STUDENT_B)
        assert response.status_code == 403
        assert "history" not in response.json
        assert "4.5" not in response.get_data(as_text=True)
        fresh = ctx.app.flask.test_client()
        fresh.get("/")
        assert history_lookup(ctx, STUDENT_A, fresh).status_code == 403


def test_a_pending_check_in_also_unlocks_history():
    with campus() as ctx:
        ctx.provider.reply_with("{}")
        assert post_checkin(ctx).status_code == 503
        page = history_lookup(ctx, STUDENT_A).json["history"]
        assert page["entries"] == [] and page["pending"] == 1
        assert page["trend"]["comparison"] == Trend.NONE


def test_a_signed_in_admin_can_view_any_students_history():
    with campus() as ctx:
        DataManager(JSONStorage(ctx.path)).save(
            CheckInRecord(checked_in(4.5, 1, STUDENT_B)), opt_in=True)
        login_admin(ctx.client)
        page = history_lookup(ctx, STUDENT_B).json["history"]
        assert [entry["score"] for entry in page["entries"]] == [4.5]


def test_history_lookup_checks_input_csrf_and_storage():
    with campus() as ctx:
        assert history_lookup(ctx, "1234567").status_code == 400
        assert ctx.client.post("/api/history", json={
            "student_id": STUDENT_A}).status_code == 403
        assert ctx.client.get("/api/history").status_code == 405
        assert post_checkin(ctx).status_code == 200
        ctx.path.write_text("{broken", encoding="utf-8")
        with capture_logs("data_manager", level="WARNING"):
            assert history_lookup(ctx, STUDENT_A).status_code == 500


def test_the_history_cookie_is_http_only_and_carries_no_student_id():
    with campus() as ctx:
        response = post_checkin(ctx)
        header = response.headers.get("Set-Cookie", "")
        assert header.startswith(HistoryPass.COOKIE_NAME + "=")
        assert "HttpOnly" in header and "SameSite=Lax" in header
        assert STUDENT_A not in header


def test_history_page_and_navigation():
    with campus() as ctx:
        page = ctx.client.get("/history").get_data(as_text=True)
        assert '"page": "history"' in page
        assert '"historyUrl": "/api/history"' in page
        assert 'data-nav="history"' in page
        assert ">My history<" in page
        js = static_text("campus.js")
        for expected in ("function history()", "historyChart(entries)",
                         "See how this compares with past check-ins",
                         "you can only see a Student ID that has checked "
                         "in on this device"):
            assert expected in js, expected


def test_history_works_with_a_fresh_app_after_a_restart():
    with campus() as ctx:
        assert post_checkin(ctx).status_code == 200
        cookie = ctx.client.get_cookie(HistoryPass.COOKIE_NAME).value
        again = make_app(ctx.path)
        client = again.flask.test_client()
        client.get("/")
        client.set_cookie(HistoryPass.COOKIE_NAME, cookie)
        response = client.post(
            "/api/history", json={"student_id": STUDENT_A},
            headers={"X-CSRF-Token": csrf_token(client)})
        assert response.status_code == 200
        assert len(response.json["history"]["entries"]) == 1


def load_tests(loader, tests, pattern):
    """Let `python -m unittest discover -s tests` run this file's tests."""
    return function_suite(globals())


if __name__ == "__main__":
    unittest.main()

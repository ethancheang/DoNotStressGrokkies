"""The real I/O → AI schema → Logic → save pipeline, without the network."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai.gemini_provider import GeminiProvider
from ai_manager import AIManager
from data_manager import DataManager
from helpers import (campus, login_admin, make_app, post_checkin,
                     static_text, stored_rows)
from logic_manager import LogicManager
from plain_tests import case, function_suite
from storage.save_result import SaveResult


def stored_result(ctx):
    """The result the server keeps for this session's /result page."""
    with ctx.client.session_transaction() as state:
        return ctx.app.web.results.get(state.get("checkin_token"))


def test_student_result_and_records_routes():
    with campus() as ctx:
        denied = ctx.client.get("/records")
        assert denied.status_code == 302
        assert denied.location.endswith("/admin/login")
        assert ctx.client.get("/result").status_code == 302
        assert post_checkin(ctx).status_code == 200
        result = ctx.client.get("/result")
        assert result.status_code == 200
        body = result.get_data(as_text=True)
        assert '"page": "result"' in body
        assert '"page": "records"' not in body
        assert '"resultUrl": "/result"' in body
        assert '"recordsPageUrl": "/records"' in body
        still_denied = ctx.client.get("/records")
        assert still_denied.status_code == 302
        assert still_denied.location.endswith("/admin/login")
        login_admin(ctx.client)
        records = ctx.client.get("/records")
        assert records.status_code == 200
        records_body = records.get_data(as_text=True)
        assert '"page": "records"' in records_body
        assert '"page": "result"' not in records_body
        js = static_text("campus.js")
        assert "boot.resultUrl" in js
        assert "boot.recordsPageUrl" in js
        assert "history.pushState" in js
        assert "page='result'" in js


def test_retired_page_shows_home():
    with campus() as ctx:
        response = ctx.client.get("/garden")
        assert response.status_code == 302
        assert response.location.endswith("/")
        text = ctx.client.get("/garden", follow_redirects=True).get_data(
            as_text=True)
        assert ">Home<" in text
        assert "Student view" in text
        assert "My garden" not in text
        assert 'data-nav="garden"' not in text
        login = ctx.client.get("/admin/login").get_data(as_text=True)
        assert "My garden" not in login


def test_success_uses_backend_result_and_keeps_answers_out_of_cookie():
    with campus() as ctx:
        response = post_checkin(ctx)
        assert response.status_code == 200
        assert response.json["result"]["soft"]["heading"] == (
            "Worth a check-in")
        with ctx.client.session_transaction() as state:
            assert set(state) == {"csrf_token", "checkin_token"}
        assert stored_result(ctx)["source"] == "ai_logic"
        stored = stored_rows(ctx)
        assert len(stored) == 1
        assert "feelings_text" not in stored[0]
        assert ctx.client.get("/result").status_code == 200
        assert len(stored_rows(ctx)) == 1


def test_invalid_fields_prevent_ai_call():
    with campus() as ctx:
        for field, value in [("student_id", "1200000"),
                             ("sleep_hours_avg", "6.75"), ("pss_1", "6"),
                             ("pas_workload", "0"), ("fin_stress", "yes"),
                             ("mspss_friends", "1.5")]:
            with case(field=field), \
                    patch.object(AIManager, "analyse") as analyse:
                response = post_checkin(ctx, {**ctx.values, field: value})
                assert response.status_code == 400
                assert field in response.json["errors"]
                analyse.assert_not_called()


def test_optional_text():
    with campus() as ctx:
        no_text = {**ctx.values, "feelings_text": ""}
        assert post_checkin(ctx, no_text).status_code == 200


def test_missing_key_returns_error_and_no_logic_fallback():
    with campus(GeminiProvider(api_key="")) as ctx, \
            patch.dict(os.environ, {"GEMINI_API_KEY": ""}), \
            patch.object(LogicManager, "evaluate") as evaluate:
        response = post_checkin(ctx)
        assert response.status_code == 503
        assert response.json["error_code"] == "missing_api_key"
        assert "result" not in response.json
        assert "advisor" in response.json
        evaluate.assert_not_called()


def test_invalid_ai_response_never_becomes_result():
    with campus() as ctx:
        ctx.provider.reply_with("{}")
        assert post_checkin(ctx).status_code == 503
        assert ctx.client.get("/result").status_code == 302


def test_failure_clears_previous_result():
    with campus() as ctx:
        post_checkin(ctx)
        ctx.provider.reply_with("{}")
        post_checkin(ctx)
        assert ctx.app.web.results.count == 0
        assert ctx.client.get("/result").status_code == 302


def test_save_is_automatic_and_refresh_does_not_duplicate():
    with campus() as ctx:
        post_checkin(ctx)
        assert len(stored_rows(ctx)) == 1
        assert ctx.client.get("/result").status_code == 200
        assert post_checkin(ctx, {"opt_in": True}, "/save").status_code == 200
        assert post_checkin(ctx, {}, "/save").status_code == 200
        assert len(stored_rows(ctx)) == 1


def test_submit_saves_record_for_admin_without_reflection():
    with campus() as ctx:
        ctx.values["feelings_text"] = "PRIVATE REFLECTION not to be stored"
        assert post_checkin(ctx).status_code == 200
        stored = stored_rows(ctx)
        assert len(stored) == 1
        assert stored[0]["student_id"] == "2605581"
        assert stored[0]["pss_1"] == 3
        assert stored[0]["sleep_hours_avg"] == 6.5
        assert "feelings_text" not in stored[0]
        assert "PRIVATE REFLECTION" not in ctx.path.read_text(
            encoding="utf-8")
        assert ctx.client.get("/result").status_code == 200
        assert len(stored_rows(ctx)) == 1
        assert ctx.client.get("/api/records").status_code == 401
        login_admin(ctx.client)
        assert '"page": "records"' in ctx.client.get("/records").get_data(
            as_text=True)
        payload = ctx.client.get("/api/records").json
        assert payload["matching"] == 1
        row = payload["records"][0]
        assert row["student_id"] == "2605581"
        assert row["status"] == "Evaluated"
        assert "feelings_text" not in row
        assert "reflection" not in row
        assert "PRIVATE REFLECTION" not in json.dumps(payload)


def test_ai_down_saves_pending_record_without_reflection():
    with campus() as ctx:
        ctx.values["feelings_text"] = "PRIVATE REFLECTION not to be stored"
        ctx.provider.reply_with("{}")
        response = post_checkin(ctx)
        assert response.status_code == 503
        assert "result" not in response.json
        assert ctx.app.web.results.count == 0
        stored = stored_rows(ctx)
        assert len(stored) == 1
        assert stored[0]["status"] == "pending"
        assert stored[0]["student_id"] == "2605581"
        assert stored[0]["sleep_hours_avg"] == 6.5
        assert stored[0]["ai_ok"] is False
        assert "feelings_text" not in stored[0]
        assert "PRIVATE REFLECTION" not in ctx.path.read_text(
            encoding="utf-8")
        login_admin(ctx.client)
        row = ctx.client.get("/api/records").json["records"][0]
        assert row["student_id"] == "2605581"
        assert row["status"] == "Pending"
        assert "PRIVATE REFLECTION" not in json.dumps(row)


def test_csrf_and_malformed_requests():
    with campus() as ctx:
        assert ctx.client.post("/", json=ctx.values).status_code == 403
        assert post_checkin(ctx, []).status_code == 400
        assert ctx.client.post("/save", json={"opt_in": True}
                               ).status_code == 403


def test_new_and_expired_result():
    with campus() as ctx:
        post_checkin(ctx)
        ctx.client.get("/new")
        assert ctx.app.web.results.count == 0
        assert ctx.client.get("/result").status_code == 302
        post_checkin(ctx)
        ctx.app.web.results.ttl_seconds = -1
        assert ctx.client.get("/result").status_code == 302
        assert post_checkin(ctx, {"opt_in": True}, "/save").status_code == 409


def test_save_failure_is_retryable():
    with campus() as ctx:
        with patch.object(DataManager, "save",
                          return_value=SaveResult(error="disk full")):
            assert post_checkin(ctx).status_code == 500
        assert not ctx.path.exists()
        assert post_checkin(ctx).status_code == 200
        assert len(stored_rows(ctx)) == 1


def test_oversized_requests_are_refused_politely():
    with campus() as ctx:
        huge = {**ctx.values, "feelings_text": "x" * (70 * 1024)}
        response = post_checkin(ctx, huge)
        assert response.status_code == 413
        assert "too long" in response.json["message"]


def test_health_lists_every_manager_without_secrets():
    with tempfile.TemporaryDirectory() as temp:
        app = make_app(Path(temp) / "records.json",
                       GeminiProvider("sk-health-secret"))
        response = app.flask.test_client().get("/health")
    assert response.status_code == 200
    names = [manager["name"] for manager in response.json["managers"]]
    assert names == ["io_manager", "ai_manager", "logic_manager",
                     "data_manager"]
    assert "sk-health-secret" not in response.get_data(as_text=True)


def load_tests(loader, tests, pattern):
    """Let `python -m unittest discover -s tests` run this file's tests."""
    return function_suite(globals())


if __name__ == "__main__":
    unittest.main()

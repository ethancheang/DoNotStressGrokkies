"""Repeated submits of one check-in must not duplicate a pending row.

Gemini is a FakeProvider. These tests do not call the network.
"""
import json
import os
import re
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from ai.fake_provider import FakeProvider
from helpers import (campus, fake_generate, login_admin, post_checkin,
                     static_text, stored_rows)
from plain_tests import function_suite

CALM = ("We could not complete your check-in right now. "
        "Your answers are still here; please try again.")


@contextmanager
def pending_app():
    """A fresh app whose Gemini always fails, with its own records file."""
    with campus(FakeProvider("{}")) as ctx:
        ctx.values = dict(
            student_id="2603050", pss_1=1, pss_2=4, pss_3=4, pss_4=3,
            sleep_hours_avg=7, sleep_quality=3, pas_workload=4,
            pas_catchup=3, fin_stress=4, mspss_friends=4, mspss_family=3,
            feelings_text="PRIVATE note that must not be stored")
        yield ctx


def test_repeated_failures_then_success_keep_one_record():
    with pending_app() as ctx:
        for _ in range(5):
            response = post_checkin(ctx)
            assert response.status_code == 503
            assert response.json["message"] == CALM
            assert "result" not in response.json
        # Feelings are not part of the submission fingerprint.
        ctx.values["feelings_text"] = "A different private note"
        assert post_checkin(ctx).status_code == 503
        rows = stored_rows(ctx)
        assert len(rows) == 1
        assert rows[0]["status"] == "pending"
        assert rows[0]["ai_ok"] is False
        assert rows[0]["student_id"] == "2603050"
        assert rows[0]["pss_1"] == 1
        assert rows[0]["sleep_hours_avg"] == 7
        assert re.fullmatch(r"[0-9a-f]{32}", rows[0]["record_id"])
        assert "feelings_text" not in rows[0]
        assert "PRIVATE" not in ctx.path.read_text(encoding="utf-8")
        record_id = rows[0]["record_id"]
        with ctx.client.session_transaction() as session:
            assert session["pending_record_id"] == record_id
            assert len(session["pending_fingerprint"]) == 64

        ctx.provider.reply_with(fake_generate)
        assert post_checkin(ctx).status_code == 200
        rows = stored_rows(ctx)
        assert len(rows) == 1
        assert rows[0]["record_id"] == record_id
        assert rows[0].get("status") != "pending"
        assert rows[0]["ai_ok"] is True
        assert rows[0]["pss_1"] == 1
        assert "feelings_text" not in rows[0]

        changed = {**ctx.values, "pss_1": 5, "feelings_text": "Private"}
        assert post_checkin(ctx, changed).status_code == 200
        rows = stored_rows(ctx)
        assert len(rows) == 2
        assert rows[0]["record_id"] == record_id
        assert rows[0]["pss_1"] == 1
        assert rows[1]["pss_1"] == 5
        assert re.fullmatch(r"[0-9a-f]{32}", rows[1]["record_id"])
        assert rows[1]["record_id"] != record_id
        assert rows[1]["ai_ok"] is True

        login_admin(ctx.client)
        payload = ctx.client.get("/api/records").json
        assert payload["matching"] == 2
        assert {row["status"] for row in payload["records"]} == {
            "Evaluated"}
        assert "PRIVATE" not in json.dumps(payload)


def test_rapid_posts_keep_one_pending_record():
    with pending_app() as ctx:
        assert post_checkin(ctx).status_code == 503
        assert post_checkin(ctx).status_code == 503
        rows = stored_rows(ctx)
        assert len(rows) == 1
        assert rows[0]["status"] == "pending"
        assert rows[0]["student_id"] == "2603050"


def test_concurrent_posts_keep_one_pending_record():
    with pending_app() as ctx:
        cookie = ctx.client.get_cookie("session")
        barrier = threading.Barrier(2)
        statuses = []
        gate = threading.Lock()

        def worker():
            client = ctx.app.flask.test_client()
            client.set_cookie("session", cookie.value)
            barrier.wait(timeout=5)
            response = post_checkin(ctx, client=client)
            with gate:
                statuses.append(response.status_code)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        assert sorted(statuses) == [503, 503]
        rows = stored_rows(ctx)
        assert len(rows) == 1
        assert rows[0]["status"] == "pending"


def test_different_answers_save_a_second_pending_row():
    with pending_app() as ctx:
        assert post_checkin(ctx).status_code == 503
        changed = {**ctx.values, "sleep_quality": 5}
        assert post_checkin(ctx, changed).status_code == 503
        rows = stored_rows(ctx)
        assert len(rows) == 2
        assert {row["status"] for row in rows} == {"pending"}
        assert {row["sleep_quality"] for row in rows} == {3, 5}
        assert rows[0]["record_id"] != rows[1]["record_id"]


def test_pending_write_uses_atomic_replace():
    with pending_app() as ctx:
        with patch("storage.json_storage.os.replace",
                   wraps=os.replace) as replaced:
            assert post_checkin(ctx).status_code == 503
        assert replaced.called
        assert Path(replaced.call_args.args[1]) == ctx.path
        assert list(ctx.path.parent.glob("*.tmp")) == []
        assert len(stored_rows(ctx)) == 1


def test_submit_button_ignores_repeat_clicks():
    js = static_text("campus.js")
    assert ("let assessment = boot.result || null, busy = false, "
            "submitting = false;") in js
    assert "if(!button||busy||submitting)return;" in js
    assert "button.disabled=true;await submit();" in js
    assert "if(submitting)return;" in js
    assert CALM in js


def load_tests(loader, tests, pattern):
    """Let `python -m unittest discover -s tests` run this file's tests."""
    return function_suite(globals())


if __name__ == "__main__":
    unittest.main()

"""Background check-ins: Gemini runs on a worker thread, not the request.

Every wait here is on a threading.Event the test controls, never a sleep,
so the results are the same on every run.
"""
import threading
import unittest

from ai.fake_provider import FakeProvider
from checkins.background_jobs import BackgroundJobs
from checkins.check_in_job import CheckInJob
from checkins.check_in_outcome import CheckInOutcome
from helpers import campus, fake_generate, post_checkin, stored_rows
from plain_tests import capture_logs, function_suite

WAIT = 10


def outcome(status=CheckInOutcome.DONE):
    return CheckInOutcome(status, "2605581", "fingerprint", "id")


class Gate:
    """A Gemini stand-in that holds each call until the test opens it."""

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.threads = []

    def __call__(self, prompt, model_name):
        self.threads.append(threading.current_thread().name)
        self.entered.set()
        assert self.release.wait(WAIT), "the test never released Gemini"
        return fake_generate(prompt, model_name)


# --- BackgroundJobs --------------------------------------------------------

def test_a_job_runs_on_a_worker_thread_and_reports_its_status():
    jobs = BackgroundJobs(workers=1)
    started, release = threading.Event(), threading.Event()
    seen = []

    def task():
        seen.append(threading.current_thread().name)
        started.set()
        assert release.wait(WAIT)
        return outcome()

    job = jobs.submit("owner", "key", False, task)
    assert started.wait(WAIT)
    assert job.status == CheckInJob.RUNNING and not job.is_done
    assert jobs.get(job.id, "owner") is job
    release.set()
    assert jobs.wait(job.id, WAIT)
    assert job.status == CheckInJob.DONE
    assert job.outcome.status == CheckInOutcome.DONE
    assert seen[0].startswith("checkin")
    assert seen[0] != threading.current_thread().name
    jobs.shutdown()


def test_jobs_queue_when_every_worker_is_busy():
    jobs = BackgroundJobs(workers=1)
    release = threading.Event()

    def slow():
        assert release.wait(WAIT)
        return outcome()

    first = jobs.submit("a", "1", False, slow)
    second = jobs.submit("b", "2", False, outcome)
    assert second.status == CheckInJob.QUEUED
    release.set()
    assert jobs.wait(first.id, WAIT) and jobs.wait(second.id, WAIT)
    assert second.status == CheckInJob.DONE
    jobs.shutdown()


def test_a_repeat_joins_the_running_job_and_owners_stay_separate():
    jobs = BackgroundJobs(workers=2)
    release = threading.Event()

    def task():
        assert release.wait(WAIT)
        return outcome()

    job = jobs.submit("owner", "same answers", False, task)
    assert jobs.submit("owner", "same answers", False, task) is job
    other = jobs.submit("someone else", "same answers", False, task)
    assert other is not job
    assert jobs.get(job.id, "someone else") is None
    assert jobs.get(job.id, "") is None
    assert jobs.get("unknown", "owner") is None
    release.set()
    assert jobs.wait(job.id, WAIT) and jobs.wait(other.id, WAIT)
    again = jobs.submit("owner", "same answers", False, outcome)
    assert again is not job
    jobs.shutdown()


def test_a_crashing_task_still_ends_its_job():
    jobs = BackgroundJobs(workers=1)

    def task():
        raise RuntimeError("bug")

    with capture_logs("main.jobs", level="WARNING"):
        job = jobs.submit("owner", "key", False, task)
        assert jobs.wait(job.id, WAIT)
    assert job.status == CheckInJob.FAILED
    assert job.outcome is None
    jobs.shutdown()


def test_finished_jobs_expire():
    jobs = BackgroundJobs(workers=1)
    job = jobs.submit("owner", "key", False, outcome)
    assert jobs.wait(job.id, WAIT)
    jobs.expire()
    assert jobs.count == 1
    jobs.ttl_seconds = -1
    jobs.expire()
    assert jobs.count == 0 and jobs.get(job.id, "owner") is None
    jobs.shutdown()


# --- The web flow ----------------------------------------------------------

def test_submitting_returns_before_gemini_answers():
    gate = Gate()
    with campus(FakeProvider(gate)) as ctx:
        response = ctx.client.post("/", json=ctx.values,
                                   headers={"X-CSRF-Token": ctx.token})
        assert response.status_code == 202
        assert gate.entered.wait(WAIT)
        status = ctx.client.get(response.json["statusUrl"])
        assert status.status_code == 202
        assert status.json["status"] == "running"
        assert not ctx.path.exists()
        gate.release.set()
        assert ctx.app.jobs.wait(response.json["jobId"], WAIT)
        final = ctx.client.get(response.json["statusUrl"])
        assert final.status_code == 200
        assert final.json["result"]["soft"]["heading"] == "Worth a check-in"
        assert len(stored_rows(ctx)) == 1
        assert gate.threads[0].startswith("checkin")
        assert ctx.client.get("/result").status_code == 200


def test_the_pending_flow_is_unchanged_in_the_background():
    with campus(FakeProvider("{}")) as ctx:
        response = post_checkin(ctx)
        assert response.status_code == 503
        assert response.json["error_code"] == "invalid_response"
        assert stored_rows(ctx)[0]["status"] == "pending"
        with ctx.client.session_transaction() as state:
            assert state["pending_record_id"] == stored_rows(ctx)[0][
                "record_id"]


def test_a_repeat_while_gemini_is_busy_makes_one_call():
    gate = Gate()
    provider = FakeProvider(gate)
    with campus(provider) as ctx:
        headers = {"X-CSRF-Token": ctx.token}
        first = ctx.client.post("/", json=ctx.values, headers=headers)
        assert gate.entered.wait(WAIT)
        second = ctx.client.post("/", json=ctx.values, headers=headers)
        assert second.json["jobId"] == first.json["jobId"]
        gate.release.set()
        assert ctx.app.jobs.wait(first.json["jobId"], WAIT)
        assert len(provider.calls) == 1
        assert len(stored_rows(ctx)) == 1


def test_another_session_cannot_read_a_job():
    gate = Gate()
    with campus(FakeProvider(gate)) as ctx:
        response = ctx.client.post("/", json=ctx.values,
                                   headers={"X-CSRF-Token": ctx.token})
        stranger = ctx.app.flask.test_client()
        stranger.get("/")
        assert stranger.get(response.json["statusUrl"]).status_code == 404
        assert ctx.client.get("/checkin/status/unknown").status_code == 404
        gate.release.set()
        assert ctx.app.jobs.wait(response.json["jobId"], WAIT)


def test_the_browser_polls_for_the_result():
    from helpers import static_text
    js = static_text("campus.js")
    assert "async function waitForResult(url, showProgress)" in js
    assert "sent.response.status===202" in js
    assert "Your check-in is next in line." in js


def load_tests(loader, tests, pattern):
    """Let `python -m unittest discover -s tests` run this file's tests."""
    return function_suite(globals())


if __name__ == "__main__":
    unittest.main()

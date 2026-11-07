"""Shared test set-up: a fake Gemini, a fresh App, and request helpers.

Nothing here reaches the real Gemini API or the real records file.
"""
import json
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from ai.fake_provider import FakeProvider
from logic.stress_scorer import StressScorer
from main import App

SCORER = StressScorer()
ADMIN_PASSWORD = "DoNotStress2026!"


def fake_generate(prompt, model_name):
    """A fake Gemini that replays the formula on the prompt's answers."""
    if isinstance(prompt, str) and "{" in prompt:
        answers = json.loads(prompt[prompt.rfind("{"):])
    else:
        answers = {key: 3 for key in StressScorer.ANSWER_KEYS}
        answers["sleep_hours_avg"] = 6.5
    stress = SCORER.score(answers).stress_score
    category = SCORER.category_for(stress)
    return json.dumps({
        "scored_items": SCORER.scored_items(answers),
        "stress_score": stress,
        "risk_category": category,
        "primary_stressors": ["academic_overload"],
        "confidence": 0.8,
        "reasoning": "Test fixture, not a real assessment.",
        "soft_label": SCORER.label_for(category),
        "tips": ["workload_chunks", "short_breaks"],
        "speak_prominence": SCORER.prominence_for(category),
    })


def make_app(path, provider=None):
    """An App with a fake Gemini, no retry delay and its own records file."""
    return App(provider=provider or FakeProvider(fake_generate),
               data_path=Path(path), secret_key="test-only", testing=True,
               ai_max_attempts=1, ai_retry_delay_sec=0)


@contextmanager
def campus(provider=None):
    """A fresh App, a client holding a CSRF token, and sample answers."""
    with tempfile.TemporaryDirectory() as temp:
        ctx = SimpleNamespace(temp=temp)
        ctx.path = Path(temp) / "records.json"
        ctx.provider = provider or FakeProvider(fake_generate)
        ctx.app = make_app(ctx.path, ctx.provider)
        ctx.client = ctx.app.flask.test_client()
        ctx.client.get("/")
        ctx.token = csrf_token(ctx.client)
        ctx.values = dict(
            student_id="2605581", pss_1=3, pss_2=3, pss_3=3, pss_4=3,
            sleep_hours_avg=6.5, sleep_quality=3, pas_workload=3,
            pas_catchup=3, fin_stress=3, mspss_friends=3, mspss_family=3,
            feelings_text="Example concern")
        try:
            yield ctx
        finally:
            ctx.app.close()


def csrf_token(client):
    with client.session_transaction() as state:
        return state["csrf_token"]


def post_checkin(ctx, values=None, url="/", client=None):
    """Submit as JSON with the CSRF token; return the final response.

    A check-in is analysed on a worker thread, so the POST answers 202.
    This waits on the job's event (no sleeping) and then fetches the
    final response, exactly as the browser's poll would.
    """
    client = client or ctx.client
    response = client.post(url, json=ctx.values if values is None else values,
                           headers={"X-CSRF-Token": ctx.token})
    if response.status_code != 202:
        return response
    assert ctx.app.jobs.wait(response.json["jobId"], timeout=10)
    return client.get(response.json["statusUrl"])


def stored_rows(ctx):
    """The saved rows; fails if the records file was never written."""
    assert ctx.path.exists()
    return json.loads(ctx.path.read_text(encoding="utf-8"))


def login_admin(client):
    client.get("/admin/login")
    response = client.post("/admin/login", data={
        "username": "admin", "password": ADMIN_PASSWORD,
        "csrf_token": csrf_token(client)})
    assert response.status_code == 302, response.status_code
    return response


def static_text(name):
    root = Path(__file__).resolve().parents[1]
    return (root / "static" / name).read_text(encoding="utf-8")

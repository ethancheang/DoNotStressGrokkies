"""Smoke tests for the student-facing Flask wiring (AI mandatory)."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ai_manager
import app as flask_app
import data_manager
import io_manager
import logic_manager


VALID_FORM = {
    "student_id": "2605581",
    "sleep_hours": "8.0",
    "stress_level": "3",
    "academic_workload": "3",
    "financial_stress": "2",
    "social_support": "8",
    "feelings_text": "School has been alright.",
}

HIGH_FORM = {
    "student_id": "2605581",
    "sleep_hours": "4.5",
    "stress_level": "9",
    "academic_workload": "8",
    "financial_stress": "4",
    "social_support": "6",
    "feelings_text": "",
}

FAKE_AI = {
    "risk_score": 0.81,
    "risk_category": "High",
    "primary_stressors": ["high_stress", "sleep_deprivation"],
    "recommended_support": "Encourage a confidential check-in.",
    "confidence": 0.9,
    "reasoning": "Stress is high and sleep is short.",
    "soft_label": "Please reach out",
    "tips": ["talk_to_someone", "sleep_routine"],
    "speak_prominence": "high",
}

LOW_AI = {
    "risk_score": 0.2,
    "risk_category": "Low",
    "primary_stressors": [],
    "recommended_support": "Keep current habits.",
    "confidence": 0.8,
    "reasoning": "Sleep and stress look steady.",
    "soft_label": "You're doing ok",
    "tips": ["keep_social_contact"],
    "speak_prominence": "low",
}


@pytest.fixture
def data_path(tmp_path):
    return str(tmp_path / "student_records.json")


@pytest.fixture
def client(data_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    application = flask_app.create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATA_PATH": data_path,
            "AI_MAX_ATTEMPTS": 1,
            "AI_RETRY_DELAY_SEC": 0,
        }
    )
    return application.test_client()


def _load_saved(data_path):
    loaded = data_manager.load_all_records(data_path=data_path)
    return loaded["records"]


def _patch_ai_success(monkeypatch, ai_fields):
    def fake_analyse(student_dict, **_kwargs):
        enriched = dict(student_dict)
        enriched.update(ai_fields)
        enriched["source"] = "gemini"
        return True, enriched, None

    monkeypatch.setattr(ai_manager, "analyse_student", fake_analyse)


def _patch_ai_failure(monkeypatch, error_code="missing_api_key", detail="GEMINI_API_KEY is not set"):
    monkeypatch.setattr(
        ai_manager,
        "analyse_student",
        lambda *args, **kwargs: (
            False,
            None,
            {"error_code": error_code, "detail": detail, "source": "gemini"},
        ),
    )


def _assert_ai_error_page(html, *, status_code, response=None):
    if response is not None:
        assert response.status_code == status_code
    assert "We couldn't complete your check-in" in html
    assert "AI is required" in html or "Gemini" in html
    assert "try again later" in html.lower()
    assert "Try again" in html
    assert "Suggestions for you" not in html
    assert "Save this check-in" not in html
    assert "Save my check-in" not in html
    assert "You're doing ok" not in html
    assert "Worth a check-in" not in html
    assert "GEMINI_API_KEY" not in html
    assert io_manager.ADVISOR_EMAIL in html
    assert io_manager.ADVISOR_HELPLINE in html
    assert io_manager.ADVISOR_MAILTO in html
    assert "Speak to advisor" in html
    assert "prominence-high" in html


def test_app_source_does_not_use_removed_logic_fallback():
    source = Path(flask_app.__file__).read_text(encoding="utf-8")
    assert "apply_soft_outcome" not in source
    assert "assign_soft_outcome" not in source
    assert "logic_fallback" not in source
    assert "evaluate_checkin" not in source
    assert hasattr(logic_manager, "apply_logic")
    assert not hasattr(logic_manager, "apply_soft_outcome")
    assert not hasattr(logic_manager, "assign_soft_outcome")


def test_home_shows_student_form_and_feelings_prompt(client):
    response = client.get("/")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "DoNotStress" in html
    for field in io_manager.FORM_FIELDS:
        assert f'name="{field}"' in html
    assert "In your own words, how have you been feeling about school lately?" in html
    assert "Speak to advisor" not in html


def test_invalid_form_redisplays_errors_and_does_not_save(client, data_path):
    response = client.post(
        "/",
        data={"student_id": "99", "sleep_hours": "5.25", "feelings_text": ""},
    )
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "Student ID" in html
    assert "0.5-hour steps" in html or "0.5-hour" in html
    assert _load_saved(data_path) == []


def test_submit_without_api_key_shows_ai_error_not_fake_tips(client, data_path):
    response = client.post("/", data=VALID_FORM)
    html = response.get_data(as_text=True)
    _assert_ai_error_page(html, status_code=503, response=response)
    assert _load_saved(data_path) == []


def test_logic_is_not_called_when_ai_fails(client, monkeypatch, data_path):
    called = {"n": 0}

    def must_not_run(_record):
        called["n"] += 1
        raise AssertionError("Logic must not replace missing AI")

    monkeypatch.setattr(logic_manager, "apply_logic", must_not_run)
    _patch_ai_failure(monkeypatch, error_code="timeout", detail="Gemini timed out")
    response = client.post("/", data=VALID_FORM)
    html = response.get_data(as_text=True)
    assert called["n"] == 0
    _assert_ai_error_page(html, status_code=503, response=response)
    assert _load_saved(data_path) == []


@pytest.mark.parametrize("error_code", list(io_manager.AI_ERROR_CODES))
def test_ai_error_codes_render_error_page(client, monkeypatch, data_path, error_code):
    _patch_ai_failure(monkeypatch, error_code=error_code, detail=f"stub {error_code}")
    response = client.post("/", data=VALID_FORM)
    html = response.get_data(as_text=True)
    _assert_ai_error_page(html, status_code=503, response=response)
    assert _load_saved(data_path) == []


def test_ai_path_used_when_analyse_student_succeeds(client, monkeypatch):
    _patch_ai_success(monkeypatch, FAKE_AI)
    response = client.post("/", data=VALID_FORM, follow_redirects=True)
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Please reach out" in html
    assert "prominence-high" in html
    assert "Try to keep a regular sleep schedule" in html
    assert "Suggestions for you" in html
    assert "We couldn't complete your check-in" not in html


def test_high_severity_makes_advisor_panel_more_prominent(client, monkeypatch, data_path):
    _patch_ai_success(monkeypatch, FAKE_AI)
    response = client.post("/", data=HIGH_FORM, follow_redirects=True)
    html = response.get_data(as_text=True)
    assert "Please reach out" in html
    assert "prominence-high" in html
    assert "Contact support now" in html
    assert 'href="mailto:SITCounselling@SingaporeTech.edu.sg"' in html
    assert _load_saved(data_path) == []


def test_low_ai_outcome_uses_formatters_after_logic(client, monkeypatch):
    _patch_ai_success(monkeypatch, LOW_AI)
    response = client.post("/", data=VALID_FORM, follow_redirects=True)
    html = response.get_data(as_text=True)
    assert "You&#39;re doing ok" in html or "You're doing ok" in html
    assert "Suggestions for you" in html
    assert "Speak to advisor" in html
    assert "prominence-low" in html
    assert io_manager.ADVISOR_EMAIL in html


def test_save_without_opt_in_does_not_write(client, data_path, monkeypatch):
    _patch_ai_success(monkeypatch, LOW_AI)
    client.post("/", data=VALID_FORM, follow_redirects=True)
    response = client.post("/save", data={}, follow_redirects=True)
    html = response.get_data(as_text=True)
    assert "Nothing was saved" in html
    assert _load_saved(data_path) == []


def test_explicit_opt_in_saves_ai_processed_record(client, data_path, monkeypatch):
    _patch_ai_success(monkeypatch, LOW_AI)
    client.post("/", data=VALID_FORM, follow_redirects=True)
    response = client.post("/save", data={"opt_in": "yes"}, follow_redirects=True)
    html = response.get_data(as_text=True)
    assert "Saved on this computer" in html
    records = _load_saved(data_path)
    assert len(records) == 1
    assert records[0]["student_id"] == "2605581"
    assert records[0]["save_opt_in"] is True
    assert records[0]["source"] == logic_manager.LOGIC_SOURCE
    assert records[0]["ai_ok"] is True
    assert records[0]["soft_label"] in io_manager.SOFT_LABELS


def test_save_is_not_offered_on_ai_error_page(client, data_path):
    client.post("/", data=VALID_FORM)
    response = client.post("/save", data={"opt_in": "yes"}, follow_redirects=True)
    html = response.get_data(as_text=True)
    assert _load_saved(data_path) == []
    assert "Saved on this computer" not in html


def test_mailto_uses_official_sit_email_only(client, monkeypatch):
    _patch_ai_success(monkeypatch, FAKE_AI)
    html = client.post("/", data=HIGH_FORM, follow_redirects=True).get_data(as_text=True)
    assert html.count("mailto:") == 1
    assert "mailto:SITCounselling@SingaporeTech.edu.sg" in html
    assert "@" in html
    for token in ("gmail.com", "hotmail", "outlook.com", "counsellor@", "advisor@"):
        assert token not in html.lower()


def test_error_page_mailto_is_official_only(client):
    html = client.post("/", data=VALID_FORM).get_data(as_text=True)
    assert html.count("mailto:") == 1
    assert "mailto:SITCounselling@SingaporeTech.edu.sg" in html
    for token in ("gmail.com", "hotmail", "outlook.com", "counsellor@", "advisor@"):
        assert token not in html.lower()


def test_process_checkin_errors_when_ai_fails(monkeypatch):
    monkeypatch.setattr(
        ai_manager,
        "analyse_student",
        lambda *args, **kwargs: (
            False,
            None,
            {"error_code": "missing_api_key", "detail": "no key", "source": "gemini"},
        ),
    )
    record = {
        "student_id": "2605581",
        "sleep_hours": 8.0,
        "stress_level": 3,
        "academic_workload": 3,
        "financial_stress": 2,
        "social_support": 8,
        "feelings_text": "",
    }
    ok, result = flask_app.process_checkin(record)
    assert ok is False
    assert result["heading"] == "We couldn't complete your check-in"
    assert result["error_code"] == "missing_api_key"
    assert result["ai_required"] is True
    assert "soft_label" not in result
    assert "tips" not in result
    assert result.get("source") != logic_manager.LOGIC_SOURCE


def test_process_checkin_finalizes_ai_fields(monkeypatch):
    def fake_analyse(student_dict, **_kwargs):
        enriched = dict(student_dict)
        enriched.update(FAKE_AI)
        enriched["source"] = "gemini"
        return True, enriched, None

    monkeypatch.setattr(ai_manager, "analyse_student", fake_analyse)
    ok, result = flask_app.process_checkin({"student_id": "2605581", **{
        "sleep_hours": 8.0,
        "stress_level": 3,
        "academic_workload": 3,
        "financial_stress": 2,
        "social_support": 8,
        "feelings_text": "",
    }})
    assert ok is True
    assert result["source"] == logic_manager.LOGIC_SOURCE
    assert result["ai_ok"] is True
    assert result["soft_label"] == "Please reach out"
    assert result["tips"] == ["talk_to_someone", "sleep_routine"]


def test_process_checkin_does_not_let_logic_replace_missing_ai(monkeypatch):
    monkeypatch.setattr(
        ai_manager,
        "analyse_student",
        lambda *args, **kwargs: (False, None, None),
    )
    ok, result = flask_app.process_checkin({"student_id": "2605581"})
    assert ok is False
    assert result["error_code"] == "unavailable"
    assert "soft_label" not in result


def test_generate_fn_runs_full_ai_then_logic_pipeline(data_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def fake_generate(_prompt: str, _key: str, _model: str) -> str:
        return json.dumps(FAKE_AI)

    application = flask_app.create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATA_PATH": data_path,
            "AI_GENERATE_FN": fake_generate,
            "AI_MAX_ATTEMPTS": 1,
            "AI_RETRY_DELAY_SEC": 0,
        }
    )
    client = application.test_client()
    response = client.post("/", data=HIGH_FORM, follow_redirects=True)
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Please reach out" in html
    assert "prominence-high" in html
    client.post("/save", data={"opt_in": "yes"}, follow_redirects=True)
    records = _load_saved(data_path)
    assert len(records) == 1
    assert records[0]["source"] == "ai_logic"
    assert records[0]["ai_ok"] is True

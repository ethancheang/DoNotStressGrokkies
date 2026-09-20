"""Smoke tests for the student-facing Flask wiring."""

from __future__ import annotations

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


@pytest.fixture
def data_path(tmp_path):
    return str(tmp_path / "student_records.json")


@pytest.fixture
def client(data_path):
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


def test_submit_without_api_key_uses_logic_fallback(client, monkeypatch, data_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    response = client.post("/", data=VALID_FORM, follow_redirects=True)
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "You&#39;re doing ok" in html or "You're doing ok" in html
    assert "Suggestions for you" in html
    assert "Speak to advisor" in html
    assert io_manager.ADVISOR_EMAIL in html
    assert io_manager.ADVISOR_HELPLINE in html
    assert io_manager.ADVISOR_MAILTO in html
    assert "prominence-low" in html
    assert _load_saved(data_path) == []


def test_high_severity_makes_advisor_panel_more_prominent(client, monkeypatch, data_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    response = client.post("/", data=HIGH_FORM, follow_redirects=True)
    html = response.get_data(as_text=True)
    assert "Please reach out" in html
    assert "prominence-high" in html
    assert "Contact support now" in html
    assert 'href="mailto:SITCounselling@SingaporeTech.edu.sg"' in html
    assert _load_saved(data_path) == []


def test_ai_path_used_when_analyse_student_succeeds(client, monkeypatch):
    def fake_analyse(student_dict, **_kwargs):
        enriched = dict(student_dict)
        enriched.update(FAKE_AI)
        return True, enriched, None

    monkeypatch.setattr(ai_manager, "analyse_student", fake_analyse)
    response = client.post("/", data=VALID_FORM, follow_redirects=True)
    html = response.get_data(as_text=True)
    assert "Please reach out" in html
    assert "prominence-high" in html
    assert "Try to keep a regular sleep schedule" in html


def test_save_without_opt_in_does_not_write(client, data_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client.post("/", data=VALID_FORM, follow_redirects=True)
    response = client.post("/save", data={}, follow_redirects=True)
    html = response.get_data(as_text=True)
    assert "Nothing was saved" in html
    assert _load_saved(data_path) == []


def test_explicit_opt_in_saves_record(client, data_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client.post("/", data=VALID_FORM, follow_redirects=True)
    response = client.post("/save", data={"opt_in": "yes"}, follow_redirects=True)
    html = response.get_data(as_text=True)
    assert "Saved on this computer" in html
    records = _load_saved(data_path)
    assert len(records) == 1
    assert records[0]["student_id"] == "2605581"
    assert records[0]["save_opt_in"] is True
    assert records[0]["source"] == logic_manager.LOGIC_SOURCE
    assert records[0]["soft_label"] in io_manager.SOFT_LABELS


def test_mailto_uses_official_sit_email_only(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    html = client.post("/", data=HIGH_FORM, follow_redirects=True).get_data(as_text=True)
    assert html.count("mailto:") == 1
    assert "mailto:SITCounselling@SingaporeTech.edu.sg" in html
    assert "@" in html
    for token in ("gmail.com", "hotmail", "outlook.com", "counsellor@", "advisor@"):
        assert token not in html.lower()


def test_evaluate_checkin_falls_back_when_ai_fails(monkeypatch):
    monkeypatch.setattr(
        ai_manager,
        "analyse_student",
        lambda *args, **kwargs: (False, None, "no key"),
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
    result = flask_app.evaluate_checkin(record)
    assert result["source"] == logic_manager.LOGIC_SOURCE
    assert result["soft_label"] == "You're doing ok"


def test_evaluate_checkin_keeps_ai_fields(monkeypatch):
    def fake_analyse(student_dict, **_kwargs):
        enriched = dict(student_dict)
        enriched.update(FAKE_AI)
        return True, enriched, None

    monkeypatch.setattr(ai_manager, "analyse_student", fake_analyse)
    result = flask_app.evaluate_checkin({"student_id": "2605581"})
    assert result["source"] == "gemini"
    assert result["soft_label"] == "Please reach out"
    assert result["tips"] == ["talk_to_someone", "sleep_routine"]

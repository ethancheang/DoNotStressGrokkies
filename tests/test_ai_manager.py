"""Tests for ai_manager — schema validation, retries, and analyse_student."""

from __future__ import annotations

import json

import pytest

import ai_manager as am


SAMPLE_STUDENT = {
    "student_id": "2605581",
    "sleep_hours": 5.0,
    "stress_level": 8,
    "submission_rate": 45.0,
    "cca_count": 2,
    "financial_stress": True,
    "consecutive_absences": 3,
    "free_text_concern": "Struggling to keep up",
}

VALID_AI = {
    "risk_score": 0.82,
    "risk_category": "High",
    "primary_stressors": ["sleep_deprivation", "financial_pressure", "academic_disengagement"],
    "recommended_support": "Urgent counselling referral and financial aid check-in.",
    "confidence": 0.91,
    "reasoning": "Low sleep, high stress, low submission rate, absences, and financial stress.",
}


def _fake_ok(_prompt: str, _key: str, _model: str) -> str:
    return json.dumps(VALID_AI)


def _fake_malformed(_prompt: str, _key: str, _model: str) -> str:
    return "not-json-at-all"


def test_build_prompt_includes_key_fields():
    prompt = am.build_prompt(SAMPLE_STUDENT)
    assert "academic welfare specialist" in prompt.lower() or "welfare specialist" in prompt.lower()
    assert "2605581" in prompt
    assert "risk_score" in prompt
    assert "primary_stressors" in prompt
    assert "5.0" in prompt or "5" in prompt


def test_validate_ai_response_accepts_valid_dict():
    ok, result = am.validate_ai_response(VALID_AI)
    assert ok is True
    assert result["risk_score"] == pytest.approx(0.82)
    assert result["risk_category"] == "High"
    assert "financial_pressure" in result["primary_stressors"]


def test_validate_ai_response_accepts_json_string():
    ok, result = am.validate_ai_response(json.dumps(VALID_AI))
    assert ok is True
    assert result["confidence"] == pytest.approx(0.91)


def test_validate_rejects_missing_fields():
    bad = dict(VALID_AI)
    del bad["reasoning"]
    ok, err = am.validate_ai_response(bad)
    assert ok is False
    assert "reasoning" in err


def test_validate_rejects_bad_risk_score():
    bad = dict(VALID_AI)
    bad["risk_score"] = 1.5
    ok, err = am.validate_ai_response(bad)
    assert ok is False
    assert "risk_score" in err


def test_validate_rejects_bad_category():
    bad = dict(VALID_AI)
    bad["risk_category"] = "Critical"
    ok, err = am.validate_ai_response(bad)
    assert ok is False
    assert "risk_category" in err


def test_validate_rejects_non_list_stressors():
    bad = dict(VALID_AI)
    bad["primary_stressors"] = "sleep_deprivation"
    ok, err = am.validate_ai_response(bad)
    assert ok is False
    assert "primary_stressors" in err


def test_call_gemini_success_with_stub():
    ok, data, err = am.call_gemini("prompt", generate_fn=_fake_ok, max_attempts=1)
    assert ok is True
    assert err is None
    assert data["risk_category"] == "High"


def test_call_gemini_retries_then_fails_on_malformed():
    ok, data, err = am.call_gemini(
        "prompt",
        generate_fn=_fake_malformed,
        max_attempts=2,
        retry_delay_sec=0.0,
    )
    assert ok is False
    assert data is None
    assert err is not None
    assert "Schema validation failed" in err or "not valid JSON" in err


def test_call_gemini_retries_after_api_exception():
    calls = {"n": 0}

    def flaky(prompt: str, key: str, model: str) -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            raise TimeoutError("simulated timeout")
        return json.dumps(VALID_AI)

    ok, data, err = am.call_gemini(
        "prompt",
        generate_fn=flaky,
        max_attempts=3,
        retry_delay_sec=0.0,
    )
    assert ok is True
    assert data["risk_score"] == pytest.approx(0.82)
    assert calls["n"] == 2


def test_analyse_student_merges_ai_fields():
    ok, enriched, err = am.analyse_student(
        SAMPLE_STUDENT,
        generate_fn=_fake_ok,
        max_attempts=1,
    )
    assert ok is True
    assert err is None
    assert enriched["student_id"] == "2605581"
    assert enriched["sleep_hours"] == 5.0
    assert enriched["risk_score"] == pytest.approx(0.82)
    assert enriched["risk_category"] == "High"
    assert isinstance(enriched["primary_stressors"], list)
    assert enriched["recommended_support"]
    assert enriched["confidence"] == pytest.approx(0.91)
    assert enriched["reasoning"]


def test_analyse_student_soft_fails_without_crash():
    ok, enriched, err = am.analyse_student(
        SAMPLE_STUDENT,
        generate_fn=_fake_malformed,
        max_attempts=2,
        retry_delay_sec=0.0,
    )
    assert ok is False
    assert enriched is None
    assert isinstance(err, str) and len(err) > 0


def test_no_class_keyword_in_module_source():
    source = open(am.__file__, encoding="utf-8").read()
    assert "\nclass " not in source
    assert not source.strip().startswith("class ")


def test_module_has_no_print_or_input_calls():
    source = open(am.__file__, encoding="utf-8").read()
    assert "print(" not in source
    assert "input(" not in source

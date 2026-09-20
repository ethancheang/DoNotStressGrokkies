"""Tests for ai_manager — student schema, allow-lists, retries, merge."""

from __future__ import annotations

import json

import pytest

import ai_manager as am


SAMPLE_STUDENT = {
    "student_id": "2605581",
    "sleep_hours": 5.0,
    "stress_level": 8,
    "academic_workload": 7,
    "financial_stress": 6,
    "social_support": 3,
    "feelings_text": "Struggling to keep up",
}

VALID_AI = {
    "risk_score": 0.82,
    "risk_category": "High",
    "primary_stressors": [
        "sleep_deprivation",
        "high_stress",
        "academic_overload",
    ],
    "recommended_support": "Encourage rest and a confidential check-in.",
    "confidence": 0.91,
    "reasoning": "Sleep is low, stress and workload are high, and support feels thin.",
    "soft_label": "Please reach out",
    "tips": ["sleep_routine", "talk_to_someone", "feelings_check_in"],
    "speak_prominence": "high",
}

DROPPED_FIELD_NAMES = (
    "submission_rate",
    "cca_count",
    "consecutive_absences",
)


def _fake_ok(_prompt: str, _key: str, _model: str) -> str:
    return json.dumps(VALID_AI)


def _fake_malformed(_prompt: str, _key: str, _model: str) -> str:
    return "not-json-at-all"


def test_allowlists_match_io_manager_pr6():
    assert am.SOFT_LABELS == (
        "You're doing ok",
        "Worth a check-in",
        "Please reach out",
    )
    assert am.ALLOWED_TIP_IDS == frozenset(
        {
            "sleep_routine",
            "rest_a_little_more",
            "short_breaks",
            "workload_chunks",
            "money_worries",
            "talk_to_someone",
            "keep_social_contact",
            "feelings_check_in",
        }
    )
    assert am.SPEAK_PROMINENCE == ("low", "medium", "high")
    assert not hasattr(am, "ALLOWED_TIPS")
    assert not hasattr(am, "TIPS_ALLOWLIST")


def test_build_prompt_includes_feelings_text_and_student_fields():
    prompt = am.build_prompt(SAMPLE_STUDENT)
    assert "feelings_text" in prompt
    assert "Struggling to keep up" in prompt
    assert "2605581" in prompt
    assert "academic_workload" in prompt
    assert "social_support" in prompt
    assert "student-wellbeing" in prompt.lower() or "wellbeing assistant" in prompt.lower()
    assert "risk_score" in prompt
    assert "soft_label" in prompt
    assert "speak_prominence" in prompt
    assert "Never invent phone numbers, emails, or offices" in prompt
    assert "Do not include contact details in JSON" in prompt
    assert "You're doing ok" in prompt
    assert "tip IDs" in prompt
    for tip_id in am.ALLOWED_TIP_IDS:
        assert tip_id in prompt


def test_build_prompt_omits_dropped_fields():
    prompt = am.build_prompt(SAMPLE_STUDENT)
    for name in DROPPED_FIELD_NAMES:
        assert name not in prompt


def test_build_prompt_ignores_legacy_keys_on_input():
    legacy = dict(SAMPLE_STUDENT)
    legacy["submission_rate"] = 45.0
    legacy["cca_count"] = 2
    legacy["consecutive_absences"] = 3
    prompt = am.build_prompt(legacy)
    for name in DROPPED_FIELD_NAMES:
        assert name not in prompt


def test_validate_ai_response_accepts_valid_dict():
    ok, result = am.validate_ai_response(VALID_AI)
    assert ok is True
    assert result["risk_score"] == pytest.approx(0.82)
    assert result["risk_category"] == "High"
    assert "academic_overload" in result["primary_stressors"]
    assert result["soft_label"] == "Please reach out"
    assert result["speak_prominence"] == "high"
    assert 1 <= len(result["tips"]) <= 3
    assert all(tip in am.ALLOWED_TIP_IDS for tip in result["tips"])
    assert result["tips"] == ["sleep_routine", "talk_to_someone", "feelings_check_in"]


def test_validate_ai_response_accepts_json_string():
    ok, result = am.validate_ai_response(json.dumps(VALID_AI))
    assert ok is True
    assert result["confidence"] == pytest.approx(0.91)
    assert result["soft_label"] == VALID_AI["soft_label"]


def test_validate_keeps_ascii_youre_doing_ok():
    payload = dict(VALID_AI)
    payload["soft_label"] = "You're doing ok"
    payload["risk_category"] = "Low"
    payload["speak_prominence"] = "low"
    ok, result = am.validate_ai_response(payload)
    assert ok is True
    assert result["soft_label"] == "You're doing ok"


def test_validate_normalises_curly_youre_to_ascii():
    payload = dict(VALID_AI)
    payload["soft_label"] = "You’re doing ok"
    payload["risk_category"] = "Low"
    payload["speak_prominence"] = "low"
    ok, result = am.validate_ai_response(payload)
    assert ok is True
    assert result["soft_label"] == "You're doing ok"


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


def test_validate_rejects_off_list_soft_label():
    bad = dict(VALID_AI)
    bad["soft_label"] = "Critical — contact advisor now"
    ok, err = am.validate_ai_response(bad)
    assert ok is False
    assert "soft_label" in err


def test_validate_rejects_off_list_tip_ids():
    bad = dict(VALID_AI)
    bad["tips"] = ["emergency_hotline"]
    ok, err = am.validate_ai_response(bad)
    assert ok is False
    assert "tip" in err.lower()


def test_validate_rejects_free_text_tips():
    bad = dict(VALID_AI)
    bad["tips"] = ["Call 6592 2030 right now for emergency help."]
    ok, err = am.validate_ai_response(bad)
    assert ok is False
    assert "tip" in err.lower()


def test_validate_rejects_empty_or_too_many_tips():
    empty = dict(VALID_AI)
    empty["tips"] = []
    ok, err = am.validate_ai_response(empty)
    assert ok is False
    assert "tips" in err

    too_many = dict(VALID_AI)
    too_many["tips"] = [
        "sleep_routine",
        "rest_a_little_more",
        "short_breaks",
        "workload_chunks",
    ]
    ok, err = am.validate_ai_response(too_many)
    assert ok is False
    assert "tips" in err


def test_validate_rejects_off_list_speak_prominence():
    bad = dict(VALID_AI)
    bad["speak_prominence"] = "urgent"
    ok, err = am.validate_ai_response(bad)
    assert ok is False
    assert "speak_prominence" in err


def test_validate_rejects_off_list_primary_stressor():
    bad = dict(VALID_AI)
    bad["primary_stressors"] = ["academic_disengagement"]
    ok, err = am.validate_ai_response(bad)
    assert ok is False
    assert "allow-list" in err


def _assert_structured_error(err, *allowed_codes):
    assert isinstance(err, dict)
    assert set(err) >= {"error_code", "detail", "source"}
    assert err["error_code"] in allowed_codes
    assert err["error_code"] in am.AI_ERROR_CODES
    assert err["source"] == "gemini"
    assert isinstance(err["detail"], str) and err["detail"]
    for field in ("soft_label", "tips", "speak_prominence"):
        assert field not in err


def test_call_gemini_success_with_stub():
    ok, data, err = am.call_gemini("prompt", generate_fn=_fake_ok, max_attempts=1)
    assert ok is True
    assert err is None
    assert data["risk_category"] == "High"
    assert data["soft_label"] == "Please reach out"
    assert data["speak_prominence"] == "high"
    assert data["source"] == "gemini"


def test_call_gemini_retries_then_fails_on_malformed():
    ok, data, err = am.call_gemini(
        "prompt",
        generate_fn=_fake_malformed,
        max_attempts=2,
        retry_delay_sec=0.0,
    )
    assert ok is False
    assert data is None
    _assert_structured_error(err, "invalid_response", "retries_exhausted")
    assert "Schema validation failed" in err["detail"] or "not valid JSON" in err["detail"]


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
    assert data["soft_label"] == "Please reach out"
    assert calls["n"] == 2


def test_call_gemini_retries_on_off_list_payload_then_accepts():
    calls = {"n": 0}

    def first_bad(prompt: str, key: str, model: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            bad = dict(VALID_AI)
            bad["soft_label"] = "All good mate"
            return json.dumps(bad)
        return json.dumps(VALID_AI)

    ok, data, err = am.call_gemini(
        "prompt",
        generate_fn=first_bad,
        max_attempts=3,
        retry_delay_sec=0.0,
    )
    assert ok is True
    assert err is None
    assert data["soft_label"] == "Please reach out"
    assert calls["n"] == 2


def test_analyse_student_merges_io_and_ai_fields():
    ok, enriched, err = am.analyse_student(
        SAMPLE_STUDENT,
        generate_fn=_fake_ok,
        max_attempts=1,
    )
    assert ok is True
    assert err is None
    assert enriched["student_id"] == "2605581"
    assert enriched["sleep_hours"] == 5.0
    assert enriched["academic_workload"] == 7
    assert enriched["financial_stress"] == 6
    assert enriched["social_support"] == 3
    assert enriched["feelings_text"] == "Struggling to keep up"
    assert enriched["risk_score"] == pytest.approx(0.82)
    assert enriched["risk_category"] == "High"
    assert isinstance(enriched["primary_stressors"], list)
    assert enriched["recommended_support"]
    assert enriched["confidence"] == pytest.approx(0.91)
    assert enriched["reasoning"]
    assert enriched["soft_label"] == "Please reach out"
    assert enriched["tips"] == VALID_AI["tips"]
    assert enriched["speak_prominence"] == "high"
    assert enriched["source"] == "gemini"
    for name in DROPPED_FIELD_NAMES:
        assert name not in enriched


def test_analyse_student_soft_fails_without_crash():
    ok, enriched, err = am.analyse_student(
        SAMPLE_STUDENT,
        generate_fn=_fake_malformed,
        max_attempts=2,
        retry_delay_sec=0.0,
    )
    assert ok is False
    assert enriched is None
    _assert_structured_error(err, "invalid_response", "retries_exhausted")


def test_analyse_student_rejects_non_dict_without_raising():
    ok, enriched, err = am.analyse_student(
        "not-a-record",  # type: ignore[arg-type]
        generate_fn=_fake_ok,
        max_attempts=1,
    )
    assert ok is False
    assert enriched is None
    _assert_structured_error(err, "invalid_response")
    assert "dict" in err["detail"]


def test_no_class_keyword_in_module_source():
    source = open(am.__file__, encoding="utf-8").read()
    assert "\nclass " not in source
    assert not source.strip().startswith("class ")


def test_module_has_no_print_or_input_calls():
    source = open(am.__file__, encoding="utf-8").read()
    assert "print(" not in source
    assert "input(" not in source


def test_module_does_not_hardcode_gemini_key():
    source = open(am.__file__, encoding="utf-8").read()
    assert "AIza" not in source
    assert "os.environ.get(\"GEMINI_API_KEY\"" in source


def test_module_has_no_invented_tip_sentences():
    source = open(am.__file__, encoding="utf-8").read()
    assert "ALLOWED_TIPS =" not in source
    invented = (
        "Keep a regular sleep window",
        "Try a 10-minute reset",
        "Break the next assignment",
        "Talk to someone you trust about how school has felt lately.",
        "Check in with SIT Counselling if you want a confidential conversation.",
        "If money stress is high, ask Student Services",
    )
    for sentence in invented:
        assert sentence not in source


def test_module_has_no_logic_fallback():
    source = open(am.__file__, encoding="utf-8").read()
    assert "import logic_manager" not in source
    assert "from logic_manager" not in source
    assert "logic_fallback" not in source
    assert "apply_soft_outcome" not in source
    assert "assign_soft_outcome" not in source


def test_call_gemini_missing_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    called = {"n": 0}

    def must_not_run(_prompt: str, _key: str, _model: str) -> str:
        called["n"] += 1
        raise AssertionError("Gemini must not be called when the API key is missing")

    # Real path: no generate_fn, blank env key → do not attempt the API.
    monkeypatch.setattr(am, "_default_generate", must_not_run)
    ok, data, err = am.call_gemini("prompt", max_attempts=3, retry_delay_sec=0.0)
    assert ok is False
    assert data is None
    assert called["n"] == 0
    _assert_structured_error(err, "missing_api_key")
    assert "GEMINI_API_KEY" in err["detail"]


def test_analyse_student_missing_api_key_does_not_invent_product(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    ok, enriched, err = am.analyse_student(SAMPLE_STUDENT, max_attempts=1)
    assert ok is False
    assert enriched is None
    _assert_structured_error(err, "missing_api_key")


def test_call_gemini_timeout_stub():
    def boom(_prompt: str, _key: str, _model: str) -> str:
        raise TimeoutError("simulated timeout")

    ok, data, err = am.call_gemini(
        "prompt",
        generate_fn=boom,
        max_attempts=1,
        retry_delay_sec=0.0,
    )
    assert ok is False
    assert data is None
    _assert_structured_error(err, "timeout", "retries_exhausted")
    assert err["error_code"] == "timeout"


def test_call_gemini_timeout_after_retries_stays_timeout_or_exhausted():
    def boom(_prompt: str, _key: str, _model: str) -> str:
        raise TimeoutError("DeadlineExceeded: timed out")

    ok, data, err = am.call_gemini(
        "prompt",
        generate_fn=boom,
        max_attempts=3,
        retry_delay_sec=0.0,
    )
    assert ok is False
    assert data is None
    _assert_structured_error(err, "timeout", "retries_exhausted")


def test_call_gemini_other_api_exception_exhausted():
    def boom(_prompt: str, _key: str, _model: str) -> str:
        raise ConnectionError("gemini unreachable")

    ok, data, err = am.call_gemini(
        "prompt",
        generate_fn=boom,
        max_attempts=3,
        retry_delay_sec=0.0,
    )
    assert ok is False
    assert data is None
    _assert_structured_error(err, "retries_exhausted", "unavailable")
    assert err["error_code"] == "retries_exhausted"


def test_call_gemini_other_api_exception_one_shot_unavailable():
    def boom(_prompt: str, _key: str, _model: str) -> str:
        raise ConnectionError("gemini unreachable")

    ok, data, err = am.call_gemini(
        "prompt",
        generate_fn=boom,
        max_attempts=1,
        retry_delay_sec=0.0,
    )
    assert ok is False
    assert data is None
    _assert_structured_error(err, "unavailable")


def test_malformed_json_after_retries_is_invalid_or_exhausted():
    ok, data, err = am.call_gemini(
        "prompt",
        generate_fn=_fake_malformed,
        max_attempts=3,
        retry_delay_sec=0.0,
    )
    assert ok is False
    assert data is None
    _assert_structured_error(err, "invalid_response", "retries_exhausted")


def test_analyse_student_malformed_does_not_invent_soft_fields():
    ok, enriched, err = am.analyse_student(
        SAMPLE_STUDENT,
        generate_fn=_fake_malformed,
        max_attempts=3,
        retry_delay_sec=0.0,
    )
    assert ok is False
    assert enriched is None
    _assert_structured_error(err, "invalid_response", "retries_exhausted")


def test_classify_ai_error_mapping():
    assert am.classify_ai_error(TimeoutError("timed out")) == "timeout"
    assert am.classify_ai_error("DeadlineExceeded") == "timeout"
    assert am.classify_ai_error("GEMINI_API_KEY is not set") == "missing_api_key"
    assert am.classify_ai_error("Schema validation failed: not valid JSON") == (
        "invalid_response"
    )
    assert am.classify_ai_error(ConnectionError("dns")) == "unavailable"
    assert am.classify_ai_error({"error_code": "retries_exhausted"}) == (
        "retries_exhausted"
    )


def test_error_codes_match_io_format_ai_error():
    expected = (
        "missing_api_key",
        "timeout",
        "invalid_response",
        "retries_exhausted",
        "unavailable",
    )
    assert am.AI_ERROR_CODES == expected

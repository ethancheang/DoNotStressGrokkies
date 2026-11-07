"""Gemini calculates the stress average from raw answers. These tests never call the API.

AIManager holds no scoring rules. Where a test needs them it hands AIManager
the Logic layer's auditor, exactly as App does.
"""
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from views.student_copy import StudentCopy
from ai.validators.soft_label_validator import SoftLabelValidator
from ai.validators.stressors_validator import StressorsValidator
from ai.validators.tips_validator import TipsValidator
import survey
from ai.ai_failure import AIFailure
from ai.ai_result import AIResult
from ai.error_classifier import ErrorClassifier
from ai.score_auditor import ScoreAuditor
from ai_manager import AIManager
from logic.stress_scorer import StressScorer
from base_manager import BaseManager
from plain_tests import capture_logs, function_suite
from ai.fake_provider import FakeProvider
from ai.gemini_provider import GeminiProvider
from questions.question import Question

AUDITOR = StressScorer()
QUESTIONS = survey.QUESTIONNAIRE.questions
ANSWER_KEYS = survey.QUESTIONNAIRE.keys


def _manager(provider=None, *, audited=True, max_attempts=3, questions=None):
    """An AIManager with the real questionnaire, no retry delay and (by default) Logic's auditor."""
    return AIManager(provider if provider is not None else FakeProvider(),
                     QUESTIONS if questions is None else questions,
                     auditor=AUDITOR if audited else None,
                     max_attempts=max_attempts, retry_delay_sec=0)


def _checkin():
    """A full record with scores and a reflection Gemini must not see."""
    return {
        "student_id": "2605581",
        "feelings_text": "PRIVATE REFLECTION that must stay off the prompt",
        "survey_version": survey.VERSION,
        "pss_1": 4,
        "pss_2": 2,
        "pss_3": 5,
        "pss_4": 3,
        "sleep_hours_avg": 6.5,
        "sleep_quality": 4,
        "pas_workload": 5,
        "pas_catchup": 2,
        "fin_stress": 1,
        "mspss_friends": 2,
        "mspss_family": 5,
        "stress_score": 9.99,
        "scored_item_count": 11,
        "support_mean": 1.25,
        "support_item_count": 2,
        "context_flags": {"SENTINEL_FLAG": True},
        "risk_category": "SENTINEL_CATEGORY",
        "soft_label": "SENTINEL_SOFT_LABEL",
        "speak_prominence": "SENTINEL_PROMINENCE",
        "safety_flag": True,
        "risk_score": 0.99,
    }


def _gemini(**overrides):
    """A Moderate reply. Overrides replace fields; they do not fill gaps."""
    payload = {
        "stress_score": 3.0,
        "risk_category": "Moderate",
        "primary_stressors": ["academic_overload"],
        "scored_items": {key: 3 for key in ANSWER_KEYS},
        "confidence": 0.8,
        "reasoning": (
            "School looks a bit heavy right now. "
            "A smaller plan for the week could take some of the pressure off."
        ),
        "soft_label": "Worth a check-in",
        "tips": ["workload_chunks", "short_breaks"],
        "speak_prominence": "medium",
    }
    payload.update(overrides)
    return payload


def _for_score(score, **overrides):
    """Tier fields that match score, plus any extra overrides."""
    if score < 2.5:
        category, label, prominence = "Low", "You're doing ok", "low"
    elif score <= 3.5:
        category, label, prominence = "Moderate", "Worth a check-in", "medium"
    else:
        category, label, prominence = "High", "Please reach out", "high"
    payload = _gemini(
        stress_score=score,
        risk_category=category,
        soft_label=label,
        speak_prominence=prominence,
    )
    payload.update(overrides)
    return payload


def _expected(answers):
    """What Gemini should return for these answers, from logic_manager (the formula's only owner)."""
    return AUDITOR.scored_items(answers), AUDITOR.score(answers).stress_score


def _all_threes():
    """Answers that score 3 on every item: stress_score 3.0 (Moderate)."""
    answers = {key: 3 for key in ANSWER_KEYS}
    answers["sleep_hours_avg"] = 6.5
    return answers


def _input_payload(prompt):
    """The JSON object at the end of the prompt is the only student data."""
    start = prompt.rfind("{")
    return json.loads(prompt[start:])


def _validate(payload):
    return _manager().validate_response(payload)


# --- Manager ---------------------------------------------------------------

def test_ai_manager_is_a_manager_with_a_health_summary():
    manager = _manager(FakeProvider())
    assert isinstance(manager, BaseManager)
    health = manager.health()
    assert health["name"] == "ai_manager"
    assert health["provider"] == "fake"
    assert health["ready"] is True
    assert health["models"] == list(GeminiProvider.MODEL_CHAIN)
    assert health["validated_fields"] == list(manager.required_fields)
    secret = AIManager(GeminiProvider("sk-secret-health"), QUESTIONS).health()
    assert "sk-secret-health" not in json.dumps(secret)


def test_the_same_pipeline_runs_with_any_provider():
    """Polymorphism: AIManager never branches on the provider type."""
    reply = json.dumps(_for_score(3.0))
    fake_gemini = SimpleNamespace(text=reply)

    def client(**kwargs):
        return SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: fake_gemini))

    with patch("google.genai.Client", client):
        for provider in (FakeProvider(reply), GeminiProvider("key")):
            result = _manager(provider, audited=False).call_api("prompt")
            assert result.ok, (provider.name, result.failure)
            assert result.fields["stress_score"] == 3.0


# --- Prompt ----------------------------------------------------------------

def test_prompt_has_raw_answers_and_wording_only():
    prompt = _manager().build_prompt(_checkin())
    payload = _input_payload(prompt)

    assert set(payload) == set(_manager().prompt_fields)
    assert payload["pss_1"] == 4
    assert payload["pss_2"] == 2
    assert payload["sleep_hours_avg"] == 6.5
    assert payload["mspss_family"] == 5
    assert payload["survey_version"] == survey.VERSION
    for banned in (
        "student_id",
        "feelings_text",
        "stress_score",
        "context_flags",
        "risk_category",
        "soft_label",
        "speak_prominence",
        "support_mean",
        "scored_item_count",
        "risk_score",
        "safety_flag",
    ):
        assert banned not in payload

    assert survey.QUESTIONNAIRE.question("pss_1").prompt in prompt
    assert survey.QUESTIONNAIRE.question("fin_stress").prompt in prompt
    assert "1 = Never" in prompt
    assert "5 = Very often" in prompt
    assert "1 = No stress at all" in prompt
    assert "5 = Overwhelming stress" in prompt
    assert "half-hour" in prompt
    assert "positively worded" in prompt.lower()
    assert "Talk to someone" in prompt
    assert "SIT Counselling" in prompt

    assert "2605581" not in prompt
    assert "PRIVATE REFLECTION" not in prompt
    assert "student_id" not in prompt
    assert "feelings_text" not in prompt
    assert "context_flags" not in prompt
    assert "SENTINEL_FLAG" not in prompt
    assert "SENTINEL_CATEGORY" not in prompt
    assert "SENTINEL_SOFT_LABEL" not in prompt
    assert "SENTINEL_PROMINENCE" not in prompt
    assert "9.99" not in prompt
    assert "support_mean" not in prompt
    assert "risk_score" not in prompt
    assert "Speak to advisor" not in prompt
    assert "advisor dashboard" not in prompt
    assert "emotional_distress" not in prompt
    assert "feelings_check_in" not in prompt
    assert "6 - answer" in prompt
    assert "scored_items" in prompt
    assert "rounded to 2 decimal places" in prompt
    assert "8 or more hours -> 1" in prompt
    assert "otherwise 5" in prompt
    assert "estimate" not in prompt.lower()


def test_ai_manager_holds_no_scoring_rules():
    """The formula and tier cut-offs live only in logic_manager (brief: no domain logic here)."""
    import ai_manager
    for name in ("expected_stress_score", "LOW_BELOW", "HIGH_ABOVE", "POSITIVE_ITEM_KEYS",
                 "_category_for_stress_score", "_tier_consistency_error", "_formula_mismatch",
                 "_risk_score_from_stress", "_RECOMMENDED_SUPPORT", "logic_manager", "survey"):
        assert not hasattr(ai_manager, name), name

    bare = _manager(audited=False).build_prompt(_checkin())
    assert "6 - answer" not in bare
    assert "below 2.5" not in bare
    with_rules = _manager().build_prompt(_checkin())
    assert AUDITOR.instructions() in with_rules

    # Schema only: a well-formed reply with the wrong tier still passes here.
    wrong_tier = _for_score(2.0, risk_category="High", soft_label="Please reach out",
                            speak_prominence="high")
    ok, result = _validate(wrong_tier)
    assert ok, result
    assert "risk_score" not in result
    assert "recommended_support" not in result


def test_caller_can_pass_question_wording():
    def generate(prompt, model_name):
        scored, stress = _expected(_checkin())
        return json.dumps(_for_score(
            stress, scored_items=scored, tips=["short_breaks"], primary_stressors=[],
        ))

    provider = FakeProvider(generate)
    wording = list(QUESTIONS)
    wording[0] = Question("pss_1", "Control", "UNIQUE WORDING XYZ", 1, 2, ("No", "Yes"))
    result = _manager(provider, audited=False, max_attempts=1, questions=wording).analyse(_checkin())
    assert result.ok, result.failure
    sent = provider.calls[0][0]
    assert "UNIQUE WORDING XYZ" in sent
    assert "1 = No" in sent
    assert "2605581" not in sent
    scored, stress = _expected(_checkin())
    assert result.fields["source"] == "gemini"
    assert result.fields["stress_score"] == stress
    assert result.fields["scored_items"] == scored


def test_non_dict_check_in_is_an_invalid_response():
    provider = FakeProvider(_ok_body())
    result = _manager(provider).analyse(["not", "a", "record"])
    assert not result.ok
    assert result.failure.code == AIFailure.INVALID_RESPONSE
    assert provider.calls == []


# --- Response Validation ---------------------------------------------------

def test_valid_response_is_normalised():
    supplied = _for_score(2.5)
    supplied["risk_score"] = 0.99
    supplied["recommended_support"] = "Speak to advisor"
    ok, result = _validate(json.dumps(supplied))
    assert ok, result
    assert result["stress_score"] == 2.5
    assert result["risk_category"] == "Moderate"
    assert result["soft_label"] == "Worth a check-in"
    assert result["speak_prominence"] == "medium"
    # Extra keys from Gemini are dropped. Logic works these two out.
    assert "risk_score" not in result
    assert "recommended_support" not in result

    for score in (1.0, 3.0, 5.0):
        ok, result = _validate(_for_score(score))
        assert ok, result
        assert result["stress_score"] == score


def test_band_edges_and_stripped_category():
    for score in (1, 2.49, 2.5, 3.5, 3.51, 5):
        ok, result = _validate(_for_score(score))
        assert ok, (score, result)
        assert result["stress_score"] == float(score)

    padded = _for_score(3.0, risk_category="  Moderate  ")
    ok, result = _validate(padded)
    assert ok, result
    assert result["risk_category"] == "Moderate"


def test_out_of_range_stress_score_fails():
    for bad in (0.9, 5.1, 0, 6, -1, True, False, None, "high", "",
                float("nan"), float("inf"), float("-inf")):
        ok, message = _validate(_for_score(3.0, stress_score=bad))
        assert not ok, bad
        assert "stress_score" in message


def test_malformed_replies_are_rejected_with_a_reason():
    assert _validate("") == (False, "Empty AI response string.")
    assert _validate("[]") == (False, "AI response must be a JSON object.")
    ok, message = _validate("{broken")
    assert not ok and "not valid JSON" in message
    reply = _for_score(3.0)
    del reply["tips"], reply["confidence"]
    ok, message = _validate(reply)
    assert not ok
    assert message == "AI response missing required fields: tips, confidence."


def test_tier_mismatch_fails_the_logic_check():
    """A reply whose tier disagrees with its score is retried, then rejected.

    The tier rule is logic_manager's; AIManager runs it through the auditor.
    """
    low_score_high_tier = _for_score(
        2.0,
        risk_category="High",
        soft_label="Please reach out",
        speak_prominence="high",
    )
    label_mismatch = _for_score(
        4.0,
        risk_category="High",
        soft_label="You're doing ok",
        speak_prominence="high",
    )
    prominence_mismatch = _for_score(
        4.0,
        risk_category="High",
        soft_label="Please reach out",
        speak_prominence="low",
    )
    for reply in (low_score_high_tier, label_mismatch, prominence_mismatch):
        assert _validate(reply)[0]
        result = _manager(FakeProvider(json.dumps(reply)), max_attempts=1).call_api(
            "check-in", answers=_all_threes())
        assert not result.ok
        assert result.fields is None
        assert result.failure.code == "invalid_response"


def test_removed_ids_are_rejected():
    assert "emotional_distress" not in StressorsValidator.ALLOWED
    assert "feelings_check_in" not in TipsValidator.ALLOWED
    assert not _validate(_for_score(3.0, primary_stressors=["emotional_distress"]))[0]
    assert not _validate(_for_score(3.0, primary_stressors=["academic_overload", "emotional_distress"]))[0]
    assert not _validate(_for_score(3.0, tips=["feelings_check_in"]))[0]
    assert not _validate(_for_score(3.0, tips=["short_breaks", "feelings_check_in"]))[0]


def test_remaining_tip_ids_still_format():
    assert TipsValidator.ALLOWED <= set(StudentCopy.TIPS)
    formatted = StudentCopy().tips(sorted(TipsValidator.ALLOWED))
    assert {item["id"] for item in formatted["items"]} == set(TipsValidator.ALLOWED)
    legacy = StudentCopy().tips(["feelings_check_in"])
    assert legacy["items"][0]["id"] == "feelings_check_in"


# --- Gemini Call -----------------------------------------------------------

def test_mismatch_is_an_invalid_response():
    reply = _for_score(4.2, risk_category="Low", soft_label="You're doing ok",
                       speak_prominence="low")
    result = _manager(FakeProvider(json.dumps(reply)), max_attempts=1).call_api("check-in", answers=_all_threes())
    assert not result.ok
    assert result.fields is None
    assert result.failure.code == "invalid_response"
    assert result.failure.source == "gemini"
    assert result.failure.as_dict()["error_code"] == "invalid_response"


def test_missing_api_key_does_not_call_generator():
    def client_must_not_be_built(**kwargs):
        raise AssertionError("Gemini must not be called without a key")

    with patch("google.genai.Client", client_must_not_be_built):
        result = _manager(GeminiProvider(api_key="  ")).call_api("check-in")
    assert not result.ok
    assert result.fields is None
    assert result.failure.code == "missing_api_key"
    assert result.failure.source == "gemini"

    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
        with patch("google.genai.Client", client_must_not_be_built):
            result = _manager(GeminiProvider()).call_api("check-in")
    assert result.failure.code == "missing_api_key"


def test_structured_schema_is_sent_with_the_mime_type():
    captured = {}

    def fake_generate_content(*, model, contents, config):
        captured["model"] = model
        captured["contents"] = contents
        captured["config"] = config
        return SimpleNamespace(text=json.dumps(_for_score(3.0)))

    def fake_client(*, api_key, http_options):
        captured["api_key"] = api_key
        return SimpleNamespace(models=SimpleNamespace(generate_content=fake_generate_content))

    manager = _manager(GeminiProvider("secret-key"), audited=False)
    with patch("google.genai.Client", fake_client):
        assert manager.call_api("prompt text").ok

    assert captured["api_key"] == "secret-key"
    assert captured["model"] == "gemini-3.6-flash"
    assert captured["contents"] == "prompt text"
    config = captured["config"]
    assert config["response_mime_type"] == "application/json"
    assert config["response_schema"] is manager.response_schema
    assert config["temperature"] == 0.0
    schema = manager.response_schema
    assert "risk_score" not in schema["properties"]
    assert schema["required"] == list(manager.required_fields)

    properties = schema["properties"]
    assert properties["risk_category"]["enum"] == ["Low", "Moderate", "High"]
    assert properties["soft_label"]["enum"] == list(SoftLabelValidator.LABELS)
    assert properties["speak_prominence"]["enum"] == ["low", "medium", "high"]
    assert set(properties["primary_stressors"]["items"]["enum"]) == set(StressorsValidator.ALLOWED)
    assert set(properties["tips"]["items"]["enum"]) == set(TipsValidator.ALLOWED)
    assert (properties["tips"]["minItems"], properties["tips"]["maxItems"]) == (1, 3)
    assert "emotional_distress" not in properties["primary_stressors"]["items"]["enum"]
    assert "feelings_check_in" not in properties["tips"]["items"]["enum"]
    scored_items = properties["scored_items"]
    assert scored_items["type"] == "OBJECT"
    assert set(scored_items["required"]) == set(ANSWER_KEYS)
    assert set(scored_items["properties"]) == set(ANSWER_KEYS)
    for spec in scored_items["properties"].values():
        assert spec == {"type": "INTEGER", "minimum": 1, "maximum": 5}
    assert "estimate" not in json.dumps(schema).lower()

    from google.genai import types
    types.GenerateContentConfig.model_validate({
        "temperature": 0.0,
        "response_mime_type": "application/json",
        "response_schema": schema,
        "automatic_function_calling": {"disable": True},
    })


def _minimum_stress():
    """Answers that convert to 1 on every item. stress_score is 1.00."""
    return {
        "pss_1": 1,
        "pss_2": 5,
        "pss_3": 5,
        "pss_4": 1,
        "sleep_hours_avg": 8,
        "sleep_quality": 1,
        "pas_workload": 1,
        "pas_catchup": 1,
        "fin_stress": 1,
        "mspss_friends": 5,
        "mspss_family": 5,
        "survey_version": "evidence-v3",
    }


def _exact_reply(answers, **overrides):
    scored, stress = _expected(answers)
    payload = _for_score(stress, scored_items=scored)
    payload.update(overrides)
    return payload


# --- Formula check ---------------------------------------------------------
# The formula itself is tested in test_logic_manager. These tests check that
# AIManager runs the auditor's verify() on every reply it is given.

def test_exact_response_passes():
    answers = _minimum_stress()
    ok, result = _validate(_exact_reply(answers))
    assert ok, result
    assert AUDITOR.verify(result, answers) is None
    assert result["scored_items"] == {key: 1 for key in ANSWER_KEYS}
    assert result["stress_score"] == 1.0
    assert result["risk_category"] == "Low"

    analysis = _manager(FakeProvider(json.dumps(_exact_reply(answers))), max_attempts=1).analyse(answers)
    assert analysis.ok, analysis.failure
    assert analysis.fields["stress_score"] == 1.0
    assert analysis.fields["scored_items"]["sleep_hours_avg"] == 1


def test_off_by_one_scored_item_fails():
    answers = _minimum_stress()
    reply = _exact_reply(answers)
    reply["scored_items"] = dict(reply["scored_items"])
    reply["scored_items"]["pss_1"] = 2
    message = AUDITOR.verify(reply, answers)
    assert "scored_items" in message

    result = _manager(FakeProvider(json.dumps(reply)), max_attempts=1).call_api("check-in", answers=answers)
    assert not result.ok
    assert result.fields is None
    assert result.failure.code == "invalid_response"

    # Without the auditor, AIManager only validates the schema.
    assert _validate(reply)[0]
    result = _manager(FakeProvider(json.dumps(reply)), audited=False, max_attempts=1).call_api(
        "check-in", answers=answers)
    assert result.ok, result.failure


def test_stress_score_off_by_a_tenth_fails():
    answers = _minimum_stress()
    reply = _exact_reply(answers, stress_score=1.1)
    message = AUDITOR.verify(reply, answers)
    assert "stress_score" in message

    result = _manager(FakeProvider(json.dumps(reply)), max_attempts=1).analyse(answers)
    assert not result.ok
    assert result.failure.code == "invalid_response"


class BrokenAuditor(ScoreAuditor):
    """A ScoreAuditor whose check has a bug."""

    def instructions(self):
        return ""

    def verify(self, ai_fields, answers):
        raise ValueError("bug in the check")


def test_a_broken_check_is_an_invalid_response_not_a_crash():
    manager = AIManager(FakeProvider(json.dumps(_for_score(3.0))), QUESTIONS,
                        BrokenAuditor(), max_attempts=1, retry_delay_sec=0)
    result = manager.call_api("check-in", answers=_all_threes())
    assert not result.ok
    assert result.fields is None
    assert result.failure.code == "invalid_response"
    assert "Score check could not run" in result.failure.detail


def api_fault(message, code=None):
    """Build the error a fake Gemini raises, with an optional HTTP status code."""
    error = RuntimeError(message)
    error.code = code
    return error


def _ok_body():
    return json.dumps(_for_score(3.0))


# --- Fallback --------------------------------------------------------------

def _call(*replies):
    """Run call_api against a scripted FakeProvider; return (result, models called)."""
    provider = FakeProvider(*replies)
    result = _manager(provider, audited=False).call_api("check-in")
    return result, provider.models_called


def test_model_order_and_call_cap():
    assert GeminiProvider.MODEL_CHAIN == ("gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite")
    assert "gemini-flash-latest" not in GeminiProvider.MODEL_CHAIN
    assert AIManager.MAX_TOTAL_CALLS == 4


def test_timeout_then_success_retries_the_same_model():
    result, calls = _call(api_fault("timed out"), _ok_body())
    assert result.ok, result.failure
    assert result.failure is None
    assert result.fields["source"] == "gemini"
    assert calls == ["gemini-3.6-flash", "gemini-3.6-flash"]


def test_503_on_first_model_falls_back():
    def by_model(prompt, model_name):
        if model_name == "gemini-3.6-flash":
            raise api_fault("503 unavailable high demand", 503)
        return _ok_body()

    result, calls = _call(by_model)
    assert result.ok, result.failure
    assert calls == ["gemini-3.6-flash", "gemini-3.5-flash"]


def test_404_falls_back_without_retrying_the_same_model():
    result, calls = _call(api_fault("404 not found", 404), _ok_body())
    assert result.ok, result.failure
    assert calls == ["gemini-3.6-flash", "gemini-3.5-flash"]


def test_429_moves_to_the_next_model_without_a_retry():
    result, calls = _call(api_fault("429 too many requests", 429), _ok_body())
    assert result.ok, result.failure
    assert calls == ["gemini-3.6-flash", "gemini-3.5-flash"]


def test_every_model_rate_limited():
    result, calls = _call(api_fault("resource exhausted quota", 429))
    assert not result.ok
    assert result.fields is None
    assert result.failure.code == "rate_limited"
    assert calls == list(GeminiProvider.MODEL_CHAIN)
    copy = StudentCopy().ai_error("rate_limited")
    assert copy["error_code"] == "rate_limited"
    assert copy["body"] == ("Our check-in assistant is busy right now. "
        "Your answers have been saved and will be reviewed soon.")
    assert copy["error"] is None


def test_bad_json_is_invalid_after_the_call_cap():
    result, calls = _call("not json")
    assert not result.ok
    assert result.fields is None
    assert result.failure.code == "invalid_response"
    assert len(calls) == AIManager.MAX_TOTAL_CALLS


def test_fenced_json_is_parsed_before_validation():
    result, _ = _call("```json\n" + _ok_body() + "\n```")
    assert result.ok, result.failure


def test_missing_key_never_calls_the_generator():
    fake = FakeProvider(_ok_body(), ready=False)
    result = _manager(fake).call_api("check-in")
    assert not result.ok
    assert result.fields is None
    assert result.failure.code == "missing_api_key"
    assert fake.calls == []


def test_a_missing_key_error_from_the_provider_stops_at_once():
    result, calls = _call(RuntimeError("GEMINI_API_KEY is not set"))
    assert result.failure.code == "missing_api_key"
    assert calls == ["gemini-3.6-flash"]


def test_total_calls_never_exceed_the_cap():
    result, calls = _call(api_fault("timed out"))
    assert not result.ok
    assert result.failure.code == "timeout"
    assert len(calls) == AIManager.MAX_TOTAL_CALLS
    assert max(calls.count(name) for name in calls) <= 2


def test_a_retried_model_that_still_errors_ends_as_retries_exhausted():
    provider = FakeProvider(api_fault("timed out"), api_fault("500 internal error", 500),
                            models=("solo-model",))
    result = _manager(provider, audited=False).call_api("check-in")
    assert result.failure.code == "retries_exhausted"
    assert provider.models_called == ["solo-model", "solo-model"]


def test_api_key_is_absent_from_logs_and_error_detail():
    secret = "sk-live-DO-NOT-PRINT-991122"
    calls = []

    def fake_client(*, api_key, http_options):
        def generate_content(*, model, contents, config):
            calls.append(model)
            raise api_fault(f"403 permission denied using {api_key}", 403)
        return SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))

    with patch("google.genai.Client", fake_client), \
            capture_logs("ai_manager", level="DEBUG") as captured:
        result = _manager(GeminiProvider(secret)).call_api("check-in")
    assert not result.ok
    assert result.fields is None
    assert result.failure.code != "missing_api_key"
    blob = "\n".join(captured.output) + "\n" + result.failure.detail
    assert secret not in blob
    assert "[redacted]" in result.failure.detail
    assert len(calls) <= AIManager.MAX_TOTAL_CALLS


# --- Result objects --------------------------------------------------------

def test_failure_codes_are_normalised_and_results_are_one_or_the_other():
    assert AIFailure("made_up").code == "unavailable"
    assert AIFailure("timeout", "slow").as_dict() == {
        "error_code": "timeout", "detail": "slow", "source": "gemini"}
    assert AIResult(fields={"a": 1}).ok
    assert not AIResult(failure=AIFailure("timeout")).ok
    assert not AIResult().ok


def test_error_classifier_maps_messages_and_status_codes():
    classifier = ErrorClassifier()
    assert classifier.classify(TimeoutError("deadline exceeded")) == "timeout"
    assert classifier.classify("GEMINI_API_KEY is missing") == "missing_api_key"
    assert classifier.classify(api_fault("slow down", 429)) == "rate_limited"
    assert classifier.classify("malformed JSON body") == "invalid_response"
    assert classifier.classify("retries exhausted") == "retries_exhausted"
    assert classifier.classify(None) == "unavailable"
    assert classifier.classify(ConnectionError("network unreachable")) == "unavailable"


def test_rate_limit_still_saves_a_pending_checkin():
    from helpers import campus, post_checkin, stored_rows

    with campus(FakeProvider(api_fault("429 quota", 429))) as ctx:
        ctx.values["feelings_text"] = "PRIVATE NOTE that must not be stored"
        response = post_checkin(ctx)
        assert response.status_code == 503
        assert response.json["error_code"] == "rate_limited"
        stored = stored_rows(ctx)
        assert stored[0]["status"] == "pending"
        assert "feelings_text" not in stored[0]
        assert "PRIVATE NOTE" not in ctx.path.read_text(encoding="utf-8")


def load_tests(loader, tests, pattern):
    """Let `python -m unittest discover -s tests` run this file's test_ functions."""
    return function_suite(globals())


if __name__ == "__main__":
    unittest.main()

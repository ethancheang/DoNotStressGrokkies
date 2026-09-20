"""Unit tests for logic_manager post-AI finalizer (Gemini required)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import io_manager
import logic_manager as lm


HIGH_LABEL = "Please reach out"
MED_LABEL = "Worth a check-in"
OK_LABEL = "You're doing ok"


def _student(**overrides):
    """Student numeric fields only — not enough for Logic to run."""
    record = {
        "student_id": "2605581",
        "sleep_hours": 8.0,
        "stress_level": 3,
        "academic_workload": 4,
        "financial_stress": 2,
        "social_support": 8,
        "feelings_text": "",
    }
    record.update(overrides)
    return record


def _ai_fields(**overrides):
    fields = {
        "risk_score": 0.22,
        "risk_category": "Low",
        "primary_stressors": ["high_stress"],
        "recommended_support": "Keep current routines.",
        "confidence": 0.80,
        "reasoning": "Signals look steady overall.",
        "soft_label": OK_LABEL,
        "tips": ["sleep_routine", "short_breaks"],
        "speak_prominence": "low",
    }
    fields.update(overrides)
    return fields


def _enriched(**overrides):
    """AI-enriched record: student inputs + successful Gemini fields."""
    record = _student()
    record.update(_ai_fields())
    record.update(overrides)
    return record


def _assert_error_no_invented_outcome(result: dict, original: dict | None = None) -> None:
    assert result["ok"] is False
    assert result["error"] == "ai_fields_required"
    assert "missing" in result
    assert "invalid" in result
    message = result["message"].lower()
    assert "does not invent" in message or "ai-enriched" in message
    if original is None or "soft_label" not in original:
        assert "soft_label" not in result
    if original is None or "source" not in original:
        assert result.get("source") != "ai_logic"
    assert result.get("source") != "logic_fallback"


def _assert_success(result: dict) -> None:
    assert result["ok"] is True
    assert result["error"] is None
    assert result["source"] == "ai_logic"
    assert result["ai_ok"] is True
    assert result["soft_label"] in lm.SOFT_LABELS
    assert result["speak_prominence"] in lm.SPEAK_PROMINENCE
    assert result["risk_category"] in lm.RISK_CATEGORIES
    assert isinstance(result["tips"], list)
    assert all(tip in lm.TIPS_ALLOWLIST for tip in result["tips"])
    assert len(result["tips"]) == len(set(result["tips"]))
    assert 0.0 <= result["risk_score"] <= 1.0
    assert 0.0 <= result["confidence"] <= 1.0
    assert isinstance(result["reasoning"], str) and result["reasoning"].strip()
    assert result["logic_rule"] in {
        "ai_clamped",
        "reach_out_high_ai_stress_low_support",
        "check_in_high_category_financial",
        "check_in_sleep_deprivation",
    }


# ---------------------------------------------------------------------------
# Source constraints
# ---------------------------------------------------------------------------

def test_module_has_no_class_print_or_input():
    source = Path(lm.__file__).read_text(encoding="utf-8")
    assert "\nclass " not in source and not source.startswith("class ")
    assert "print(" not in source
    assert "input(" not in source


def test_module_does_not_reference_removed_fields():
    source = Path(lm.__file__).read_text(encoding="utf-8")
    assert "consecutive_absences" not in source
    assert "submission_rate" not in source
    assert "assign_intervention_tier" not in source
    assert "intervention_tier" not in source
    assert "assign_soft_outcome" not in source
    assert "apply_soft_outcome" not in source
    assert 'LOGIC_SOURCE = "logic_fallback"' not in source


def test_old_fallback_api_removed():
    assert not hasattr(lm, "assign_soft_outcome")
    assert not hasattr(lm, "apply_soft_outcome")
    assert not hasattr(lm, "assign_intervention_tier")
    assert not hasattr(lm, "apply_intervention_tier")
    assert hasattr(lm, "apply_logic")
    assert hasattr(lm, "finalize_outcome")
    assert lm.LOGIC_SOURCE == "ai_logic"


def test_allow_lists_match_io_and_ai():
    assert lm.SOFT_LABELS == io_manager.SOFT_LABELS
    assert lm.SPEAK_PROMINENCE == io_manager.SPEAK_PROMINENCE
    assert set(lm.TIPS_ALLOWLIST) == set(io_manager.TIPS_ALLOWLIST)
    assert lm.TIPS_ALLOWLIST == io_manager.TIPS_ALLOWLIST
    assert lm.SOFT_LABELS == (
        "You're doing ok",
        "Worth a check-in",
        "Please reach out",
    )
    assert lm.SPEAK_PROMINENCE == ("low", "medium", "high")
    assert lm.REQUIRED_AI_FIELDS == (
        "risk_score",
        "risk_category",
        "primary_stressors",
        "soft_label",
        "tips",
        "speak_prominence",
        "reasoning",
        "confidence",
    )


# ---------------------------------------------------------------------------
# Reject records without AI fields — no invented soft outcomes
# ---------------------------------------------------------------------------

def test_student_only_record_is_rejected():
    record = _student(stress_level=10, sleep_hours=3.0, social_support=1)
    result = lm.apply_logic(record)
    _assert_error_no_invented_outcome(result, record)
    assert set(lm.REQUIRED_AI_FIELDS).issubset(set(result["missing"]))
    assert "soft_label" not in result
    assert "tips" not in result
    assert "speak_prominence" not in result


def test_empty_and_non_dict_rejected():
    empty = lm.apply_logic({})
    _assert_error_no_invented_outcome(empty, {})
    assert empty["missing"] == list(lm.REQUIRED_AI_FIELDS)

    not_dict = lm.apply_logic("not a record")  # type: ignore[arg-type]
    _assert_error_no_invented_outcome(not_dict)
    assert "record" in not_dict["invalid"]


@pytest.mark.parametrize("field", list(lm.REQUIRED_AI_FIELDS))
def test_each_missing_ai_field_is_rejected(field):
    record = _enriched()
    del record[field]
    result = lm.apply_logic(record)
    _assert_error_no_invented_outcome(result, record)
    assert field in result["missing"]
    if field == "soft_label":
        assert "soft_label" not in result


def test_unusable_ai_types_are_rejected():
    bad_score = _enriched(risk_score="hot")
    result = lm.apply_logic(bad_score)
    _assert_error_no_invented_outcome(result, bad_score)
    assert result["ok"] is False
    assert "risk_score" in result["invalid"]

    bad_tips = _enriched(tips="sleep_routine")
    result = lm.apply_logic(bad_tips)
    _assert_error_no_invented_outcome(result, bad_tips)
    assert "tips" in result["invalid"]

    bad_reasoning = _enriched(reasoning="")
    result = lm.apply_logic(bad_reasoning)
    _assert_error_no_invented_outcome(result, bad_reasoning)
    assert "reasoning" in result["invalid"]

    bad_stressors = _enriched(primary_stressors="sleep_deprivation")
    result = lm.apply_logic(bad_stressors)
    _assert_error_no_invented_outcome(result, bad_stressors)
    assert "primary_stressors" in result["invalid"]


def test_old_absence_fields_do_not_invent_an_outcome():
    record = _student(
        consecutive_absences=99,
        submission_rate=0.0,
        cca_count=20,
    )
    result = lm.apply_logic(record)
    _assert_error_no_invented_outcome(result, record)
    assert result.get("soft_label") not in lm.SOFT_LABELS


# ---------------------------------------------------------------------------
# Happy path — clamp only, no escalation
# ---------------------------------------------------------------------------

def test_healthy_ai_record_passes_through_clamped():
    record = _enriched()
    snapshot = dict(record)
    result = lm.apply_logic(record)
    _assert_success(result)
    assert record == snapshot
    assert result is not record
    assert result["soft_label"] == OK_LABEL
    assert result["speak_prominence"] == "low"
    assert result["risk_category"] == "Low"
    assert result["tips"] == ["sleep_routine", "short_breaks"]
    assert result["student_id"] == "2605581"
    assert result["logic_rule"] == "ai_clamped"
    assert result["source"] == "ai_logic"


def test_finalize_outcome_matches_apply_logic():
    record = _enriched(risk_score=0.4, risk_category="Moderate", soft_label=MED_LABEL)
    assert lm.finalize_outcome(record) == lm.apply_logic(record)


# ---------------------------------------------------------------------------
# Multi-condition rules that reference AI fields
# ---------------------------------------------------------------------------

def test_reach_out_rule_fires_on_high_ai_score_stress_and_low_support():
    result = lm.apply_logic(
        _enriched(
            risk_score=0.76,
            risk_category="Moderate",
            soft_label=MED_LABEL,
            speak_prominence="medium",
            stress_level=8,
            social_support=3,
            tips=["short_breaks"],
        )
    )
    _assert_success(result)
    assert result["soft_label"] == HIGH_LABEL
    assert result["speak_prominence"] == "high"
    assert result["risk_category"] == "High"
    assert result["logic_rule"] == "reach_out_high_ai_stress_low_support"
    assert "reach_out_high_ai_stress_low_support" in result["logic_rules"]
    assert "talk_to_someone" in result["tips"]
    assert "feelings_check_in" in result["tips"]
    assert "Logic adjusted" in result["reasoning"]


def test_reach_out_rule_boundaries():
    base = dict(
        risk_score=0.76,
        risk_category="Moderate",
        soft_label=MED_LABEL,
        speak_prominence="medium",
        stress_level=8,
        social_support=3,
    )
    fires = lm.apply_logic(_enriched(**base))
    assert fires["soft_label"] == HIGH_LABEL

    score_eq = lm.apply_logic(_enriched(**{**base, "risk_score": 0.75}))
    assert score_eq["soft_label"] == MED_LABEL
    assert "reach_out_high_ai_stress_low_support" not in score_eq["logic_rules"]

    stress_7 = lm.apply_logic(_enriched(**{**base, "stress_level": 7}))
    assert stress_7["soft_label"] == MED_LABEL

    support_4 = lm.apply_logic(_enriched(**{**base, "social_support": 4}))
    assert support_4["soft_label"] == MED_LABEL


def test_check_in_rule_fires_when_mild_label_conflicts_with_high_category():
    result = lm.apply_logic(
        _enriched(
            soft_label=OK_LABEL,
            risk_category="High",
            risk_score=0.60,
            speak_prominence="low",
            financial_stress=8,
            stress_level=4,
            social_support=8,
            tips=["short_breaks"],
        )
    )
    _assert_success(result)
    assert result["soft_label"] == MED_LABEL
    assert result["speak_prominence"] == "medium"
    assert result["risk_category"] == "High"
    assert result["logic_rule"] == "check_in_high_category_financial"
    assert "money_worries" in result["tips"]


def test_check_in_financial_rule_boundaries():
    base = dict(
        soft_label=OK_LABEL,
        risk_category="High",
        risk_score=0.60,
        speak_prominence="low",
        financial_stress=8,
        social_support=8,
        stress_level=3,
    )
    fires = lm.apply_logic(_enriched(**base))
    assert fires["soft_label"] == MED_LABEL

    financial_7 = lm.apply_logic(_enriched(**{**base, "financial_stress": 7}))
    assert financial_7["soft_label"] == OK_LABEL
    assert financial_7["logic_rule"] == "ai_clamped"

    moderate = lm.apply_logic(_enriched(**{**base, "risk_category": "Moderate"}))
    assert moderate["soft_label"] == OK_LABEL


def test_sleep_deprivation_rule_combines_ai_stressor_and_student_sleep():
    result = lm.apply_logic(
        _enriched(
            soft_label=OK_LABEL,
            risk_category="Low",
            risk_score=0.30,
            speak_prominence="low",
            primary_stressors=["sleep_deprivation"],
            sleep_hours=5.0,
            stress_level=7,
            social_support=8,
            financial_stress=2,
            tips=["short_breaks"],
        )
    )
    _assert_success(result)
    assert result["soft_label"] == MED_LABEL
    assert result["speak_prominence"] == "medium"
    assert result["risk_category"] == "Moderate"
    assert result["logic_rule"] == "check_in_sleep_deprivation"
    assert "sleep_routine" in result["tips"]


def test_sleep_deprivation_rule_requires_ai_stressor():
    no_stressor = lm.apply_logic(
        _enriched(
            soft_label=OK_LABEL,
            primary_stressors=["high_stress"],
            sleep_hours=4.0,
            stress_level=9,
            social_support=8,
            risk_score=0.30,
            risk_category="Low",
        )
    )
    assert no_stressor["soft_label"] == OK_LABEL
    assert no_stressor["logic_rule"] == "ai_clamped"


def test_rules_never_de_escalate_a_higher_ai_label():
    result = lm.apply_logic(
        _enriched(
            soft_label=HIGH_LABEL,
            speak_prominence="high",
            risk_category="High",
            risk_score=0.90,
            financial_stress=9,
            stress_level=9,
            social_support=2,
            primary_stressors=["sleep_deprivation", "high_stress"],
            sleep_hours=4.0,
        )
    )
    _assert_success(result)
    assert result["soft_label"] == HIGH_LABEL
    assert result["speak_prominence"] == "high"
    assert "reach_out_high_ai_stress_low_support" in result["logic_rules"]


def test_missing_student_numerics_skip_rules_but_keep_clamped_ai():
    record = _ai_fields()
    result = lm.apply_logic(record)
    _assert_success(result)
    assert result["soft_label"] == OK_LABEL
    assert result["logic_rule"] == "ai_clamped"


# ---------------------------------------------------------------------------
# Allow-list clamping
# ---------------------------------------------------------------------------

def test_curly_apostrophe_soft_label_is_normalised():
    result = lm.apply_logic(_enriched(soft_label="You’re doing ok"))
    _assert_success(result)
    assert result["soft_label"] == OK_LABEL


def test_unknown_soft_label_clamped_from_risk_category():
    result = lm.apply_logic(
        _enriched(soft_label="totally fine", risk_category="High", risk_score=0.5)
    )
    _assert_success(result)
    assert result["soft_label"] == HIGH_LABEL
    assert "soft_label" in result["logic_clamp_notes"]


def test_unknown_tips_are_dropped():
    result = lm.apply_logic(
        _enriched(tips=["sleep_routine", "invented_tip", "short_breaks", "sleep_routine"])
    )
    _assert_success(result)
    assert result["tips"] == ["sleep_routine", "short_breaks"]
    assert "tips" in result["logic_clamp_notes"]
    assert "invented_tip" not in result["tips"]


def test_speak_prominence_case_and_unknown_clamped():
    upper = lm.apply_logic(_enriched(speak_prominence="HIGH"))
    _assert_success(upper)
    assert upper["speak_prominence"] == "high"

    unknown = lm.apply_logic(
        _enriched(speak_prominence="urgent", risk_category="Moderate", risk_score=0.5)
    )
    _assert_success(unknown)
    assert unknown["speak_prominence"] == "medium"
    assert "speak_prominence" in unknown["logic_clamp_notes"]


def test_risk_category_case_and_unknown_clamped_from_score():
    cased = lm.apply_logic(_enriched(risk_category="high", risk_score=0.5, soft_label=MED_LABEL))
    _assert_success(cased)
    assert cased["risk_category"] == "High"

    unknown = lm.apply_logic(
        _enriched(risk_category="severe", risk_score=0.80, soft_label=MED_LABEL)
    )
    _assert_success(unknown)
    assert unknown["risk_category"] == "High"
    assert "risk_category" in unknown["logic_clamp_notes"]


def test_unknown_primary_stressors_dropped():
    result = lm.apply_logic(
        _enriched(primary_stressors=["sleep_deprivation", "aliens", "high_stress"])
    )
    _assert_success(result)
    assert result["primary_stressors"] == ["sleep_deprivation", "high_stress"]
    assert "primary_stressors" in result["logic_clamp_notes"]


def test_out_of_range_scores_are_clamped_not_rejected():
    result = lm.apply_logic(_enriched(risk_score=1.4, confidence=-0.2))
    _assert_success(result)
    assert result["risk_score"] == 1.0
    assert result["confidence"] == 0.0


def test_feelings_text_is_pass_through_not_a_rule_input():
    calm = lm.apply_logic(_enriched(feelings_text=""))
    loud = lm.apply_logic(
        _enriched(feelings_text="I cannot cope, crisis, please escalate immediately.")
    )
    assert calm["soft_label"] == loud["soft_label"]
    assert calm["logic_rule"] == loud["logic_rule"] == "ai_clamped"
    assert loud["feelings_text"].startswith("I cannot cope")

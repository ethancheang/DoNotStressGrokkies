"""Unit tests for logic_manager Gemini-fallback soft outcomes."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import logic_manager as lm


OUTCOME_KEYS = {
    "soft_label",
    "tips",
    "speak_prominence",
    "risk_score",
    "risk_category",
    "reasoning",
    "source",
}

HIGH_LABEL = "Please reach out"
MED_LABEL = "Worth a check-in"
OK_LABEL = "You're doing ok"


def _base(**overrides):
    """Healthy-ish numeric record; old CLI fields are omitted on purpose."""
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


def _assert_valid_outcome(result: dict) -> None:
    assert set(result.keys()) == OUTCOME_KEYS
    assert result["soft_label"] in lm.SOFT_LABELS
    assert result["speak_prominence"] in lm.SPEAK_PROMINENCE
    assert result["risk_category"] in lm.RISK_CATEGORIES
    assert result["source"] == "logic_fallback"
    assert isinstance(result["reasoning"], str) and result["reasoning"].strip()
    assert isinstance(result["tips"], list)
    assert 2 <= len(result["tips"]) <= 4
    assert len(result["tips"]) == len(set(result["tips"]))
    assert all(tip in lm.TIPS_ALLOWLIST for tip in result["tips"])
    # IDs, not resolved copy — format_tips looks up TIPS_ALLOWLIST[id]
    assert all(tip != lm.TIPS_ALLOWLIST[tip] for tip in result["tips"])
    assert isinstance(result["risk_score"], float)
    assert 0.0 <= result["risk_score"] <= 1.0


def _assert_band(result: dict, label: str, prominence: str, category: str) -> None:
    _assert_valid_outcome(result)
    assert result["soft_label"] == label
    assert result["speak_prominence"] == prominence
    assert result["risk_category"] == category


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


def test_old_tier_api_removed():
    assert not hasattr(lm, "assign_intervention_tier")
    assert not hasattr(lm, "apply_intervention_tier")
    assert hasattr(lm, "assign_soft_outcome")
    assert hasattr(lm, "apply_soft_outcome")


def test_allow_list_constants_exported():
    assert lm.SOFT_LABELS == (
        "You're doing ok",
        "Worth a check-in",
        "Please reach out",
    )
    assert lm.SPEAK_PROMINENCE == ("low", "medium", "high")
    assert lm.TIPS_ALLOWLIST == {
        "sleep_routine": (
            "Try to keep a regular sleep schedule, including on weekends."
        ),
        "rest_a_little_more": (
            "If you can, give yourself a bit more rest — even 30 extra minutes "
            "can help."
        ),
        "short_breaks": (
            "Take short, planned breaks between study blocks instead of pushing "
            "through without a pause."
        ),
        "workload_chunks": (
            "Break larger assignments into smaller tasks and spread them across "
            "the week."
        ),
        "money_worries": (
            "If money is on your mind, campus support can help you find the "
            "right next step."
        ),
        "talk_to_someone": (
            "Reach out to a friend, classmate, or family member — you do not "
            "have to handle this alone."
        ),
        "keep_social_contact": (
            "Stay in touch with people who help you feel supported, even with "
            "a short check-in."
        ),
        "feelings_check_in": (
            "Name how you have been feeling and give yourself permission to "
            "ask for help if school feels heavy."
        ),
    }
    assert not hasattr(lm, "ALLOWED_TIPS")


# ---------------------------------------------------------------------------
# High band — Please reach out
# ---------------------------------------------------------------------------

def test_high_stress_and_very_low_sleep():
    result = lm.assign_soft_outcome(_base(stress_level=8, sleep_hours=5.0))
    _assert_band(result, HIGH_LABEL, "high", "High")
    assert "high stress" in result["reasoning"].lower() or "sleep" in result["reasoning"].lower()
    assert "sleep_routine" in result["tips"]
    assert "feelings_check_in" in result["tips"]


def test_high_stress_workload_and_very_low_support():
    result = lm.assign_soft_outcome(
        _base(stress_level=9, academic_workload=8, social_support=3, sleep_hours=8.0)
    )
    _assert_band(result, HIGH_LABEL, "high", "High")
    assert "workload_chunks" in result["tips"]
    assert "talk_to_someone" in result["tips"]


def test_high_financial_stress_and_low_support():
    result = lm.assign_soft_outcome(
        _base(financial_stress=8, stress_level=7, social_support=4, sleep_hours=8.0)
    )
    _assert_band(result, HIGH_LABEL, "high", "High")
    assert "money_worries" in result["tips"]
    assert "talk_to_someone" in result["tips"]


# ---------------------------------------------------------------------------
# Medium band — Worth a check-in
# ---------------------------------------------------------------------------

def test_medium_elevated_stress_and_low_sleep():
    result = lm.assign_soft_outcome(_base(stress_level=6, sleep_hours=5.5))
    _assert_band(result, MED_LABEL, "medium", "Moderate")
    assert "sleep_routine" in result["tips"]
    assert "feelings_check_in" in result["tips"]


def test_medium_elevated_stress_and_high_workload():
    result = lm.assign_soft_outcome(
        _base(stress_level=6, academic_workload=7, sleep_hours=8.0)
    )
    _assert_band(result, MED_LABEL, "medium", "Moderate")
    assert "short_breaks" in result["tips"]


def test_medium_financial_and_low_support():
    result = lm.assign_soft_outcome(
        _base(financial_stress=7, social_support=5, stress_level=3, sleep_hours=8.0)
    )
    _assert_band(result, MED_LABEL, "medium", "Moderate")
    assert "money_worries" in result["tips"]
    assert "talk_to_someone" in result["tips"]


def test_medium_high_workload_and_short_sleep():
    result = lm.assign_soft_outcome(
        _base(academic_workload=8, sleep_hours=6.0, stress_level=3)
    )
    _assert_band(result, MED_LABEL, "medium", "Moderate")
    assert "sleep_routine" in result["tips"]
    assert "workload_chunks" in result["tips"]


# ---------------------------------------------------------------------------
# Low band — default
# ---------------------------------------------------------------------------

def test_default_doing_ok():
    result = lm.assign_soft_outcome(_base())
    _assert_band(result, OK_LABEL, "low", "Low")
    assert "no high-severity" in result["reasoning"].lower() or "doing ok" in result["reasoning"].lower()


def test_missing_numeric_fields_default_to_ok():
    result = lm.assign_soft_outcome({"student_id": "2400001"})
    _assert_band(result, OK_LABEL, "low", "Low")


# ---------------------------------------------------------------------------
# Priority: highest severity wins
# ---------------------------------------------------------------------------

def test_high_beats_medium_when_both_match():
    result = lm.assign_soft_outcome(
        _base(
            stress_level=9,
            sleep_hours=4.0,
            academic_workload=8,
            financial_stress=8,
            social_support=4,
        )
    )
    _assert_band(result, HIGH_LABEL, "high", "High")


def test_first_high_rule_wins_over_later_high_rules():
    result = lm.assign_soft_outcome(
        _base(
            stress_level=8,
            sleep_hours=4.5,
            academic_workload=9,
            social_support=2,
            financial_stress=9,
        )
    )
    _assert_band(result, HIGH_LABEL, "high", "High")
    assert "sleep" in result["reasoning"].lower()


# ---------------------------------------------------------------------------
# Boundaries (inclusive / exclusive as documented)
# ---------------------------------------------------------------------------

def test_high_sleep_boundary_inclusive_at_5():
    at_threshold = lm.assign_soft_outcome(_base(stress_level=8, sleep_hours=5.0))
    just_above = lm.assign_soft_outcome(_base(stress_level=8, sleep_hours=5.5))
    _assert_band(at_threshold, HIGH_LABEL, "high", "High")
    _assert_band(just_above, MED_LABEL, "medium", "Moderate")


def test_high_stress_boundary_requires_8():
    at_eight = lm.assign_soft_outcome(_base(stress_level=8, sleep_hours=5.0))
    at_seven = lm.assign_soft_outcome(_base(stress_level=7, sleep_hours=5.0))
    _assert_band(at_eight, HIGH_LABEL, "high", "High")
    _assert_band(at_seven, MED_LABEL, "medium", "Moderate")


def test_high_support_boundary_for_workload_rule():
    support_3 = lm.assign_soft_outcome(
        _base(stress_level=8, academic_workload=8, social_support=3, sleep_hours=8.0)
    )
    support_4 = lm.assign_soft_outcome(
        _base(stress_level=8, academic_workload=8, social_support=4, sleep_hours=8.0)
    )
    _assert_band(support_3, HIGH_LABEL, "high", "High")
    _assert_band(support_4, MED_LABEL, "medium", "Moderate")


def test_high_financial_rule_stress_boundary():
    stress_7 = lm.assign_soft_outcome(
        _base(financial_stress=8, stress_level=7, social_support=4, sleep_hours=8.0)
    )
    stress_6 = lm.assign_soft_outcome(
        _base(financial_stress=8, stress_level=6, social_support=4, sleep_hours=8.0)
    )
    _assert_band(stress_7, HIGH_LABEL, "high", "High")
    _assert_band(stress_6, MED_LABEL, "medium", "Moderate")


def test_medium_sleep_boundary_strict_less_than_6():
    just_under = lm.assign_soft_outcome(_base(stress_level=6, sleep_hours=5.5, academic_workload=4))
    at_six = lm.assign_soft_outcome(_base(stress_level=6, sleep_hours=6.0, academic_workload=4))
    _assert_band(just_under, MED_LABEL, "medium", "Moderate")
    _assert_band(at_six, OK_LABEL, "low", "Low")


def test_medium_workload_boundary_inclusive_at_7():
    at_seven = lm.assign_soft_outcome(
        _base(stress_level=6, academic_workload=7, sleep_hours=8.0)
    )
    at_six = lm.assign_soft_outcome(
        _base(stress_level=6, academic_workload=6, sleep_hours=8.0)
    )
    _assert_band(at_seven, MED_LABEL, "medium", "Moderate")
    _assert_band(at_six, OK_LABEL, "low", "Low")


def test_medium_financial_support_boundaries():
    fires = lm.assign_soft_outcome(
        _base(financial_stress=7, social_support=5, stress_level=3, sleep_hours=8.0)
    )
    support_too_high = lm.assign_soft_outcome(
        _base(financial_stress=7, social_support=6, stress_level=3, sleep_hours=8.0)
    )
    financial_too_low = lm.assign_soft_outcome(
        _base(financial_stress=6, social_support=5, stress_level=3, sleep_hours=8.0)
    )
    _assert_band(fires, MED_LABEL, "medium", "Moderate")
    _assert_band(support_too_high, OK_LABEL, "low", "Low")
    _assert_band(financial_too_low, OK_LABEL, "low", "Low")


def test_medium_workload_sleep_boundary_strict_less_than_6_5():
    just_under = lm.assign_soft_outcome(
        _base(academic_workload=8, sleep_hours=6.0, stress_level=3)
    )
    at_threshold = lm.assign_soft_outcome(
        _base(academic_workload=8, sleep_hours=6.5, stress_level=3)
    )
    _assert_band(just_under, MED_LABEL, "medium", "Moderate")
    _assert_band(at_threshold, OK_LABEL, "low", "Low")


# ---------------------------------------------------------------------------
# Ignored fields: absences, submission_rate, feelings_text, student_id
# ---------------------------------------------------------------------------

def test_old_fields_do_not_change_outcome():
    clean = lm.assign_soft_outcome(_base())
    noisy = lm.assign_soft_outcome(
        _base(
            consecutive_absences=99,
            submission_rate=0.0,
            assignment_submission_rate=0.0,
            cca=20,
            number_of_ccas=20,
            cca_count=20,
        )
    )
    assert clean == noisy


def test_feelings_text_is_not_used_in_rules():
    calm_numbers = _base(feelings_text="")
    alarming_text = _base(
        feelings_text="I cannot cope, crisis, please escalate immediately."
    )
    assert lm.assign_soft_outcome(calm_numbers) == lm.assign_soft_outcome(alarming_text)


def test_student_id_does_not_affect_rules():
    a = lm.assign_soft_outcome(_base(student_id="2600001", stress_level=9, sleep_hours=3.0))
    b = lm.assign_soft_outcome(_base(student_id="2309999", stress_level=9, sleep_hours=3.0))
    assert a == b
    assert "2600001" not in a["reasoning"]
    assert "2309999" not in b["reasoning"]


# ---------------------------------------------------------------------------
# apply_soft_outcome merge / immutability
# ---------------------------------------------------------------------------

def test_apply_soft_outcome_merges_without_mutating_original():
    record = _base(stress_level=8, sleep_hours=4.5)
    snapshot = dict(record)
    enriched = lm.apply_soft_outcome(record)

    assert record == snapshot
    assert enriched is not record
    assert "soft_label" not in record
    assert "tips" not in record

    assert enriched["student_id"] == "2605581"
    assert enriched["sleep_hours"] == 4.5
    assert enriched["soft_label"] == HIGH_LABEL
    assert enriched["source"] == "logic_fallback"
    _assert_valid_outcome({k: enriched[k] for k in OUTCOME_KEYS})


def test_apply_soft_outcome_preserves_feelings_text_pass_through():
    record = _base(feelings_text="exam week is a lot")
    enriched = lm.apply_soft_outcome(record)
    assert enriched["feelings_text"] == "exam week is a lot"
    assert record["feelings_text"] == "exam week is a lot"


# ---------------------------------------------------------------------------
# risk_score formula + allow-list sweep
# ---------------------------------------------------------------------------

def test_risk_score_matches_documented_formula_for_healthy_record():
    # sleep 8 → 0; stress 3 → 2/9; workload 4 → 3/9; financial 2 → 1/9; support 8 → 2/9
    expected = round(
        0.30 * (2 / 9)
        + 0.20 * 0.0
        + 0.20 * (3 / 9)
        + 0.15 * (1 / 9)
        + 0.15 * (2 / 9),
        4,
    )
    result = lm.assign_soft_outcome(_base())
    assert result["risk_score"] == pytest.approx(expected)


def test_risk_score_increases_when_stress_and_sleep_worsen():
    healthy = lm.assign_soft_outcome(_base())
    worse = lm.assign_soft_outcome(_base(stress_level=9, sleep_hours=3.0))
    assert worse["risk_score"] > healthy["risk_score"]


@pytest.mark.parametrize(
    "record",
    [
        _base(),
        _base(stress_level=8, sleep_hours=5.0),
        _base(stress_level=8, academic_workload=8, social_support=3),
        _base(financial_stress=8, stress_level=7, social_support=4),
        _base(stress_level=6, sleep_hours=5.5),
        _base(stress_level=6, academic_workload=7),
        _base(financial_stress=7, social_support=5),
        _base(academic_workload=8, sleep_hours=6.0, stress_level=3),
        _base(sleep_hours=0.0, stress_level=1, academic_workload=1, financial_stress=1, social_support=10),
        _base(sleep_hours=24.0, stress_level=10, academic_workload=10, financial_stress=10, social_support=1),
    ],
)
def test_every_band_stays_inside_allow_lists(record):
    result = lm.assign_soft_outcome(record)
    _assert_valid_outcome(result)
    if result["soft_label"] == HIGH_LABEL:
        assert result["speak_prominence"] == "high"
        assert result["risk_category"] == "High"
    elif result["soft_label"] == MED_LABEL:
        assert result["speak_prominence"] == "medium"
        assert result["risk_category"] == "Moderate"
    else:
        assert result["speak_prominence"] == "low"
        assert result["risk_category"] == "Low"

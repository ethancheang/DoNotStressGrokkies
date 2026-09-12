"""Unit tests for logic_manager Intervention Tier rules."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import logic_manager as lm


def _base(**overrides):
    record = {
        "student_id": "2605581",
        "sleep_hours": 7.0,
        "stress_level": 5,
        "submission_rate": 80.0,
        "number_of_ccas": 2,
        "financial_stress": False,
        "consecutive_absences": 0,
        "free_text_concern": "",
        "risk_score": 0.2,
        "risk_category": "Low",
        "primary_stressors": [],
        "recommended_support": "None",
        "confidence": 0.9,
        "reasoning": "Baseline.",
    }
    record.update(overrides)
    return record


def test_module_has_no_class_print_or_input():
    source = Path(lm.__file__).read_text(encoding="utf-8")
    assert "\nclass " not in source and not source.startswith("class ")
    assert "print(" not in source
    assert "input(" not in source


def test_rule1_critical_escalation():
    result = lm.assign_intervention_tier(
        _base(risk_score=0.8, consecutive_absences=3, risk_category="High")
    )
    assert result["tier"] == 1
    assert result["intervention_tier"] == 1
    assert result["rule"] == "critical_escalation"
    assert result["tier_label"] == "Critical"
    assert "Dean" in result["outcome"]


def test_rule2_urgent_financial():
    result = lm.assign_intervention_tier(
        _base(
            risk_score=0.7,
            financial_stress=True,
            primary_stressors=["financial_pressure", "sleep_deprivation"],
        )
    )
    assert result["tier"] == 2
    assert result["rule"] == "urgent_financial"
    assert result["colour"] == "Orange"


def test_rule3_academic_watch():
    result = lm.assign_intervention_tier(
        _base(
            risk_score=0.6,
            submission_rate=40.0,
            risk_category="High",
            consecutive_absences=1,
        )
    )
    assert result["tier"] == 3
    assert result["rule"] == "academic_watch"


def test_rule3_accepts_assignment_submission_rate_alias():
    record = _base(
        risk_score=0.6,
        risk_category="High",
        consecutive_absences=1,
    )
    del record["submission_rate"]
    record["assignment_submission_rate"] = 40.0
    result = lm.assign_intervention_tier(record)
    assert result["rule"] == "academic_watch"


def test_rule4_physical_wellness():
    result = lm.assign_intervention_tier(
        _base(risk_score=0.55, sleep_hours=5.0, stress_level=8)
    )
    assert result["tier"] == 3
    assert result["rule"] == "physical_wellness"


def test_rule4_accepts_average_sleep_hours_alias():
    record = _base(risk_score=0.55, stress_level=8)
    del record["sleep_hours"]
    record["average_sleep_hours"] = 5.0
    result = lm.assign_intervention_tier(record)
    assert result["rule"] == "physical_wellness"


def test_rule5_default_clear():
    result = lm.assign_intervention_tier(_base())
    assert result["tier"] == 4
    assert result["rule"] == "default_clear"
    assert result["colour"] == "Green"


def test_priority_rule1_beats_later_rules():
    result = lm.assign_intervention_tier(
        _base(
            risk_score=0.9,
            consecutive_absences=4,
            financial_stress=True,
            primary_stressors=["financial_pressure"],
            submission_rate=20.0,
            risk_category="High",
            sleep_hours=4.0,
            stress_level=9,
        )
    )
    assert result["tier"] == 1
    assert result["rule"] == "critical_escalation"


def test_boundary_rule1_score_eq_075_does_not_fire():
    result = lm.assign_intervention_tier(
        _base(risk_score=0.75, consecutive_absences=5, risk_category="High")
    )
    assert result["rule"] != "critical_escalation"
    assert result["tier"] == 4


def test_apply_intervention_tier_merges_into_record():
    record = _base(risk_score=0.8, consecutive_absences=3)
    enriched = lm.apply_intervention_tier(record)
    assert enriched["student_id"] == "2605581"
    assert enriched["intervention_tier"] == 1
    assert enriched["tier_label"] == "Critical"
    assert "outcome" in enriched
    # original unchanged
    assert "intervention_tier" not in record

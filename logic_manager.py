"""
DoNotStress — Logic Layer (logic_manager)

Sole owner of Intervention Tier assignment (domain brain).
Pure procedural Python: functions only — no classes.
No terminal I/O (print / input), no Gemini / network, no file I/O.

Pipeline position:
  User → io_manager → ai_manager → logic_manager → data_manager
"""

from __future__ import annotations

from typing import Any


def assign_intervention_tier(record: dict[str, Any]) -> dict[str, Any]:
    """
    Map a combined student + AI record to an Intervention Tier.

    Expected keys (I/O + AI):
      risk_score: float (0.0–1.0)
      consecutive_absences: int (>= 0)
      financial_stress: bool
      primary_stressors: list[str]
      submission_rate: float (0.0–100.0)
        (alias: assignment_submission_rate)
      risk_category: str ("Low" | "Moderate" | "High")
      sleep_hours: float
        (alias: average_sleep_hours)
      stress_level: int (1–10)

    Returns:
      {
        "tier": int,                 # 1–4
        "intervention_tier": int,    # same as tier (Data Manager key)
        "label": str,                # Critical | Urgent | Monitor | Clear
        "tier_label": str,           # same as label
        "colour": str,               # Red | Orange | Yellow | Green
        "rule": str,                 # which rule fired, or "default_clear"
        "action": str,               # recommended next step
        "outcome": str,              # same as action (Data Manager key)
      }
    """
    if _rule_1_critical_escalation(record):
        return _tier_result(
            tier=1,
            label="Critical",
            colour="Red",
            rule="critical_escalation",
            action="Escalate to Dean's Office immediately.",
        )

    if _rule_2_urgent_financial(record):
        return _tier_result(
            tier=2,
            label="Urgent",
            colour="Orange",
            rule="urgent_financial",
            action="Refer to Financial Aid Office and Student Counsellor.",
        )

    if _rule_3_academic_watch(record):
        return _tier_result(
            tier=3,
            label="Monitor",
            colour="Yellow",
            rule="academic_watch",
            action="Flag for Academic Advisor follow-up within two weeks.",
        )

    if _rule_4_physical_wellness(record):
        return _tier_result(
            tier=3,
            label="Monitor",
            colour="Yellow",
            rule="physical_wellness",
            action="Recommend Wellness Workshop and peer-support resources.",
        )

    # Rule 5 — Default Clear
    return _tier_result(
        tier=4,
        label="Clear",
        colour="Green",
        rule="default_clear",
        action="No immediate action. Record saved for trend tracking.",
    )


def apply_intervention_tier(record: dict[str, Any]) -> dict[str, Any]:
    """
    Return a shallow copy of `record` with Logic outcome fields merged in.
    Use this before handing off to data_manager.save_record(...).
    """
    outcome = assign_intervention_tier(record)
    enriched = dict(record)
    enriched.update(outcome)
    return enriched


def _tier_result(
    tier: int,
    label: str,
    colour: str,
    rule: str,
    action: str,
) -> dict[str, Any]:
    return {
        "tier": tier,
        "intervention_tier": tier,
        "label": label,
        "tier_label": label,
        "colour": colour,
        "rule": rule,
        "action": action,
        "outcome": action,
    }


def _field(record: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    return default


def _rule_1_critical_escalation(record: dict[str, Any]) -> bool:
    """Tier 1: risk_score > 0.75 AND consecutive_absences >= 3."""
    risk_score = _field(record, "risk_score", default=0.0)
    consecutive_absences = _field(record, "consecutive_absences", default=0)
    return risk_score > 0.75 and consecutive_absences >= 3


def _rule_2_urgent_financial(record: dict[str, Any]) -> bool:
    """
    Tier 2: risk_score > 0.65
             AND financial_stress is True
             AND "financial_pressure" in primary_stressors.
    """
    risk_score = _field(record, "risk_score", default=0.0)
    financial_stress = _field(record, "financial_stress", default=False)
    primary_stressors = _field(record, "primary_stressors", default=[]) or []
    return (
        risk_score > 0.65
        and financial_stress is True
        and "financial_pressure" in primary_stressors
    )


def _rule_3_academic_watch(record: dict[str, Any]) -> bool:
    """
    Tier 3: submission_rate < 50.0
            AND risk_category == "High"
            AND consecutive_absences >= 1.
    """
    submission_rate = _field(
        record, "submission_rate", "assignment_submission_rate", default=100.0
    )
    risk_category = _field(record, "risk_category", default="")
    consecutive_absences = _field(record, "consecutive_absences", default=0)
    return (
        submission_rate < 50.0
        and risk_category == "High"
        and consecutive_absences >= 1
    )


def _rule_4_physical_wellness(record: dict[str, Any]) -> bool:
    """
    Tier 3: sleep_hours < 5.5
            AND stress_level >= 7
            AND risk_score > 0.5.
    """
    sleep_hours = _field(record, "sleep_hours", "average_sleep_hours", default=24.0)
    stress_level = _field(record, "stress_level", default=0)
    risk_score = _field(record, "risk_score", default=0.0)
    return sleep_hours < 5.5 and stress_level >= 7 and risk_score > 0.5

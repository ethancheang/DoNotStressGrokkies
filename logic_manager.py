"""
DoNotStress — Logic Layer (logic_manager)

FALLBACK decision engine when Gemini / ai_manager fails.
Produces the same UI-facing outcome fields as the AI path so the Flask
result page can render identically.

Pure procedural Python: functions only — no classes.
No terminal I/O (print / input), no Gemini / network, no file I/O.

Pipeline position:
  User → io_manager → ai_manager → logic_manager → data_manager
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Locked allow-lists — copied verbatim from io_manager (PR #6)
# so Flask format_soft_label / format_tips / format_speak_to_advisor_panel
# render identically on the Gemini fallback path.
# ---------------------------------------------------------------------------

SOFT_LABELS = (
    "You're doing ok",
    "Worth a check-in",
    "Please reach out",
)

SPEAK_PROMINENCE = ("low", "medium", "high")

# Tip IDs that templates / other layers may pass into format_tips.
# Copy is student-facing. Do not add phone numbers or extra emails here.
TIPS_ALLOWLIST = {
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

RISK_CATEGORIES = ("Low", "Moderate", "High")
LOGIC_SOURCE = "logic_fallback"

# Numeric inputs used by fallback rules. feelings_text is accepted on the
# record but never read here — AI may use it; this layer is numeric only.
# student_id is pass-through via apply_soft_outcome, not used in rules.
_SLEEP_DEFAULT = 8.0
_STRESS_DEFAULT = 3
_WORKLOAD_DEFAULT = 3
_FINANCIAL_DEFAULT = 2
_SUPPORT_DEFAULT = 8

# Tip IDs returned in `tips` — io_manager.format_tips accepts these keys.
_TIP_SLEEP = "sleep_routine"
_TIP_REST = "rest_a_little_more"
_TIP_BREAKS = "short_breaks"
_TIP_CHUNKS = "workload_chunks"
_TIP_MONEY = "money_worries"
_TIP_TALK = "talk_to_someone"
_TIP_SOCIAL = "keep_social_contact"
_TIP_FEELINGS = "feelings_check_in"

_MIN_TIPS = 2
_MAX_TIPS = 4


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def assign_soft_outcome(record: dict[str, Any]) -> dict[str, Any]:
    """
    Map student numeric fields to a soft UI outcome (Gemini fallback).

    Expected keys (new student-facing inputs only):
      student_id: str          — ignored by rules; preserved by apply_soft_outcome
      sleep_hours: float       — typically 0–24, 0.5 steps
      stress_level: int        — 1–10
      academic_workload: int   — 1–10
      financial_stress: int    — 1–10 (scale, not bool)
      social_support: int      — 1–10
      feelings_text: str       — optional; NOT used in fallback rules

    Severity bands (first matching highest-severity rule wins):

    Please reach out / speak_prominence high / risk_category High when ANY of:
      1. stress_level >= 8 AND sleep_hours <= 5.0
      2. stress_level >= 8 AND academic_workload >= 8 AND social_support <= 3
      3. financial_stress >= 8 AND stress_level >= 7 AND social_support <= 4

    Worth a check-in / speak_prominence medium / Moderate when ANY of:
      1. stress_level >= 6 AND (sleep_hours < 6.0 OR academic_workload >= 7)
      2. financial_stress >= 7 AND social_support <= 5
      3. academic_workload >= 8 AND sleep_hours < 6.5

    You're doing ok / speak_prominence low / Low: default

    `tips` is a list of TIPS_ALLOWLIST keys (not copy text) so
    io_manager.format_tips can resolve the student-facing strings.

    risk_score is a separate 0.0–1.0 logging heuristic (see _risk_score).
    """
    sleep, stress, workload, financial, support = _read_numeric_fields(record)
    flags = _signal_flags(sleep, stress, workload, financial, support)

    band, rule_id = _winning_band(flags)
    tips = _select_tips(flags, band)
    reasoning = _reasoning(rule_id, sleep, stress, workload, financial, support)
    score = _risk_score(sleep, stress, workload, financial, support)

    return {
        "soft_label": _BAND_TO_LABEL[band],
        "tips": tips,  # list of TIPS_ALLOWLIST keys for io_manager.format_tips
        "speak_prominence": _BAND_TO_PROMINENCE[band],
        "risk_score": score,
        "risk_category": _BAND_TO_CATEGORY[band],
        "reasoning": reasoning,
        "source": LOGIC_SOURCE,
    }


def apply_soft_outcome(record: dict[str, Any]) -> dict[str, Any]:
    """
    Return a shallow copy of `record` with Logic outcome fields merged in.
    Does not mutate the original dict. Use before data_manager.save_record.
    """
    source = record if isinstance(record, dict) else {}
    outcome = assign_soft_outcome(source)
    enriched = dict(source)
    enriched.update(outcome)
    return enriched


# ---------------------------------------------------------------------------
# Band tables (aligned: label ↔ prominence ↔ category)
# ---------------------------------------------------------------------------

_BAND_TO_LABEL = {
    "high": SOFT_LABELS[2],
    "medium": SOFT_LABELS[1],
    "low": SOFT_LABELS[0],
}
_BAND_TO_PROMINENCE = {
    "high": SPEAK_PROMINENCE[2],
    "medium": SPEAK_PROMINENCE[1],
    "low": SPEAK_PROMINENCE[0],
}
_BAND_TO_CATEGORY = {
    "high": RISK_CATEGORIES[2],
    "medium": RISK_CATEGORIES[1],
    "low": RISK_CATEGORIES[0],
}


# ---------------------------------------------------------------------------
# Field readers (numeric only — feelings_text / student_id unused)
# ---------------------------------------------------------------------------

def _read_numeric_fields(record: dict[str, Any]) -> tuple[float, int, int, int, int]:
    data = record if isinstance(record, dict) else {}
    sleep = _as_float(data.get("sleep_hours"), _SLEEP_DEFAULT)
    stress = _as_int(data.get("stress_level"), _STRESS_DEFAULT)
    workload = _as_int(data.get("academic_workload"), _WORKLOAD_DEFAULT)
    financial = _as_int(data.get("financial_stress"), _FINANCIAL_DEFAULT)
    support = _as_int(data.get("social_support"), _SUPPORT_DEFAULT)
    return sleep, stress, workload, financial, support


def _as_float(value: Any, default: float) -> float:
    if value is None or isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    if number == float("inf") or number == float("-inf"):
        return default
    return number


def _as_int(value: Any, default: int) -> int:
    number = _as_float(value, float(default))
    return int(round(number))


def _clamp(value: float, lo: float, hi: float) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


# ---------------------------------------------------------------------------
# Signals and rules
# ---------------------------------------------------------------------------

def _signal_flags(
    sleep: float,
    stress: int,
    workload: int,
    financial: int,
    support: int,
) -> dict[str, bool]:
    return {
        "sleep_very_low": sleep <= 5.0,
        "sleep_low": sleep < 6.0,
        "sleep_short": sleep < 6.5,
        "stress_very_high": stress >= 8,
        "stress_high": stress >= 7,
        "stress_elevated": stress >= 6,
        "workload_high": workload >= 8,
        "workload_elevated": workload >= 7,
        "financial_high": financial >= 8,
        "financial_elevated": financial >= 7,
        "support_very_low": support <= 3,
        "support_low": support <= 4,
        "support_somewhat_low": support <= 5,
    }


def _winning_band(flags: dict[str, bool]) -> tuple[str, str]:
    """Return (band, rule_id). Highest severity first."""
    if flags["stress_very_high"] and flags["sleep_very_low"]:
        return "high", "high_stress_low_sleep"
    if flags["stress_very_high"] and flags["workload_high"] and flags["support_very_low"]:
        return "high", "high_stress_workload_low_support"
    if flags["financial_high"] and flags["stress_high"] and flags["support_low"]:
        return "high", "high_financial_stress_low_support"

    if flags["stress_elevated"] and (flags["sleep_low"] or flags["workload_elevated"]):
        return "medium", "elevated_stress_sleep_or_workload"
    if flags["financial_elevated"] and flags["support_somewhat_low"]:
        return "medium", "financial_and_low_support"
    if flags["workload_high"] and flags["sleep_short"]:
        return "medium", "high_workload_short_sleep"

    return "low", "default_ok"


# ---------------------------------------------------------------------------
# risk_score heuristic (logging only; category follows the rule band)
# ---------------------------------------------------------------------------

def _risk_score(
    sleep: float,
    stress: int,
    workload: int,
    financial: int,
    support: int,
) -> float:
    """
    Composite in [0.0, 1.0]. Higher is more concerning.

    Normalize each field to [0, 1] (higher = worse):
      stress_n     = clamp((stress_level - 1) / 9, 0, 1)
      workload_n   = clamp((academic_workload - 1) / 9, 0, 1)
      financial_n  = clamp((financial_stress - 1) / 9, 0, 1)
      support_n    = clamp((10 - social_support) / 9, 0, 1)   # low support → high
      sleep_n      = clamp((8.0 - sleep_hours) / 8.0, 0, 1)   # 8h+ → 0, 0h → 1

    Weighted sum (weights total 1.0):
      0.30 * stress_n
    + 0.20 * sleep_n
    + 0.20 * workload_n
    + 0.15 * financial_n
    + 0.15 * support_n
    """
    stress_n = _clamp((float(stress) - 1.0) / 9.0, 0.0, 1.0)
    workload_n = _clamp((float(workload) - 1.0) / 9.0, 0.0, 1.0)
    financial_n = _clamp((float(financial) - 1.0) / 9.0, 0.0, 1.0)
    support_n = _clamp((10.0 - float(support)) / 9.0, 0.0, 1.0)
    sleep_n = _clamp((8.0 - float(sleep)) / 8.0, 0.0, 1.0)
    score = (
        0.30 * stress_n
        + 0.20 * sleep_n
        + 0.20 * workload_n
        + 0.15 * financial_n
        + 0.15 * support_n
    )
    return round(_clamp(score, 0.0, 1.0), 4)


# ---------------------------------------------------------------------------
# Tips — 2–4 unique TIPS_ALLOWLIST IDs, driven by fired signals.
# IDs (not copy text) so io_manager.format_tips can resolve UI strings.
# ---------------------------------------------------------------------------

def _select_tips(flags: dict[str, bool], band: str) -> list[str]:
    ordered: list[str] = []

    # Order so rule-critical signals land in the 2–4 tip window.
    if band == "high":
        ordered.append(_TIP_FEELINGS)
        ordered.append(_TIP_TALK)
    if flags["sleep_short"]:
        ordered.append(_TIP_SLEEP)
    if flags["sleep_very_low"]:
        ordered.append(_TIP_REST)
    if flags["stress_elevated"] and band != "high":
        ordered.append(_TIP_FEELINGS)
    if flags["support_somewhat_low"]:
        ordered.append(_TIP_TALK)
        ordered.append(_TIP_SOCIAL)
    if flags["financial_elevated"]:
        ordered.append(_TIP_MONEY)
    if flags["workload_high"]:
        ordered.append(_TIP_CHUNKS)
        ordered.append(_TIP_BREAKS)
    elif flags["workload_elevated"]:
        ordered.append(_TIP_BREAKS)
        ordered.append(_TIP_CHUNKS)

    unique: list[str] = []
    for tip_id in ordered:
        if tip_id in TIPS_ALLOWLIST and tip_id not in unique:
            unique.append(tip_id)

    pad_order = (_TIP_SLEEP, _TIP_BREAKS, _TIP_SOCIAL)
    for tip_id in pad_order:
        if len(unique) >= _MIN_TIPS:
            break
        if tip_id not in unique:
            unique.append(tip_id)

    return unique[:_MAX_TIPS]


def _reasoning(
    rule_id: str,
    sleep: float,
    stress: int,
    workload: int,
    financial: int,
    support: int,
) -> str:
    details = (
        f"sleep_hours={sleep:g}, stress_level={stress}, "
        f"academic_workload={workload}, financial_stress={financial}, "
        f"social_support={support}"
    )
    explanations = {
        "high_stress_low_sleep": (
            "Please reach out: high stress combined with very low sleep"
        ),
        "high_stress_workload_low_support": (
            "Please reach out: high stress, heavy workload, and low social support"
        ),
        "high_financial_stress_low_support": (
            "Please reach out: high financial stress with elevated stress and low support"
        ),
        "elevated_stress_sleep_or_workload": (
            "Worth a check-in: elevated stress with short sleep or heavy workload"
        ),
        "financial_and_low_support": (
            "Worth a check-in: financial strain with limited social support"
        ),
        "high_workload_short_sleep": (
            "Worth a check-in: heavy academic workload with short sleep"
        ),
        "default_ok": "You're doing ok: no high-severity numeric signals fired",
    }
    lead = explanations.get(rule_id, "Numeric fallback outcome")
    return f"{lead} ({details})."

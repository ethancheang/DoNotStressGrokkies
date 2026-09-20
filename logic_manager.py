"""
DoNotStress — Logic Layer (logic_manager)

Post-AI finalizer. Gemini is mandatory for every record.

This module does NOT invent soft_label / tips / speak_prominence from
student numeric inputs when AI is missing or failed. It only runs on an
AI-enriched record (after a successful `ai_manager.analyse_student`).

Design
------
1. Require AI fields produced by Gemini (see REQUIRED_AI_FIELDS).
2. Clamp present-but-invalid AI values onto I/O allow-lists
   (io_manager SOFT_LABELS / TIPS_ALLOWLIST keys / SPEAK_PROMINENCE).
3. Apply multi-condition rules that combine AI fields with student
   numerics. Rules may escalate the outcome; they never de-escalate.
4. Mark the result `source: "ai_logic"` (never `logic_fallback`).

Pure procedural Python: functions only — no classes.
No terminal I/O (print / input), no Gemini / network, no file I/O.

Pipeline position:
  User → io_manager → ai_manager (must succeed) → logic_manager → data_manager
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Locked allow-lists — keys/strings must match io_manager (PR #6) and
# ai_manager (PR #8) so Flask formatters and Data Layer saves stay aligned.
# ---------------------------------------------------------------------------

SOFT_LABEL_OK = "You're doing ok"
SOFT_LABEL_CHECK_IN = "Worth a check-in"
SOFT_LABEL_REACH_OUT = "Please reach out"
SOFT_LABEL_OK_CURLY = "You’re doing ok"

SOFT_LABELS = (
    SOFT_LABEL_OK,
    SOFT_LABEL_CHECK_IN,
    SOFT_LABEL_REACH_OUT,
)
ALLOWED_SOFT_LABELS = frozenset(SOFT_LABELS)
_SOFT_LABEL_ALIASES = {
    SOFT_LABEL_OK: SOFT_LABEL_OK,
    SOFT_LABEL_OK_CURLY: SOFT_LABEL_OK,
    SOFT_LABEL_CHECK_IN: SOFT_LABEL_CHECK_IN,
    SOFT_LABEL_REACH_OUT: SOFT_LABEL_REACH_OUT,
}

SPEAK_PROMINENCE = ("low", "medium", "high")
ALLOWED_SPEAK_PROMINENCE = frozenset(SPEAK_PROMINENCE)

RISK_CATEGORIES = ("Low", "Moderate", "High")
ALLOWED_RISK_CATEGORIES = frozenset(RISK_CATEGORIES)

# Tip IDs only — same keys as io_manager.TIPS_ALLOWLIST. Copy lives in I/O.
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
ALLOWED_TIP_IDS = frozenset(TIPS_ALLOWLIST)

ALLOWED_PRIMARY_STRESSORS = frozenset(
    {
        "sleep_deprivation",
        "high_stress",
        "academic_overload",
        "financial_pressure",
        "low_social_support",
        "emotional_distress",
    }
)

# Gemini fields that must already be on the record. Matching ai_manager
# `_REQUIRED_FIELDS` except recommended_support (pass-through, unused here).
REQUIRED_AI_FIELDS = (
    "risk_score",
    "risk_category",
    "primary_stressors",
    "soft_label",
    "tips",
    "speak_prominence",
    "reasoning",
    "confidence",
)

LOGIC_SOURCE = "ai_logic"
ERROR_AI_FIELDS_REQUIRED = "ai_fields_required"

_MAX_TIPS = 4

_LABEL_RANK = {
    SOFT_LABEL_OK: 0,
    SOFT_LABEL_CHECK_IN: 1,
    SOFT_LABEL_REACH_OUT: 2,
}
_PROMINENCE_RANK = {"low": 0, "medium": 1, "high": 2}
_CATEGORY_RANK = {"Low": 0, "Moderate": 1, "High": 2}

_CATEGORY_TO_LABEL = {
    "High": SOFT_LABEL_REACH_OUT,
    "Moderate": SOFT_LABEL_CHECK_IN,
    "Low": SOFT_LABEL_OK,
}
_CATEGORY_TO_PROMINENCE = {
    "High": "high",
    "Moderate": "medium",
    "Low": "low",
}

_TIP_SLEEP = "sleep_routine"
_TIP_MONEY = "money_worries"
_TIP_TALK = "talk_to_someone"
_TIP_FEELINGS = "feelings_check_in"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_logic(record: dict[str, Any]) -> dict[str, Any]:
    """
    Finalize an AI-enriched student record.

    Input MUST be a dict that already contains Gemini's fields
    (see REQUIRED_AI_FIELDS). Student numerics are used only inside
    multi-condition rules that also reference AI fields.

    On success, returns a shallow copy with clamped / possibly escalated
    outcome fields, `ok=True`, `source="ai_logic"`, and `ai_ok=True`.

    On missing or unusable AI fields, returns an error result:
      {"ok": False, "error": "ai_fields_required", "missing": [...], ...}
    and does not invent soft_label / tips / speak_prominence from
    sleep/stress alone.

    Does not mutate the original dict.
    """
    if not isinstance(record, dict):
        return _error_result(
            {},
            missing=list(REQUIRED_AI_FIELDS),
            invalid=["record"],
        )

    missing, invalid = _ai_field_problems(record)
    if missing or invalid:
        return _error_result(record, missing=missing, invalid=invalid)

    clamped, clamp_notes = _clamp_ai_fields(record)
    label = clamped["soft_label"]
    prominence = clamped["speak_prominence"]
    category = clamped["risk_category"]
    tips = list(clamped["tips"])
    reasoning = clamped["reasoning"]

    applied_rules: list[str] = []
    sleep = _optional_float(record.get("sleep_hours"))
    stress = _optional_int(record.get("stress_level"))
    financial = _optional_int(record.get("financial_stress"))
    support = _optional_int(record.get("social_support"))
    stressors = clamped["primary_stressors"]

    # Rule 1 — force reach-out from AI risk + student stress/support.
    # risk_score > 0.75 AND stress_level >= 8 AND social_support <= 3
    if (
        clamped["risk_score"] > 0.75
        and stress is not None
        and stress >= 8
        and support is not None
        and support <= 3
    ):
        label, prominence, category = _raise_band(
            label, prominence, category,
            SOFT_LABEL_REACH_OUT, "high", "High",
        )
        tips = _ensure_tips(tips, (_TIP_TALK, _TIP_FEELINGS))
        applied_rules.append("reach_out_high_ai_stress_low_support")

    # Rule 2 — mild AI label vs High category + financial strain.
    # soft_label is "You're doing ok" AND risk_category == "High"
    # AND financial_stress >= 8 → at least "Worth a check-in" / medium
    if (
        label == SOFT_LABEL_OK
        and category == "High"
        and financial is not None
        and financial >= 8
    ):
        label, prominence, category = _raise_band(
            label, prominence, category,
            SOFT_LABEL_CHECK_IN, "medium", "High",
        )
        tips = _ensure_tips(tips, (_TIP_MONEY,))
        applied_rules.append("check_in_high_category_financial")

    # Rule 3 — AI sleep_deprivation stressor + student sleep/stress.
    # "sleep_deprivation" in primary_stressors AND sleep_hours <= 5.0
    # AND stress_level >= 7 → at least "Worth a check-in" / medium
    if (
        "sleep_deprivation" in stressors
        and sleep is not None
        and sleep <= 5.0
        and stress is not None
        and stress >= 7
    ):
        label, prominence, category = _raise_band(
            label, prominence, category,
            SOFT_LABEL_CHECK_IN, "medium", "Moderate",
        )
        tips = _ensure_tips(tips, (_TIP_SLEEP,))
        applied_rules.append("check_in_sleep_deprivation")

    if applied_rules:
        reasoning = (
            f"{reasoning} Logic adjusted: {', '.join(applied_rules)}."
        )

    enriched = dict(record)
    enriched.update({
        "ok": True,
        "error": None,
        "soft_label": label,
        "tips": tips,
        "speak_prominence": prominence,
        "risk_score": clamped["risk_score"],
        "risk_category": category,
        "primary_stressors": stressors,
        "reasoning": reasoning,
        "confidence": clamped["confidence"],
        "source": LOGIC_SOURCE,
        "ai_ok": True,
        "logic_rule": applied_rules[0] if applied_rules else "ai_clamped",
        "logic_rules": applied_rules,
        "logic_clamp_notes": clamp_notes,
    })
    return enriched


def finalize_outcome(record: dict[str, Any]) -> dict[str, Any]:
    """Alias of apply_logic — finalize a Gemini-enriched record."""
    return apply_logic(record)


# ---------------------------------------------------------------------------
# Error result — no invented outcomes
# ---------------------------------------------------------------------------

def _error_result(
    record: dict[str, Any],
    *,
    missing: list[str],
    invalid: list[str],
) -> dict[str, Any]:
    """
    Pass through the original fields without adding soft outcomes.
    Callers must treat ok=False as a hard stop, not a fallback engine.
    """
    result = dict(record) if isinstance(record, dict) else {}
    result["ok"] = False
    result["error"] = ERROR_AI_FIELDS_REQUIRED
    result["missing"] = list(missing)
    result["invalid"] = list(invalid)
    result["message"] = (
        "Logic requires a successful Gemini (AI-enriched) record; "
        "it does not invent soft outcomes from student inputs alone."
    )
    return result


def _ai_field_problems(record: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return (missing keys, unusable-type keys). Values are clamped later."""
    missing: list[str] = []
    invalid: list[str] = []

    for key in REQUIRED_AI_FIELDS:
        if key not in record:
            missing.append(key)

    if "risk_score" in record and _as_unit_interval(record.get("risk_score")) is None:
        invalid.append("risk_score")
    if "confidence" in record and _as_unit_interval(record.get("confidence")) is None:
        invalid.append("confidence")
    if "risk_category" in record and not isinstance(record.get("risk_category"), str):
        invalid.append("risk_category")
    if "soft_label" in record and not isinstance(record.get("soft_label"), str):
        invalid.append("soft_label")
    if "speak_prominence" in record and not isinstance(record.get("speak_prominence"), str):
        invalid.append("speak_prominence")
    if "primary_stressors" in record and not isinstance(record.get("primary_stressors"), list):
        invalid.append("primary_stressors")
    if "tips" in record and not isinstance(record.get("tips"), list):
        invalid.append("tips")
    if "reasoning" in record:
        reasoning = record.get("reasoning")
        if not isinstance(reasoning, str) or not reasoning.strip():
            invalid.append("reasoning")

    return missing, invalid


# ---------------------------------------------------------------------------
# Clamp AI values onto allow-lists (present but invalid → map, don't invent)
# ---------------------------------------------------------------------------

def _clamp_ai_fields(record: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    notes: list[str] = []
    risk_score = _as_unit_interval(record.get("risk_score"))
    confidence = _as_unit_interval(record.get("confidence"))
    assert risk_score is not None and confidence is not None

    category, category_clamped = _clamp_risk_category(
        record.get("risk_category"), risk_score
    )
    if category_clamped:
        notes.append("risk_category")

    label, label_clamped = _clamp_soft_label(record.get("soft_label"), category)
    if label_clamped:
        notes.append("soft_label")

    prominence, prominence_clamped = _clamp_speak_prominence(
        record.get("speak_prominence"), category
    )
    if prominence_clamped:
        notes.append("speak_prominence")

    tips, tips_clamped = _clamp_tips(record.get("tips"))
    if tips_clamped:
        notes.append("tips")

    stressors, stressors_clamped = _clamp_stressors(record.get("primary_stressors"))
    if stressors_clamped:
        notes.append("primary_stressors")

    reasoning = str(record.get("reasoning")).strip()

    return {
        "risk_score": risk_score,
        "confidence": confidence,
        "risk_category": category,
        "soft_label": label,
        "speak_prominence": prominence,
        "tips": tips,
        "primary_stressors": stressors,
        "reasoning": reasoning,
    }, notes


def _clamp_risk_category(value: Any, risk_score: float) -> tuple[str, bool]:
    if isinstance(value, str):
        text = value.strip()
        for cat in RISK_CATEGORIES:
            if text.lower() == cat.lower():
                return cat, text != cat
    return _score_to_category(risk_score), True


def _score_to_category(risk_score: float) -> str:
    if risk_score > 0.75:
        return "High"
    if risk_score >= 0.40:
        return "Moderate"
    return "Low"


def _clamp_soft_label(value: Any, risk_category: str) -> tuple[str, bool]:
    if isinstance(value, str):
        mapped = _SOFT_LABEL_ALIASES.get(value.strip())
        if mapped is not None:
            return mapped, mapped != value
    fallback = _CATEGORY_TO_LABEL.get(risk_category, SOFT_LABEL_CHECK_IN)
    return fallback, True


def _clamp_speak_prominence(value: Any, risk_category: str) -> tuple[str, bool]:
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ALLOWED_SPEAK_PROMINENCE:
            return text, text != value
    fallback = _CATEGORY_TO_PROMINENCE.get(risk_category, "medium")
    return fallback, True


def _clamp_tips(value: Any) -> tuple[list[str], bool]:
    cleaned: list[str] = []
    dropped = False
    if not isinstance(value, list):
        return [], True
    for item in value:
        if not isinstance(item, str):
            dropped = True
            continue
        tip_id = item.strip()
        if tip_id in ALLOWED_TIP_IDS:
            if tip_id not in cleaned:
                cleaned.append(tip_id)
        else:
            dropped = True
    return cleaned, dropped


def _clamp_stressors(value: Any) -> tuple[list[str], bool]:
    cleaned: list[str] = []
    dropped = False
    if not isinstance(value, list):
        return [], True
    for item in value:
        if not isinstance(item, str):
            dropped = True
            continue
        name = item.strip()
        if name in ALLOWED_PRIMARY_STRESSORS:
            if name not in cleaned:
                cleaned.append(name)
        else:
            dropped = True
    return cleaned, dropped


def _ensure_tips(tips: list[str], extra: tuple[str, ...]) -> list[str]:
    """Prepend rule-required allow-listed IDs; keep unique; cap at _MAX_TIPS."""
    ordered: list[str] = []
    for tip_id in list(extra) + list(tips):
        if tip_id in ALLOWED_TIP_IDS and tip_id not in ordered:
            ordered.append(tip_id)
    return ordered[:_MAX_TIPS]


def _raise_band(
    label: str,
    prominence: str,
    category: str,
    target_label: str,
    target_prominence: str,
    target_category: str,
) -> tuple[str, str, str]:
    """Escalate only — never lower AI's already-higher band."""
    if _LABEL_RANK.get(target_label, 0) > _LABEL_RANK.get(label, 0):
        label = target_label
    if _PROMINENCE_RANK.get(target_prominence, 0) > _PROMINENCE_RANK.get(prominence, 0):
        prominence = target_prominence
    if _CATEGORY_RANK.get(target_category, 0) > _CATEGORY_RANK.get(category, 0):
        category = target_category
    return label, prominence, category


# ---------------------------------------------------------------------------
# Numeric readers — missing/unparseable means the rule does not fire.
# No defaults: defaults would invent outcomes from incomplete inputs.
# ---------------------------------------------------------------------------

def _as_unit_interval(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number == float("inf") or number == float("-inf"):
        return None
    if number < 0.0:
        return 0.0
    if number > 1.0:
        return 1.0
    return number


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number == float("inf") or number == float("-inf"):
        return None
    return number


def _optional_int(value: Any) -> int | None:
    number = _optional_float(value)
    if number is None:
        return None
    return int(round(number))

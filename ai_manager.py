"""
DoNotStress — AI Processing Layer (ai_manager)

Sole owner of Gemini prompt construction, structured JSON API calls,
schema validation, and graceful retries.

Audience: students (local Flask web UI), not advisors.
Gemini is PRIMARY: it chooses soft_label / tips / speak_prominence
when available. Business-rule fallback lives in logic_manager — not here.

Pure procedural Python: functions only.
No terminal I/O (print / input), no Intervention Tier rules, no file persistence.

Pipeline position:
  User → io_manager → ai_manager → logic_manager → data_manager
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# I/O fields this layer may send to Gemini (student check-in only)
# ---------------------------------------------------------------------------

STUDENT_PROMPT_FIELDS = (
    "student_id",
    "sleep_hours",
    "stress_level",
    "academic_workload",
    "financial_stress",
    "social_support",
    "feelings_text",
)

# ---------------------------------------------------------------------------
# Shared allow-lists — MUST match io_manager (PR #6) exactly.
# logic_manager fallback MUST use the same IDs / strings.
# Tip *copy* lives in io_manager.format_tips — this layer returns IDs only.
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
ALLOWED_RISK_CATEGORIES = frozenset({"Low", "Moderate", "High"})

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

# IDs only — same keys as io_manager.TIPS_ALLOWLIST. Do not invent tip text.
ALLOWED_TIP_IDS = frozenset(
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

_REQUIRED_FIELDS = (
    "risk_score",
    "risk_category",
    "primary_stressors",
    "recommended_support",
    "confidence",
    "reasoning",
    "soft_label",
    "tips",
    "speak_prominence",
)

_DEFAULT_MODEL = "gemini-2.0-flash"
_DEFAULT_MAX_ATTEMPTS = 3
_DEFAULT_RETRY_DELAY_SEC = 0.5
_TIPS_MIN = 1
_TIPS_MAX = 3


def build_prompt(student_dict: dict[str, Any]) -> str:
    """
    Build a structured prompt from a validated student check-in (from io_manager).

    Uses only the student-facing fields. Instructs Gemini to act as a
    supportive student-wellbeing assistant and return ONLY the required JSON.
    """
    payload = {
        "student_id": student_dict.get("student_id"),
        "sleep_hours": student_dict.get("sleep_hours"),
        "stress_level": student_dict.get("stress_level"),
        "academic_workload": student_dict.get("academic_workload"),
        "financial_stress": student_dict.get("financial_stress"),
        "social_support": student_dict.get("social_support"),
        "feelings_text": student_dict.get("feelings_text") or "",
    }
    record_json = json.dumps(payload, ensure_ascii=False, indent=2)
    stressor_list = ", ".join(sorted(ALLOWED_PRIMARY_STRESSORS))
    tip_id_list = ", ".join(sorted(ALLOWED_TIP_IDS))
    soft_label_list = ", ".join(f'"{label}"' for label in SOFT_LABELS)

    return (
        "You are a supportive student-wellbeing assistant for DoNotStress, "
        "a local check-in tool used by students (not an advisor dashboard).\n"
        "Speak to the student with warmth and care. Analyse the check-in "
        "holistically and return ONLY a single JSON object (no markdown "
        "fences, no commentary) with exactly these keys:\n"
        '- "risk_score": float between 0.0 and 1.0 (composite risk likelihood)\n'
        '- "risk_category": one of "Low", "Moderate", "High"\n'
        '- "primary_stressors": list of short snake_case strings chosen ONLY '
        f"from this allow-list: {stressor_list}\n"
        '- "recommended_support": short internal string (the UI shows tips, '
        "not this field)\n"
        '- "confidence": float between 0.0 and 1.0 (your confidence)\n'
        '- "reasoning": short plain-English explanation that is safe to show '
        "a student; do not invent contacts\n"
        f'- "soft_label": EXACTLY one of: {soft_label_list} '
        "(ASCII apostrophe in You're doing ok)\n"
        '- "tips": list of 1 to 3 tip IDs only (not sentences). Each ID MUST '
        f"be one of: {tip_id_list}. Do not invent tip text or extra IDs. "
        "The UI maps these IDs to student-facing copy.\n"
        '- "speak_prominence": one of "low", "medium", "high" — how strongly '
        "the UI should highlight Speak to advisor (always visible; more "
        "prominent when risk is higher)\n"
        "\n"
        "Never invent phone numbers, emails, or offices. Do not include "
        "contact details in JSON. Speak-to-advisor contacts are shown by "
        "the UI separately.\n"
        "\n"
        "Student check-in:\n"
        f"{record_json}\n"
    )


def _as_unit_interval(value: Any, field_name: str) -> tuple[bool, Any]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False, f"{field_name} must be a float between 0.0 and 1.0."
    if number < 0.0 or number > 1.0:
        return False, f"{field_name} must be between 0.0 and 1.0."
    return True, number


def _normalise_soft_label(value: Any) -> tuple[bool, Any]:
    if not isinstance(value, str):
        return False, "soft_label must be a string."
    label = value.strip()
    normalised = _SOFT_LABEL_ALIASES.get(label)
    if normalised is None:
        return (
            False,
            'soft_label must be "You\'re doing ok", "Worth a check-in", '
            'or "Please reach out".',
        )
    return True, normalised


def _normalise_stressors(value: Any) -> tuple[bool, Any]:
    if not isinstance(value, list):
        return False, "primary_stressors must be a list of allow-listed strings."
    seen: set[str] = set()
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return False, "primary_stressors must be a list of strings."
        name = item.strip()
        if name not in ALLOWED_PRIMARY_STRESSORS:
            return False, f"primary_stressor is not on the allow-list: {name}."
        if name not in seen:
            seen.add(name)
            cleaned.append(name)
    return True, cleaned


def _normalise_tips(value: Any) -> tuple[bool, Any]:
    if not isinstance(value, list):
        return False, "tips must be a list of 1–3 allow-listed tip IDs."
    if len(value) < _TIPS_MIN or len(value) > _TIPS_MAX:
        return False, "tips must contain between 1 and 3 allow-listed tip IDs."
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            return False, "each tip must be an allow-listed tip ID."
        tip_id = item.strip()
        if tip_id not in ALLOWED_TIP_IDS:
            return False, f"tip ID is not on the allow-list: {tip_id}"
        if tip_id not in seen:
            seen.add(tip_id)
            cleaned.append(tip_id)
    if not cleaned:
        return False, "tips must contain between 1 and 3 allow-listed tip IDs."
    return True, cleaned


def validate_ai_response(payload: Any) -> tuple[bool, Any]:
    """
    Validate Gemini JSON against the student schema and allow-lists.

    Returns (True, normalised_dict) or (False, error_message).
    Never raises for malformed payloads.
    """
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return False, "Empty AI response string."
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            return False, f"AI response is not valid JSON: {exc}"

    if not isinstance(payload, dict):
        return False, "AI response must be a JSON object."

    missing = [key for key in _REQUIRED_FIELDS if key not in payload]
    if missing:
        return False, f"AI response missing required fields: {', '.join(missing)}."

    score_ok, risk_score = _as_unit_interval(payload["risk_score"], "risk_score")
    if not score_ok:
        return False, risk_score

    risk_category = payload["risk_category"]
    if (
        not isinstance(risk_category, str)
        or risk_category not in ALLOWED_RISK_CATEGORIES
    ):
        return False, 'risk_category must be "Low", "Moderate", or "High".'

    stressors_ok, stressors = _normalise_stressors(payload["primary_stressors"])
    if not stressors_ok:
        return False, stressors

    recommended = payload["recommended_support"]
    if not isinstance(recommended, str) or not recommended.strip():
        return False, "recommended_support must be a non-empty string."

    conf_ok, confidence = _as_unit_interval(payload["confidence"], "confidence")
    if not conf_ok:
        return False, confidence

    reasoning = payload["reasoning"]
    if not isinstance(reasoning, str) or not reasoning.strip():
        return False, "reasoning must be a non-empty string."

    label_ok, soft_label = _normalise_soft_label(payload["soft_label"])
    if not label_ok:
        return False, soft_label

    tips_ok, tips = _normalise_tips(payload["tips"])
    if not tips_ok:
        return False, tips

    speak_prominence = payload["speak_prominence"]
    if (
        not isinstance(speak_prominence, str)
        or speak_prominence.strip() not in ALLOWED_SPEAK_PROMINENCE
    ):
        return False, 'speak_prominence must be "low", "medium", or "high".'

    normalised = {
        "risk_score": risk_score,
        "risk_category": risk_category,
        "primary_stressors": stressors,
        "recommended_support": recommended.strip(),
        "confidence": confidence,
        "reasoning": reasoning.strip(),
        "soft_label": soft_label,
        "tips": tips,
        "speak_prominence": speak_prominence.strip(),
    }
    return True, normalised


def _default_generate(prompt: str, api_key: str, model_name: str) -> str:
    """
    Real Gemini call (structured JSON). Isolated so tests can inject a stub.
    Reads the key from the caller; never hardcode GEMINI_API_KEY.
    """
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=model_name,
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.2,
        },
    )
    response = model.generate_content(prompt)
    text = getattr(response, "text", None)
    if text is None:
        try:
            text = response.candidates[0].content.parts[0].text
        except (AttributeError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Gemini returned no text payload: {exc}") from exc
    return text


def call_gemini(
    prompt: str,
    *,
    api_key: str | None = None,
    model_name: str = _DEFAULT_MODEL,
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
    retry_delay_sec: float = _DEFAULT_RETRY_DELAY_SEC,
    generate_fn: Callable[[str, str, str], str] | None = None,
) -> tuple[bool, dict[str, Any] | None, str | None]:
    """
    Call Gemini with structured JSON output, validate schema, retry on failure.

    Returns (ok, validated_ai_dict_or_None, error_or_None).
    Never crashes the program on API / timeout / malformed JSON.
    """
    key = (api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "")).strip()
    generator = generate_fn if generate_fn is not None else _default_generate

    if generate_fn is None and not key:
        msg = "GEMINI_API_KEY is not set; cannot call Gemini."
        logger.error(msg)
        return False, None, msg

    last_error = "Unknown AI failure."
    attempts = max(1, int(max_attempts))

    for attempt in range(1, attempts + 1):
        try:
            raw_text = generator(prompt, key, model_name)
        except Exception as exc:  # noqa: BLE001 — must not crash pipeline
            last_error = f"Gemini API failure (attempt {attempt}/{attempts}): {exc}"
            logger.warning(last_error)
            if attempt < attempts:
                time.sleep(retry_delay_sec)
            continue

        ok, result = validate_ai_response(raw_text)
        if ok:
            return True, result, None

        last_error = f"Schema validation failed (attempt {attempt}/{attempts}): {result}"
        logger.warning(last_error)
        if attempt < attempts:
            time.sleep(retry_delay_sec)

    return False, None, last_error


def analyse_student(
    student_dict: dict[str, Any],
    *,
    api_key: str | None = None,
    model_name: str = _DEFAULT_MODEL,
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
    retry_delay_sec: float = _DEFAULT_RETRY_DELAY_SEC,
    generate_fn: Callable[[str, str, str], str] | None = None,
) -> tuple[bool, dict[str, Any] | None, str | None]:
    """
    Entry point for the AI Processing Layer.

    Builds prompt → calls Gemini → validates schema → merges AI fields into
    a shallow copy of the student record for logic_manager / the Flask UI.

    Returns (ok, enriched_record_or_None, error_or_None). Never raises for
    API / schema failures.
    """
    if not isinstance(student_dict, dict):
        return False, None, "student_dict must be a dict from io_manager."

    prompt = build_prompt(student_dict)
    ok, ai_fields, err = call_gemini(
        prompt,
        api_key=api_key,
        model_name=model_name,
        max_attempts=max_attempts,
        retry_delay_sec=retry_delay_sec,
        generate_fn=generate_fn,
    )
    if not ok or ai_fields is None:
        return False, None, err

    enriched = dict(student_dict)
    enriched.update(ai_fields)
    return True, enriched, None

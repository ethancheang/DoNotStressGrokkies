"""
DoNotStress — AI Processing Layer (ai_manager)

Sole owner of Gemini prompt construction, structured JSON API calls,
schema validation, and graceful retries.
Pure procedural Python: functions only — no classes.
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
# Schema
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS = (
    "risk_score",
    "risk_category",
    "primary_stressors",
    "recommended_support",
    "confidence",
    "reasoning",
)
_VALID_RISK_CATEGORIES = frozenset({"Low", "Moderate", "High"})
_DEFAULT_MODEL = "gemini-2.0-flash"
_DEFAULT_MAX_ATTEMPTS = 3
_DEFAULT_RETRY_DELAY_SEC = 0.5


def build_prompt(student_dict: dict[str, Any]) -> str:
    """
    Build a structured prompt from a validated student record (from io_manager).

    Instructs Gemini to act as an academic welfare specialist and return
    ONLY the required JSON fields.
    """
    payload = {
        "student_id": student_dict.get("student_id"),
        "sleep_hours": student_dict.get("sleep_hours"),
        "stress_level": student_dict.get("stress_level"),
        "submission_rate": student_dict.get("submission_rate"),
        "cca_count": student_dict.get("cca_count"),
        "financial_stress": student_dict.get("financial_stress"),
        "consecutive_absences": student_dict.get("consecutive_absences"),
        "free_text_concern": student_dict.get("free_text_concern") or "",
    }
    record_json = json.dumps(payload, ensure_ascii=False, indent=2)

    return (
        "You are an academic welfare specialist for a Singapore university "
        "early-warning system (DoNotStress).\n"
        "Analyse the student welfare indicators holistically and return ONLY "
        "a single JSON object (no markdown fences, no commentary) with exactly "
        "these keys:\n"
        '- "risk_score": float between 0.0 and 1.0 (composite risk likelihood)\n'
        '- "risk_category": one of "Low", "Moderate", "High"\n'
        '- "primary_stressors": list of short snake_case strings '
        '(e.g. "sleep_deprivation", "financial_pressure", '
        '"academic_disengagement", "high_stress")\n'
        '- "recommended_support": plain-English recommendation string\n'
        '- "confidence": float between 0.0 and 1.0 (your confidence)\n'
        '- "reasoning": plain-English explanation for an academic advisor\n'
        "\n"
        "Student record:\n"
        f"{record_json}\n"
    )


def validate_ai_response(payload: Any) -> tuple[bool, Any]:
    """
    Validate Gemini JSON against the required schema.

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

    missing = [k for k in _REQUIRED_FIELDS if k not in payload]
    if missing:
        return False, f"AI response missing required fields: {', '.join(missing)}."

    try:
        risk_score = float(payload["risk_score"])
    except (TypeError, ValueError):
        return False, "risk_score must be a float between 0.0 and 1.0."
    if risk_score < 0.0 or risk_score > 1.0:
        return False, "risk_score must be between 0.0 and 1.0."

    risk_category = payload["risk_category"]
    if not isinstance(risk_category, str) or risk_category not in _VALID_RISK_CATEGORIES:
        return False, 'risk_category must be "Low", "Moderate", or "High".'

    stressors = payload["primary_stressors"]
    if not isinstance(stressors, list) or not all(isinstance(s, str) for s in stressors):
        return False, "primary_stressors must be a list of strings."

    recommended = payload["recommended_support"]
    if not isinstance(recommended, str) or not recommended.strip():
        return False, "recommended_support must be a non-empty string."

    try:
        confidence = float(payload["confidence"])
    except (TypeError, ValueError):
        return False, "confidence must be a float between 0.0 and 1.0."
    if confidence < 0.0 or confidence > 1.0:
        return False, "confidence must be between 0.0 and 1.0."

    reasoning = payload["reasoning"]
    if not isinstance(reasoning, str) or not reasoning.strip():
        return False, "reasoning must be a non-empty string."

    normalised = {
        "risk_score": risk_score,
        "risk_category": risk_category,
        "primary_stressors": list(stressors),
        "recommended_support": recommended.strip(),
        "confidence": confidence,
        "reasoning": reasoning.strip(),
    }
    return True, normalised


def _default_generate(prompt: str, api_key: str, model_name: str) -> str:
    """
    Real Gemini call (structured JSON). Isolated so tests can inject a stub.
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
    a shallow copy of the student record for logic_manager.

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

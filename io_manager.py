"""I/O Manager for DoNotStress — student-facing Flask input layer.

Audience is students via a local Flask web UI (not advisors). This module
owns pure-function validators and template formatters only.

Joe's Flask app should import FORM_FIELDS / validate_student_form /
format_* helpers. Do not put Gemini, Intervention Tier rules, or file I/O
here. Functions only — no object types defined in this module.

Canonical Flask form field names (request.form keys) — use FORM_FIELDS:
  student_id          required  str   2-digit year in {23,24,25,26} + 5 digits
  sleep_hours         required  float 0.0–24.0 inclusive, 0.5-hour steps
  stress_level        required  int   1–10 inclusive
  academic_workload   required  int   1–10 inclusive
  financial_stress    required  int   1–10 inclusive (scale, not yes/no)
  social_support      required  int   1–10 inclusive
  feelings_text       optional  str   blank allowed
                                      prompt: "In your own words, how have you
                                      been feeling about school lately?"

Removed from this public API (do not collect):
  submission_rate, cca_count, consecutive_absences, free_text_concern,
  and the old financial_stress yes/no bool.

Validators are pure: validate_X(raw) -> (ok, value_or_error_message).
Web entry point: validate_student_form(form_dict) -> (ok, record_or_errors).
A thin CLI collect_student_record() remains for smoke tests only.
"""

# ---------------------------------------------------------------------------
# Form field names for Flask coordination
# ---------------------------------------------------------------------------

FORM_FIELDS = {
    "student_id": "student_id",
    "sleep_hours": "sleep_hours",
    "stress_level": "stress_level",
    "academic_workload": "academic_workload",
    "financial_stress": "financial_stress",
    "social_support": "social_support",
    "feelings_text": "feelings_text",
}

FORM_PROMPTS = {
    "student_id": "Student ID",
    "sleep_hours": "How many hours of sleep did you get last night?",
    "stress_level": "How stressed have you been feeling? (1–10)",
    "academic_workload": "How heavy has your academic workload felt? (1–10)",
    "financial_stress": "How stressed have you been about money? (1–10)",
    "social_support": "How supported have you felt by people around you? (1–10)",
    "feelings_text": (
        "In your own words, how have you been feeling about school lately?"
    ),
}

RECORD_FIELD_ORDER = (
    "student_id",
    "sleep_hours",
    "stress_level",
    "academic_workload",
    "financial_stress",
    "social_support",
    "feelings_text",
)

REQUIRED_FORM_FIELDS = (
    "student_id",
    "sleep_hours",
    "stress_level",
    "academic_workload",
    "financial_stress",
    "social_support",
)

# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------

VALID_STUDENT_ID_YEARS = ("23", "24", "25", "26")
STUDENT_ID_EXAMPLE = "2605581"
STUDENT_ID_SERIAL_DIGITS = 5

SLEEP_HOURS_MIN = 0.0
SLEEP_HOURS_MAX = 24.0
SLEEP_HOURS_STEP = 0.5

SCALE_MIN = 1
SCALE_MAX = 10

# ---------------------------------------------------------------------------
# Soft labels, tips allow-list, advisor contacts (hardcoded — never invent)
# ---------------------------------------------------------------------------

SOFT_LABELS = (
    "You're doing ok",
    "Worth a check-in",
    "Please reach out",
)

SOFT_LABEL_COPY = {
    "You're doing ok": {
        "label": "You're doing ok",
        "heading": "You're doing ok",
        "body": "Your check-in looks steady. Keep looking after yourself.",
        "tone": "reassuring",
    },
    "Worth a check-in": {
        "label": "Worth a check-in",
        "heading": "Worth a check-in",
        "body": (
            "Some things look a bit heavier right now. "
            "A conversation could help."
        ),
        "tone": "supportive",
    },
    "Please reach out": {
        "label": "Please reach out",
        "heading": "Please reach out",
        "body": (
            "Please reach out for support. "
            "You do not have to handle this on your own."
        ),
        "tone": "urgent",
    },
}

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

SPEAK_PROMINENCE = ("low", "medium", "high")

# Real contacts only. Model / callers must never invent others.
ADVISOR_EMAIL = "SITCounselling@SingaporeTech.edu.sg"
ADVISOR_HELPLINE = "6592 2030"
ADVISOR_MAILTO = "mailto:SITCounselling@SingaporeTech.edu.sg"

ADVISOR_CONTACTS = {
    "email": ADVISOR_EMAIL,
    "helpline": ADVISOR_HELPLINE,
    "mailto": ADVISOR_MAILTO,
}

SPEAK_PANEL_COPY = {
    "low": {
        "heading": "Support is available",
        "body": (
            "If you would like to talk, you can contact SIT Counselling."
        ),
        "cta": "Optional: get in touch",
    },
    "medium": {
        "heading": "Consider speaking with someone",
        "body": (
            "It may help to talk with SIT Counselling about how you have "
            "been feeling."
        ),
        "cta": "Reach out when you are ready",
    },
    "high": {
        "heading": "Please reach out",
        "body": (
            "Please contact SIT Counselling. You do not have to handle "
            "this on your own."
        ),
        "cta": "Contact support now",
    },
}


# ---------------------------------------------------------------------------
# Internal helpers (pure)
# ---------------------------------------------------------------------------

def _as_text(raw) -> str:
    """Normalize raw input to a stripped string. None becomes empty."""
    if raw is None:
        return ""
    return str(raw).strip()


def _looks_like_int(text: str) -> bool:
    """True when text is a base-10 integer (optional leading + or -)."""
    if not text:
        return False
    if text[0] in "+-":
        return len(text) > 1 and text[1:].isdigit()
    return text.isdigit()


def _parse_int(raw) -> tuple[bool, int | str]:
    text = _as_text(raw)
    if not _looks_like_int(text):
        return False, "must be a whole number (integer)"
    return True, int(text)


def _parse_float(raw) -> tuple[bool, float | str]:
    text = _as_text(raw)
    if text == "":
        return False, "must be a number"
    lowered = text.lower()
    if lowered in {"nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}:
        return False, "must be a finite number"
    try:
        value = float(text)
    except ValueError:
        return False, "must be a number"
    if value != value:  # NaN
        return False, "must be a finite number"
    if value == float("inf") or value == float("-inf"):
        return False, "must be a finite number"
    return True, value


def _is_half_hour_step(value: float) -> bool:
    """True when value is a multiple of 0.5 (within a tiny float tolerance)."""
    steps = value / SLEEP_HOURS_STEP
    return abs(steps - round(steps)) <= 1e-9


def _quantize_half_hour(value: float) -> float:
    return round(value / SLEEP_HOURS_STEP) * SLEEP_HOURS_STEP


def _validate_scale_1_to_10(raw, field_label: str) -> tuple[bool, int | str]:
    ok, parsed = _parse_int(raw)
    if not ok:
        return False, f"{field_label} {parsed}."
    if parsed < SCALE_MIN or parsed > SCALE_MAX:
        return False, (
            f"{field_label} must be an integer between {SCALE_MIN} and "
            f"{SCALE_MAX} (inclusive)."
        )
    return True, parsed


def _form_get(form_dict, key: str):
    """Read one key from a Flask request.form-like mapping."""
    if form_dict is None:
        return ""
    getter = getattr(form_dict, "get", None)
    if getter is None:
        return ""
    value = getter(key)
    if value is None:
        return ""
    return value


# ---------------------------------------------------------------------------
# Normalize helpers (Flask request.form strings)
# ---------------------------------------------------------------------------

def normalize_form_value(raw) -> str:
    """Strip a single form value. None becomes ''."""
    return _as_text(raw)


def extract_form_fields(form_dict) -> dict:
    """Return only the canonical FORM_FIELDS keys from a form mapping."""
    return {key: normalize_form_value(_form_get(form_dict, key)) for key in FORM_FIELDS}


# ---------------------------------------------------------------------------
# Validators — validate_X(raw) -> (ok, value_or_error)
# ---------------------------------------------------------------------------

def validate_student_id(raw) -> tuple[bool, str]:
    """Require a 2-digit year in {23,24,25,26} followed by 5 digits."""
    text = _as_text(raw)
    if not text:
        return False, (
            "Student ID is required. Use a 2-digit year (23, 24, 25, or 26) "
            f"followed by 5 digits (e.g. {STUDENT_ID_EXAMPLE})."
        )
    if not text.isdigit() or len(text) != 2 + STUDENT_ID_SERIAL_DIGITS:
        return False, (
            "Student ID must be 7 digits: a 2-digit year (23, 24, 25, or 26) "
            f"followed by 5 digits (e.g. {STUDENT_ID_EXAMPLE})."
        )
    year = text[:2]
    if year not in VALID_STUDENT_ID_YEARS:
        allowed = ", ".join(VALID_STUDENT_ID_YEARS)
        return False, f"Student ID year '{year}' is not allowed. Use one of: {allowed}."
    return True, text


def validate_sleep_hours(raw) -> tuple[bool, float | str]:
    """Require a float in [0.0, 24.0] on 0.5-hour steps (5.0, 5.5, 6.0)."""
    ok, parsed = _parse_float(raw)
    if not ok:
        return False, f"Sleep hours {parsed}."
    if parsed < SLEEP_HOURS_MIN or parsed > SLEEP_HOURS_MAX:
        return False, (
            f"Sleep hours must be between {SLEEP_HOURS_MIN:.1f} and "
            f"{SLEEP_HOURS_MAX:.1f} (inclusive), in {SLEEP_HOURS_STEP}-hour "
            "steps (e.g. 5.0, 5.5, 6.0)."
        )
    if not _is_half_hour_step(parsed):
        return False, (
            "Sleep hours must be in 0.5-hour steps "
            "(e.g. 5.0, 5.5, 6.0). Values like 5.25 are not allowed."
        )
    return True, _quantize_half_hour(parsed)


def validate_stress_level(raw) -> tuple[bool, int | str]:
    """Require an integer in [1, 10]."""
    return _validate_scale_1_to_10(raw, "Stress level")


def validate_academic_workload(raw) -> tuple[bool, int | str]:
    """Require an integer in [1, 10]."""
    return _validate_scale_1_to_10(raw, "Academic workload")


def validate_financial_stress(raw) -> tuple[bool, int | str]:
    """Require an integer in [1, 10] (scale, not yes/no)."""
    return _validate_scale_1_to_10(raw, "Financial stress")


def validate_social_support(raw) -> tuple[bool, int | str]:
    """Require an integer in [1, 10]."""
    return _validate_scale_1_to_10(raw, "Social support")


def validate_feelings_text(raw) -> tuple[bool, str]:
    """Optional free text. Blank or whitespace-only is stored as ''."""
    return True, _as_text(raw)


_FIELD_VALIDATORS = {
    "student_id": validate_student_id,
    "sleep_hours": validate_sleep_hours,
    "stress_level": validate_stress_level,
    "academic_workload": validate_academic_workload,
    "financial_stress": validate_financial_stress,
    "social_support": validate_social_support,
    "feelings_text": validate_feelings_text,
}


def validate_student_form(form_dict) -> tuple[bool, dict]:
    """Validate every student field from a Flask request.form-like mapping.

    Returns (True, record) when all fields are valid.
    Returns (False, errors) when any required field fails. `errors` maps
    field name -> error message. All fields are checked (not fail-fast).

    `form_dict` may be a dict, Flask ImmutableMultiDict, or any object
    with .get(key). Missing keys are treated as blank strings.
    """
    record = {}
    errors = {}
    for key in RECORD_FIELD_ORDER:
        raw = _form_get(form_dict, key)
        ok, result = _FIELD_VALIDATORS[key](raw)
        if ok:
            record[key] = result
        else:
            errors[key] = result
    if errors:
        return False, errors
    return True, record


def collect_student_record_from_form(form_dict) -> tuple[bool, dict]:
    """Alias of validate_student_form for Flask call sites."""
    return validate_student_form(form_dict)


# ---------------------------------------------------------------------------
# Formatters for web templates — strings / plain dicts of copy; no print
# ---------------------------------------------------------------------------

def format_soft_label(soft_label) -> dict:
    """Return template copy for a soft label.

    soft_label must be one of SOFT_LABELS:
      "You're doing ok" | "Worth a check-in" | "Please reach out"
    """
    text = _as_text(soft_label)
    copy = SOFT_LABEL_COPY.get(text)
    if copy is None:
        allowed = ", ".join(f'"{label}"' for label in SOFT_LABELS)
        return {
            "label": "",
            "heading": "",
            "body": "",
            "tone": "",
            "error": f"Unknown soft label. Use one of: {allowed}.",
        }
    return {
        "label": copy["label"],
        "heading": copy["heading"],
        "body": copy["body"],
        "tone": copy["tone"],
        "error": None,
    }


def format_tips(tips) -> dict:
    """Return template copy for an allow-listed tip list.

    `tips` is a list of tip IDs (preferred) or exact allow-list strings.
    Unknown tips are dropped — this formatter never invents copy.
    Duplicates keep the first occurrence only.
    """
    items = []
    seen = set()
    if tips is None:
        tips = []
    for raw in tips:
        text = _as_text(raw)
        if not text or text in seen:
            continue
        tip_id = None
        tip_text = None
        if text in TIPS_ALLOWLIST:
            tip_id = text
            tip_text = TIPS_ALLOWLIST[text]
        else:
            for known_id, known_text in TIPS_ALLOWLIST.items():
                if text == known_text:
                    tip_id = known_id
                    tip_text = known_text
                    break
        if tip_id is None:
            continue
        seen.add(tip_id)
        seen.add(tip_text)
        items.append({"id": tip_id, "text": tip_text})
    return {
        "heading": "Suggestions for you",
        "items": items,
        "texts": [item["text"] for item in items],
    }


def format_speak_to_advisor_panel(speak_prominence) -> dict:
    """Return the Speak-to-Advisor panel copy and hardcoded contacts.

    speak_prominence is "low" | "medium" | "high" and changes tone only.
    Contacts are always the same real values — never invented:
      email    SITCounselling@SingaporeTech.edu.sg
      helpline 6592 2030
      mailto   mailto:SITCounselling@SingaporeTech.edu.sg

    Unknown prominence still includes those contacts and uses medium copy.
    """
    prominence = _as_text(speak_prominence).lower()
    copy = SPEAK_PANEL_COPY.get(prominence)
    error = None
    if copy is None:
        prominence = "medium"
        copy = SPEAK_PANEL_COPY["medium"]
        allowed = ", ".join(SPEAK_PROMINENCE)
        error = f"Unknown speak_prominence. Use one of: {allowed}."
    return {
        "prominence": prominence,
        "heading": copy["heading"],
        "body": copy["body"],
        "cta": copy["cta"],
        "email": ADVISOR_EMAIL,
        "helpline": ADVISOR_HELPLINE,
        "mailto": ADVISOR_MAILTO,
        "contacts": {
            "email": ADVISOR_EMAIL,
            "helpline": ADVISOR_HELPLINE,
            "mailto": ADVISOR_MAILTO,
        },
        "error": error,
    }


def format_student_record(record: dict) -> dict:
    """Return a plain dict of labelled values for a confirmation template."""
    if not record:
        return {
            "heading": "Your check-in",
            "fields": [],
            "empty": True,
        }
    fields = []
    for key in RECORD_FIELD_ORDER:
        if key not in record:
            continue
        value = record[key]
        if key == "feelings_text":
            display = str(value).strip() if value is not None else ""
            if not display:
                display = "(skipped)"
        elif key == "sleep_hours":
            display = f"{float(value):.1f}"
        else:
            display = str(value)
        fields.append({
            "key": key,
            "label": FORM_PROMPTS[key],
            "value": display,
        })
    return {
        "heading": "Your check-in",
        "fields": fields,
        "empty": len(fields) == 0,
    }


# ---------------------------------------------------------------------------
# Thin CLI helper — smoke tests only; field names match the web form
# ---------------------------------------------------------------------------

def print_message(message: str) -> None:
    print(message)


def print_error(message: str) -> None:
    print(f"Error: {message}")


def _prompt_until_valid(prompt: str, validator):
    """Read a line, validate, and re-prompt with the error until valid."""
    while True:
        raw = input(prompt)
        ok, result = validator(raw)
        if ok:
            return result
        print_error(result)


def get_student_id() -> str:
    return _prompt_until_valid(
        "Student ID (YYxxxxx, year 23-26, e.g. 2605581): ",
        validate_student_id,
    )


def get_sleep_hours() -> float:
    return _prompt_until_valid(
        "Sleep hours last night (0.0 to 24.0, in 0.5 steps): ",
        validate_sleep_hours,
    )


def get_stress_level() -> int:
    return _prompt_until_valid(
        "Stress level (1 to 10): ",
        validate_stress_level,
    )


def get_academic_workload() -> int:
    return _prompt_until_valid(
        "Academic workload (1 to 10): ",
        validate_academic_workload,
    )


def get_financial_stress() -> int:
    return _prompt_until_valid(
        "Financial stress (1 to 10): ",
        validate_financial_stress,
    )


def get_social_support() -> int:
    return _prompt_until_valid(
        "Social support (1 to 10): ",
        validate_social_support,
    )


def get_feelings_text() -> str:
    return _prompt_until_valid(
        "In your own words, how have you been feeling about school lately? "
        "(optional, press Enter to skip): ",
        validate_feelings_text,
    )


def collect_student_record() -> dict:
    """Prompt for every web-aligned field (CLI smoke test only)."""
    print_message("Student wellbeing check-in.")
    print_message("Invalid values will be rejected until a valid value is entered.")
    return {
        "student_id": get_student_id(),
        "sleep_hours": get_sleep_hours(),
        "stress_level": get_stress_level(),
        "academic_workload": get_academic_workload(),
        "financial_stress": get_financial_stress(),
        "social_support": get_social_support(),
        "feelings_text": get_feelings_text(),
    }


if __name__ == "__main__":
    demo = collect_student_record()
    print_message("")
    print_message(str(format_student_record(demo)))

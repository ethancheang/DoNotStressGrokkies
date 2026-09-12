"""I/O Manager for DoNotStress — Student Academic & Wellbeing Risk CLI.

This is the only application module allowed to call print() or input().
Validators are pure: validate_X(raw) -> (ok, value_or_error) and never
touch stdin/stdout, so they can be unit-tested in isolation.

Other layers (ai_manager, logic_manager, data_manager, main) should call
the getters, collect_student_record(), formatters, and print_* helpers
here instead of talking to the console themselves.
"""

VALID_STUDENT_ID_YEARS = ("23", "24", "25", "26")
STUDENT_ID_EXAMPLE = "2605581"
STUDENT_ID_SERIAL_DIGITS = 5

SLEEP_HOURS_MIN = 0.0
SLEEP_HOURS_MAX = 24.0
STRESS_LEVEL_MIN = 1
STRESS_LEVEL_MAX = 10
SUBMISSION_RATE_MIN = 0.0
SUBMISSION_RATE_MAX = 100.0

RECORD_FIELD_ORDER = (
    "student_id",
    "sleep_hours",
    "stress_level",
    "submission_rate",
    "cca_count",
    "financial_stress",
    "consecutive_absences",
    "free_text_concern",
)

RECORD_LABELS = {
    "student_id": "Student ID",
    "sleep_hours": "Sleep Hours",
    "stress_level": "Stress Level",
    "submission_rate": "Submission Rate",
    "cca_count": "CCA Count",
    "financial_stress": "Financial Stress",
    "consecutive_absences": "Consecutive Absences",
    "free_text_concern": "Free-text Concern",
}

SUMMARY_LABELS = {
    "total_students": "Total Students",
    "average_sleep_hours": "Average Sleep Hours",
    "average_stress_level": "Average Stress Level",
    "average_submission_rate": "Average Submission Rate",
    "average_cca_count": "Average CCA Count",
    "financial_stress_count": "Students with Financial Stress",
    "average_consecutive_absences": "Average Consecutive Absences",
    "high_risk_count": "High Risk Count",
    "medium_risk_count": "Medium Risk Count",
    "low_risk_count": "Low Risk Count",
}

PERCENT_KEYS = {
    "submission_rate",
    "average_submission_rate",
}

_YES_VALUES = {"yes"}
_NO_VALUES = {"no"}


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


def _humanize_key(key: str) -> str:
    return str(key).replace("_", " ").title()


def _format_bool(value: bool) -> str:
    return "Yes" if value else "No"


def _format_field_value(key: str, value) -> str:
    if value is None:
        return "(none)"
    if key == "free_text_concern":
        text = str(value).strip()
        return text if text else "(none)"
    if key == "financial_stress" or type(value) is bool:
        return _format_bool(bool(value))
    if key in PERCENT_KEYS:
        return f"{float(value):.1f}%"
    if key in {"sleep_hours", "average_sleep_hours", "average_submission_rate"}:
        return f"{float(value):.1f}"
    if type(value) is float:
        return f"{value:.1f}"
    return str(value)


def _format_summary_value(key: str, value) -> str:
    if type(value) is bool:
        return _format_bool(value)
    if type(value) is list or type(value) is tuple:
        if len(value) == 0:
            return "(none)"
        return ", ".join(str(item) for item in value)
    if type(value) is dict:
        if len(value) == 0:
            return "(none)"
        inner = "; ".join(
            f"{_humanize_key(inner_key)}={_format_summary_value(inner_key, inner_value)}"
            for inner_key, inner_value in value.items()
        )
        return inner
    if key in PERCENT_KEYS:
        try:
            return f"{float(value):.1f}%"
        except (TypeError, ValueError):
            return str(value)
    if type(value) is float:
        return f"{value:.1f}"
    return str(value)


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
    """Require a float in [0.0, 24.0]."""
    ok, parsed = _parse_float(raw)
    if not ok:
        return False, f"Sleep hours {parsed}."
    if parsed < SLEEP_HOURS_MIN or parsed > SLEEP_HOURS_MAX:
        return False, (
            f"Sleep hours must be between {SLEEP_HOURS_MIN:.1f} and "
            f"{SLEEP_HOURS_MAX:.1f} (inclusive)."
        )
    return True, parsed


def validate_stress_level(raw) -> tuple[bool, int | str]:
    """Require an integer in [1, 10]."""
    ok, parsed = _parse_int(raw)
    if not ok:
        return False, f"Stress level {parsed}."
    if parsed < STRESS_LEVEL_MIN or parsed > STRESS_LEVEL_MAX:
        return False, (
            f"Stress level must be an integer between {STRESS_LEVEL_MIN} and "
            f"{STRESS_LEVEL_MAX} (inclusive)."
        )
    return True, parsed


def validate_submission_rate(raw) -> tuple[bool, float | str]:
    """Require a float in [0.0, 100.0]."""
    ok, parsed = _parse_float(raw)
    if not ok:
        return False, f"Submission rate {parsed}."
    if parsed < SUBMISSION_RATE_MIN or parsed > SUBMISSION_RATE_MAX:
        return False, (
            f"Submission rate must be between {SUBMISSION_RATE_MIN:.1f} and "
            f"{SUBMISSION_RATE_MAX:.1f} (inclusive)."
        )
    return True, parsed


def validate_cca_count(raw) -> tuple[bool, int | str]:
    """Require an integer >= 0."""
    ok, parsed = _parse_int(raw)
    if not ok:
        return False, f"CCA count {parsed}."
    if parsed < 0:
        return False, "CCA count must be an integer greater than or equal to 0."
    return True, parsed


def validate_financial_stress(raw) -> tuple[bool, bool | str]:
    """Require yes/no only (case-insensitive). Returns a bool on success."""
    text = _as_text(raw).lower()
    if text in _YES_VALUES:
        return True, True
    if text in _NO_VALUES:
        return True, False
    return False, "Financial stress must be 'yes' or 'no' (not y/n or true/false)."


def validate_consecutive_absences(raw) -> tuple[bool, int | str]:
    """Require an integer >= 0."""
    ok, parsed = _parse_int(raw)
    if not ok:
        return False, f"Consecutive absences {parsed}."
    if parsed < 0:
        return False, "Consecutive absences must be an integer greater than or equal to 0."
    return True, parsed


def validate_free_text_concern(raw) -> tuple[bool, str]:
    """Optional free text. Blank or whitespace-only is stored as ''."""
    return True, _as_text(raw)


# ---------------------------------------------------------------------------
# Interactive getters — re-prompt until a validator accepts the value
# ---------------------------------------------------------------------------

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
        "Sleep hours last night (0.0 to 24.0): ",
        validate_sleep_hours,
    )


def get_stress_level() -> int:
    return _prompt_until_valid(
        "Stress level (1 to 10): ",
        validate_stress_level,
    )


def get_submission_rate() -> float:
    return _prompt_until_valid(
        "Assignment submission rate (0.0 to 100.0): ",
        validate_submission_rate,
    )


def get_cca_count() -> int:
    return _prompt_until_valid(
        "Number of CCAs (0 or more): ",
        validate_cca_count,
    )


def get_financial_stress() -> bool:
    return _prompt_until_valid(
        "Financial stress? (yes/no): ",
        validate_financial_stress,
    )


def get_consecutive_absences() -> int:
    return _prompt_until_valid(
        "Consecutive absences (0 or more): ",
        validate_consecutive_absences,
    )


def get_free_text_concern() -> str:
    return _prompt_until_valid(
        "Free-text concern (optional, press Enter to skip): ",
        validate_free_text_concern,
    )


def collect_student_record() -> dict:
    """Prompt for every student field and return a snake_case record dict."""
    print_message("Enter student academic and wellbeing details.")
    print_message("Invalid values will be rejected until a valid value is entered.")
    return {
        "student_id": get_student_id(),
        "sleep_hours": get_sleep_hours(),
        "stress_level": get_stress_level(),
        "submission_rate": get_submission_rate(),
        "cca_count": get_cca_count(),
        "financial_stress": get_financial_stress(),
        "consecutive_absences": get_consecutive_absences(),
        "free_text_concern": get_free_text_concern(),
    }


# ---------------------------------------------------------------------------
# Formatters — return strings; no print()
# ---------------------------------------------------------------------------

def format_student_record(record: dict) -> str:
    """Render one student record as a labelled block."""
    if not record:
        return "Student Record\n--------------\nNo student data to display."

    label_width = max(len(label) for label in RECORD_LABELS.values())
    lines = ["Student Record", "-" * len("Student Record")]
    for key in RECORD_FIELD_ORDER:
        if key not in record:
            continue
        label = RECORD_LABELS[key]
        value = _format_field_value(key, record[key])
        lines.append(f"{label + ':':<{label_width + 1}} {value}")
    return "\n".join(lines)


def format_cohort_list(records) -> str:
    """Render a list of student records as a numbered cohort listing."""
    if records is None:
        records = []
    count = len(records)
    heading = f"Cohort List ({count} student{'s' if count != 1 else ''})"
    lines = [heading, "=" * len(heading)]
    if count == 0:
        lines.append("No student records to display.")
        return "\n".join(lines)

    for index, record in enumerate(records, start=1):
        record = record or {}
        student_id = record.get("student_id", "(unknown)")
        sleep = _format_field_value("sleep_hours", record.get("sleep_hours", 0.0))
        stress = record.get("stress_level", "?")
        submit = _format_field_value("submission_rate", record.get("submission_rate", 0.0))
        cca = record.get("cca_count", "?")
        financial = _format_field_value("financial_stress", record.get("financial_stress", False))
        absences = record.get("consecutive_absences", "?")
        concern = _format_field_value("free_text_concern", record.get("free_text_concern", ""))
        lines.append(
            f"{index}. {student_id} | sleep {sleep}h | stress {stress}/10 | "
            f"submit {submit} | cca {cca} | financial {financial} | absences {absences}"
        )
        lines.append(f"   Concern: {concern}")
    return "\n".join(lines)


def format_summary_view(summary: dict) -> str:
    """Render a cohort summary dict produced by another layer.

    Known keys get friendly labels; any extra snake_case keys are humanized.
    Nested dicts and lists are formatted inline so logic_manager can pass
    extra aggregates without this module knowing the scoring rules.
    """
    heading = "Cohort Summary"
    lines = [heading, "=" * len(heading)]
    if not summary:
        lines.append("No summary data to display.")
        return "\n".join(lines)

    rendered_keys = set()
    rows = []

    for key in SUMMARY_LABELS:
        if key in summary:
            rows.append((SUMMARY_LABELS[key], _format_summary_value(key, summary[key])))
            rendered_keys.add(key)

    for key, value in summary.items():
        if key in rendered_keys:
            continue
        rows.append((_humanize_key(key), _format_summary_value(key, value)))

    label_width = max(len(label) for label, _ in rows)
    for label, value in rows:
        lines.append(f"{label + ':':<{label_width + 1}} {value}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# print_* helpers — the only console output API other layers should use
# ---------------------------------------------------------------------------

def print_message(message: str) -> None:
    print(message)


def print_error(message: str) -> None:
    print(f"Error: {message}")


def print_student_record(record: dict) -> None:
    print(format_student_record(record))


def print_cohort_list(records) -> None:
    print(format_cohort_list(records))


def print_summary_view(summary: dict) -> None:
    print(format_summary_view(summary))


if __name__ == "__main__":
    demo_record = collect_student_record()
    print_message("")
    print_student_record(demo_record)

"""Tests for io_manager validators and formatters.

Validators are pure and must not touch stdin/stdout. Formatters return
strings and must not call print(). Getters are covered with mocked I/O
to confirm re-prompt-until-valid behaviour.
"""

from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import io_manager as io


# ---------------------------------------------------------------------------
# Source / architecture constraints
# ---------------------------------------------------------------------------

def test_io_manager_has_no_class_keyword():
    source = Path(io.__file__).read_text(encoding="utf-8")
    assert "class " not in source
    assert "\nclass" not in source


def test_validators_do_not_use_print_or_input():
    source = Path(io.__file__).read_text(encoding="utf-8")
    # Validators live above the interactive getters. Ensure each validate_*
    # function body itself never calls print/input by executing them with
    # no patched builtins — they must not raise or block.
    validators = (
        io.validate_student_id,
        io.validate_sleep_hours,
        io.validate_stress_level,
        io.validate_submission_rate,
        io.validate_cca_count,
        io.validate_financial_stress,
        io.validate_consecutive_absences,
        io.validate_free_text_concern,
    )
    with patch("builtins.input", side_effect=AssertionError("validator used input()")):
        with patch("builtins.print", side_effect=AssertionError("validator used print()")):
            for validator in validators:
                validator("1")
                validator("")
                validator(None)


# ---------------------------------------------------------------------------
# validate_student_id
# ---------------------------------------------------------------------------

def test_validate_student_id_accepts_allowed_years():
    for student_id in ("2300000", "2412345", "2500001", "2605581"):
        ok, value = io.validate_student_id(student_id)
        assert ok is True
        assert value == student_id


def test_validate_student_id_strips_whitespace():
    ok, value = io.validate_student_id("  2605581  ")
    assert ok is True
    assert value == "2605581"


def test_validate_student_id_accepts_numeric_raw():
    ok, value = io.validate_student_id(2605581)
    assert ok is True
    assert value == "2605581"


def test_validate_student_id_rejects_disallowed_year():
    ok, error = io.validate_student_id("2705581")
    assert ok is False
    assert "27" in error
    ok, error = io.validate_student_id("2205581")
    assert ok is False
    assert "22" in error


def test_validate_student_id_rejects_wrong_length_and_non_digits():
    for raw in ("260558", "26055811", "26a5581", "2605581a", "", "   ", None, "26 05581"):
        ok, error = io.validate_student_id(raw)
        assert ok is False
        assert isinstance(error, str)
        assert error


# ---------------------------------------------------------------------------
# validate_sleep_hours
# ---------------------------------------------------------------------------

def test_validate_sleep_hours_accepts_bounds_and_decimals():
    cases = (
        ("0", 0.0),
        ("0.0", 0.0),
        ("24", 24.0),
        ("24.0", 24.0),
        ("7.5", 7.5),
        (" 8 ", 8.0),
        (8, 8.0),
        (6.25, 6.25),
    )
    for raw, expected in cases:
        ok, value = io.validate_sleep_hours(raw)
        assert ok is True
        assert value == expected


def test_validate_sleep_hours_rejects_out_of_range_and_non_numeric():
    for raw in ("-0.1", "24.01", "25", "abc", "", None, "nan", "inf", "+inf", "-inf"):
        ok, error = io.validate_sleep_hours(raw)
        assert ok is False
        assert isinstance(error, str)
        assert error


# ---------------------------------------------------------------------------
# validate_stress_level
# ---------------------------------------------------------------------------

def test_validate_stress_level_accepts_integers_1_to_10():
    for raw, expected in (("1", 1), ("10", 10), ("5", 5), (" 7 ", 7), (3, 3)):
        ok, value = io.validate_stress_level(raw)
        assert ok is True
        assert value == expected
        assert type(value) is int


def test_validate_stress_level_rejects_invalid():
    for raw in ("0", "11", "5.5", "5.0", "", None, "abc", "-1"):
        ok, error = io.validate_stress_level(raw)
        assert ok is False
        assert isinstance(error, str)


# ---------------------------------------------------------------------------
# validate_submission_rate
# ---------------------------------------------------------------------------

def test_validate_submission_rate_accepts_bounds_and_decimals():
    cases = (("0", 0.0), ("100", 100.0), ("85.5", 85.5), (" 50 ", 50.0), (0, 0.0))
    for raw, expected in cases:
        ok, value = io.validate_submission_rate(raw)
        assert ok is True
        assert value == expected


def test_validate_submission_rate_rejects_invalid():
    for raw in ("-0.1", "100.01", "101", "", None, "abc", "nan"):
        ok, error = io.validate_submission_rate(raw)
        assert ok is False
        assert isinstance(error, str)


# ---------------------------------------------------------------------------
# validate_cca_count
# ---------------------------------------------------------------------------

def test_validate_cca_count_accepts_zero_and_positive():
    for raw, expected in (("0", 0), ("3", 3), (" 12 ", 12), (0, 0)):
        ok, value = io.validate_cca_count(raw)
        assert ok is True
        assert value == expected
        assert type(value) is int


def test_validate_cca_count_rejects_invalid():
    for raw in ("-1", "1.5", "2.0", "", None, "abc"):
        ok, error = io.validate_cca_count(raw)
        assert ok is False
        assert isinstance(error, str)


# ---------------------------------------------------------------------------
# validate_financial_stress
# ---------------------------------------------------------------------------

def test_validate_financial_stress_yes_no_case_insensitive():
    for raw in ("yes", "YES", "Yes", " yes "):
        ok, value = io.validate_financial_stress(raw)
        assert ok is True
        assert value is True
    for raw in ("no", "NO", "No", " no "):
        ok, value = io.validate_financial_stress(raw)
        assert ok is True
        assert value is False


def test_validate_financial_stress_rejects_aliases_and_blank():
    for raw in ("y", "n", "true", "false", "1", "0", "", None, "yeah"):
        ok, error = io.validate_financial_stress(raw)
        assert ok is False
        assert isinstance(error, str)


# ---------------------------------------------------------------------------
# validate_consecutive_absences
# ---------------------------------------------------------------------------

def test_validate_consecutive_absences_accepts_zero_and_positive():
    for raw, expected in (("0", 0), ("15", 15), (" 2 ", 2)):
        ok, value = io.validate_consecutive_absences(raw)
        assert ok is True
        assert value == expected


def test_validate_consecutive_absences_rejects_invalid():
    for raw in ("-1", "1.2", "", None, "abc"):
        ok, error = io.validate_consecutive_absences(raw)
        assert ok is False
        assert isinstance(error, str)


# ---------------------------------------------------------------------------
# validate_free_text_concern
# ---------------------------------------------------------------------------

def test_validate_free_text_concern_blank_is_ok():
    for raw in ("", "   ", None):
        ok, value = io.validate_free_text_concern(raw)
        assert ok is True
        assert value == ""


def test_validate_free_text_concern_keeps_trimmed_text():
    ok, value = io.validate_free_text_concern("  Feeling overwhelmed  ")
    assert ok is True
    assert value == "Feeling overwhelmed"


# ---------------------------------------------------------------------------
# format_student_record
# ---------------------------------------------------------------------------

def _sample_record():
    return {
        "student_id": "2605581",
        "sleep_hours": 7.5,
        "stress_level": 6,
        "submission_rate": 85.0,
        "cca_count": 2,
        "financial_stress": True,
        "consecutive_absences": 1,
        "free_text_concern": "Feeling overwhelmed",
    }


def test_format_student_record_includes_labels_and_values():
    text = io.format_student_record(_sample_record())
    assert text.startswith("Student Record")
    assert "Student ID:" in text
    assert "2605581" in text
    assert "Sleep Hours:" in text
    assert "7.5" in text
    assert "Stress Level:" in text
    assert "6" in text
    assert "Submission Rate:" in text
    assert "85.0%" in text
    assert "CCA Count:" in text
    assert "Financial Stress:" in text
    assert "Yes" in text
    assert "Consecutive Absences:" in text
    assert "Free-text Concern:" in text
    assert "Feeling overwhelmed" in text


def test_format_student_record_shows_no_for_false_financial_and_none_concern():
    record = _sample_record()
    record["financial_stress"] = False
    record["free_text_concern"] = ""
    text = io.format_student_record(record)
    assert "No" in text
    assert "(none)" in text


def test_format_student_record_empty_dict():
    text = io.format_student_record({})
    assert "No student data to display." in text


def test_format_student_record_does_not_print():
    with patch("builtins.print", side_effect=AssertionError("formatter used print()")):
        io.format_student_record(_sample_record())


# ---------------------------------------------------------------------------
# format_cohort_list
# ---------------------------------------------------------------------------

def test_format_cohort_list_empty():
    text = io.format_cohort_list([])
    assert "Cohort List (0 students)" in text
    assert "No student records to display." in text


def test_format_cohort_list_none_treated_as_empty():
    text = io.format_cohort_list(None)
    assert "Cohort List (0 students)" in text


def test_format_cohort_list_singular_heading():
    text = io.format_cohort_list([_sample_record()])
    assert "Cohort List (1 student)" in text
    assert "students)" not in text.split("\n")[0]


def test_format_cohort_list_multiple_records():
    second = _sample_record()
    second["student_id"] = "2501111"
    second["financial_stress"] = False
    second["free_text_concern"] = ""
    text = io.format_cohort_list([_sample_record(), second])
    assert "Cohort List (2 students)" in text
    assert "1. 2605581" in text
    assert "2. 2501111" in text
    assert "sleep 7.5h" in text
    assert "stress 6/10" in text
    assert "submit 85.0%" in text
    assert "financial Yes" in text
    assert "financial No" in text
    assert "Concern: Feeling overwhelmed" in text
    assert "Concern: (none)" in text


def test_format_cohort_list_does_not_print():
    with patch("builtins.print", side_effect=AssertionError("formatter used print()")):
        io.format_cohort_list([_sample_record()])


# ---------------------------------------------------------------------------
# format_summary_view
# ---------------------------------------------------------------------------

def test_format_summary_view_empty():
    text = io.format_summary_view({})
    assert text.startswith("Cohort Summary")
    assert "No summary data to display." in text


def test_format_summary_view_known_keys_and_percent():
    summary = {
        "total_students": 3,
        "average_sleep_hours": 7.25,
        "average_stress_level": 5.0,
        "average_submission_rate": 82.1,
        "average_cca_count": 1.5,
        "financial_stress_count": 1,
        "average_consecutive_absences": 0.7,
        "high_risk_count": 1,
        "medium_risk_count": 1,
        "low_risk_count": 1,
    }
    text = io.format_summary_view(summary)
    assert "Total Students:" in text
    assert "3" in text
    assert "Average Sleep Hours:" in text
    assert "7.2" in text or "7.3" in text  # 7.25 -> 7.2 with one decimal
    assert "Average Submission Rate:" in text
    assert "82.1%" in text
    assert "Students with Financial Stress:" in text
    assert "High Risk Count:" in text
    assert "Medium Risk Count:" in text
    assert "Low Risk Count:" in text


def test_format_summary_view_humanizes_unknown_keys():
    text = io.format_summary_view({"watchlist_ids": ["2605581", "2501111"]})
    assert "Watchlist Ids:" in text
    assert "2605581, 2501111" in text


def test_format_summary_view_does_not_print():
    with patch("builtins.print", side_effect=AssertionError("formatter used print()")):
        io.format_summary_view({"total_students": 1})


# ---------------------------------------------------------------------------
# collect_student_record + getters (mocked stdin)
# ---------------------------------------------------------------------------

def test_collect_student_record_returns_snake_case_dict():
    answers = [
        "bad-id",
        "2605581",
        "25",
        "7.5",
        "6",
        "85",
        "2",
        "yeah",
        "yes",
        "-3",
        "1",
        "Feeling overwhelmed",
    ]
    with patch("builtins.input", side_effect=answers):
        with patch("builtins.print"):
            record = io.collect_student_record()

    assert list(record.keys()) == list(io.RECORD_FIELD_ORDER)
    assert record == {
        "student_id": "2605581",
        "sleep_hours": 7.5,
        "stress_level": 6,
        "submission_rate": 85.0,
        "cca_count": 2,
        "financial_stress": True,
        "consecutive_absences": 1,
        "free_text_concern": "Feeling overwhelmed",
    }


def test_get_student_id_reprompts_until_valid():
    with patch("builtins.input", side_effect=["xx", "2605581"]) as mocked_input:
        with patch("builtins.print") as mocked_print:
            value = io.get_student_id()
    assert value == "2605581"
    assert mocked_input.call_count == 2
    assert mocked_print.call_count >= 1


def test_print_helpers_emit_formatter_output():
    record = _sample_record()
    with patch("builtins.print") as mocked_print:
        io.print_student_record(record)
        io.print_cohort_list([record])
        io.print_summary_view({"total_students": 1})
        io.print_message("hello")
        io.print_error("oops")
    printed = [call.args[0] for call in mocked_print.call_args_list]
    assert io.format_student_record(record) in printed
    assert io.format_cohort_list([record]) in printed
    assert io.format_summary_view({"total_students": 1}) in printed
    assert "hello" in printed
    assert "Error: oops" in printed

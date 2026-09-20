"""Tests for the student-facing io_manager web input layer.

Validators are pure and must not touch stdin/stdout. Formatters return
strings or plain dicts of copy and must not call print().
"""

from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import io_manager as io


DROPPED_PUBLIC_NAMES = (
    "validate_submission_rate",
    "validate_cca_count",
    "validate_consecutive_absences",
    "validate_free_text_concern",
    "get_submission_rate",
    "get_cca_count",
    "get_consecutive_absences",
    "get_free_text_concern",
    "format_cohort_list",
    "format_summary_view",
    "print_cohort_list",
    "print_summary_view",
)

VALIDATORS = (
    io.validate_student_id,
    io.validate_sleep_hours,
    io.validate_stress_level,
    io.validate_academic_workload,
    io.validate_financial_stress,
    io.validate_social_support,
    io.validate_feelings_text,
)


def _valid_form(**overrides):
    form = {
        "student_id": "2605581",
        "sleep_hours": "5.5",
        "stress_level": "6",
        "academic_workload": "7",
        "financial_stress": "4",
        "social_support": "8",
        "feelings_text": "A bit tired but managing.",
    }
    form.update(overrides)
    return form


def _valid_record(**overrides):
    record = {
        "student_id": "2605581",
        "sleep_hours": 5.5,
        "stress_level": 6,
        "academic_workload": 7,
        "financial_stress": 4,
        "social_support": 8,
        "feelings_text": "A bit tired but managing.",
    }
    record.update(overrides)
    return record


# ---------------------------------------------------------------------------
# Source / architecture constraints
# ---------------------------------------------------------------------------

def test_io_manager_has_no_class_keyword():
    source = Path(io.__file__).read_text(encoding="utf-8")
    assert "class " not in source
    assert "\nclass" not in source


def test_dropped_fields_are_gone_from_public_api():
    for name in DROPPED_PUBLIC_NAMES:
        assert not hasattr(io, name), f"{name} should not be a public API"


def test_form_fields_lists_exact_web_names():
    assert list(io.FORM_FIELDS.keys()) == [
        "student_id",
        "sleep_hours",
        "stress_level",
        "academic_workload",
        "financial_stress",
        "social_support",
        "feelings_text",
    ]
    assert list(io.RECORD_FIELD_ORDER) == list(io.FORM_FIELDS.keys())
    assert "submission_rate" not in io.FORM_FIELDS
    assert "cca_count" not in io.FORM_FIELDS
    assert "consecutive_absences" not in io.FORM_FIELDS
    assert "free_text_concern" not in io.FORM_FIELDS


def test_feelings_prompt_matches_open_question():
    assert (
        io.FORM_PROMPTS["feelings_text"]
        == "In your own words, how have you been feeling about school lately?"
    )


def test_validators_do_not_use_print_or_input():
    with patch("builtins.input", side_effect=AssertionError("validator used input()")):
        with patch("builtins.print", side_effect=AssertionError("validator used print()")):
            for validator in VALIDATORS:
                validator("1")
                validator("")
                validator(None)
            io.validate_student_form(_valid_form())
            io.collect_student_record_from_form(_valid_form())
            io.extract_form_fields(_valid_form())
            io.normalize_form_value("  5.5  ")


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
# validate_sleep_hours — range + 0.5 steps
# ---------------------------------------------------------------------------

def test_validate_sleep_hours_accepts_half_steps_and_bounds():
    cases = (
        ("0", 0.0),
        ("0.0", 0.0),
        ("0.5", 0.5),
        ("5.0", 5.0),
        ("5.5", 5.5),
        ("6.0", 6.0),
        ("24", 24.0),
        ("24.0", 24.0),
        (" 8 ", 8.0),
        (8, 8.0),
        (7.5, 7.5),
        ("8.50", 8.5),
    )
    for raw, expected in cases:
        ok, value = io.validate_sleep_hours(raw)
        assert ok is True, raw
        assert value == expected
        assert type(value) is float


def test_validate_sleep_hours_rejects_non_half_steps():
    for raw in ("5.25", "5.1", "7.75", "0.25", "1.2", 6.25, "23.3"):
        ok, error = io.validate_sleep_hours(raw)
        assert ok is False, raw
        assert "0.5" in error


def test_validate_sleep_hours_rejects_out_of_range_and_non_numeric():
    for raw in ("-0.5", "24.5", "25", "abc", "", None, "nan", "inf", "+inf", "-inf"):
        ok, error = io.validate_sleep_hours(raw)
        assert ok is False
        assert isinstance(error, str)
        assert error


# ---------------------------------------------------------------------------
# 1–10 scales
# ---------------------------------------------------------------------------

def test_scale_validators_accept_integers_1_to_10():
    validators = (
        io.validate_stress_level,
        io.validate_academic_workload,
        io.validate_financial_stress,
        io.validate_social_support,
    )
    for validator in validators:
        for raw, expected in (("1", 1), ("10", 10), ("5", 5), (" 7 ", 7), (3, 3)):
            ok, value = validator(raw)
            assert ok is True, (validator.__name__, raw)
            assert value == expected
            assert type(value) is int


def test_scale_validators_reject_invalid():
    validators = (
        io.validate_stress_level,
        io.validate_academic_workload,
        io.validate_financial_stress,
        io.validate_social_support,
    )
    for validator in validators:
        for raw in ("0", "11", "5.5", "5.0", "", None, "abc", "-1", "yes", "no", "true"):
            ok, error = validator(raw)
            assert ok is False, (validator.__name__, raw)
            assert isinstance(error, str)


def test_financial_stress_is_scale_not_yes_no():
    ok, error = io.validate_financial_stress("yes")
    assert ok is False
    assert isinstance(error, str)
    ok, value = io.validate_financial_stress("8")
    assert ok is True
    assert value == 8
    assert value is not True


# ---------------------------------------------------------------------------
# validate_feelings_text
# ---------------------------------------------------------------------------

def test_validate_feelings_text_blank_is_ok():
    for raw in ("", "   ", None):
        ok, value = io.validate_feelings_text(raw)
        assert ok is True
        assert value == ""


def test_validate_feelings_text_keeps_trimmed_text():
    ok, value = io.validate_feelings_text("  Feeling overwhelmed  ")
    assert ok is True
    assert value == "Feeling overwhelmed"


# ---------------------------------------------------------------------------
# extract / normalize helpers
# ---------------------------------------------------------------------------

def test_normalize_form_value_strips_and_handles_none():
    assert io.normalize_form_value("  5.5  ") == "5.5"
    assert io.normalize_form_value(None) == ""
    assert io.normalize_form_value(8) == "8"


def test_extract_form_fields_keeps_only_canonical_keys():
    form = _valid_form(extra_noise="ignore me", submission_rate="99")
    extracted = io.extract_form_fields(form)
    assert set(extracted) == set(io.FORM_FIELDS)
    assert "submission_rate" not in extracted
    assert extracted["student_id"] == "2605581"
    assert extracted["feelings_text"] == "A bit tired but managing."


def test_extract_form_fields_missing_keys_are_blank():
    extracted = io.extract_form_fields({})
    assert extracted == {key: "" for key in io.FORM_FIELDS}


# ---------------------------------------------------------------------------
# validate_student_form / collect_student_record_from_form
# ---------------------------------------------------------------------------

def test_validate_student_form_happy_path():
    ok, record = io.validate_student_form(_valid_form())
    assert ok is True
    assert record == _valid_record()
    assert list(record.keys()) == list(io.RECORD_FIELD_ORDER)


def test_collect_student_record_from_form_is_alias():
    form = _valid_form()
    assert io.collect_student_record_from_form(form) == io.validate_student_form(form)


def test_validate_student_form_blank_feelings_ok():
    ok, record = io.validate_student_form(_valid_form(feelings_text="   "))
    assert ok is True
    assert record["feelings_text"] == ""


def test_validate_student_form_missing_feelings_ok():
    form = _valid_form()
    del form["feelings_text"]
    ok, record = io.validate_student_form(form)
    assert ok is True
    assert record["feelings_text"] == ""


def test_validate_student_form_collects_all_errors():
    form = {
        "student_id": "2705581",
        "sleep_hours": "5.25",
        "stress_level": "11",
        "academic_workload": "no",
        "financial_stress": "yes",
        "social_support": "0",
        "feelings_text": "",
    }
    ok, errors = io.validate_student_form(form)
    assert ok is False
    assert set(errors) == {
        "student_id",
        "sleep_hours",
        "stress_level",
        "academic_workload",
        "financial_stress",
        "social_support",
    }
    assert "feelings_text" not in errors
    assert "0.5" in errors["sleep_hours"]


def test_validate_student_form_empty_mapping_fails_required_fields():
    ok, errors = io.validate_student_form({})
    assert ok is False
    assert set(errors) == set(io.REQUIRED_FORM_FIELDS)


def test_validate_student_form_accepts_get_interface():
    class FakeMultiDict:  # local test double only
        def __init__(self, data):
            self._data = data

        def get(self, key, default=None):
            return self._data.get(key, default)

    ok, record = io.validate_student_form(FakeMultiDict(_valid_form()))
    assert ok is True
    assert record["sleep_hours"] == 5.5


def test_validate_student_form_ignores_dropped_keys():
    form = _valid_form(
        submission_rate="10",
        cca_count="3",
        consecutive_absences="2",
        free_text_concern="old field",
    )
    ok, record = io.validate_student_form(form)
    assert ok is True
    assert "submission_rate" not in record
    assert "cca_count" not in record
    assert "consecutive_absences" not in record
    assert "free_text_concern" not in record


# ---------------------------------------------------------------------------
# format_soft_label
# ---------------------------------------------------------------------------

def test_format_soft_label_known_values():
    for label in io.SOFT_LABELS:
        copy = io.format_soft_label(label)
        assert copy["label"] == label
        assert copy["heading"] == label
        assert copy["body"]
        assert copy["tone"]
        assert copy["error"] is None


def test_format_soft_label_unknown_does_not_invent():
    copy = io.format_soft_label("You are doomed")
    assert copy["label"] == ""
    assert copy["heading"] == ""
    assert copy["body"] == ""
    assert copy["error"]
    assert "You're doing ok" in copy["error"]


def test_format_soft_label_does_not_print():
    with patch("builtins.print", side_effect=AssertionError("formatter used print()")):
        io.format_soft_label("You're doing ok")


# ---------------------------------------------------------------------------
# format_tips
# ---------------------------------------------------------------------------

def test_format_tips_allowlist_ids_and_exact_copy():
    copy = io.format_tips(["sleep_routine", io.TIPS_ALLOWLIST["short_breaks"]])
    assert copy["items"][0]["id"] == "sleep_routine"
    assert copy["items"][0]["text"] == io.TIPS_ALLOWLIST["sleep_routine"]
    assert copy["items"][1]["id"] == "short_breaks"
    assert copy["texts"] == [
        io.TIPS_ALLOWLIST["sleep_routine"],
        io.TIPS_ALLOWLIST["short_breaks"],
    ]


def test_format_tips_drops_unknown_and_dedupes():
    copy = io.format_tips(
        ["sleep_routine", "invented tip", "sleep_routine", "not-a-tip"]
    )
    assert [item["id"] for item in copy["items"]] == ["sleep_routine"]


def test_format_tips_empty_or_none():
    for raw in ([], None):
        copy = io.format_tips(raw)
        assert copy["items"] == []
        assert copy["texts"] == []


def test_format_tips_does_not_print():
    with patch("builtins.print", side_effect=AssertionError("formatter used print()")):
        io.format_tips(["sleep_routine"])


# ---------------------------------------------------------------------------
# format_speak_to_advisor_panel
# ---------------------------------------------------------------------------

def test_format_speak_to_advisor_panel_always_uses_hardcoded_contacts():
    for prominence in ("low", "medium", "high", "LOW", "unknown"):
        panel = io.format_speak_to_advisor_panel(prominence)
        assert panel["email"] == "SITCounselling@SingaporeTech.edu.sg"
        assert panel["helpline"] == "6592 2030"
        assert panel["mailto"] == "mailto:SITCounselling@SingaporeTech.edu.sg"
        assert panel["contacts"] == {
            "email": "SITCounselling@SingaporeTech.edu.sg",
            "helpline": "6592 2030",
            "mailto": "mailto:SITCounselling@SingaporeTech.edu.sg",
        }


def test_format_speak_to_advisor_panel_tone_changes_with_prominence():
    low = io.format_speak_to_advisor_panel("low")
    medium = io.format_speak_to_advisor_panel("medium")
    high = io.format_speak_to_advisor_panel("high")
    assert low["prominence"] == "low"
    assert medium["prominence"] == "medium"
    assert high["prominence"] == "high"
    assert low["heading"] != high["heading"]
    assert low["cta"] != high["cta"]
    assert low["error"] is None
    assert high["error"] is None


def test_format_speak_to_advisor_panel_unknown_falls_back_but_keeps_contacts():
    panel = io.format_speak_to_advisor_panel("urgent")
    assert panel["prominence"] == "medium"
    assert panel["error"]
    assert panel["email"] == "SITCounselling@SingaporeTech.edu.sg"
    assert panel["helpline"] == "6592 2030"


def test_format_speak_to_advisor_panel_does_not_invent_contacts():
    panel = io.format_speak_to_advisor_panel("high")
    contact_values = (
        panel["email"],
        panel["helpline"],
        panel["mailto"],
        *panel["contacts"].values(),
    )
    for value in contact_values:
        assert value in {
            "SITCounselling@SingaporeTech.edu.sg",
            "6592 2030",
            "mailto:SITCounselling@SingaporeTech.edu.sg",
        }


def test_format_speak_to_advisor_panel_does_not_print():
    with patch("builtins.print", side_effect=AssertionError("formatter used print()")):
        io.format_speak_to_advisor_panel("high")


# ---------------------------------------------------------------------------
# format_student_record
# ---------------------------------------------------------------------------

def test_format_student_record_includes_new_fields():
    copy = io.format_student_record(_valid_record())
    keys = [field["key"] for field in copy["fields"]]
    assert keys == list(io.RECORD_FIELD_ORDER)
    values = {field["key"]: field["value"] for field in copy["fields"]}
    assert values["student_id"] == "2605581"
    assert values["sleep_hours"] == "5.5"
    assert "submission_rate" not in values


def test_format_student_record_empty():
    copy = io.format_student_record({})
    assert copy["empty"] is True
    assert copy["fields"] == []


def test_format_student_record_does_not_print():
    with patch("builtins.print", side_effect=AssertionError("formatter used print()")):
        io.format_student_record(_valid_record())


# ---------------------------------------------------------------------------
# thin CLI helper (mocked stdin)
# ---------------------------------------------------------------------------

def test_collect_student_record_returns_web_aligned_dict():
    answers = [
        "bad-id",
        "2605581",
        "5.25",
        "5.5",
        "6",
        "7",
        "yes",
        "4",
        "8",
        "A bit tired but managing.",
    ]
    with patch("builtins.input", side_effect=answers):
        with patch("builtins.print"):
            record = io.collect_student_record()

    assert list(record.keys()) == list(io.RECORD_FIELD_ORDER)
    assert record == _valid_record()


def test_get_student_id_reprompts_until_valid():
    with patch("builtins.input", side_effect=["xx", "2605581"]) as mocked_input:
        with patch("builtins.print") as mocked_print:
            value = io.get_student_id()
    assert value == "2605581"
    assert mocked_input.call_count == 2
    assert mocked_print.call_count >= 1


def test_print_helpers_emit_messages():
    with patch("builtins.print") as mocked_print:
        io.print_message("hello")
        io.print_error("oops")
    printed = [call.args[0] for call in mocked_print.call_args_list]
    assert "hello" in printed
    assert "Error: oops" in printed

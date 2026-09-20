"""Unit tests for data_manager persistence and query helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import data_manager as dm


def _sample_record(**overrides):
    base = {
        "student_id": "2605581",
        "sleep_hours": 5.5,
        "stress_level": 8,
        "academic_workload": 7,
        "financial_stress": 6,
        "social_support": 4,
        "feelings_text": "Feeling overwhelmed by deadlines.",
        "soft_label": "Please reach out",
        "tips": ["Talk to someone you trust", "Take a short break"],
        "speak_prominence": "high",
        "risk_score": 0.82,
        "risk_category": "High",
        "reasoning": "Multiple elevated stress signals.",
        "source": "gemini",
    }
    base.update(overrides)
    return base


def test_module_has_no_class_print_or_input():
    source = Path(dm.__file__).read_text(encoding="utf-8")
    assert "\nclass " not in source and not source.startswith("class ")
    assert "print(" not in source
    assert "input(" not in source


def test_save_refused_without_opt_in(tmp_path):
    path = tmp_path / "student_records.json"
    result = dm.save_record(_sample_record(), data_path=str(path))
    assert result["ok"] is False
    assert "opt-in" in result["error"].lower()
    assert not path.exists()

    result2 = dm.save_record(_sample_record(), data_path=str(path), opt_in=False)
    assert result2["ok"] is False
    assert not path.exists()


def test_save_and_load_roundtrip_with_opt_in(tmp_path):
    path = tmp_path / "student_records.json"
    result = dm.save_record(_sample_record(), data_path=str(path), opt_in=True)
    assert result["ok"] is True
    assert result["error"] is None
    assert result["record"]["saved_at"]
    assert result["record"]["save_opt_in"] is True

    loaded = dm.load_all_records(data_path=str(path))
    assert loaded["ok"] is True
    assert len(loaded["records"]) == 1
    assert loaded["records"][0]["student_id"] == "2605581"
    assert loaded["records"][0]["soft_label"] == "Please reach out"
    assert loaded["records"][0]["speak_prominence"] == "high"


def test_opt_in_accepts_yes_string(tmp_path):
    path = tmp_path / "records.json"
    result = dm.save_record(_sample_record(), data_path=str(path), opt_in="yes")
    assert result["ok"] is True


def test_missing_file_returns_empty(tmp_path):
    path = tmp_path / "missing.json"
    loaded = dm.load_all_records(data_path=str(path))
    assert loaded["ok"] is True
    assert loaded["records"] == []
    assert loaded["error"] is None


def test_empty_file_returns_empty(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text("", encoding="utf-8")
    loaded = dm.load_all_records(data_path=str(path))
    assert loaded["ok"] is True
    assert loaded["records"] == []


def test_corrupted_json_does_not_crash(tmp_path):
    path = tmp_path / "corrupt.json"
    path.write_text("{not-valid-json", encoding="utf-8")
    loaded = dm.load_all_records(data_path=str(path))
    assert loaded["ok"] is True
    assert loaded["records"] == []
    assert loaded["error"] is not None
    assert "Corrupted" in loaded["error"]


def test_save_recovers_after_corrupt_file(tmp_path):
    path = tmp_path / "corrupt.json"
    path.write_text("<<<bad>>>", encoding="utf-8")
    result = dm.save_record(_sample_record(), data_path=str(path), opt_in=True)
    assert result["ok"] is True
    loaded = dm.load_all_records(data_path=str(path))
    assert len(loaded["records"]) == 1


def test_filter_helpers(tmp_path):
    path = tmp_path / "records.json"
    dm.save_record(
        _sample_record(soft_label="Please reach out", risk_category="High"),
        data_path=str(path),
        opt_in=True,
    )
    dm.save_record(
        _sample_record(
            student_id="2600002",
            soft_label="You're doing ok",
            risk_category="Low",
            speak_prominence="low",
        ),
        data_path=str(path),
        opt_in=True,
    )
    dm.save_record(
        _sample_record(
            student_id="2500001",
            soft_label="Worth a check-in",
            risk_category="Moderate",
            speak_prominence="medium",
        ),
        data_path=str(path),
        opt_in=True,
    )

    reach = dm.get_records_by_soft_label("Please reach out", data_path=str(path))
    assert len(reach) == 1

    by_id = dm.get_record_by_student_id("2600002", data_path=str(path))
    assert len(by_id) == 1
    assert by_id[0]["soft_label"] == "You're doing ok"

    high = dm.get_records_by_risk_category("high", data_path=str(path))
    assert len(high) == 1

    cohort_26 = dm.get_records_by_cohort_year("26", data_path=str(path))
    assert len(cohort_26) == 2


def test_filter_records_in_memory():
    records = [
        _sample_record(soft_label="Worth a check-in", student_id="2601111"),
        _sample_record(soft_label="You're doing ok", student_id="2402222", risk_category="Low"),
    ]
    assert len(dm.filter_records(records, soft_label="Worth a check-in")) == 1
    assert len(dm.filter_records(records, cohort_year="24")) == 1
    assert dm.filter_records([], soft_label="x") == []


def test_wrapped_records_object_format(tmp_path):
    path = tmp_path / "wrapped.json"
    path.write_text(
        json.dumps({"records": [_sample_record(student_id="2609999")]}),
        encoding="utf-8",
    )
    loaded = dm.load_all_records(data_path=str(path))
    assert len(loaded["records"]) == 1
    assert loaded["records"][0]["student_id"] == "2609999"


def test_get_default_data_path():
    p = dm.get_default_data_path()
    assert p.endswith("data/student_records.json")

def test_save_refused_for_logic_fallback(tmp_path):
    path = tmp_path / "student_records.json"
    result = dm.save_record(
        _sample_record(source="logic_fallback"),
        data_path=str(path),
        opt_in=True,
    )
    assert result["ok"] is False
    assert "AI-processed" in result["error"] or "logic_fallback" in result["error"]
    assert not path.exists()


def test_save_refused_without_ai_source(tmp_path):
    path = tmp_path / "student_records.json"
    rec = _sample_record()
    rec.pop("source", None)
    result = dm.save_record(rec, data_path=str(path), opt_in=True)
    assert result["ok"] is False
    assert "Gemini" in result["error"] or "AI" in result["error"]
    assert not path.exists()


def test_save_refused_when_ai_fields_missing(tmp_path):
    path = tmp_path / "student_records.json"
    rec = _sample_record(source="gemini")
    del rec["risk_score"]
    result = dm.save_record(rec, data_path=str(path), opt_in=True)
    assert result["ok"] is False
    assert "missing" in result["error"].lower()
    assert not path.exists()


def test_save_allows_ai_ok_flag(tmp_path):
    path = tmp_path / "student_records.json"
    rec = _sample_record()
    rec.pop("source", None)
    rec["ai_ok"] = True
    result = dm.save_record(rec, data_path=str(path), opt_in=True)
    assert result["ok"] is True


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
        "average_sleep_hours": 5.5,
        "stress_level": 8,
        "assignment_submission_rate": 60.0,
        "number_of_ccas": 3,
        "financial_stress": True,
        "consecutive_absences": 4,
        "free_text_concern": "Struggling to keep up",
        "risk_score": 0.82,
        "risk_category": "High",
        "primary_stressors": ["sleep_deprivation", "financial_pressure"],
        "recommended_support": "Urgent counselling referral",
        "confidence": 0.9,
        "reasoning": "Multiple high-risk signals.",
        "intervention_tier": 1,
        "tier_label": "Critical",
        "outcome": "Escalate to Dean's Office immediately.",
    }
    base.update(overrides)
    return base


def test_module_has_no_class_print_or_input():
    source = Path(dm.__file__).read_text(encoding="utf-8")
    assert "\nclass " not in source and not source.startswith("class ")
    assert "print(" not in source
    assert "input(" not in source


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "student_records.json"
    result = dm.save_record(_sample_record(), data_path=str(path))
    assert result["ok"] is True
    assert result["error"] is None
    assert result["record"]["saved_at"]

    loaded = dm.load_all_records(data_path=str(path))
    assert loaded["ok"] is True
    assert len(loaded["records"]) == 1
    assert loaded["records"][0]["student_id"] == "2605581"
    assert loaded["records"][0]["intervention_tier"] == 1
    assert loaded["records"][0]["primary_stressors"] == [
        "sleep_deprivation",
        "financial_pressure",
    ]


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
    result = dm.save_record(_sample_record(), data_path=str(path))
    assert result["ok"] is True
    loaded = dm.load_all_records(data_path=str(path))
    assert len(loaded["records"]) == 1


def test_filter_by_tier_and_helpers(tmp_path):
    path = tmp_path / "records.json"
    dm.save_record(_sample_record(intervention_tier=1), data_path=str(path))
    dm.save_record(
        _sample_record(student_id="2600002", intervention_tier=3, risk_category="Moderate"),
        data_path=str(path),
    )
    dm.save_record(
        _sample_record(student_id="2500001", intervention_tier=1, risk_category="High"),
        data_path=str(path),
    )

    tier1 = dm.get_records_by_tier(1, data_path=str(path))
    assert len(tier1) == 2
    assert all(r["intervention_tier"] == 1 for r in tier1)

    by_id = dm.get_record_by_student_id("2600002", data_path=str(path))
    assert len(by_id) == 1
    assert by_id[0]["intervention_tier"] == 3

    high = dm.get_records_by_risk_category("high", data_path=str(path))
    assert len(high) == 2

    cohort_26 = dm.get_records_by_cohort_year("26", data_path=str(path))
    assert len(cohort_26) == 2
    cohort_25 = dm.get_records_by_cohort_year("25", data_path=str(path))
    assert len(cohort_25) == 1


def test_filter_records_in_memory():
    records = [
        _sample_record(intervention_tier=2, student_id="2601111"),
        _sample_record(intervention_tier=4, student_id="2402222", risk_category="Low"),
    ]
    assert len(dm.filter_records(records, tier=2)) == 1
    assert len(dm.filter_records(records, cohort_year="24")) == 1
    assert dm.filter_records([], tier=1) == []


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

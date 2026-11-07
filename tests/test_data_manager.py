"""Records, storage backends and DataManager, on synthetic data only."""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from base_manager import BaseManager
from data_manager import DataManager
from plain_tests import capture_logs, case, function_suite
from records.check_in_record import CheckInRecord
from records.pending_record import PendingRecord
from records.record import Record
from storage.json_storage import JSONStorage
from storage.storage_backend import StorageBackend
from storage.storage_error import StorageError


class MemoryStorage(StorageBackend):
    """A backend that keeps rows in a list, written only for these tests."""

    def __init__(self):
        super().__init__()
        self.__rows = []

    @property
    def location(self):
        return "memory"

    def load(self):
        return [dict(row) for row in self.__rows]

    def append(self, row):
        self.__rows.append(dict(row))

    def replace(self, record_id, row):
        for index, existing in enumerate(self.__rows):
            if existing.get("record_id") == record_id:
                self.__rows[index] = dict(row)
                return
        self.__rows.append(dict(row))


def evaluated(student_id="2605581", score=3.0, **changes):
    """A finished check-in exactly as LogicManager returns one."""
    row = {"student_id": student_id, "survey_version": "evidence-v3",
           "stress_score": score, "risk_score": (score - 1) / 4,
           "risk_category": "Moderate", "soft_label": "Worth a check-in",
           "primary_stressors": ["academic_overload"],
           "recommended_support": "Internal note", "confidence": 0.8,
           "reasoning": "Warm words.", "source": "ai_logic", "ai_ok": True,
           "feelings_text": "PRIVATE reflection", "pss_1": 3}
    row.update(changes)
    return row


def json_data(temp):
    path = Path(temp) / "records.json"
    return path, DataManager(JSONStorage(path))


# --- Records ---------------------------------------------------------------

def test_both_record_kinds_honour_the_record_contract():
    """Liskov: DataManager can save and read either kind the same way."""
    for record in (CheckInRecord(evaluated()), PendingRecord(evaluated())):
        with case(status=record.status):
            assert isinstance(record, Record)
            assert record.status in ("evaluated", "pending")
            assert record.problem() is None
            row = record.to_row()
            assert "feelings_text" not in row
            assert record.get("feelings_text") is None
            assert record.belongs_to("2605581")
            assert not record.belongs_to("260558")
            assert not record.belongs_to("")


def test_record_kinds_differ_only_in_their_own_rules():
    finished = CheckInRecord(evaluated(status="pending"))
    waiting = PendingRecord(evaluated(ai_ok=True))
    assert finished.score == 3.0 and waiting.score is None
    assert "status" not in finished.to_row()
    assert waiting.to_row()["status"] == "pending"
    assert waiting.to_row()["ai_ok"] is False


def test_a_check_in_record_must_really_have_passed_the_ai_step():
    cases = (
        (dict(source="logic_fallback"), "not AI-processed"),
        (dict(source="manual", ai_ok=False), "successful Gemini processing"),
        (dict(reasoning=None), "AI fields missing: reasoning"),
        (dict(risk_score=1.5), "risk_score must be a float"),
        (dict(confidence=True), "confidence must be a float"),
        (dict(risk_category="Critical"), "risk_category must be"),
        (dict(primary_stressors=[1]), "primary_stressors must be"),
        (dict(recommended_support=3), "recommended_support must be"),
    )
    for changes, expected in cases:
        with case(changes=changes):
            assert expected in CheckInRecord(evaluated(**changes)).problem()


# --- DataManager -----------------------------------------------------------

def test_data_manager_works_with_any_backend():
    """Open/closed: a new backend needs no change to DataManager."""
    data = DataManager(MemoryStorage())
    assert isinstance(data, BaseManager)
    assert data.health() == {"name": "data_manager",
                             "backend": "MemoryStorage"}
    assert data.save(CheckInRecord(evaluated()), opt_in=True).ok
    assert data.save(PendingRecord(evaluated("2700001")), opt_in=True).ok
    assert [record.status for record in data.load()] == ["evaluated",
                                                         "pending"]


def test_save_needs_consent_and_a_valid_record():
    data = DataManager(MemoryStorage())
    for opt_in in (False, "yes", 1):
        with case(opt_in=opt_in):
            refused = data.save(CheckInRecord(evaluated()), opt_in=opt_in)
            assert not refused.ok
            assert "opt-in" in refused.error
    refused = data.save(CheckInRecord(evaluated(source="logic")),
                        opt_in=True)
    assert not refused.ok and refused.row is None and refused.record_id == ""
    assert data.load() == []


def test_saved_rows_get_an_id_a_time_and_lose_the_reflection():
    with tempfile.TemporaryDirectory() as temp:
        path, data = json_data(temp)
        saved = data.save(CheckInRecord(evaluated()), opt_in=True)
        assert saved.ok
        assert re.fullmatch(r"[0-9a-f]{32}", saved.record_id)
        stored = json.loads(path.read_text(encoding="utf-8"))
        assert stored[0]["record_id"] == saved.record_id
        assert stored[0]["save_opt_in"] is True
        assert stored[0]["saved_at"].endswith("+00:00")
        assert "PRIVATE" not in path.read_text(encoding="utf-8")


def test_a_pending_record_is_replaced_in_place_by_its_result():
    with tempfile.TemporaryDirectory() as temp:
        path, data = json_data(temp)
        pending = data.save(PendingRecord(evaluated("2700001")),
                            opt_in=True)
        other = data.save(PendingRecord(evaluated("2700002")), opt_in=True)
        upgraded = data.replace_pending_record(
            pending.record_id, CheckInRecord(evaluated("2700001", 2.0)),
            opt_in=True)
        assert upgraded.ok and upgraded.record_id == pending.record_id
        rows = json.loads(path.read_text(encoding="utf-8"))
        assert [row["record_id"] for row in rows] == [pending.record_id,
                                                      other.record_id]
        assert "status" not in rows[0] and rows[0]["stress_score"] == 2.0
        assert rows[1]["status"] == "pending"


def test_replacing_an_unknown_id_appends_once_and_checks_its_input():
    data = DataManager(MemoryStorage())
    assert data.replace_pending_record("abc", CheckInRecord(evaluated()),
                                       opt_in=True).ok
    assert len(data.load()) == 1
    assert data.replace_pending_record(" ", CheckInRecord(evaluated()),
                                       opt_in=True).error == (
        "record_id is required")
    assert not data.replace_pending_record(
        "abc", CheckInRecord(evaluated()), opt_in=False).ok
    assert not data.replace_pending_record(
        "abc", CheckInRecord(evaluated(source="logic")), opt_in=True).ok


def test_query_filters_and_cohorts():
    data = DataManager(MemoryStorage())
    data.save(CheckInRecord(evaluated("2603503")), opt_in=True)
    data.save(CheckInRecord(evaluated(
        "2703504", 4.2, risk_category="High",
        soft_label="Please reach out")), opt_in=True)
    data.save(PendingRecord({"student_id": "2000123",
                             "risk_category": "Low"}), opt_in=True)
    records = data.load()
    high = data.query(lambda record: record.get("risk_category") == "High")
    assert [record.student_id for record in high] == ["2703504"]
    assert data.cohorts(records) == ["27", "26", "20"]
    by_tier = data.filter_records(records, tier="You're doing ok")
    assert [record.student_id for record in by_tier] == ["2000123"]
    by_cohort = data.filter_records(records, cohort_year="2026")
    assert [record.student_id for record in by_cohort] == ["2603503"]
    by_part = data.filter_records(records, id_contains="035")
    assert len(by_part) == 2


# --- JSONStorage -----------------------------------------------------------

def test_a_missing_or_empty_file_is_no_records():
    with tempfile.TemporaryDirectory() as temp:
        path, data = json_data(temp)
        assert data.load() == []
        path.write_text("  \n", encoding="utf-8")
        assert data.load() == []
        path.write_text('{"records": [{"student_id": "2000001"}, 3]}',
                        encoding="utf-8")
        assert [record.student_id for record in data.load()] == ["2000001"]


def test_a_corrupt_file_is_backed_up_and_never_read_as_empty():
    for corrupt in ('[{"student_id": "2603503"', '"just text"'):
        with case(corrupt=corrupt), tempfile.TemporaryDirectory() as temp:
            path, data = json_data(temp)
            path.write_text(corrupt, encoding="utf-8")
            with capture_logs("data_manager", level="WARNING"):
                try:
                    data.load()
                except StorageError as error:
                    assert "Corrupted" in str(error)
                else:
                    raise AssertionError("corrupt data must raise")
            with capture_logs("data_manager", level="WARNING"):
                assert data.save(PendingRecord({"student_id": "2000123"}),
                                 opt_in=True).ok
            backups = sorted(Path(temp).glob("records.corrupt-*.json"))
            assert len(backups) == 2
            assert backups[0].read_text(encoding="utf-8") == corrupt
            assert len(data.load()) == 1


def test_nothing_is_overwritten_when_the_backup_fails():
    with tempfile.TemporaryDirectory() as temp:
        path, data = json_data(temp)
        path.write_text("{broken", encoding="utf-8")
        with patch("storage.json_storage.shutil.copy2",
                   side_effect=OSError("disk full")), \
                capture_logs("data_manager", level="WARNING"):
            result = data.save(PendingRecord({"student_id": "2000123"}),
                               opt_in=True)
        assert not result.ok and "Backup failed" in result.error
        assert path.read_text(encoding="utf-8") == "{broken"


def test_a_failed_write_reports_an_error_and_leaves_no_temp_file():
    with tempfile.TemporaryDirectory() as temp:
        path, data = json_data(temp)
        with patch("storage.json_storage.os.replace",
                   side_effect=OSError("read-only")), \
                capture_logs("data_manager", level="WARNING"):
            result = data.save(CheckInRecord(evaluated()), opt_in=True)
        assert not result.ok and "Could not write" in result.error
        assert list(Path(temp).iterdir()) == []


def load_tests(loader, tests, pattern):
    """Let `python -m unittest discover -s tests` run this file's tests."""
    return function_suite(globals())


if __name__ == "__main__":
    unittest.main()

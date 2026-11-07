"""DoNotStress — Data Layer (data_manager).

DataManager is the only class that saves, loads and queries check-in
records. It works through a StorageBackend, so it never touches files
itself and a new backend needs no change here.

A finished check-in is saved as a CheckInRecord; one the AI step could not
finish is saved as a PendingRecord, and replace_pending_record later
upgrades that same row. Reflection text is never stored. Each row gets a
record_id (uuid4 hex) and a UTC saved_at time.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from base_manager import BaseManager
from json_types import JSONObject
from records.check_in_record import CheckInRecord
from records.pending_record import PendingRecord
from records.record import Record
from records.stress_history import StressHistory
from storage.save_result import SaveResult
from storage.storage_backend import StorageBackend
from storage.storage_error import StorageError


class DataManager(BaseManager):
    """Saves and queries records through a backend it is given.

    The backend is passed in and outlives this manager (aggregation).
    """

    TIER_TO_CATEGORY: dict[str, str] = {
        "You're doing ok": "Low",
        "Worth a check-in": "Moderate",
        "Please reach out": "High",
    }
    CONSENT_REQUIRED: str = ("Save refused: student opt-in required "
                             "(pass opt_in=True).")

    def __init__(self, backend: StorageBackend) -> None:
        super().__init__("data_manager")
        self.__backend: StorageBackend = backend

    def describe(self) -> JSONObject:
        """The backend type only; its location stays out of /health."""
        return {"backend": type(self.__backend).__name__}

    def save(self, record: Record, *, opt_in: bool) -> SaveResult:
        """Append one record. Any kind of Record is saved the same way."""
        if opt_in is not True:
            return SaveResult(error=self.CONSENT_REQUIRED)
        problem = record.problem()
        if problem:
            return SaveResult(error=problem)
        row = self.__stamped(record, record.record_id or uuid.uuid4().hex)
        return self.__write(row, lambda: self.__backend.append(row))

    def replace_pending_record(self, record_id: str, record: CheckInRecord,
                               *, opt_in: bool) -> SaveResult:
        """Upgrade a pending row to its finished result, keeping its id.

        When no row has that id yet, the finished record is appended.
        """
        clean_id = record_id.strip()
        if not clean_id:
            return SaveResult(error="record_id is required")
        if opt_in is not True:
            return SaveResult(error=self.CONSENT_REQUIRED)
        problem = record.problem()
        if problem:
            return SaveResult(error=problem)
        row = self.__stamped(record, clean_id)
        return self.__write(
            row, lambda: self.__backend.replace(clean_id, row))

    def load(self) -> list[Record]:
        """Every saved record. [] when nothing has been saved yet.

        Raises StorageError when the store is corrupt or unreadable, so a
        broken file is never mistaken for an empty history.
        """
        return [self.__to_record(row) for row in self.__backend.load()]

    def query(self, wanted: Callable[[Record], bool]) -> list[Record]:
        """The saved records for which wanted(record) is True."""
        return [record for record in self.load() if wanted(record)]

    def history_for(self, student_id: str,
                    survey_version: str) -> StressHistory:
        """One student's check-ins on this questionnaire, and nobody else's.

        Only an exact Student ID match counts. Raises StorageError when
        the store cannot be read.
        """
        finished: list[CheckInRecord] = []
        pending = 0
        for row in self.__backend.load():
            record = self.__to_record(row)
            if (not record.belongs_to(student_id)
                    or record.survey_version != survey_version):
                continue
            if self.__is_pending(row):
                pending += 1
            else:
                finished.append(CheckInRecord(row))
        return StressHistory(student_id.strip(), finished, pending)

    def filter_records(self, records: list[Record], tier: str = "",
                       cohort_year: str = "",
                       id_contains: str = "") -> list[Record]:
        """Admin filters: tier label, cohort year and part of an ID."""
        category = self.TIER_TO_CATEGORY.get(tier)
        prefix = cohort_year.zfill(2)[-2:] if cohort_year else ""
        kept: list[Record] = []
        for record in records:
            in_tier = (record.get("soft_label") == tier
                       or record.get("risk_category") == category)
            if tier and not in_tier:
                continue
            if prefix and record.student_id[:2] != prefix:
                continue
            if id_contains not in record.student_id:
                continue
            kept.append(record)
        return kept

    def cohorts(self, records: list[Record]) -> list[str]:
        """Two-digit cohort years (first two ID digits), newest first."""
        years = {record.student_id[:2] for record in records}
        return sorted((year for year in years
                       if len(year) == 2 and year.isascii()
                       and year.isdigit()), reverse=True)

    def __stamped(self, record: Record, record_id: str) -> JSONObject:
        row = record.to_row()
        row["record_id"] = record_id
        row["save_opt_in"] = True
        if not row.get("saved_at"):
            row["saved_at"] = datetime.now(timezone.utc).isoformat()
        return row

    def __write(self, row: JSONObject,
                action: Callable[[], None]) -> SaveResult:
        try:
            action()
        except StorageError as error:
            self.logger.warning("Saving a record failed: %s", error)
            return SaveResult(error=str(error))
        return SaveResult(row=row)

    def __to_record(self, row: JSONObject) -> Record:
        """Rebuild the right kind of Record from a stored row."""
        if self.__is_pending(row):
            return PendingRecord(row)
        return CheckInRecord(row)

    def __is_pending(self, row: JSONObject) -> bool:
        """Marked pending, or never successfully processed by the AI."""
        pending = str(row.get("status") or "").strip().lower() == "pending"
        source = str(row.get("source") or "").strip().lower()
        processed = (row.get("ai_ok") is True
                     or source in CheckInRecord.AI_SUCCESS_SOURCES)
        return pending or not processed

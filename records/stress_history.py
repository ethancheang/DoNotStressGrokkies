"""One student's finished check-ins, oldest first."""

from __future__ import annotations

from records.check_in_record import CheckInRecord


class StressHistory:
    """The scored check-ins of one Student ID (aggregation).

    The records are passed in: they live in storage and exist whether or
    not a history is built from them. Pending check-ins have no score yet,
    so only their number is kept.
    """

    def __init__(self, student_id: str, records: list[CheckInRecord],
                 pending_count: int = 0) -> None:
        self.__student_id: str = student_id
        self.__records: list[CheckInRecord] = sorted(
            records, key=lambda record: record.saved_at)
        self.__pending_count: int = pending_count

    @property
    def student_id(self) -> str:
        return self.__student_id

    @property
    def records(self) -> list[CheckInRecord]:
        return list(self.__records)

    @property
    def count(self) -> int:
        return len(self.__records)

    @property
    def pending_count(self) -> int:
        return self.__pending_count

    @property
    def scores(self) -> list[float]:
        """Verified stress scores, oldest first."""
        return [record.score for record in self.__records
                if record.score is not None]

    @property
    def latest(self) -> CheckInRecord | None:
        return self.__records[-1] if self.__records else None

    @property
    def previous(self) -> CheckInRecord | None:
        return self.__records[-2] if len(self.__records) > 1 else None

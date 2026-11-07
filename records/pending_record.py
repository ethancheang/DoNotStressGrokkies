"""A check-in whose answers were kept while the AI step could not finish."""

from __future__ import annotations

from json_types import JSONObject
from records.record import Record


class PendingRecord(Record):
    """Answers saved for follow-up after a Gemini failure or mismatch.

    It has no score yet. A later successful attempt replaces it in place
    through DataManager.replace_pending_record.
    """

    @property
    def status(self) -> str:
        return "pending"

    @property
    def score(self) -> float | None:
        return None

    def problem(self) -> str | None:
        return None

    def _mark(self, row: JSONObject) -> None:
        row["status"] = "pending"
        row["ai_ok"] = False

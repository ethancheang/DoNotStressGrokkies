"""One row of the admin records table."""

from __future__ import annotations

from json_types import JSONObject
from records.record import Record
from views.view import View


class AdminRecordsView(View):
    """The columns staff see: ID, score, tier, the 11 answers, status.

    Free-text reasoning, internal notes and reflection text are never
    part of a row.
    """

    COLUMNS: tuple[str, ...] = (
        "student_id", "stress_score", "risk_category", "soft_label",
        "pss_1", "pss_2", "pss_3", "pss_4", "sleep_hours_avg",
        "sleep_quality", "pas_workload", "pas_catchup", "fin_stress",
        "mspss_friends", "mspss_family", "saved_at", "survey_version",
    )
    CATEGORY_LABELS: dict[str, str] = {
        "Low": "You're doing ok",
        "Moderate": "Worth a check-in",
        "High": "Please reach out",
    }
    STATUS_LABELS: dict[str, str] = {
        "evaluated": "Evaluated",
        "pending": "Pending",
    }

    def render(self, record: Record) -> JSONObject:
        row: JSONObject = {key: record.get(key) for key in self.COLUMNS}
        if not row["soft_label"]:
            row["soft_label"] = self.CATEGORY_LABELS.get(
                str(record.get("risk_category")))
        row["status"] = self.STATUS_LABELS[record.status]
        return row

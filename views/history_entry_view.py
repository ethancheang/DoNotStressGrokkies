"""One check-in on the student's own history page."""

from __future__ import annotations

from json_types import JSONObject
from records.record import Record
from views.view import View


class HistoryEntryView(View):
    """Date, score and tier only: no answers, reasoning or notes."""

    RISK_CLASSES: dict[str, str] = {
        "Low": "low", "Moderate": "moderate", "High": "high"}
    CATEGORY_LABELS: dict[str, str] = {
        "Low": "You're doing ok",
        "Moderate": "Worth a check-in",
        "High": "Please reach out",
    }

    def render(self, record: Record) -> JSONObject:
        category = str(record.get("risk_category") or "")
        label = str(record.get("soft_label") or "")
        return {
            "saved_at": record.saved_at,
            "score": record.score,
            "tier": label or self.CATEGORY_LABELS.get(category, ""),
            "risk": self.RISK_CLASSES.get(category, "unknown"),
            "status": record.status,
        }

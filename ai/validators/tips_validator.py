"""Validator for tips."""

from __future__ import annotations

from ai.validators.id_list_validator import IdListValidator


class TipsValidator(IdListValidator):
    """tips: one to three allow-listed tip IDs. Gemini never writes tip text.

    The student-facing text for each ID lives in the I/O layer.
    feelings_check_in is deliberately absent: it needs the reflection.
    """

    ALLOWED: frozenset[str] = frozenset({
        "sleep_routine",
        "rest_a_little_more",
        "short_breaks",
        "workload_chunks",
        "money_worries",
        "talk_to_someone",
        "keep_social_contact",
    })
    MIN_TIPS: int = 1
    MAX_TIPS: int = 3

    def __init__(self) -> None:
        super().__init__("tips", self.ALLOWED, self.MIN_TIPS, self.MAX_TIPS)

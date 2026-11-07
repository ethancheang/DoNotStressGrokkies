"""Keeps one saved row per submission, however often it is sent."""

from __future__ import annotations

import hashlib
import json
import threading

from checkins.submission_context import SubmissionContext
from json_types import JSONObject


class SubmissionTracker:
    """Duplicate-pending protection.

    The same Student ID, answers and questionnaire version are one
    submission. While a session retries it, every attempt reuses the row
    saved the first time, so a refresh or double-click never appends a
    second pending row, and a later success upgrades that same row.
    """

    def __init__(self, answer_keys: tuple[str, ...]) -> None:
        self.__answer_keys: tuple[str, ...] = answer_keys
        self.__claims: dict[str, tuple[str, str]] = {}
        self.__lock: threading.Lock = threading.Lock()

    def fingerprint(self, record: JSONObject) -> str:
        """sha256 of the Student ID, the answers and survey_version."""
        answers = [record.get(key) for key in self.__answer_keys]
        payload = json.dumps(
            [record.get("student_id"), answers,
             record.get("survey_version")],
            separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def match(self, fingerprint: str,
              context: SubmissionContext) -> str | None:
        """The record_id this session already saved for the submission."""
        if (context.pending_fingerprint == fingerprint
                and context.pending_record_id):
            return context.pending_record_id
        with self.__lock:
            claim = self.__claims.get(context.owner)
        if claim is not None and claim[0] == fingerprint and claim[1]:
            return claim[1]
        return None

    def remember(self, owner: str, fingerprint: str, record_id: str) -> None:
        if owner:
            with self.__lock:
                self.__claims[owner] = (fingerprint, record_id)

    def forget(self, owner: str) -> None:
        with self.__lock:
            self.__claims.pop(owner, None)

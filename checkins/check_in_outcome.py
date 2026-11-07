"""How one check-in ended: shown, saved as pending, or not saved."""

from __future__ import annotations

from json_types import JSONObject


class CheckInOutcome:
    """The result of running the pipeline on one submission.

    DONE      Gemini and Logic finished and the record was saved.
    PENDING   the AI step failed or Logic rejected it; answers were kept.
    SAVE_FAILED  the result could not be written; nothing is shown.
    """

    DONE: str = "done"
    PENDING: str = "pending"
    SAVE_FAILED: str = "save_failed"

    def __init__(self, status: str, student_id: str, fingerprint: str,
                 record_id: str = "", error_code: str = "",
                 result: JSONObject | None = None) -> None:
        self.__status: str = status
        self.__student_id: str = student_id
        self.__fingerprint: str = fingerprint
        self.__record_id: str = record_id
        self.__error_code: str = error_code
        self.__result: JSONObject | None = result

    @property
    def status(self) -> str:
        return self.__status

    @property
    def student_id(self) -> str:
        return self.__student_id

    @property
    def saved(self) -> bool:
        """True when a row (finished or pending) is in the records store."""
        return bool(self.__record_id)

    @property
    def fingerprint(self) -> str:
        return self.__fingerprint

    @property
    def record_id(self) -> str:
        return self.__record_id

    @property
    def error_code(self) -> str:
        return self.__error_code

    @property
    def result(self) -> JSONObject | None:
        """The evaluated check-in, only when status is DONE."""
        return self.__result

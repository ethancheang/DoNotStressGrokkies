"""What happened when DataManager tried to save a record."""

from __future__ import annotations

from json_types import JSONObject


class SaveResult:
    """The stored row, or the reason nothing was stored."""

    def __init__(self, row: JSONObject | None = None,
                 error: str | None = None) -> None:
        self.__row: JSONObject | None = row
        self.__error: str | None = error

    @property
    def ok(self) -> bool:
        return self.__error is None and self.__row is not None

    @property
    def row(self) -> JSONObject | None:
        return self.__row

    @property
    def error(self) -> str | None:
        return self.__error

    @property
    def record_id(self) -> str:
        """The stored row's record_id, or "" when nothing was stored."""
        if self.__row is None:
            return ""
        return str(self.__row.get("record_id") or "")

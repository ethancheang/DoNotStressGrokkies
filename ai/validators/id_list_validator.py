"""A list of allow-listed IDs."""

from __future__ import annotations

from ai.validators.response_validator import ResponseValidator
from json_types import JSONObject, JSONValue


class IdListValidator(ResponseValidator):
    """Allow-listed IDs only; repeats are dropped, first one kept."""

    def __init__(self, field: str, allowed: frozenset[str],
                 min_items: int = 0, max_items: int | None = None) -> None:
        super().__init__(field)
        self.__allowed: frozenset[str] = allowed
        self.__min_items: int = min_items
        self.__max_items: int | None = max_items

    def validate(self, value: object) -> tuple[bool, JSONValue]:
        if not isinstance(value, list):
            return False, f"{self.field} must be a list of allow-listed IDs."
        if not self.__size_ok(len(value)):
            return False, self.__size_problem()
        cleaned: list[JSONValue] = []
        for item in value:
            if not isinstance(item, str):
                return False, f"each {self.field} item must be an ID."
            name = item.strip()
            if name not in self.__allowed:
                return False, (f"{self.field} ID is not on the "
                               f"allow-list: {name}.")
            if name not in cleaned:
                cleaned.append(name)
        if not self.__size_ok(len(cleaned)):
            return False, self.__size_problem()
        return True, cleaned

    def schema(self) -> JSONObject:
        entry: JSONObject = {
            "type": "ARRAY",
            "items": {"type": "STRING", "enum": sorted(self.__allowed)},
        }
        if self.__min_items:
            entry["minItems"] = self.__min_items
        if self.__max_items is not None:
            entry["maxItems"] = self.__max_items
        return entry

    def __size_ok(self, count: int) -> bool:
        too_many = self.__max_items is not None and count > self.__max_items
        return count >= self.__min_items and not too_many

    def __size_problem(self) -> str:
        most = ("any number of" if self.__max_items is None
                else f"at most {self.__max_items}")
        return (f"{self.field} must contain at least {self.__min_items} "
                f"and {most} allow-listed IDs.")

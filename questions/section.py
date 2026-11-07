"""One chapter of the check-in, grouping related questions."""

from __future__ import annotations

from json_types import JSONObject


class Section:
    """A chapter: its heading, time period, explanation and question keys."""

    def __init__(self, title: str, heading: str, period: str, intro: str,
                 why: str, keys: tuple[str, ...]) -> None:
        self.__title: str = title
        self.__heading: str = heading
        self.__period: str = period
        self.__intro: str = intro
        self.__why: str = why
        self.__keys: tuple[str, ...] = keys

    @property
    def title(self) -> str:
        return self.__title

    @property
    def heading(self) -> str:
        return self.__heading

    @property
    def keys(self) -> tuple[str, ...]:
        return self.__keys

    def as_dict(self) -> JSONObject:
        return {
            "title": self.__title,
            "heading": self.__heading,
            "period": self.__period,
            "intro": self.__intro,
            "why": self.__why,
            "keys": list(self.__keys),
        }

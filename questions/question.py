"""One check-in question: its wording, answer scale and input check."""

from __future__ import annotations

import math

from json_types import JSONObject


class Question:
    """A required question answered on a numeric scale.

    Choice questions label every point of the scale. Slider questions such
    as sleep hours may use half steps and name only the two ends.
    """

    def __init__(self, key: str, label: str, prompt: str, minimum: int,
                 maximum: int, options: tuple[str, ...] = (),
                 step: float = 1, reverse: bool = False,
                 kind: str = "choice", default: float | None = None,
                 low: str = "", high: str = "", unit: str = "") -> None:
        self.__key: str = key
        self.__label: str = label
        self.__prompt: str = prompt
        self.__minimum: int = minimum
        self.__maximum: int = maximum
        self.__options: tuple[str, ...] = options
        self.__step: float = step
        self.__reverse: bool = reverse
        self.__kind: str = kind
        self.__default: float | None = default
        self.__low: str = low
        self.__high: str = high
        self.__unit: str = unit

    @property
    def key(self) -> str:
        return self.__key

    @property
    def label(self) -> str:
        return self.__label

    @property
    def prompt(self) -> str:
        return self.__prompt

    @property
    def minimum(self) -> int:
        return self.__minimum

    @property
    def maximum(self) -> int:
        return self.__maximum

    @property
    def options(self) -> tuple[str, ...]:
        return self.__options

    @property
    def step(self) -> float:
        return self.__step

    @property
    def reverse(self) -> bool:
        """True when a high answer means less stress (positively worded)."""
        return self.__reverse

    @property
    def kind(self) -> str:
        return self.__kind

    @property
    def low(self) -> str:
        return self.__low

    @property
    def high(self) -> str:
        return self.__high

    def validate(self, raw: object) -> tuple[bool, int | float | str]:
        """(True, the answer as a number) or (False, a message to show)."""
        if raw is None or str(raw).strip() == "":
            return False, "Please answer this question."
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
            return False, "Choose one of the available answers."
        try:
            value = float(raw)
        except (ValueError, OverflowError):
            return False, "Choose a number in the available range."
        in_range = self.__minimum <= value <= self.__maximum
        if (not math.isfinite(value) or not in_range
                or not (value / self.__step).is_integer()):
            return False, (f"Choose {self.__minimum} to {self.__maximum} "
                           f"in steps of {self.__step:g}.")
        return True, int(value) if float(self.__step).is_integer() else value

    def option_label(self, value: int) -> str:
        """The word label for a choice answer, e.g. 3 -> "Sometimes"."""
        return self.__options[value - self.__minimum]

    def as_dict(self) -> JSONObject:
        """The question as the browser needs it."""
        return {
            "key": self.__key,
            "label": self.__label,
            "prompt": self.__prompt,
            "min": self.__minimum,
            "max": self.__maximum,
            "step": self.__step,
            "options": list(self.__options) or None,
            "reverse": self.__reverse,
            "kind": self.__kind,
            "default": self.__default,
            "low": self.__low,
            "high": self.__high,
            "unit": self.__unit,
        }

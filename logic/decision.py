"""The outcome Logic builds up while its business rules run."""

from __future__ import annotations

from json_types import JSONObject, JSONValue


class Decision:
    """Gemini's tier and tips, adjusted rule by rule.

    It starts as exactly what Gemini returned. Rules may raise the tier,
    lead with a tip, suggest extra tips and add notes; the setters below
    are the only way they change it.
    """

    def __init__(self, record: JSONObject,
                 context_flags: dict[str, bool]) -> None:
        self.__record: JSONObject = record
        self.__context_flags: dict[str, bool] = dict(context_flags)
        self.__risk_category: str = str(record.get("risk_category", ""))
        self.__soft_label: str = str(record.get("soft_label", ""))
        self.__speak_prominence: str = str(
            record.get("speak_prominence", ""))
        self.__gemini_tips: list[str] = self.__strings(record.get("tips"))
        self.__lead_tips: list[str] = []
        self.__extra_tips: list[str] = []
        self.__tips: list[str] = list(self.__gemini_tips)
        self.__notes: list[str] = []
        self.__support_priority: bool = False

    def field(self, name: str) -> JSONValue:
        """A field of the AI-enriched check-in, exactly as Gemini sent it."""
        return self.__record.get(name)

    @property
    def context_flags(self) -> dict[str, bool]:
        return dict(self.__context_flags)

    @property
    def risk_category(self) -> str:
        return self.__risk_category

    @risk_category.setter
    def risk_category(self, value: str) -> None:
        self.__risk_category = value

    @property
    def soft_label(self) -> str:
        return self.__soft_label

    @soft_label.setter
    def soft_label(self, value: str) -> None:
        self.__soft_label = value

    @property
    def speak_prominence(self) -> str:
        return self.__speak_prominence

    @speak_prominence.setter
    def speak_prominence(self, value: str) -> None:
        self.__speak_prominence = value

    @property
    def support_priority(self) -> bool:
        return self.__support_priority

    @support_priority.setter
    def support_priority(self, value: bool) -> None:
        self.__support_priority = value

    @property
    def gemini_tips(self) -> list[str]:
        return list(self.__gemini_tips)

    @property
    def lead_tips(self) -> list[str]:
        return list(self.__lead_tips)

    @property
    def extra_tips(self) -> list[str]:
        return list(self.__extra_tips)

    @property
    def tips(self) -> list[str]:
        """The final tip IDs, in the order the student sees them."""
        return list(self.__tips)

    @tips.setter
    def tips(self, value: list[str]) -> None:
        self.__tips = list(value)

    @property
    def notes(self) -> list[str]:
        return list(self.__notes)

    def lead_with(self, tip_id: str) -> None:
        """Show this tip before all others."""
        self.__lead_tips = [tip_id]

    def suggest(self, tip_id: str) -> None:
        """Add a tip after Gemini's, if there is room."""
        if tip_id not in self.__extra_tips:
            self.__extra_tips.append(tip_id)

    def note(self, text: str) -> None:
        """Record why a rule changed the outcome (for staff, not students)."""
        self.__notes.append(text)

    def __strings(self, value: JSONValue) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value]

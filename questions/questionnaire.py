"""The whole check-in: its questions, chapters and safety check."""

from __future__ import annotations

from json_types import JSONObject
from questions.question import Question
from questions.safety_check import SafetyCheck
from questions.section import Section


class Questionnaire:
    """A versioned set of questions grouped into chapters.

    Questions and chapters are passed in and can be shared (aggregation).
    The safety check is built here from its patterns and belongs to this
    questionnaire alone (composition).
    """

    def __init__(self, version: str, questions: list[Question],
                 sections: list[Section],
                 safety_patterns: tuple[str, ...]) -> None:
        self.__version: str = version
        self.__questions: list[Question] = list(questions)
        self.__sections: list[Section] = list(sections)
        self.__safety: SafetyCheck = SafetyCheck(safety_patterns)
        self.__by_key: dict[str, Question] = {
            question.key: question for question in questions}

    @property
    def version(self) -> str:
        return self.__version

    @property
    def questions(self) -> list[Question]:
        return list(self.__questions)

    @property
    def sections(self) -> list[Section]:
        return list(self.__sections)

    @property
    def safety(self) -> SafetyCheck:
        return self.__safety

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(self.__by_key)

    @property
    def reversed_keys(self) -> tuple[str, ...]:
        """Positively worded items, scored as 6 - answer."""
        return tuple(question.key for question in self.__questions
                     if question.reverse)

    def question(self, key: str) -> Question:
        """The question with this key. Raises KeyError for an unknown key."""
        return self.__by_key[key]

    def public_config(self) -> JSONObject:
        """Everything the browser needs to draw the check-in."""
        return {
            "version": self.__version,
            "questions": [question.as_dict() for question in self.__questions],
            "sections": [section.as_dict() for section in self.__sections],
            "safetyPatterns": list(self.__safety.patterns),
        }

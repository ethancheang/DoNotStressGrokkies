"""Question, Section, SafetyCheck and Questionnaire on their own."""
import unittest

from plain_tests import case, function_suite
from questions.question import Question
from questions.questionnaire import Questionnaire
from questions.section import Section
from survey import QUESTIONNAIRE

CHOICE = Question("q1", "Label", "How often?", 1, 5, ("a", "b", "c", "d", "e"))
SLIDER = Question("hours", "Sleep", "How long?", 0, 14, step=0.5,
                  kind="slider", low="0 hours", high="14 hours")


def test_choice_answers_become_integers_and_bad_input_is_explained():
    assert CHOICE.validate("3") == (True, 3)
    assert CHOICE.validate(5.0) == (True, 5)
    for raw, message in ((None, "Please answer this question."),
                         ("  ", "Please answer this question."),
                         (True, "Choose one of the available answers."),
                         ([3], "Choose one of the available answers."),
                         ("three", "Choose a number in the available range."),
                         (6, "Choose 1 to 5 in steps of 1."),
                         (2.5, "Choose 1 to 5 in steps of 1."),
                         (float("nan"), "Choose 1 to 5 in steps of 1.")):
        with case(raw=raw):
            assert CHOICE.validate(raw) == (False, message)


def test_slider_answers_keep_half_steps():
    assert SLIDER.validate("6.5") == (True, 6.5)
    assert SLIDER.validate(6.75)[0] is False
    assert SLIDER.as_dict()["options"] is None
    assert CHOICE.option_label(3) == "c"


def test_questionnaire_builds_its_own_safety_check():
    section = Section("One", "Heading", "Now", "Intro", "Why", ("q1",))
    questionnaire = Questionnaire("v-test", [CHOICE, SLIDER], [section],
                                  (r"\bhelp me\b",))
    assert questionnaire.keys == ("q1", "hours")
    assert questionnaire.question("hours") is SLIDER
    assert questionnaire.safety.fired("please HELP ME")
    assert not questionnaire.safety.fired(None)
    config = questionnaire.public_config()
    assert config["version"] == "v-test"
    assert [item["key"] for item in config["questions"]] == ["q1", "hours"]
    assert config["sections"][0]["keys"] == ["q1"]
    assert config["safetyPatterns"] == [r"\bhelp me\b"]
    questionnaire.questions.clear()
    assert len(questionnaire.questions) == 2


def test_the_live_questionnaire_is_evidence_v3():
    assert QUESTIONNAIRE.version == "evidence-v3"
    assert len(QUESTIONNAIRE.questions) == 11
    assert len(QUESTIONNAIRE.sections) == 6
    assert QUESTIONNAIRE.safety.fired("I can’t keep myself safe")
    assert not QUESTIONNAIRE.safety.fired("exams are stressful")


def load_tests(loader, tests, pattern):
    """Let `python -m unittest discover -s tests` run this file's tests."""
    return function_suite(globals())


if __name__ == "__main__":
    unittest.main()

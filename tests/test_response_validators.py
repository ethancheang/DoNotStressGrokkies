"""Each ResponseValidator on its own: good values, bad values, schema."""
import unittest

from ai.validators.choice_validator import ChoiceValidator
from ai.validators.confidence_validator import ConfidenceValidator
from ai.validators.range_validator import RangeValidator
from ai.validators.reasoning_validator import ReasoningValidator
from ai.validators.response_validator import ResponseValidator
from ai.validators.score_validator import ScoreValidator
from ai.validators.scored_items_validator import ScoredItemsValidator
from ai.validators.soft_label_validator import SoftLabelValidator
from ai.validators.stressors_validator import StressorsValidator
from ai.validators.tips_validator import TipsValidator
from plain_tests import case, function_suite

KEYS = ("a", "b")
TIERS = ("Low", "Moderate", "High")


def test_every_validator_shares_the_contract():
    """Liskov: each one rejects junk with a message naming its field."""
    validators = (
        ScoredItemsValidator(KEYS), ScoreValidator(), SoftLabelValidator(),
        ChoiceValidator("risk_category", TIERS), StressorsValidator(),
        TipsValidator(), ConfidenceValidator(), ReasoningValidator(),
    )
    for validator in validators:
        with case(field=validator.field):
            assert isinstance(validator, ResponseValidator)
            assert "type" in validator.schema()
            ok, message = validator.validate(object())
            assert ok is False
            assert validator.field.split("_")[0] in message


def test_scored_items():
    validator = ScoredItemsValidator(KEYS)
    assert validator.validate({"a": 1, "b": 5}) == (True, {"a": 1, "b": 5})
    for bad in ({"a": 1}, {"a": 1, "b": 6}, {"a": 1, "b": True},
                {"a": 1, "b": 2.0}, {"a": 1, "b": 2, "c": 3}, [1, 2]):
        with case(bad=bad):
            assert validator.validate(bad)[0] is False
    assert validator.schema()["required"] == ["a", "b"]


def test_score_and_confidence_share_the_range_check():
    assert isinstance(ScoreValidator(), RangeValidator)
    assert isinstance(ConfidenceValidator(), RangeValidator)
    assert ScoreValidator().validate("2.5") == (True, 2.5)
    assert ConfidenceValidator().validate(0) == (True, 0.0)
    for bad in (0.99, 5.01, True, None, float("nan"), 10 ** 400):
        with case(bad=bad):
            assert ScoreValidator().validate(bad)[0] is False
    for bad in (-0.1, 1.1, False, "high", float("inf")):
        with case(bad=bad):
            assert ConfidenceValidator().validate(bad)[0] is False
    assert ScoreValidator().validate(9)[1] == (
        "stress_score must be a float between 1.0 and 5.0.")


def test_choices_strip_spaces_and_soft_label_accepts_curly_quotes():
    tier = ChoiceValidator("risk_category", TIERS)
    assert tier.validate("  High ") == (True, "High")
    assert tier.validate("Critical") == (
        False, 'risk_category must be "Low", "Moderate", or "High".')
    label = SoftLabelValidator()
    assert label.validate("You’re doing ok") == (True, "You're doing ok")
    assert label.validate("Please reach out") == (True, "Please reach out")
    assert label.validate("Doing great")[0] is False
    assert isinstance(label, ChoiceValidator)


def test_id_lists_drop_repeats_and_respect_their_limits():
    stressors = StressorsValidator()
    assert stressors.validate([]) == (True, [])
    assert stressors.validate([" academic_overload", "academic_overload"]) \
        == (True, ["academic_overload"])
    assert stressors.validate(["made_up"])[0] is False
    assert "emotional_distress" not in StressorsValidator.ALLOWED
    tips = TipsValidator()
    assert tips.validate(["short_breaks", "short_breaks"]) == (
        True, ["short_breaks"])
    for bad in ([], ["a", "b", "c", "d"], ["short_breaks", 3],
                ["feelings_check_in"]):
        with case(bad=bad):
            assert tips.validate(bad)[0] is False
    assert tips.schema()["minItems"] == 1
    assert tips.schema()["maxItems"] == 3
    assert "minItems" not in stressors.schema()


def test_reasoning_must_be_real_text():
    assert ReasoningValidator().validate("  Kind. ") == (True, "Kind.")
    assert ReasoningValidator().validate("   ")[0] is False


def load_tests(loader, tests, pattern):
    """Let `python -m unittest discover -s tests` run this file's tests."""
    return function_suite(globals())


if __name__ == "__main__":
    unittest.main()

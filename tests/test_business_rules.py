"""Each BusinessRule on its own Decision, without Gemini or LogicManager."""
import unittest

from logic.business_rule import BusinessRule
from logic.context_flag_rule import ContextFlagRule
from logic.decision import Decision
from logic.safety_override_rule import SafetyOverrideRule
from logic.support_priority_rule import SupportPriorityRule
from logic.tip_cap_rule import TipCapRule
from plain_tests import case, function_suite

NO_FLAGS = {"sleep": False, "workload": False, "finances": False,
            "support": False}


def _decision(flags=None, **fields):
    """A Moderate Gemini reply with two tips, plus any changed fields."""
    record = {"risk_category": "Moderate", "soft_label": "Worth a check-in",
              "speak_prominence": "medium", "primary_stressors": [],
              "tips": ["short_breaks", "rest_a_little_more"],
              "safety_flag": False}
    record.update(fields)
    return Decision(record, NO_FLAGS if flags is None else flags)


def test_every_rule_is_a_business_rule_with_a_name():
    rules = (SafetyOverrideRule(), SupportPriorityRule(), ContextFlagRule(),
             TipCapRule())
    for rule in rules:
        with case(rule=rule.name):
            assert isinstance(rule, BusinessRule)
            assert rule.run(_decision()) == rule.applies(_decision())
    assert len({rule.name for rule in rules}) == 4


def test_a_decision_starts_as_exactly_what_gemini_said():
    decision = _decision()
    assert decision.risk_category == "Moderate"
    assert decision.tips == ["short_breaks", "rest_a_little_more"]
    assert decision.notes == [] and decision.support_priority is False
    decision.tips.append("changed outside")
    assert decision.tips == ["short_breaks", "rest_a_little_more"]


def test_safety_override_only_fires_on_a_true_flag():
    assert not SafetyOverrideRule().applies(_decision(safety_flag="yes"))
    decision = _decision(safety_flag=True)
    assert SafetyOverrideRule().run(decision)
    assert (decision.risk_category, decision.soft_label,
            decision.speak_prominence) == ("High", "Please reach out",
                                           "high")
    assert decision.lead_tips == ["talk_to_someone"]
    assert decision.notes[0].startswith("safety_override")


def test_support_priority_needs_both_ai_fields():
    rule = SupportPriorityRule()
    high = dict(risk_category="High", primary_stressors=["low_social_support"])
    assert rule.applies(_decision(**high))
    for fields in (dict(high, risk_category="Moderate"),
                   dict(high, primary_stressors=["academic_overload"]),
                   dict(high, primary_stressors=[]),
                   dict(high, primary_stressors="low_social_support")):
        with case(fields=fields):
            assert not rule.applies(_decision(**fields))
    assert not rule.applies(Decision({}, NO_FLAGS))
    decision = _decision(**high)
    rule.run(decision)
    assert decision.support_priority is True
    assert decision.lead_tips == ["talk_to_someone"]
    assert decision.extra_tips == ["keep_social_contact"]


def test_context_flags_suggest_their_tips_in_order():
    assert not ContextFlagRule().applies(_decision())
    decision = _decision(flags=dict(NO_FLAGS, sleep=True, support=True))
    assert ContextFlagRule().run(decision)
    assert decision.extra_tips == ["sleep_routine", "talk_to_someone"]
    assert decision.risk_category == "Moderate"


def test_tip_cap_leads_keeps_gemini_tips_and_stops_at_four():
    decision = _decision(tips=["short_breaks", "rest_a_little_more",
                               "talk_to_someone"])
    decision.lead_with("talk_to_someone")
    for tip in ("keep_social_contact", "sleep_routine", "money_worries"):
        decision.suggest(tip)
    TipCapRule().run(decision)
    assert decision.tips == ["talk_to_someone", "short_breaks",
                             "rest_a_little_more", "keep_social_contact"]
    assert len(decision.tips) == TipCapRule.MAX_TIPS


def load_tests(loader, tests, pattern):
    """Let `python -m unittest discover -s tests` run this file's tests."""
    return function_suite(globals())


if __name__ == "__main__":
    unittest.main()

"""LogicManager validates Gemini's analysis; it never replaces it.

No real Gemini call: the AI fields come from a FakeProvider run through
AIManager's own validation, or are written by hand for disagreements.
"""

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import survey
from ai.ai_result import AIResult
from ai.fake_provider import FakeProvider
from ai_manager import AIManager
from base_manager import BaseManager
from data_manager import DataManager
from records.check_in_record import CheckInRecord
from storage.json_storage import JSONStorage
from logic.stress_scorer import StressScorer
from logic_manager import LogicManager
from plain_tests import case, function_suite

ROOT = Path(__file__).resolve().parents[1]
LOGIC = LogicManager()
SCORER = LOGIC.scorer
KEYS = StressScorer.ANSWER_KEYS


def _answers(**changes):
    """All-3 answers with 6.5 h sleep: scored 3 each, average 3.0."""
    answers = {key: 3 for key in KEYS}
    answers["sleep_hours_avg"] = 6.5
    answers.update(changes)
    return answers


def _fake_generate_fn(**overrides):
    """A fake Gemini that replays the formula on the prompt's answers."""
    def generate(prompt, model_name):
        answers = json.loads(prompt[prompt.rfind("{"):])
        stress = SCORER.score(answers).stress_score
        category = SCORER.category_for(stress)
        reply = {
            "scored_items": SCORER.scored_items(answers),
            "stress_score": stress,
            "risk_category": category,
            "primary_stressors": ["academic_overload"],
            "confidence": 0.8,
            "reasoning": "Gemini reasoning for the student.",
            "soft_label": SCORER.label_for(category),
            "tips": ["short_breaks", "rest_a_little_more"],
            "speak_prominence": SCORER.prominence_for(category),
        }
        reply.update(overrides)
        return json.dumps(reply)
    return generate


def _enriched(answers=None, **ai_overrides):
    """Run the real AIManager.analyse with a FakeProvider."""
    record = {"student_id": "2605581", "survey_version": "evidence-v3",
              "safety_flag": False, **(answers or _answers())}
    manager = AIManager(FakeProvider(_fake_generate_fn(**ai_overrides)),
                        survey.QUESTIONNAIRE.questions,
                        max_attempts=1, retry_delay_sec=0)
    result = manager.analyse(record)
    assert result.ok, result.failure
    return result.fields


def _with_gemini_score(record, stress_score):
    """Replace Gemini's score with one that may disagree with the answers.

    AIManager would reject a reply over 0.01 off, so this is set by hand
    to test Logic's own cross-check.
    """
    record = dict(record)
    record.update(stress_score=stress_score,
                  risk_score=(stress_score - 1) / 4)
    return record


# --- Manager ---------------------------------------------------------------

def test_logic_manager_is_a_manager_that_owns_its_rules():
    assert isinstance(LOGIC, BaseManager)
    assert LOGIC.health() == {
        "name": "logic_manager", "rule_version": "v3",
        "rules": ["safety_override", "support_priority", "context_flags",
                  "tip_cap"]}
    assert LogicManager().scorer is not LOGIC.scorer


# --- Cross Check -----------------------------------------------------------

def test_gemini_match_is_kept_untouched():
    enriched = _enriched()
    result = LOGIC.evaluate(enriched)
    assert result["ok"]
    for key in ("stress_score", "risk_category", "soft_label",
                "speak_prominence", "tips", "primary_stressors",
                "reasoning"):
        assert result[key] == enriched[key], key
    assert result["risk_score"] == (result["stress_score"] - 1) / 4
    assert result["logic_stress_score"] == 3.0
    assert result["logic_clamp_notes"] == []


def test_gemini_within_0_01_is_kept_untouched():
    record = _with_gemini_score(_enriched(), 3.01)
    result = LOGIC.evaluate(record)
    assert result["ok"]
    assert result["stress_score"] == 3.01
    assert result["logic_stress_score"] == 3.0
    for key in ("risk_score", "risk_category", "soft_label",
                "speak_prominence", "reasoning"):
        assert result[key] == record[key], key
    assert result["logic_clamp_notes"] == []


def test_mismatch_over_0_01_returns_error():
    for gemini_score in (3.02, 2.98, 3.5, 2.1, 4.9):
        with case(gemini_score=gemini_score):
            record = _with_gemini_score(_enriched(), gemini_score)
            record["feelings_text"] = "private"
            result = LOGIC.evaluate(record)
            assert not result["ok"]
            assert result["error"] == LogicManager.ERROR_SCORE_MISMATCH
            assert result["stress_score"] == gemini_score
            assert result["logic_stress_score"] == 3.0
            assert "feelings_text" not in result
            # No outcome is invented on a mismatch.
            assert "logic_rule" not in result
            assert "context_flags" not in result


def _app(provider, max_attempts=1):
    from main import App
    temp = tempfile.mkdtemp()
    return App(provider=provider, data_path=Path(temp) / "records.json",
               ai_max_attempts=max_attempts, ai_retry_delay_sec=0)


def test_mismatch_is_an_ai_failure_in_the_pipeline():
    record = _with_gemini_score(_enriched(), 4.5)
    with patch.object(AIManager, "analyse",
                      return_value=AIResult(fields=record)):
        result = _app(FakeProvider()).process_checkin(dict(record))
    assert not result.ok
    assert result.failure.code == "unavailable"
    assert "score_mismatch" in result.failure.detail


# --- Scoring ---------------------------------------------------------------

def test_reverse_scoring_and_sleep_conversion():
    answers = dict(pss_1=4, pss_2=2, pss_3=1, pss_4=3, sleep_hours_avg=5.5,
                   sleep_quality=2, pas_workload=5, pas_catchup=1,
                   fin_stress=2, mspss_friends=5, mspss_family=4)
    # 4 + (6-2) + (6-1) + 3 + 4 (5.5 h) + 2 + 5 + 1 + 2 + (6-5) + (6-4)
    assert SCORER.score(answers).stress_score == 3.0


def test_sleep_hour_bands():
    for hours, value in [(14, 1), (8, 1), (7.5, 2), (7, 2), (6.5, 3),
                         (6, 3), (5.5, 4), (5, 4), (4.5, 5), (0, 5)]:
        assert SCORER.sleep_hours_stress(hours) == value, hours


def test_reversed_items_only():
    assert StressScorer.REVERSED_KEYS == (
        "pss_2", "pss_3", "mspss_friends", "mspss_family")
    assert StressScorer.REVERSED_KEYS == survey.QUESTIONNAIRE.reversed_keys
    for key in KEYS:
        if key == "sleep_hours_avg":
            continue
        expected = 5 if key in StressScorer.REVERSED_KEYS else 1
        assert SCORER.scored_value(key, 1) == expected, key


def test_tier_boundaries():
    assert SCORER.category_for(2.49) == "Low"
    assert SCORER.category_for(2.5) == "Moderate"
    assert SCORER.category_for(3.5) == "Moderate"
    assert SCORER.category_for(3.51) == "High"


def test_score_card_holds_the_audit_values():
    card = SCORER.score(_answers(mspss_friends=1, mspss_family=3))
    assert card.item_count == 11
    assert card.support_mean == 2
    assert card.context_flags["support"] is True
    assert card.risk_category == SCORER.category_for(card.stress_score)
    card.context_flags["support"] = False
    assert card.context_flags["support"] is True


# --- Flag Tip --------------------------------------------------------------

FLAG_CASES = (
    ("sleep", dict(sleep_hours_avg=5.5), "sleep_routine"),
    ("sleep", dict(sleep_quality=4), "sleep_routine"),
    ("workload", dict(pas_workload=4), "workload_chunks"),
    ("finances", dict(fin_stress=4), "money_worries"),
    ("support", dict(mspss_friends=2, mspss_family=2), "talk_to_someone"),
)


def test_each_flag_adds_its_tip():
    for flag, changes, tip in FLAG_CASES:
        with case(flag=flag, changes=changes):
            result = LOGIC.evaluate(_enriched(_answers(**changes)))
            assert result["context_flags"][flag]
            assert tip in result["tips"]
            assert result["tips"][:2] == ["short_breaks",
                                          "rest_a_little_more"]
            assert len(result["tips"]) <= 4


def test_no_flag_adds_no_tip():
    result = LOGIC.evaluate(_enriched())
    assert not any(result["context_flags"].values())
    assert result["tips"] == ["short_breaks", "rest_a_little_more"]


def test_all_flags_never_exceed_four_or_replace_gemini_tips():
    gemini_tips = ["short_breaks", "rest_a_little_more",
                   "keep_social_contact"]
    answers = _answers(sleep_hours_avg=4, pas_workload=5, fin_stress=5,
                       mspss_friends=1, mspss_family=1)
    result = LOGIC.evaluate(_enriched(answers, tips=gemini_tips))
    assert all(result["context_flags"].values())
    assert len(result["tips"]) == 4
    assert result["tips"][:3] == gemini_tips


def test_flags_never_change_the_tier():
    # Low average but workload and finances flagged.
    answers = {key: 1 for key in KEYS}
    answers.update(sleep_hours_avg=8, pss_2=5, pss_3=5, mspss_friends=5,
                   mspss_family=5, pas_workload=5, fin_stress=5)
    result = LOGIC.evaluate(_enriched(answers))
    assert result["risk_category"] == "Low"
    assert "workload_chunks" in result["tips"]
    assert "money_worries" in result["tips"]


# --- Safety ----------------------------------------------------------------

def test_safety_flag_forces_reach_out():
    record = _enriched(_answers(pss_1=1, pss_4=1))
    record["safety_flag"] = True
    record["feelings_text"] = "should never survive Logic"
    result = LOGIC.evaluate(record)
    assert result["risk_category"] == "High"
    assert result["soft_label"] == "Please reach out"
    assert result["speak_prominence"] == "high"
    assert result["tips"][0] == "talk_to_someone"
    assert len(result["tips"]) <= 4
    assert result["stress_score"] == record["stress_score"]
    assert any(note.startswith("safety_override")
               for note in result["logic_clamp_notes"])
    assert "feelings_text" not in result


def test_safety_moves_talk_tip_first_without_dropping_gemini_tips():
    gemini_tips = ["short_breaks", "rest_a_little_more", "talk_to_someone"]
    record = _enriched(tips=gemini_tips)
    record["safety_flag"] = True
    result = LOGIC.evaluate(record)
    assert result["tips"][0] == "talk_to_someone"
    assert set(gemini_tips) <= set(result["tips"])


def test_only_true_safety_flag_counts():
    record = _enriched(_answers(pss_1=1, pss_4=1))
    record["safety_flag"] = "yes"
    assert LOGIC.evaluate(record)["risk_category"] != "High"


# --- Output ----------------------------------------------------------------

def test_output_contract():
    record = _enriched()
    record["feelings_text"] = "private"
    result = LOGIC.evaluate(record)
    assert result["source"] == "ai_logic"
    assert result["ai_ok"] is True
    assert result["logic_rule"] == "v3"
    for key in ("stress_score", "logic_stress_score", "risk_category",
                "soft_label", "speak_prominence", "tips",
                "primary_stressors", "reasoning", "risk_score",
                "logic_clamp_notes", "context_flags", "support_mean"):
        assert key in result
    assert "feelings_text" not in result
    # Student-facing wording belongs to the I/O layer.
    assert "factor_insights" not in result


def test_input_is_not_mutated():
    record = _enriched()
    snapshot = json.dumps(record, sort_keys=True)
    LOGIC.evaluate(record)
    assert json.dumps(record, sort_keys=True) == snapshot


# --- Missing Field ---------------------------------------------------------

def test_missing_ai_field_gives_error_dict():
    for key in LogicManager.REQUIRED_AI_FIELDS:
        with case(key=key):
            record = _enriched()
            del record[key]
            result = LOGIC.evaluate(record)
            assert not result["ok"]
            assert result["error"] == LogicManager.ERROR_AI_FIELDS_REQUIRED
            assert key in result["missing"]


def test_missing_answer_gives_error_dict():
    for key in KEYS:
        with case(key=key):
            record = _enriched()
            del record[key]
            result = LOGIC.evaluate(record)
            assert not result["ok"]
            assert key in result["missing"]


def test_unusable_numbers_give_error_dict():
    for key, bad in (("stress_score", "high"), ("pss_1", None),
                     ("sleep_quality", 9), ("sleep_hours_avg", float("nan")),
                     ("fin_stress", 10 ** 400)):
        with case(key=key, bad=bad):
            record = _enriched()
            record[key] = bad
            result = LOGIC.evaluate(record)
            assert not result["ok"]
            assert key in result["invalid"]


def test_non_dict_gives_error_dict():
    for bad in (None, [], "record"):
        result = LOGIC.evaluate(bad)
        assert not result["ok"]
        assert "record" in result["invalid"]


# --- Legacy Removed --------------------------------------------------------

LEGACY = ("stress_level", "academic_workload", "financial_stress",
          "social_support", "ANSWER_MAX", "PSS4", "_stress_to_pss4",
          "_rescale", "REQUIRED_STUDENT_FIELDS", "0.40", "0.75", "finalise")


def test_no_legacy_names_in_logic_or_survey():
    files = [ROOT / "logic_manager.py", ROOT / "survey.py",
             *sorted((ROOT / "logic").glob("*.py"))]
    for path in files:
        text = path.read_text(encoding="utf-8")
        for legacy in LEGACY:
            with case(file=path.name, legacy=legacy):
                # Start of a name only, so the real stressor ID
                # "low_social_support" is not taken for "social_support".
                pattern = r"(?<![A-Za-z0-9_])" + re.escape(legacy)
                assert re.search(pattern, text) is None


def test_survey_only_holds_questionnaire_content():
    for gone in ("score", "finalise", "factor_insights", "explanation",
                 "scored_value", "sleep_hours_stress", "safety_check",
                 "validate_question", "public_config"):
        assert not hasattr(survey, gone), gone
    assert survey.QUESTIONNAIRE.safety.fired("I want to die")


# --- Scoring rules handed to AIManager ------------------------------------
# App lends LogicManager's StressScorer to AIManager as its ScoreAuditor,
# so these rules exist only here.

def _exact_ai_fields(answers):
    """The reply Gemini should give for these answers."""
    stress = SCORER.score(answers).stress_score
    category = SCORER.category_for(stress)
    return {
        "scored_items": SCORER.scored_items(answers),
        "stress_score": stress,
        "risk_category": category,
        "soft_label": SCORER.label_for(category),
        "speak_prominence": SCORER.prominence_for(category),
    }


def test_scored_items_are_what_gemini_must_return():
    lowest = _answers(pss_1=1, pss_2=5, pss_3=5, pss_4=1, sleep_hours_avg=8,
                      sleep_quality=1, pas_workload=1, pas_catchup=1,
                      fin_stress=1, mspss_friends=5, mspss_family=5)
    assert SCORER.scored_items(lowest) == {key: 1 for key in KEYS}
    assert all(isinstance(value, int)
               for value in SCORER.scored_items(lowest).values())
    assert SCORER.score(lowest).stress_score == 1.0
    for key in ("pss_2", "pss_3", "mspss_friends", "mspss_family"):
        with case(key=key):
            flipped = dict(lowest, **{key: 1})
            assert SCORER.scored_items(flipped)[key] == 5
            assert SCORER.score(flipped).stress_score == round(15 / 11, 2)
    for hours, band in ((14, 1), (8.5, 1), (8, 1), (7.5, 2), (7, 2),
                        (6.5, 3), (6, 3), (5.5, 4), (5, 4), (4.5, 5),
                        (0, 5)):
        with case(hours=hours):
            items = SCORER.scored_items(dict(lowest, sleep_hours_avg=hours))
            assert items["sleep_hours_avg"] == band


def test_verify_accepts_an_exact_reply():
    for answers in (_answers(),
                    _answers(pss_1=5, fin_stress=5, sleep_hours_avg=4.5),
                    _answers(pss_2=5, pss_3=5, mspss_friends=5,
                             mspss_family=5)):
        with case(answers=answers):
            assert SCORER.verify(_exact_ai_fields(answers), answers) is None
    within = dict(_exact_ai_fields(_answers()), stress_score=3.01)
    assert SCORER.verify(within, _answers()) is None


def test_exactly_0_01_off_is_accepted_and_more_is_rejected():
    """Reject a score MORE than 0.01 off; float error must not reject 0.01."""
    accepted = rejected = 0
    for total in range(11, 56):  # every possible sum of 11 items
        mean = round(total / 11, 2)
        for delta, should_pass in ((0.01, True), (-0.01, True),
                                   (0.02, False), (-0.02, False)):
            gemini = round(mean + delta, 2)
            if (not 1 <= gemini <= 5 or SCORER.category_for(gemini)
                    != SCORER.category_for(mean)):
                continue
            with case(mean=mean, gemini=gemini):
                assert SCORER.within_tolerance(gemini, mean) is should_pass
                accepted += should_pass
                rejected += not should_pass
    assert accepted > 50 and rejected > 50


def test_verify_rejects_wrong_tiers_items_and_scores():
    answers = _answers()
    exact = _exact_ai_fields(answers)
    cases = (
        (dict(exact, stress_score=2.0, risk_category="High",
              soft_label="Please reach out", speak_prominence="high"),
         "risk_category must be Low"),
        (dict(exact, soft_label="You're doing ok"), "soft_label must match"),
        (dict(exact, speak_prominence="high"), "speak_prominence must match"),
        (dict(exact, scored_items=dict(exact["scored_items"], pss_1=4)),
         "scored_items"),
        (dict(exact, stress_score=3.02), "stress_score must match"),
        (dict(exact, stress_score=3.4), "stress_score must match"),
    )
    for fields, expected in cases:
        with case(expected=expected):
            message = SCORER.verify(fields, answers)
            assert message is not None
            assert expected in message


def test_verify_never_raises_on_bad_input():
    exact = _exact_ai_fields(_answers())
    without_pss_1 = {k: v for k, v in _answers().items() if k != "pss_1"}
    assert SCORER.verify(None, _answers())
    assert SCORER.verify(exact, None)
    assert "pss_1" in SCORER.verify(exact, without_pss_1)
    assert "pss_1" in SCORER.verify(exact, _answers(pss_1=2.5))
    assert "pss_1" in SCORER.verify(exact, _answers(pss_1="three"))
    assert "stress_score" in SCORER.verify(
        dict(exact, stress_score="high"), _answers())


def test_scoring_instructions_state_the_rules():
    text = SCORER.instructions()
    for expected in ("pss_2, pss_3, mspss_friends, mspss_family are "
                     "positively worded",
                     "6 - answer", "8 or more hours -> 1", "5 or more -> 4",
                     "otherwise 5", "mean of those 11 converted values",
                     "rounded to 2 decimal places",
                     'below 2.5: risk_category Low, soft_label '
                     '"You\'re doing ok"',
                     "2.5 to 3.5 inclusive: risk_category Moderate",
                     'above 3.5: risk_category High, soft_label '
                     '"Please reach out"'):
        with case(expected=expected):
            assert expected in text


def test_pipeline_retries_and_rejects_wrong_arithmetic():
    """The pipeline hands StressScorer to AIManager as its auditor.

    A reply with one wrong scored item is never accepted: every model in
    the chain is tried, up to the call cap, then the check-in fails.
    """
    good = json.loads(_fake_generate_fn()("x " + json.dumps(_answers()), ""))
    wrong = dict(good, scored_items=dict(good["scored_items"], pss_1=4))
    provider = FakeProvider(json.dumps(wrong))
    record = {"student_id": "2605581", "survey_version": "evidence-v3",
              "safety_flag": False, **_answers()}
    result = _app(provider, max_attempts=3).process_checkin(record)
    assert not result.ok
    assert result.failure.code == "invalid_response"
    assert len(provider.calls) == AIManager.MAX_TOTAL_CALLS

    capture = FakeProvider(json.dumps(good))
    assert _app(capture).process_checkin(dict(record)).ok
    assert SCORER.instructions() in capture.calls[0][0]


def test_risk_score_and_recommended_support_come_from_logic():
    result = LOGIC.evaluate(_enriched())
    assert result["ok"]
    assert result["risk_score"] == 0.5
    assert result["recommended_support"] == (
        LogicManager.RECOMMENDED_SUPPORT["Moderate"])

    record = _enriched()
    record["safety_flag"] = True
    forced = LOGIC.evaluate(record)
    assert forced["risk_category"] == "High"
    assert forced["recommended_support"] == (
        LogicManager.RECOMMENDED_SUPPORT["High"])

    # The data layer still accepts the finished record.
    with tempfile.TemporaryDirectory() as temp_dir:
        data = DataManager(JSONStorage(Path(temp_dir) / "records.json"))
        saved = data.save(CheckInRecord(result), opt_in=True)
        assert saved.ok, saved.error


# --- Support priority (multi-condition rule on two AI fields) -------------

_HIGH_STRESS = dict(pss_1=5, pss_2=1, pss_3=1, pss_4=5, sleep_hours_avg=4.5,
                    sleep_quality=5, pas_workload=5, pas_catchup=5,
                    fin_stress=5, mspss_friends=1, mspss_family=1)


def test_high_tier_with_low_support_puts_talking_first():
    record = _enriched(_answers(**_HIGH_STRESS),
                       primary_stressors=["low_social_support",
                                          "academic_overload"])
    result = LOGIC.evaluate(record)
    assert result["ok"]
    assert result["risk_category"] == "High"
    assert result["support_priority"] is True
    assert result["tips"][0] == "talk_to_someone"
    assert "keep_social_contact" in result["tips"]
    for tip in record["tips"]:  # Gemini's own tips are kept
        assert tip in result["tips"]
    assert len(result["tips"]) <= 4
    assert ("support_priority: High tier with low social support"
            in result["logic_clamp_notes"])


def test_support_priority_does_not_fire_on_one_field_alone():
    high_no_support = LOGIC.evaluate(_enriched(
        _answers(**_HIGH_STRESS), primary_stressors=["academic_overload"]))
    assert high_no_support["risk_category"] == "High"
    assert high_no_support["support_priority"] is False
    assert high_no_support["tips"][0] != "talk_to_someone"

    moderate_low_support = LOGIC.evaluate(
        _enriched(_answers(), primary_stressors=["low_social_support"]))
    assert moderate_low_support["risk_category"] == "Moderate"
    assert moderate_low_support["support_priority"] is False
    assert moderate_low_support["logic_clamp_notes"] == []


def test_support_priority_and_safety_together_do_not_repeat_tips():
    record = _enriched(_answers(**_HIGH_STRESS),
                       primary_stressors=["low_social_support"])
    record["safety_flag"] = True
    result = LOGIC.evaluate(record)
    assert result["tips"][0] == "talk_to_someone"
    assert len(result["tips"]) == len(set(result["tips"]))
    assert result["support_priority"] is True


# --- Required functions: evaluate, score, route ---------------------------

def test_score_and_route_follow_evaluate():
    record = _enriched()
    decision = LOGIC.evaluate(record)
    assert LOGIC.score(record) == record["stress_score"]
    assert LOGIC.route(decision) == "Moderate"
    mismatched = dict(record, stress_score=4.5)
    assert LOGIC.score(mismatched) is None
    assert LOGIC.route(LOGIC.evaluate(mismatched)) == "unavailable"
    assert LOGIC.route(dict(decision, soft_label="Please reach out")) == (
        "unavailable")


def load_tests(loader, tests, pattern):
    """Let `python -m unittest discover -s tests` run this file's tests."""
    return function_suite(globals())


if __name__ == "__main__":
    unittest.main()

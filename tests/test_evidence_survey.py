"""Boundary, direction, privacy and integration tests for the survey."""
import json
import unittest

import survey
from ai.fake_provider import FakeProvider
from ai_manager import AIManager
from helpers import (campus, fake_generate, login_admin, post_checkin,
                     static_text, stored_rows)
from io_manager import IOManager
from logic_manager import LogicManager
from plain_tests import function_suite
from records.pending_record import PendingRecord

Q = survey.QUESTIONNAIRE
AI = AIManager(FakeProvider(), Q.questions)
LOGIC = LogicManager()
IO = IOManager(Q)
SCORER = LOGIC.scorer

MAX_STRESS = dict(pss_1=5, pss_2=1, pss_3=1, pss_4=5, sleep_hours_avg=4,
                  sleep_quality=5, pas_workload=5, pas_catchup=5,
                  fin_stress=5, mspss_friends=1, mspss_family=1)


def raw(**changes):
    """The lowest-stress answers, plus any changes."""
    values = dict(student_id="2605581", pss_1=1, pss_2=5, pss_3=5, pss_4=1,
                  sleep_hours_avg=8, sleep_quality=1, pas_workload=1,
                  pas_catchup=1, fin_stress=1, mspss_friends=5,
                  mspss_family=5)
    values.update(changes)
    return values


def record(**changes):
    ok, result = IO.validate_student_form(raw(**changes))
    assert ok, result
    return result


def with_score(**changes):
    """An I/O record plus Logic's deterministic score of its answers."""
    checked = record(**changes)
    card = SCORER.score(checked)
    return {**checked, "stress_score": card.stress_score,
            "risk_category": card.risk_category,
            "soft_label": SCORER.label_for(card.risk_category),
            "scored_item_count": card.item_count,
            "support_mean": card.support_mean,
            "context_flags": card.context_flags}


def finalised(**changes):
    """An I/O record run through a matching fake Gemini reply, then Logic."""
    checked = record(**changes)
    fields = AI.validate_response(fake_generate(json.dumps(checked), ""))[1]
    return LOGIC.evaluate({**checked, **fields})


def factor_cards(checked):
    return IO.display_result(PendingRecord(checked))["insights"]["factors"]


# --- Scoring ---------------------------------------------------------------

def test_reverse_coding_extremes():
    assert with_score()["stress_score"] == 1.0
    assert with_score(**MAX_STRESS)["stress_score"] == 5.0
    assert with_score(pss_2=1)["stress_score"] == round(15 / 11, 2)
    assert with_score(pss_1=5)["stress_score"] == round(15 / 11, 2)
    assert Q.reversed_keys == ("pss_2", "pss_3", "mspss_friends",
                               "mspss_family")


def test_average_and_band_boundaries():
    # 11 integer scores cannot land on 2.5 or 3.5 exactly.
    low = dict(pss_1=5, pss_4=5, sleep_hours_avg=4.5, sleep_quality=5)
    moderate = dict(low, pas_workload=2)  # sum 28
    low_result = with_score(**low)
    assert (low_result["stress_score"], low_result["risk_category"]) == (
        round(27 / 11, 2), "Low")
    crossed = with_score(**moderate)
    assert (crossed["stress_score"], crossed["risk_category"]) == (
        round(28 / 11, 2), "Moderate")
    assert crossed["soft_label"] == "Worth a check-in"
    high = dict(pss_1=5, pss_4=5, sleep_hours_avg=4.5, sleep_quality=5,
                pas_workload=5, pas_catchup=5)
    for fin, total, band in [(4, 38, "Moderate"), (5, 39, "High")]:
        scored = with_score(**high, fin_stress=fin)
        assert (scored["stress_score"], scored["risk_category"]) == (
            round(total / 11, 2), band)
        assert scored["soft_label"] == {"Moderate": "Worth a check-in",
                                        "High": "Please reach out"}[band]
    assert with_score()["soft_label"] == "You're doing ok"


def test_every_single_answer_on_every_question():
    for question in Q.questions:
        if question.key == "sleep_hours_avg":
            continue
        for value in range(1, 6):
            scored = with_score(**{question.key: value})
            item = 6 - value if question.reverse else value
            assert scored["stress_score"] == round((10 + item) / 11, 2), (
                question.key)
            assert scored["scored_item_count"] == 11


def test_sleep_hours_stay_hours_and_score_as_stress():
    bands = [(14, 1), (8.5, 1), (8, 1), (7.5, 2), (7, 2), (6.5, 3), (6, 3),
             (5.5, 4), (5, 4), (4.5, 5), (0, 5)]
    for hours, item in bands:
        scored = with_score(sleep_hours_avg=hours)
        assert scored["sleep_hours_avg"] == hours
        assert scored["stress_score"] == round((10 + item) / 11, 2), hours
    assert not IO.validate_student_form(raw(sleep_hours_avg=6.75))[0]
    sleep = Q.question("sleep_hours_avg")
    assert (sleep.kind, sleep.minimum, sleep.maximum, sleep.step) == (
        "slider", 0, 14, 0.5)
    fin = Q.question("fin_stress")
    assert (fin.kind, fin.minimum, fin.maximum, fin.step, fin.low,
            fin.high) == ("slider", 1, 5, 1, "No stress at all",
                          "Overwhelming stress")
    assert sleep.prompt == ("On average, how many hours of sleep have you "
                            "gotten each night this week?")
    js = static_text("campus.js")
    for gone in ("sleep_exact", "Or enter hours directly",
                 "Use half-hour steps", "Skip / clear this answer",
                 "ds-optional", "data-confirm", "Answer selected",
                 "Move the slider or confirm the displayed position.",
                 "Your student ID stays private.", "stressBadge",
                 "not sent to the AI provider", "Not sent to Gemini",
                 "project guidance", "project heuristics",
                 "documented project rules",
                 "not a validated combined screening instrument",
                 "Legacy /10", "Risk category", "AI Status"):
        assert gone not in js, gone
    for kept in ("ds-q-title", "Higher numbers mean more financial stress.",
                 "Only SIT wellbeing staff can see your ID, and it's never "
                 "sent to the AI.", "This space is just for you.",
                 "This check-in isn't a diagnosis", ">Your check-in<",
                 "Stress score (/5)", "You're doing ok",
                 "SIT Counselling 24-hour helpline", 'href="tel:65922030"',
                 'href="tel:1767"', 'href="tel:1771"'):
        assert kept in js, kept


def test_prompts_and_pss_sentences():
    prompts = {
        "pss_1": ("In the past month, how often have you felt you couldn't "
                  "control the important things in your life?"),
        "pss_2": ("In the past month, how often have you felt confident "
                  "handling your personal problems?"),
        "pss_3": ("In the past month, how often have you felt things were "
                  "going well for you?"),
        "pss_4": ("In the past month, how often have you felt problems were "
                  "piling up too much to handle?"),
    }
    assert Q.question("pss_1").label == "Losing control"
    assert Q.sections[0].heading == "Start with the bigger picture."
    assert all("source" not in section.as_dict() for section in Q.sections)
    assert all("card" not in item.as_dict() for item in Q.questions)
    page = static_text("campus.js")
    assert "Backed by research" in page
    for gone in ("ds-source", "cardText", "team wording"):
        assert gone not in page
    for key, prompt in prompts.items():
        assert Q.question(key).prompt == prompt
    assert Q.question("pas_workload").prompt == (
        "I feel my coursework is too much to handle.")
    assert Q.question("pas_catchup").prompt == (
        "When I fall behind on my work, I find it hard to catch up.")
    assert Q.question("mspss_family").prompt == (
        "I get the emotional help and support I need from my family.")
    questions_with_mark = ("sleep_hours_avg", "sleep_quality", "fin_stress")
    for item in Q.questions:
        asks = item.key.startswith("pss_") or item.key in questions_with_mark
        assert item.prompt.endswith("?" if asks else "."), item.key


def test_one_based_labels():
    scored = with_score(sleep_hours_avg=7.5, sleep_quality=5, fin_stress=1)
    cards = factor_cards(scored)
    values = {card["title"]: card["value"] for card in cards}
    assert values["Rest & recovery"] == "7.5 hours · Very bad quality"
    assert values["Money pressures"] == "1/5 · No stress at all"
    texts = {card["title"]: card["text"] for card in cards}
    assert texts["Rest & recovery"] == (
        "Sleep and stress affect each other. When sleep is short or "
        "restless, everyday tasks can feel harder, and stress can make it "
        "harder to sleep well.")
    assert texts["Study demands"] == (
        "A heavy workload can leave less time to rest and recharge. Feeling "
        "behind or overloaded is one of the most common sources of student "
        "stress.")
    assert texts["Money pressures"] == (
        "Financial worries can add to the pressure of studying. Concerns "
        "about money often weigh on focus and sleep.")
    assert texts["Support & connection"] == (
        "Having people to turn to can make stressful times easier to "
        "handle. Strong support from friends or family helps protect "
        "against stress.")
    flagged = {card["title"]: card["flagged"] for card in cards}
    assert flagged["Rest & recovery"]
    assert not flagged["Money pressures"]
    shown = {field["key"]: field["value"]
             for field in IO.display_record(PendingRecord(scored))["fields"]}
    assert shown["sleep_hours_avg"] == "7.5"
    assert shown["sleep_quality"] == "5 · Very bad"
    assert shown["fin_stress"] == "1 · No stress at all"
    assert shown["pss_1"] == "1 · Never"


def test_sleep_boundary_and_quality():
    assert not with_score(sleep_hours_avg=6, sleep_quality=3)[
        "context_flags"]["sleep"]
    assert with_score(sleep_hours_avg=5.5)["context_flags"]["sleep"]
    assert with_score(sleep_quality=4)["context_flags"]["sleep"]


def test_finance_direction_and_flags_only_steer_tips():
    assert not with_score(fin_stress=3)["context_flags"]["finances"]
    assert with_score(fin_stress=4)["context_flags"]["finances"]
    scored = with_score(fin_stress=5, pas_workload=5)  # 19/11 stays Low
    assert scored["risk_category"] == "Low"
    assert scored["context_flags"]["finances"]
    assert scored["context_flags"]["workload"]


def test_support_mean_and_required_fields():
    scored = with_score(mspss_friends=1, mspss_family=3)
    assert scored["support_mean"] == 2
    assert scored["scored_item_count"] == 11
    assert scored["context_flags"]["support"]
    assert not with_score(mspss_friends=3, mspss_family=2)[
        "context_flags"]["support"]
    assert not with_score(pas_catchup=5)["context_flags"]["workload"]
    assert "mspss_so" not in Q.keys
    assert len(Q.questions) == 11
    for key in ("pas_catchup", "mspss_friends", "mspss_family"):
        values = raw()
        values.pop(key)
        assert key in IO.validate_student_form(values)[1]


def test_required_and_invalid_answers():
    for question in Q.questions:
        for bad in (True, False, [], {}, float("nan"), float("inf"),
                    question.minimum - 1, question.maximum + 1, 1.25):
            assert question.key in IO.validate_student_form(
                raw(**{question.key: bad}))[1]
        values = raw()
        values.pop(question.key, None)
        assert not IO.validate_student_form(values)[0], question.key


def test_reflection_not_scored_or_sent():
    note = "PRIVATE REFLECTION: I feel sad and depressed"
    checked = record(feelings_text=note)
    assert finalised(feelings_text=note)["risk_category"] == "Low"
    assert "feelings_text" not in checked
    prompt = AI.build_prompt(checked)
    assert "PRIVATE REFLECTION" not in prompt
    assert "2605581" not in prompt
    for key in Q.keys:
        assert key in prompt
    assert Q.question("pss_1").prompt in prompt
    assert "mspss_so" not in prompt
    assert "special person" not in prompt.lower()


def test_safety_override_keeps_pss_unchanged():
    for text in ("I want to kill myself", "I feel suicidal", "I want to die",
                 "I might self-harm", "I can’t keep myself safe"):
        result = finalised(feelings_text=text)
        assert result["safety_flag"], text
        assert result["risk_category"] == "High"
        assert result["stress_score"] == 1.0


def test_no_client_score_or_flag_trusted():
    checked = record(stress_score=5, survey_version="fake",
                     safety_flag=True, risk_category="High")
    assert "stress_score" not in checked
    assert "risk_category" not in checked
    assert not checked["safety_flag"]
    assert checked["survey_version"] == survey.VERSION


def test_ai_score_far_from_answers_is_rejected():
    fields = json.loads(fake_generate(None, None))
    fields.update(stress_score=4.5, risk_score=0.875, risk_category="High",
                  soft_label="Please reach out", speak_prominence="high")
    result = LOGIC.evaluate({**record(), **fields})
    assert not result["ok"]
    assert result["error"] == "score_mismatch"
    assert result["logic_stress_score"] == 1.0


def test_ai_score_matching_answers_is_kept():
    result = finalised()
    assert result["ok"]
    assert (result["stress_score"], result["risk_category"]) == (1.0, "Low")
    assert len(factor_cards(result)) == 4


def test_nonfinite_ai_numbers_rejected():
    for field in ("stress_score", "confidence"):
        values = json.loads(fake_generate(None, None))
        values[field] = float("nan")
        assert not AI.validate_response(values)[0]


# --- Revised Pipeline ------------------------------------------------------

def test_new_record_storage_and_history():
    with campus() as ctx:
        ctx.values.update(feelings_text="SENSITIVE NOTE not to be kept",
                          pas_catchup=4, mspss_so=5)
        assert post_checkin(ctx).status_code == 200
        assert post_checkin(ctx, {"opt_in": True}, "/save").status_code == 200
        stored = stored_rows(ctx)[0]
        assert "feelings_text" not in stored
        assert "SENSITIVE NOTE" not in ctx.path.read_text(encoding="utf-8")
        assert "mspss_so" not in stored
        assert stored["sleep_hours_avg"] == 6.5  # hours, not a 1-5 band
        assert stored["pas_catchup"] == 4
        assert stored["stress_score"] == round(34 / 11, 2)
        assert ctx.client.get("/api/records").status_code == 401
        login_admin(ctx.client)
        row = ctx.client.get("/api/records").json["records"][0]
        assert row["survey_version"] == survey.VERSION
        assert row["fin_stress"] == 3
        assert "mspss_so" not in row
        assert "stress_level" not in row
        assert row["status"] == "Evaluated"


def test_safety_remains_visible_when_ai_fails():
    with campus(FakeProvider("{}")) as ctx:
        ctx.values["feelings_text"] = "I want to end my life"
        response = post_checkin(ctx)
        assert response.status_code == 503
        assert response.json["safety_flag"]
        assert "advisor" in response.json
        assert ctx.app.web.results.count == 0


def test_safety_even_with_invalid_answers():
    with campus() as ctx:
        response = post_checkin(ctx, {**ctx.values, "pss_1": None,
                                      "feelings_text": "I want to die"})
        assert response.status_code == 400
        assert response.json["safety_flag"]


def test_old_questionnaire_cannot_be_submitted_as_new():
    with campus() as ctx:
        response = post_checkin(ctx, dict(
            student_id="2605581", sleep_hours=7, stress_level=5,
            academic_workload=5, financial_stress=5, social_support=5))
        assert response.status_code == 400
        assert "pss_1" in response.json["errors"]


def load_tests(loader, tests, pattern):
    """Let `python -m unittest discover -s tests` run this file's tests."""
    return function_suite(globals())


if __name__ == "__main__":
    unittest.main()

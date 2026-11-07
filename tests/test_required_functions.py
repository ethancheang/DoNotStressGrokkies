"""The brief's required functions, now methods of the four managers.

ai_manager    AIManager.build_prompt, call_api, parse_response,
              validate_response
logic_manager LogicManager.evaluate, score, route
data_manager  DataManager.save, load, query
io_manager    IOManager.display_record, display_list, display_result

No real Gemini call.
"""
import json
import tempfile
import unittest
from pathlib import Path

import survey
from ai.ai_failure import AIFailure
from ai.fake_provider import FakeProvider
from ai_manager import AIManager
from data_manager import DataManager
from io_manager import IOManager
from logic.stress_scorer import StressScorer
from logic_manager import LogicManager
from plain_tests import function_suite
from records.check_in_record import CheckInRecord
from records.pending_record import PendingRecord
from storage.json_storage import JSONStorage
from storage.storage_error import StorageError

LOGIC = LogicManager()
SCORER = LOGIC.scorer
IO = IOManager(survey.QUESTIONNAIRE)


def _answers():
    """All-3 answers with 6.5 h sleep: average 3.0 (Moderate)."""
    answers = {key: 3 for key in StressScorer.ANSWER_KEYS}
    answers["sleep_hours_avg"] = 6.5
    return answers


def _fake_generate(prompt, model_name):
    """Fake Gemini: replays the formula on the prompt's answers."""
    answers = json.loads(prompt[prompt.rfind("{"):])
    stress = SCORER.score(answers).stress_score
    category = SCORER.category_for(stress)
    return json.dumps({
        "scored_items": SCORER.scored_items(answers),
        "stress_score": stress,
        "risk_category": category,
        "primary_stressors": ["academic_overload"],
        "confidence": 0.8,
        "reasoning": "A short, warm note.",
        "soft_label": SCORER.label_for(category),
        "tips": ["short_breaks"],
        "speak_prominence": SCORER.prominence_for(category),
    })


def _ai(*replies):
    return AIManager(FakeProvider(*replies), survey.QUESTIONNAIRE.questions,
                     SCORER, max_attempts=1, retry_delay_sec=0)


def _enriched():
    record = {"student_id": "2605581", "survey_version": "evidence-v3",
              "safety_flag": False, **_answers()}
    result = _ai(_fake_generate).analyse(record)
    assert result.ok, result.failure
    return result.fields


def test_call_api_and_validate_with_a_fake_provider():
    ai = _ai(_fake_generate)
    prompt = ai.build_prompt(_answers())
    result = ai.call_api(prompt)
    assert result.ok and result.failure is None
    assert result.fields["stress_score"] == 3.0
    ok, data = ai.validate_response(_fake_generate(prompt, ""))
    assert ok and data["risk_category"] == "Moderate"


def test_call_api_timeout_does_not_crash():
    result = _ai(TimeoutError("deadline exceeded")).call_api("prompt")
    assert not result.ok and result.fields is None
    assert result.failure.code in AIFailure.CODES


def test_parse_response_handles_bad_formats():
    ai = _ai("{}")
    assert ai.parse_response('```json\n{"a": 1}\n```') == {"a": 1}
    assert ai.parse_response("not json") is None
    assert ai.parse_response("{broken") is None
    assert ai.parse_response(None) is None


def test_validate_response_rejects_malformed():
    ai = _ai("{}")
    assert ai.validate_response({})[0] is False
    assert ai.validate_response("[]")[0] is False


def test_evaluate_score_route():
    record = _enriched()
    decision = LOGIC.evaluate(record)
    assert decision["ok"] is True
    assert LOGIC.score(record) == record["stress_score"]
    assert LOGIC.route(decision) == "Moderate"


def test_score_rejects_mismatched_ai_score():
    record = dict(_enriched(), stress_score=4.5)
    assert LOGIC.score(record) is None
    assert LOGIC.route(LOGIC.evaluate(record)) == "unavailable"


def test_save_load_query_and_missing_or_corrupt_file():
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "records.json"
        data = DataManager(JSONStorage(path))
        assert data.load() == []
        evaluated = CheckInRecord(LOGIC.evaluate(_enriched()))
        assert data.save(evaluated, opt_in=True).ok is True
        assert len(data.load()) == 1
        moderate = data.query(
            lambda record: record.get("risk_category") == "Moderate")
        assert len(moderate) == 1
        assert data.query(lambda record: False) == []
        path.write_text("{not json", encoding="utf-8")
        try:
            data.load()
        except StorageError as error:
            assert "Corrupted" in str(error)
        else:
            raise AssertionError("a corrupt file must not look empty")


def test_display_functions_return_page_data():
    finished = CheckInRecord(LOGIC.evaluate(_enriched()))
    shown = IO.display_record(PendingRecord(_answers()))
    assert shown["fields"][0]["value"] == "3 · Sometimes"
    assert IO.display_list([]) == []
    assert IO.display_list([finished])[0]["status"] == "Evaluated"
    result = IO.display_result(finished)
    assert result["soft"]["heading"] == "Worth a check-in"
    assert result["tips"]["items"][0]["id"] == "short_breaks"
    assert IO.display_error("timeout")["error_code"] == "timeout"


def load_tests(loader, tests, pattern):
    """Let `python -m unittest discover -s tests` run this file's tests."""
    return function_suite(globals())


if __name__ == "__main__":
    unittest.main()

"""Same input, same output across separate runs (brief constraint C4).

Uses the fake Gemini from helpers, so these tests never call the API. The
score, tier, label, tips and flags come from fixed rules, so they must be
identical every run. Real Gemini is asked at temperature 0 so its wording
repeats as closely as the service allows.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import survey
from ai.fake_provider import FakeProvider
from ai.gemini_provider import GeminiProvider
from ai_manager import AIManager
from data_manager import DataManager
from helpers import fake_generate
from logic.stress_scorer import StressScorer
from main import App
from plain_tests import function_suite
from records.check_in_record import CheckInRecord
from storage.json_storage import JSONStorage

ROOT = Path(__file__).resolve().parents[1]

ANSWERS = dict(
    student_id="2605581", survey_version="evidence-v3", safety_flag=False,
    pss_1=4, pss_2=2, pss_3=4, pss_4=3, sleep_hours_avg=5.5,
    sleep_quality=4, pas_workload=4, pas_catchup=3, fin_stress=4,
    mspss_friends=2, mspss_family=3,
)

# Runs one check-in in a fresh Python process and prints it as JSON.
ONE_RUN = """
import json, sys, tempfile
from pathlib import Path
sys.path[:0] = [{root!r}, {tests!r}]
from ai.fake_provider import FakeProvider
from helpers import fake_generate
from main import App
app = App(provider=FakeProvider(fake_generate),
          data_path=Path(tempfile.mkdtemp()) / "records.json",
          ai_max_attempts=1, ai_retry_delay_sec=0)
result = app.process_checkin(json.loads({answers!r}))
sys.stdout.write(json.dumps([result.ok, result.fields], sort_keys=True))
"""


def _check_in():
    """Run the full AI -> Logic pipeline once with the fake Gemini."""
    app = App(provider=FakeProvider(fake_generate),
              data_path=Path(tempfile.mkdtemp()) / "records.json",
              ai_max_attempts=1, ai_retry_delay_sec=0)
    result = app.process_checkin(dict(ANSWERS))
    assert result.ok, result.failure
    return result.fields


def test_same_answers_give_the_same_outcome_every_run():
    first = json.dumps(_check_in(), sort_keys=True)
    for _ in range(3):
        assert json.dumps(_check_in(), sort_keys=True) == first


def test_separate_processes_give_the_same_outcome():
    """Two fresh Python processes, same answers: identical outcome."""
    code = ONE_RUN.format(root=str(ROOT), tests=str(ROOT / "tests"),
                          answers=json.dumps(ANSWERS))
    outputs = [
        subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                       capture_output=True, text=True, timeout=60,
                       check=True).stdout
        for _ in range(2)
    ]
    assert outputs[0] == outputs[1]
    ok, outcome = json.loads(outputs[0])
    assert ok
    assert outcome == json.loads(json.dumps(_check_in(), sort_keys=True))


def test_scoring_and_prompt_are_deterministic():
    scorer = StressScorer()
    first_score = scorer.score(ANSWERS).stress_score
    ai = AIManager(FakeProvider(), survey.QUESTIONNAIRE.questions, scorer)
    first_prompt = ai.build_prompt(ANSWERS)
    assert scorer.instructions() in first_prompt
    for _ in range(5):
        assert scorer.score(ANSWERS).stress_score == first_score
        assert ai.build_prompt(ANSWERS) == first_prompt


def test_saved_records_load_the_same_every_time():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "records.json"
        data = DataManager(JSONStorage(path))
        assert data.save(CheckInRecord(_check_in()), opt_in=True).ok
        before = path.read_text(encoding="utf-8")
        first = [record.to_row() for record in data.load()]
        assert len(first) == 1
        assert [record.to_row() for record in data.load()] == first
        # Loading never rewrites the file.
        assert path.read_text(encoding="utf-8") == before


def test_gemini_is_asked_for_repeatable_replies():
    assert GeminiProvider.TEMPERATURE == 0.0


def load_tests(loader, tests, pattern):
    """Let `python -m unittest discover -s tests` run this file's tests."""
    return function_suite(globals())


if __name__ == "__main__":
    unittest.main()

"""DoNotStress entry point: campus UI → I/O → Gemini → Logic → records.

App builds and owns the four managers and the Flask app. The Flask routes
live in WebController and call into App for every check-in and page.

Run locally with `python main.py`, or `flask --app main:app run`.
"""

from __future__ import annotations

import logging
import os
import secrets
import threading
import uuid
from functools import partial
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from ai.ai_failure import AIFailure
from ai.ai_provider import AIProvider
from ai.ai_result import AIResult
from ai.gemini_provider import GeminiProvider
from ai_manager import AIManager
from base_manager import BaseManager
from checkins.background_jobs import BackgroundJobs
from checkins.check_in_job import CheckInJob
from checkins.check_in_outcome import CheckInOutcome
from checkins.submission_context import SubmissionContext
from checkins.submission_tracker import SubmissionTracker
from data_manager import DataManager
from io_manager import IOManager
from json_types import JSONObject
from logic_manager import LogicManager
from records.check_in_record import CheckInRecord
from records.pending_record import PendingRecord
from storage.json_storage import JSONStorage
from survey import QUESTIONNAIRE
from web.web_controller import WebController

load_dotenv()


class App:
    """The composition root: creates, owns and connects the four managers.

    IOManager, AIManager, LogicManager and DataManager are created here
    and live exactly as long as the App (composition), as are the worker
    threads that run each check-in in the background. LogicManager's
    StressScorer is lent to AIManager as its ScoreAuditor. A provider can
    be passed in (tests pass a FakeProvider); otherwise App creates the
    live GeminiProvider.
    """

    ROOT: Path = Path(__file__).resolve().parent
    DEFAULT_DATA_PATH: Path = ROOT / "data" / "student_records.json"
    MAX_CONTENT_LENGTH: int = 64 * 1024

    def __init__(self, provider: AIProvider | None = None,
                 data_path: Path | None = None,
                 secret_key: str | None = None, testing: bool = False,
                 ai_max_attempts: int = 3,
                 ai_retry_delay_sec: float = 0.5) -> None:
        self.__logger: logging.Logger = logging.getLogger("main")
        self.__flask: Flask = Flask(__name__, root_path=str(self.ROOT))
        self.__flask.config.update(
            SECRET_KEY=(secret_key or os.environ.get("FLASK_SECRET_KEY")
                        or secrets.token_hex(32)),
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE="Lax",
            MAX_CONTENT_LENGTH=self.MAX_CONTENT_LENGTH,
            TESTING=testing,
        )
        self.__io: IOManager = IOManager(QUESTIONNAIRE)
        self.__logic: LogicManager = LogicManager()
        self.__ai: AIManager = AIManager(
            provider if provider is not None else GeminiProvider(),
            QUESTIONNAIRE.questions, self.__logic.scorer,
            max_attempts=ai_max_attempts,
            retry_delay_sec=ai_retry_delay_sec)
        self.__data: DataManager = DataManager(
            JSONStorage(data_path or self.__configured_data_path()))
        self.__submissions: SubmissionTracker = SubmissionTracker(
            QUESTIONNAIRE.keys)
        self.__save_lock: threading.Lock = threading.Lock()
        self.__jobs: BackgroundJobs = BackgroundJobs()
        self.__web: WebController = WebController(self, self.__flask)

    @property
    def flask(self) -> Flask:
        return self.__flask

    @property
    def io(self) -> IOManager:
        return self.__io

    @property
    def ai(self) -> AIManager:
        return self.__ai

    @property
    def logic(self) -> LogicManager:
        return self.__logic

    @property
    def data(self) -> DataManager:
        return self.__data

    @property
    def web(self) -> WebController:
        return self.__web

    @property
    def jobs(self) -> BackgroundJobs:
        return self.__jobs

    @property
    def managers(self) -> list[BaseManager]:
        return [self.__io, self.__ai, self.__logic, self.__data]

    def health(self) -> JSONObject:
        """Every manager's health summary. Never includes secrets."""
        return {"status": "ok",
                "managers": [manager.health() for manager in self.managers]}

    def process_checkin(self, record: JSONObject) -> AIResult:
        """Gemini's analysis, then Logic's rules. AI must succeed first.

        A Logic rejection (such as a score mismatch) is reported as an
        "unavailable" failure, exactly like an AI failure.
        """
        analysis = self.__ai.analyse(record)
        if analysis.fields is None:
            code = analysis.failure.code if analysis.failure else "none"
            self.__logger.warning("Check-in could not complete: %s", code)
            return analysis
        evaluated = self.__logic.evaluate(analysis.fields)
        if not evaluated.get("ok"):
            detail = f"Logic rejected the analysis: {evaluated.get('error')}"
            self.__logger.warning(detail)
            return AIResult(failure=AIFailure(AIFailure.UNAVAILABLE, detail))
        return AIResult(fields=evaluated)

    def submit_checkin(self, record: JSONObject, context: SubmissionContext,
                       safety_flag: bool) -> CheckInJob:
        """Start run_checkin on a worker thread and return at once.

        The Gemini call can take many seconds (up to four calls), so the
        request that submitted the check-in never waits for it.
        """
        fingerprint = self.__submissions.fingerprint(record)
        return self.__jobs.submit(context.owner, fingerprint, safety_flag,
                                  partial(self.run_checkin, record, context))

    def run_checkin(self, record: JSONObject,
                    context: SubmissionContext) -> CheckInOutcome:
        """Analyse a validated check-in and save it exactly once.

        A failed analysis keeps the answers as one pending row per
        submission; a later success upgrades that same row in place.
        """
        fingerprint = self.__submissions.fingerprint(record)
        student_id = str(record.get("student_id") or "")
        try:
            analysis = self.process_checkin(record)
        except Exception as error:  # the student must never see a crash
            self.__logger.warning("Check-in pipeline failed: %s",
                                  type(error).__name__)
            analysis = AIResult(failure=AIFailure(AIFailure.UNAVAILABLE))
        with self.__save_lock:
            pending_id = self.__submissions.match(fingerprint, context)
            if analysis.fields is None:
                record_id = pending_id or self.__save_pending(record)
                if record_id:
                    self.__submissions.remember(context.owner, fingerprint,
                                                record_id)
                code = (analysis.failure.code if analysis.failure
                        else AIFailure.UNAVAILABLE)
                return CheckInOutcome(CheckInOutcome.PENDING, student_id,
                                      fingerprint, record_id, code)
            finished = CheckInRecord(analysis.fields)
            if pending_id:
                saved = self.__data.replace_pending_record(
                    pending_id, finished, opt_in=True)
            else:
                saved = self.__data.save(finished, opt_in=True)
            if not saved.ok:
                return CheckInOutcome(CheckInOutcome.SAVE_FAILED,
                                      student_id, fingerprint)
            self.__submissions.remember(context.owner, fingerprint,
                                        saved.record_id)
            return CheckInOutcome(CheckInOutcome.DONE, student_id,
                                  fingerprint, saved.record_id,
                                  result=analysis.fields)

    def forget_submission(self, owner: str) -> None:
        self.__submissions.forget(owner)

    def close(self) -> None:
        """Finish any running check-ins and stop the worker threads."""
        self.__jobs.shutdown()

    def admin_records(self, tier: str, cohort_year: str,
                      id_contains: str) -> JSONObject:
        """The admin table: current-questionnaire records, filtered.

        Raises StorageError when the records cannot be loaded.
        """
        records = [record for record in self.__data.load()
                   if record.survey_version == QUESTIONNAIRE.version]
        matching = self.__data.filter_records(records, tier, cohort_year,
                                              id_contains)
        rows = self.__io.display_list(matching)
        return {"records": rows, "total": len(records),
                "matching": len(rows),
                "cohorts": list(self.__data.cohorts(records))}

    def student_history(self, student_id: str) -> JSONObject:
        """One student's own history page. Nobody else's rows are read.

        Raises StorageError when the records cannot be loaded.
        """
        history = self.__data.history_for(student_id, QUESTIONNAIRE.version)
        return self.__io.display_history(history,
                                         self.__logic.trend(history))

    def __save_pending(self, record: JSONObject) -> str:
        """Keep the answers for follow-up; the id, or "" if not saved."""
        pending = PendingRecord({**record, "record_id": uuid.uuid4().hex})
        saved = self.__data.save(pending, opt_in=True)
        if not saved.ok:
            self.__logger.warning("Pending check-in could not be saved")
        return saved.record_id

    def __configured_data_path(self) -> Path:
        configured = os.environ.get("DONOTSTRESS_DATA_PATH", "").strip()
        return Path(configured) if configured else self.DEFAULT_DATA_PATH


app = App().flask

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")),
            debug=os.environ.get("FLASK_DEBUG", "0").lower()
            in {"1", "true", "yes"})

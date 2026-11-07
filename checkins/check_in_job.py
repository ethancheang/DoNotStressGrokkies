"""One check-in being analysed on a background thread."""

from __future__ import annotations

import secrets
import threading
import time

from checkins.check_in_outcome import CheckInOutcome


class CheckInJob:
    """Status of one background check-in, safe to read from any thread.

    QUEUED until a worker picks it up, RUNNING while Gemini, Logic and the
    save run, then DONE with an outcome, or FAILED if the work crashed.
    Only the session that submitted it may read it.
    """

    QUEUED: str = "queued"
    RUNNING: str = "running"
    DONE: str = "done"
    FAILED: str = "failed"

    def __init__(self, owner: str, key: str, safety_flag: bool) -> None:
        self.__id: str = secrets.token_urlsafe(16)
        self.__owner: str = owner
        self.__key: str = key
        self.__safety_flag: bool = safety_flag
        self.__created: float = time.monotonic()
        self.__status: str = self.QUEUED
        self.__outcome: CheckInOutcome | None = None
        self.__finished: threading.Event = threading.Event()

    @property
    def id(self) -> str:
        return self.__id

    @property
    def owner(self) -> str:
        return self.__owner

    @property
    def key(self) -> str:
        """The submission fingerprint, so a repeat can join this job."""
        return self.__key

    @property
    def safety_flag(self) -> bool:
        return self.__safety_flag

    @property
    def created(self) -> float:
        return self.__created

    @property
    def status(self) -> str:
        return self.__status

    @property
    def outcome(self) -> CheckInOutcome | None:
        """The pipeline outcome once DONE; None before then or if FAILED."""
        return self.__outcome

    @property
    def is_done(self) -> bool:
        return self.__finished.is_set()

    def start(self) -> None:
        self.__status = self.RUNNING

    def finish(self, outcome: CheckInOutcome) -> None:
        self.__outcome = outcome
        self.__status = self.DONE
        self.__finished.set()

    def fail(self) -> None:
        self.__status = self.FAILED
        self.__finished.set()

    def wait(self, timeout: float) -> bool:
        """Block until the job ends or timeout passes; True if it ended."""
        return self.__finished.wait(timeout)

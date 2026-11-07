"""Runs check-ins on worker threads so a request never waits for Gemini."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from checkins.check_in_job import CheckInJob
from checkins.check_in_outcome import CheckInOutcome


class BackgroundJobs:
    """A small pool of worker threads for the Gemini → Logic → save work.

    submit() returns at once with a CheckInJob the browser can poll. The
    same session sending the same answers again while a job runs gets
    that job back instead of a second Gemini call. Finished jobs are kept
    for ttl_seconds so a dropped poll can be repeated.
    """

    WORKERS: int = 4
    TTL_SECONDS: float = 1800

    def __init__(self, workers: int = WORKERS,
                 ttl_seconds: float = TTL_SECONDS) -> None:
        self.__executor: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="checkin")
        self.__jobs: dict[str, CheckInJob] = {}
        self.__lock: threading.Lock = threading.Lock()
        self.__ttl_seconds: float = ttl_seconds
        self.__logger: logging.Logger = logging.getLogger("main.jobs")

    @property
    def ttl_seconds(self) -> float:
        return self.__ttl_seconds

    @ttl_seconds.setter
    def ttl_seconds(self, value: float) -> None:
        self.__ttl_seconds = value

    @property
    def count(self) -> int:
        with self.__lock:
            return len(self.__jobs)

    def submit(self, owner: str, key: str, safety_flag: bool,
               task: Callable[[], CheckInOutcome]) -> CheckInJob:
        """Queue task on a worker thread; reuse a running identical job."""
        with self.__lock:
            for job in self.__jobs.values():
                if job.owner == owner and job.key == key and not job.is_done:
                    return job
            job = CheckInJob(owner, key, safety_flag)
            self.__jobs[job.id] = job
        self.__executor.submit(self.__run, job, task)
        return job

    def get(self, job_id: str, owner: str) -> CheckInJob | None:
        """The job, only for the session that submitted it."""
        with self.__lock:
            job = self.__jobs.get(job_id)
        if job is None or not owner or job.owner != owner:
            return None
        return job

    def wait(self, job_id: str, timeout: float) -> bool:
        """Block until a job ends; True if it ended within timeout."""
        with self.__lock:
            job = self.__jobs.get(job_id)
        return job is not None and job.wait(timeout)

    def expire(self) -> None:
        """Forget finished jobs older than ttl_seconds."""
        cutoff = time.monotonic() - self.__ttl_seconds
        with self.__lock:
            self.__jobs = {job_id: job for job_id, job in self.__jobs.items()
                           if not job.is_done or job.created > cutoff}

    def shutdown(self) -> None:
        """Let running jobs finish, then stop the worker threads."""
        self.__executor.shutdown(wait=True)

    def __run(self, job: CheckInJob,
              task: Callable[[], CheckInOutcome]) -> None:
        job.start()
        try:
            job.finish(task())
        except Exception as error:  # a crash must still end the job
            self.__logger.warning("Background check-in failed: %s",
                                  type(error).__name__)
            job.fail()

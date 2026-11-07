"""Check-in rows kept in one JSON file."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from json_types import JSONObject
from storage.storage_backend import StorageBackend
from storage.storage_error import StorageError


class JSONStorage(StorageBackend):
    """A JSON list of rows in one file.

    A missing or empty file means no rows. A corrupt file is copied to
    records.corrupt-<time>.json before anything can overwrite it. Writes
    go to a temp file in the same folder and then os.replace, so a crash
    never leaves a half-written file. One lock covers each read-modify-
    write, because background check-ins save from worker threads.
    """

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.__path: Path = path
        self.__lock: threading.RLock = threading.RLock()
        self.__logger: logging.Logger = logging.getLogger(
            "data_manager.storage")

    @property
    def location(self) -> str:
        return str(self.__path)

    def load(self) -> list[JSONObject]:
        with self.__lock:
            rows, problem = self.__read()
        if problem:
            raise StorageError(problem)
        return rows

    def append(self, row: JSONObject) -> None:
        with self.__lock:
            rows, _ = self.__read()
            rows.append(row)
            self.__write(rows)

    def replace(self, record_id: str, row: JSONObject) -> None:
        with self.__lock:
            rows, _ = self.__read()
            for index, existing in enumerate(rows):
                if str(existing.get("record_id") or "").strip() == record_id:
                    rows[index] = row
                    break
            else:
                rows.append(row)
            self.__write(rows)

    def __read(self) -> tuple[list[JSONObject], str | None]:
        """The rows, plus a note when a corrupt file had to be set aside.

        Raises StorageError when the file cannot be read, or is corrupt
        and cannot be backed up, so nothing ever overwrites it.
        """
        if not self.__path.exists():
            return [], None
        try:
            text = self.__path.read_text(encoding="utf-8")
        except OSError as error:
            raise StorageError(f"Could not read data file: {error}") from error
        if not text.strip():
            return [], None
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as error:
            return [], self.__back_up(f"Corrupted JSON in data file: {error}")
        if isinstance(payload, dict):
            payload = payload.get("records")
        if payload is None:
            return [], None
        if not isinstance(payload, list):
            return [], self.__back_up(
                "Corrupted data file: expected a list of records.")
        return [row for row in payload if isinstance(row, dict)], None

    def __back_up(self, problem: str) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = self.__path.with_name(
            f"{self.__path.stem}.corrupt-{stamp}.json")
        try:
            shutil.copy2(self.__path, backup)
        except OSError as error:
            self.__logger.warning("Corrupt data file %s could not be backed "
                                  "up: %s", self.__path, error)
            raise StorageError(f"{problem} Backup failed.") from error
        self.__logger.warning("Corrupt data file %s backed up to %s",
                              self.__path, backup)
        return problem

    def __write(self, rows: list[JSONObject]) -> None:
        text = json.dumps(rows, indent=2, ensure_ascii=False) + "\n"
        temporary: Path | None = None
        try:
            self.__path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                    "w", encoding="utf-8", dir=self.__path.parent,
                    prefix=f".{self.__path.name}.", suffix=".tmp",
                    delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.__path)
            temporary = None
        except OSError as error:
            message = f"Could not write data file: {error}"
            raise StorageError(message) from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

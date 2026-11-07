"""The contract for any place check-in rows can be kept."""

from __future__ import annotations

from abc import ABC, abstractmethod

from json_types import JSONObject


class StorageBackend(ABC):
    """Interface: load, append and replace check-in rows.

    DataManager depends only on this, so a new backend (a database, for
    example) is a new subclass and DataManager does not change.
    """

    @property
    @abstractmethod
    def location(self) -> str:
        """Where the rows live, for logs and health checks."""

    @abstractmethod
    def load(self) -> list[JSONObject]:
        """Every stored row; [] when nothing is stored yet.

        Raises StorageError when the rows cannot be read safely.
        """

    @abstractmethod
    def append(self, row: JSONObject) -> None:
        """Add one row. Raises StorageError when it cannot be written."""

    @abstractmethod
    def replace(self, record_id: str, row: JSONObject) -> None:
        """Replace the row with this record_id, or append when none has it.

        Raises StorageError when it cannot be written.
        """

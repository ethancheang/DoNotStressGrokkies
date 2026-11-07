"""DoNotStress — shared parent of the four managers.

AIManager, LogicManager, DataManager and IOManager each inherit a name, a
logger and a health summary from BaseManager. Their domain behaviour stays
in the subclasses; this class deliberately holds nothing else.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from json_types import JSONObject


class BaseManager(ABC):
    """Abstract parent: a name, its logger, and a secret-free summary."""

    def __init__(self, name: str) -> None:
        self.__name: str = name
        self.__logger: logging.Logger = logging.getLogger(name)

    @property
    def name(self) -> str:
        return self.__name

    @property
    def logger(self) -> logging.Logger:
        return self.__logger

    @abstractmethod
    def describe(self) -> JSONObject:
        """How this manager is set up. Never includes secrets."""

    def health(self) -> JSONObject:
        """The manager's name plus its describe() summary."""
        return {"name": self.__name, **self.describe()}

"""A scripted stand-in for Gemini, used only by the automated tests."""

from __future__ import annotations

import threading
from collections.abc import Callable

from ai.ai_provider import AIProvider
from ai.gemini_provider import GeminiProvider
from json_types import JSONObject

type FakeReply = str | Exception | Callable[[str, str], str]


class FakeProvider(AIProvider):
    """Replays scripted replies and never touches the network.

    A reply is raw text, an exception to raise, or a function of
    (prompt, model_name) that returns raw text. Replies are used in order
    and the last one repeats. The running app never selects this class.
    """

    def __init__(self, *replies: FakeReply,
                 models: tuple[str, ...] = GeminiProvider.MODEL_CHAIN,
                 ready: bool = True) -> None:
        super().__init__()
        self.__replies: list[FakeReply] = list(replies) or ["{}"]
        self.__models: tuple[str, ...] = models
        self.__ready: bool = ready
        self.__calls: list[tuple[str, str]] = []
        self.__lock: threading.Lock = threading.Lock()

    @property
    def name(self) -> str:
        return "fake"

    @property
    def models(self) -> tuple[str, ...]:
        return self.__models

    @property
    def calls(self) -> list[tuple[str, str]]:
        """(prompt, model_name) for every call so far."""
        with self.__lock:
            return list(self.__calls)

    @property
    def models_called(self) -> list[str]:
        return [model for _, model in self.calls]

    def is_ready(self) -> bool:
        return self.__ready

    def reply_with(self, *replies: FakeReply) -> None:
        """Replace the script, e.g. to make Gemini recover mid-test."""
        with self.__lock:
            self.__replies = list(replies) or ["{}"]

    def generate(self, prompt: str, model_name: str,
                 schema: JSONObject | None = None) -> str:
        with self.__lock:
            self.__calls.append((prompt, model_name))
            if len(self.__replies) > 1:
                reply = self.__replies.pop(0)
            else:
                reply = self.__replies[0]
        if isinstance(reply, Exception):
            raise reply
        if callable(reply):
            return reply(prompt, model_name)
        return reply

    def redact(self, text: str) -> str:
        return text

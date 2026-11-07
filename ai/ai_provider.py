"""The contract every AI provider honours."""

from __future__ import annotations

from abc import ABC, abstractmethod

from json_types import JSONObject


class AIProvider(ABC):
    """Interface: turn one prompt into one raw reply from one named model.

    AIManager owns retries, model fallback and validation, so they apply
    the same way to every provider. A provider only makes single calls.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short provider name for logs and health checks."""

    @property
    @abstractmethod
    def models(self) -> tuple[str, ...]:
        """Model names to try, preferred first."""

    @abstractmethod
    def is_ready(self) -> bool:
        """False when the provider cannot be called at all (no API key)."""

    @abstractmethod
    def generate(self, prompt: str, model_name: str,
                 schema: JSONObject | None = None) -> str:
        """The raw reply text. Raises on API, network or timeout failure."""

    @abstractmethod
    def redact(self, text: str) -> str:
        """Text with any credential this provider holds removed."""

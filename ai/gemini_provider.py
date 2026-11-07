"""The live Google Gemini provider."""

from __future__ import annotations

import os

from google import genai

from ai.ai_provider import AIProvider
from json_types import JSONObject


class GeminiProvider(AIProvider):
    """One structured-JSON Gemini call per generate().

    The API key stays in a private attribute and is never logged.
    """

    # Named models only, newest first. No moving alias such as -latest.
    MODEL_CHAIN: tuple[str, ...] = (
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
    )
    TEMPERATURE: float = 0.0  # most repeatable replies for the same answers
    TIMEOUT_SEC: float = 30.0

    def __init__(self, api_key: str | None = None,
                 preferred_model: str | None = None) -> None:
        super().__init__()
        if api_key is None:
            api_key = os.environ.get("GEMINI_API_KEY", "")
        self.__api_key: str = api_key.strip()
        self.__models: tuple[str, ...] = self.__model_order(preferred_model)

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def models(self) -> tuple[str, ...]:
        return self.__models

    def is_ready(self) -> bool:
        return bool(self.__api_key)

    def generate(self, prompt: str, model_name: str,
                 schema: JSONObject | None = None) -> str:
        # The SDK's own HTTP retries are off: AIManager's call cap is the
        # only retry policy, so a 429 never turns into a retry storm.
        client = genai.Client(
            api_key=self.__api_key,
            http_options={
                "timeout": int(self.TIMEOUT_SEC * 1000),
                "retry_options": {"attempts": 1},
            },
        )
        config: JSONObject = {
            "temperature": self.TEMPERATURE,
            "response_mime_type": "application/json",
            "automatic_function_calling": {"disable": True},
        }
        if schema is not None:
            config["response_schema"] = schema
        response = client.models.generate_content(
            model=model_name, contents=prompt, config=config)
        if not response.text:
            raise RuntimeError("Gemini returned no text payload.")
        return response.text

    def redact(self, text: str) -> str:
        if self.__api_key:
            return text.replace(self.__api_key, "[redacted]")
        return text

    def __model_order(self, preferred: str | None) -> tuple[str, ...]:
        """Preferred model first, then the fixed chain, without repeats."""
        first = (preferred or "").strip() or self.MODEL_CHAIN[0]
        rest = tuple(name for name in self.MODEL_CHAIN if name != first)
        return (first, *rest)

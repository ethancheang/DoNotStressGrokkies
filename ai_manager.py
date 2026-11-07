"""DoNotStress — AI Processing Layer (ai_manager).

AIManager is the only class that talks to an AI provider. For every
check-in it builds the prompt, calls the provider with model fallback,
parses the reply and validates it field by field.

It holds no domain rules. The scoring instructions and the check on each
reply come from a ScoreAuditor (the Logic layer's StressScorer). A reply
that fails that check is treated like any other invalid reply.

Only the 11 raw answers, the questionnaire version and the question
wording are sent: never a student id, reflection, or precomputed score,
flag or tier. On failure it returns an AIFailure and never invents
soft_label / tips / speak_prominence or falls back to Logic.

Pipeline position:
  User → io_manager → ai_manager (required) → logic_manager → data_manager
"""

from __future__ import annotations

import json
import time

from ai.ai_failure import AIFailure
from ai.ai_provider import AIProvider
from ai.ai_result import AIResult
from ai.error_classifier import ErrorClassifier
from ai.score_auditor import ScoreAuditor
from ai.validators.choice_validator import ChoiceValidator
from ai.validators.confidence_validator import ConfidenceValidator
from ai.validators.reasoning_validator import ReasoningValidator
from ai.validators.response_validator import ResponseValidator
from ai.validators.score_validator import ScoreValidator
from ai.validators.scored_items_validator import ScoredItemsValidator
from ai.validators.soft_label_validator import SoftLabelValidator
from ai.validators.stressors_validator import StressorsValidator
from ai.validators.tips_validator import TipsValidator
from base_manager import BaseManager
from json_types import JSONObject, JSONValue
from questions.question import Question


class AIManager(BaseManager):
    """Builds the prompt, calls the provider, parses and checks the reply.

    The provider is passed in and shared (aggregation); the auditor is
    only used, never owned (association). The validators and the error
    classifier are created here and belong to this manager (composition).
    """

    MAX_TOTAL_CALLS: int = 4  # Gemini calls one check-in may spend
    TRIES_PER_MODEL: int = 2  # a timeout or bad reply gets one more try
    REPEATABLE: tuple[str, ...] = (AIFailure.TIMEOUT,
                                   AIFailure.INVALID_RESPONSE)
    RISK_CATEGORIES: tuple[str, ...] = ("Low", "Moderate", "High")
    SPEAK_PROMINENCE: tuple[str, ...] = ("low", "medium", "high")
    SOURCE: str = "gemini"  # marks a record that passed AI processing

    def __init__(self, provider: AIProvider, questions: list[Question],
                 auditor: ScoreAuditor | None = None, *,
                 max_attempts: int = 3,
                 retry_delay_sec: float = 0.5) -> None:
        super().__init__("ai_manager")
        self.__provider: AIProvider = provider
        self.__questions: list[Question] = list(questions)
        self.__auditor: ScoreAuditor | None = auditor
        self.__tries_per_model: int = max(
            1, min(max_attempts, self.TRIES_PER_MODEL))
        self.__retry_delay_sec: float = max(0.0, retry_delay_sec)
        self.__classifier: ErrorClassifier = ErrorClassifier()
        self.__validators: list[ResponseValidator] = [
            ScoredItemsValidator(self.answer_keys),
            ScoreValidator(),
            ChoiceValidator(
                "risk_category", self.RISK_CATEGORIES,
                "The tier for stress_score, following the rules in the "
                "prompt."),
            SoftLabelValidator(),
            ChoiceValidator(
                "speak_prominence", self.SPEAK_PROMINENCE,
                "Must match risk_category: low, medium, or high."),
            StressorsValidator(),
            TipsValidator(),
            ReasoningValidator(),
            ConfidenceValidator(),
        ]
        self.__schema: JSONObject = self.__build_schema()

    @property
    def answer_keys(self) -> tuple[str, ...]:
        return tuple(question.key for question in self.__questions)

    @property
    def prompt_fields(self) -> tuple[str, ...]:
        """The only check-in fields ever sent to the provider."""
        return self.answer_keys + ("survey_version",)

    @property
    def required_fields(self) -> tuple[str, ...]:
        return tuple(validator.field for validator in self.__validators)

    @property
    def response_schema(self) -> JSONObject:
        """Gemini's structured-output schema, built from the validators."""
        return self.__schema

    def describe(self) -> JSONObject:
        return {
            "provider": self.__provider.name,
            "ready": self.__provider.is_ready(),
            "models": list(self.__provider.models),
            "validated_fields": list(self.required_fields),
        }

    def analyse(self, record: JSONObject) -> AIResult:
        """Prompt → provider → validated fields merged into the record.

        Every successful record is marked source="gemini". Never raises
        for API or schema failures.
        """
        if not isinstance(record, dict):
            return AIResult(failure=AIFailure(
                AIFailure.INVALID_RESPONSE,
                "The check-in must be a dict from io_manager."))
        result = self.call_api(self.build_prompt(record), answers=record)
        if result.fields is None:
            return result
        return AIResult(fields={**record, **result.fields})

    def build_prompt(self, record: JSONObject) -> str:
        """Ask Gemini to calculate stress_score from the raw answers.

        The JSON at the end holds only prompt_fields. Question wording and
        answer labels are instructions, not scored fields.
        """
        payload = {key: record.get(key) for key in self.prompt_fields}
        count = len(self.answer_keys)
        labels = ", ".join(f'"{label}"' for label in SoftLabelValidator.LABELS)
        rules = self.__auditor.instructions() if self.__auditor else ""
        lines = [
            "You are a supportive student-wellbeing assistant for "
            "DoNotStress, a local check-in used by students.",
            f"Calculate stress_score from the {count} answers with the "
            "formula below. You are not given a score, a tier, or a "
            "written reflection. Do not diagnose, and do not invent "
            "contacts.",
            rules + "Question wording and answer labels:",
            *(self.__format_question(item) for item in self.__questions),
            "Speak to the student with warmth. Return ONLY a single JSON "
            "object (no markdown fences, no commentary) with exactly these "
            "keys:",
            f'- "scored_items": object of the {count} converted values. '
            f"Keys are {', '.join(self.answer_keys)}. Each value is an "
            "integer from 1 to 5.",
            f'- "stress_score": the mean above, from '
            f"{ScoreValidator.MINIMUM:g} to {ScoreValidator.MAXIMUM:g}, "
            "rounded to 2 decimal places",
            '- "risk_category": "Low", "Moderate", or "High", matching '
            "stress_score",
            '- "primary_stressors": list of snake_case strings chosen ONLY '
            f"from: {', '.join(sorted(StressorsValidator.ALLOWED))}",
            '- "confidence": number from 0.0 to 1.0',
            '- "reasoning": 2 or 3 warm, plain sentences written to the '
            "student. No numbers, no jargon, no diagnosis, and no contacts",
            f'- "soft_label": exactly one of {labels}, matching '
            "risk_category. Use a straight apostrophe in You're doing ok",
            '- "tips": list of 1 to 3 tip IDs only, each one of: '
            f"{', '.join(sorted(TipsValidator.ALLOWED))}. Do not invent "
            "tip text",
            '- "speak_prominence": "low", "medium", or "high", matching '
            "risk_category. This is how strongly the UI highlights Talk to "
            "someone. SIT Counselling stays available and is shown more "
            "prominently when stress is higher",
            "Do not add other keys. Never invent phone numbers, emails, or "
            "offices. SIT Counselling contacts are shown by the UI, not by "
            "you.",
            "",
            "Student check-in:",
            json.dumps(payload, ensure_ascii=False, indent=2),
        ]
        return "\n".join(lines) + "\n"

    def call_api(self, prompt: str,
                 answers: JSONObject | None = None) -> AIResult:
        """Try the provider's models in order until a reply is valid.

        A missing key stops at once. A timeout or invalid reply gets one
        more try on the same model; any other error moves to the next
        model. At most MAX_TOTAL_CALLS calls are made, so a 429 never turns
        into a retry storm. When answers are given, the auditor checks each
        schema-valid reply. Never raises and never logs the API key.
        """
        if not self.__provider.is_ready():
            detail = "GEMINI_API_KEY is not set; cannot call Gemini."
            self.logger.error(detail)
            return AIResult(failure=AIFailure(
                AIFailure.MISSING_API_KEY, detail))
        failures: list[AIFailure] = []
        calls = 0
        last_try = 1
        for model in self.__provider.models:
            if calls == self.MAX_TOTAL_CALLS:
                break
            for attempt in range(1, self.__tries_per_model + 1):
                if calls == self.MAX_TOTAL_CALLS:
                    break
                if attempt > 1:
                    self.__pause(attempt - 1)
                calls += 1
                last_try = attempt
                result = self.__attempt(prompt, model, answers, attempt)
                if result.failure is None:
                    return result
                if result.failure.code == AIFailure.MISSING_API_KEY:
                    return result
                failures.append(result.failure)
                if result.failure.code not in self.REPEATABLE:
                    break
            self.logger.warning("Gemini model %s failed (%s)", model,
                                failures[-1].code)
        return AIResult(failure=self.__final_failure(failures, last_try))

    def parse_response(self, raw: object) -> JSONObject | None:
        """The JSON object inside a raw reply, even inside code fences.

        Returns None for empty, non-text or malformed input. Never raises.
        """
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            return None
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            data = json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def validate_response(self, payload: object) -> tuple[bool, JSONValue]:
        """Run every field validator over a reply (dict or JSON text).

        Checks required keys, types, ranges and allow-lists only; extra
        keys are dropped. Returns (True, fields) or (False, message).
        """
        if isinstance(payload, str):
            if not payload.strip():
                return False, "Empty AI response string."
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as error:
                return False, f"AI response is not valid JSON: {error}"
        if not isinstance(payload, dict):
            return False, "AI response must be a JSON object."
        missing = [name for name in self.required_fields
                   if name not in payload]
        if missing:
            return False, ("AI response missing required fields: "
                           f"{', '.join(missing)}.")
        fields: JSONObject = {}
        for validator in self.__validators:
            ok, value = validator.validate(payload[validator.field])
            if not ok:
                return False, value
            fields[validator.field] = value
        return True, fields

    def __attempt(self, prompt: str, model: str, answers: JSONObject | None,
                  attempt: int) -> AIResult:
        """One provider call, turned into fields or a failure."""
        label = f"(attempt {attempt}/{self.__tries_per_model}) model={model}"
        try:
            raw = self.__provider.generate(prompt, model, self.__schema)
        except Exception as error:  # a provider failure must not crash
            detail = (f"Gemini API failure {label}: "
                      f"{self.__provider.redact(str(error))}")
            self.logger.warning(detail)
            return AIResult(failure=AIFailure(
                self.__classifier.classify(error), detail))
        ok, checked = self.__check_reply(raw, answers)
        if ok and isinstance(checked, dict):
            return AIResult(fields={**checked, "source": self.SOURCE})
        detail = f"Schema validation failed {label}: {checked}"
        self.logger.warning(detail)
        return AIResult(failure=AIFailure(AIFailure.INVALID_RESPONSE, detail))

    def __check_reply(self, raw: str,
                      answers: JSONObject | None) -> tuple[bool, JSONValue]:
        parsed = self.parse_response(raw)
        ok, fields = self.validate_response(raw if parsed is None else parsed)
        if not ok or not isinstance(fields, dict):
            return False, fields
        if self.__auditor is None or answers is None:
            return True, fields
        try:
            problem = self.__auditor.verify(fields, answers)
        except Exception as error:  # a broken check must not crash
            return False, f"Score check could not run: {error}"
        return (False, problem) if problem else (True, fields)

    def __final_failure(self, failures: list[AIFailure],
                        last_try: int) -> AIFailure:
        """The failure to report once every allowed call has been made.

        A non-repeatable error on a model's second try means the retry
        did not help, which is reported as retries_exhausted.
        """
        if not failures:
            return AIFailure(AIFailure.UNAVAILABLE, "No model was tried.")
        last = failures[-1]
        if last_try > 1 and last.code not in self.REPEATABLE:
            return AIFailure(AIFailure.RETRIES_EXHAUSTED, last.detail)
        return last

    def __pause(self, retry: int) -> None:
        """Back off before a retry: the base delay, then doubled."""
        time.sleep(self.__retry_delay_sec * 2 ** (retry - 1))

    def __build_schema(self) -> JSONObject:
        names: list[JSONValue] = list(self.required_fields)
        return {
            "type": "OBJECT",
            "propertyOrdering": names,
            "required": names,
            "properties": {validator.field: validator.schema()
                           for validator in self.__validators},
        }

    def __format_question(self, question: Question) -> str:
        """One question line: key, wording and answer labels. No scores."""
        tone = (" Positively worded: a high answer means less stress."
                if question.reverse else "")
        head = f"- {question.key}: {question.prompt}{tone}"
        if question.options:
            labels = ", ".join(
                f"{number} = {label}"
                for number, label in enumerate(question.options, start=1))
            return f"{head} Answer labels: {labels}."
        return (f"{head} Answer: {question.minimum} to {question.maximum} "
                f"hours in steps of {question.step:g} ({question.low} to "
                f"{question.high}), not a 1 to 5 rating.")

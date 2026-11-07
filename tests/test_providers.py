"""AIProvider implementations. No test here reaches the real Gemini API."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ai.ai_provider import AIProvider
from ai.fake_provider import FakeProvider
from ai.gemini_provider import GeminiProvider
from plain_tests import case, function_suite

CHAIN = GeminiProvider.MODEL_CHAIN


def fake_client(captured, reply_text):
    """A stand-in for google.genai.Client that records what it was sent."""
    def generate_content(*, model, contents, config):
        captured.append({"model": model, "contents": contents,
                         "config": config})
        return SimpleNamespace(text=reply_text)

    def client(*, api_key, http_options):
        captured.append({"api_key": api_key, "http_options": http_options})
        return SimpleNamespace(
            models=SimpleNamespace(generate_content=generate_content))
    return client


# --- Contract shared by every provider ------------------------------------

def test_every_provider_honours_the_interface():
    """Liskov: any AIProvider can stand in wherever one is expected."""
    with patch("google.genai.Client", fake_client([], "{}")):
        for provider in (GeminiProvider("key"), FakeProvider("{}")):
            with case(provider=provider.name):
                assert isinstance(provider, AIProvider)
                assert provider.is_ready() is True
                assert provider.models
                assert provider.generate("prompt", provider.models[0]) == "{}"
                assert provider.redact("nothing secret") == "nothing secret"


def test_the_interface_cannot_be_used_on_its_own():
    try:
        AIProvider()
    except TypeError:
        return
    raise AssertionError("AIProvider must be abstract")


# --- GeminiProvider --------------------------------------------------------

def test_gemini_reads_the_key_from_the_environment_only_when_not_given():
    with patch.dict(os.environ, {"GEMINI_API_KEY": "  from-env  "}):
        assert GeminiProvider().is_ready()
        assert not GeminiProvider(api_key="").is_ready()
    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        assert not GeminiProvider().is_ready()
        assert not GeminiProvider(api_key="   ").is_ready()


def test_gemini_model_order_and_preferred_model():
    assert GeminiProvider("k").models == CHAIN
    assert GeminiProvider("k", "gemini-3.5-flash").models == (
        "gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite")
    assert GeminiProvider("k", "custom").models == ("custom", *CHAIN)


def test_gemini_sends_structured_json_settings_and_no_sdk_retries():
    captured = []
    schema = {"type": "OBJECT"}
    with patch("google.genai.Client", fake_client(captured, '{"a": 1}')):
        text = GeminiProvider("secret").generate(
            "hello", "gemini-3.6-flash", schema)
    assert text == '{"a": 1}'
    client_args, call = captured
    assert client_args["api_key"] == "secret"
    assert client_args["http_options"]["retry_options"] == {"attempts": 1}
    assert client_args["http_options"]["timeout"] == 30_000
    assert call["model"] == "gemini-3.6-flash"
    assert call["contents"] == "hello"
    assert call["config"]["response_schema"] is schema
    assert call["config"]["response_mime_type"] == "application/json"
    assert call["config"]["temperature"] == 0.0


def test_gemini_fails_loudly_on_an_empty_reply():
    for empty in (None, ""):
        with case(empty=empty), \
                patch("google.genai.Client", fake_client([], empty)):
            try:
                GeminiProvider("k").generate("p", "m")
            except RuntimeError as error:
                assert "no text payload" in str(error)
            else:
                raise AssertionError("an empty reply must raise")


def test_gemini_redacts_its_own_key_and_keeps_it_private():
    provider = GeminiProvider("sk-very-secret")
    assert provider.redact("denied for sk-very-secret") == (
        "denied for [redacted]")
    assert not hasattr(provider, "api_key")
    assert not hasattr(provider, "__api_key")


# --- FakeProvider ----------------------------------------------------------

def test_fake_replays_its_script_and_repeats_the_last_reply():
    fake = FakeProvider("first", "second")
    assert fake.generate("p1", "m1") == "first"
    assert fake.generate("p2", "m2") == "second"
    assert fake.generate("p3", "m3") == "second"
    assert fake.calls == [("p1", "m1"), ("p2", "m2"), ("p3", "m3")]
    assert fake.models_called == ["m1", "m2", "m3"]


def test_fake_raises_scripted_errors_and_runs_functions():
    fake = FakeProvider(TimeoutError("deadline exceeded"),
                        lambda prompt, model: f"{model}:{prompt}")
    try:
        fake.generate("p", "m")
    except TimeoutError:
        pass
    else:
        raise AssertionError("a scripted error must be raised")
    assert fake.generate("hello", "gemini-x") == "gemini-x:hello"


def test_fake_can_change_its_script_and_simulate_a_missing_key():
    fake = FakeProvider("{}")
    fake.reply_with("recovered")
    assert fake.generate("p", "m") == "recovered"
    assert FakeProvider(ready=False).is_ready() is False
    assert FakeProvider().generate("p", "m") == "{}"
    assert FakeProvider().models == CHAIN


def load_tests(loader, tests, pattern):
    """Let `python -m unittest discover -s tests` run this file's tests."""
    return function_suite(globals())


if __name__ == "__main__":
    unittest.main()

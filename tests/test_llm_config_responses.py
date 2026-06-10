from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING, ClassVar

import openai

from lifetrace.routers import config as config_router

if TYPE_CHECKING:
    import pytest


class FakeResponses:
    def __init__(self, owner: FakeOpenAI) -> None:
        self.owner = owner

    def create(self, **kwargs: object):
        self.owner.responses_kwargs = kwargs
        if self.owner.responses_error is not None:
            raise self.owner.responses_error
        return SimpleNamespace(output_text="ok")


class FakeChatCompletions:
    def __init__(self, owner: FakeOpenAI) -> None:
        self.owner = owner

    def create(self, **kwargs: object):
        self.owner.chat_kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )


class FakeOpenAI:
    instances: ClassVar[list[FakeOpenAI]] = []
    responses_error: ClassVar[Exception | None] = None

    def __init__(self, *, api_key: str, base_url: str) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.responses_kwargs: dict[str, object] | None = None
        self.chat_kwargs: dict[str, object] | None = None
        self.responses = FakeResponses(self)
        self.chat = SimpleNamespace(completions=FakeChatCompletions(self))
        self.responses_error = FakeOpenAI.responses_error
        FakeOpenAI.instances.append(self)


def _install_fake_openai(
    monkeypatch: pytest.MonkeyPatch,
    *,
    responses_error: Exception | None = None,
) -> type[FakeOpenAI]:
    FakeOpenAI.instances = []
    FakeOpenAI.responses_error = responses_error
    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    return FakeOpenAI


def _config_payload() -> dict[str, str]:
    return {
        "llmApiKey": "sk-test-key",
        "llmBaseUrl": "https://api.example.com/v1",
        "llmModel": "fake-model",
    }


def test_test_llm_config_reports_responses_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_openai_class = _install_fake_openai(monkeypatch)

    result = asyncio.run(config_router.test_llm_config(_config_payload()))

    assert result["success"] is True
    assert result["api_mode"] == "responses"
    instance = fake_openai_class.instances[0]
    assert instance.responses_kwargs == {
        "model": "fake-model",
        "input": "test",
        "max_output_tokens": 5,
    }
    assert instance.chat_kwargs is None


def test_test_llm_config_reports_chat_completions_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_openai_class = _install_fake_openai(
        monkeypatch,
        responses_error=RuntimeError("404 Not Found: /v1/responses"),
    )

    result = asyncio.run(config_router.test_llm_config(_config_payload()))

    assert result["success"] is True
    assert result["api_mode"] == "chat_completions_fallback"
    instance = fake_openai_class.instances[0]
    assert instance.responses_kwargs is not None
    assert instance.chat_kwargs == {
        "model": "fake-model",
        "messages": [{"role": "user", "content": "test"}],
        "max_tokens": 5,
    }

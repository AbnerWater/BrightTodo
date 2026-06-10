from __future__ import annotations

from types import SimpleNamespace

from lifetrace.llm.llm_client import LLMClient

RESPONSES_MAX_OUTPUT_TOKENS = 64
FALLBACK_MAX_TOKENS = 32


class FakeResponses:
    def __init__(self, owner: FakeOpenAIClient) -> None:
        self.owner = owner
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object):
        self.calls.append(kwargs)
        if self.owner.responses_error is not None:
            raise self.owner.responses_error
        return self.owner.responses_result


class FakeChatCompletions:
    def __init__(self, owner: FakeOpenAIClient) -> None:
        self.owner = owner
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object):
        self.calls.append(kwargs)
        message = SimpleNamespace(content=self.owner.chat_text)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeOpenAIClient:
    def __init__(
        self,
        *,
        responses_result=None,
        responses_error: Exception | None = None,
        chat_text: str = "chat fallback",
    ) -> None:
        self.responses_result = responses_result or SimpleNamespace(output_text="responses ok")
        self.responses_error = responses_error
        self.chat_text = chat_text
        self.responses = FakeResponses(self)
        self.chat = SimpleNamespace(completions=FakeChatCompletions(self))


def _client(fake_openai: FakeOpenAIClient) -> LLMClient:
    llm_client = object.__new__(LLMClient)
    llm_client.client = fake_openai
    llm_client.model = "fake-model"
    return llm_client


def test_responses_chat_extracts_output_text() -> None:
    fake_openai = FakeOpenAIClient(responses_result=SimpleNamespace(output_text="任务规划完成"))
    llm_client = _client(fake_openai)

    result = llm_client.responses_chat(
        messages=[
            {"role": "system", "content": "你是待办规划助手"},
            {"role": "user", "content": "帮我规划明天任务"},
        ],
        temperature=0.2,
        max_tokens=RESPONSES_MAX_OUTPUT_TOKENS,
    )

    assert result == "任务规划完成"
    request = fake_openai.responses.calls[0]
    assert request["model"] == "fake-model"
    assert request["instructions"] == "你是待办规划助手"
    assert request["input"] == [{"role": "user", "content": "帮我规划明天任务"}]
    assert request["max_output_tokens"] == RESPONSES_MAX_OUTPUT_TOKENS
    assert fake_openai.chat.completions.calls == []


def test_responses_chat_extracts_output_content_blocks() -> None:
    response = SimpleNamespace(
        output_text="",
        output=[
            SimpleNamespace(
                content=[
                    SimpleNamespace(type="output_text", text="第一段"),
                    {"type": "output_text", "text": "第二段"},
                ]
            )
        ],
    )
    fake_openai = FakeOpenAIClient(responses_result=response)
    llm_client = _client(fake_openai)

    result = llm_client.responses_chat(messages=[{"role": "user", "content": "test"}])

    assert result == "第一段第二段"


def test_chat_falls_back_when_responses_endpoint_unsupported() -> None:
    fake_openai = FakeOpenAIClient(
        responses_error=RuntimeError("404 Not Found: /v1/responses"),
        chat_text="chat ok",
    )
    llm_client = _client(fake_openai)

    result = llm_client.chat(
        messages=[{"role": "user", "content": "请生成待办"}],
        temperature=0.3,
        max_tokens=FALLBACK_MAX_TOKENS,
    )

    assert result == "chat ok"
    assert fake_openai.responses.calls
    request = fake_openai.chat.completions.calls[0]
    assert request["model"] == "fake-model"
    assert request["messages"] == [{"role": "user", "content": "请生成待办"}]
    assert request["max_tokens"] == FALLBACK_MAX_TOKENS

import asyncio
import json

import httpx
import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, ToolMessage, messages_from_dict, messages_to_dict
from langchain_core.runnables import Runnable
from openai import APITimeoutError

from app.infrastructure.llm.config import LLMConfig
from app.infrastructure.llm.factory import create_chat_model, model_session
from app.infrastructure.llm.usage import parse_token_usage
from app.runtime.usage import aggregate_usage


@pytest.mark.parametrize(
    "provider,base_url,model_id",
    [
        ("zhipu", "https://open.bigmodel.cn/api/paas/v4", "glm-5.3"),
        ("deepseek", "https://api.deepseek.com", "deepseek-flash"),
    ],
)
@pytest.mark.parametrize("streaming", [False, True])
def test_reasoning_survives_sdk_tool_roundtrip_and_serialization(
    provider, base_url, model_id, streaming
):
    calls = []
    tool = {"id": "call-1", "type": "function", "function": {"name": "lookup", "arguments": "{}"}}

    def handle(request):
        assert str(request.url) == base_url + "/chat/completions"
        body = json.loads(request.content)
        calls.append(body)
        assert body["max_tokens"] == 100 and "max_completion_tokens" not in body
        if len(calls) == 1:
            message = {"role": "assistant", "content": "", "tool_calls": [tool]}
            finish = "tool_calls"
        else:
            assert body["messages"][1]["reasoning_content"] == "需要查询资料"
            assert body["messages"][1]["tool_calls"] == [tool]
            assert body["messages"][2]["tool_call_id"] == "call-1"
            message = {"role": "assistant", "content": "完成"}
            finish = "stop"
        envelope = {"id": "completion-1", "model": model_id, "created": 1}
        usage = {"prompt_tokens": 7, "completion_tokens": 5, "total_tokens": 12}
        if body.get("stream"):
            pieces = [
                {
                    "delta": {"role": "assistant", "reasoning_content": "需要"},
                    "finish_reason": None,
                },
                {"delta": {"reasoning_content": "查询资料"}, "finish_reason": None},
                {
                    "delta": {
                        **message,
                        **(
                            {"tool_calls": [{"index": 0, **tool}]} if finish == "tool_calls" else {}
                        ),
                    },
                    "finish_reason": None,
                },
                {"delta": {}, "finish_reason": finish},
            ]
            events = [
                {**envelope, "object": "chat.completion.chunk", "choices": [{"index": 0, **piece}]}
                for piece in pieces
            ]
            events.append({**envelope, "choices": [], "usage": usage})
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                text="".join("data: " + json.dumps(event) + "\n\n" for event in events)
                + "data: [DONE]\n\n",
            )
        return httpx.Response(
            200,
            json={
                **envelope,
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {**message, "reasoning_content": "需要查询资料"},
                        "finish_reason": finish,
                    }
                ],
                "usage": usage,
            },
        )

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as transport:
            model = create_chat_model(
                LLMConfig(
                    api_key="test-key", model_id=model_id, base_url=base_url, provider=provider
                ),
                transport=transport,
                max_tokens=100,
            ).bind_tools(
                [
                    {
                        "name": "lookup",
                        "description": "查询资料",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ]
            )
            history = [HumanMessage(content="查询资料")]
            if streaming:
                result = None
                async for chunk in model.astream(history):
                    result = chunk if result is None else result + chunk
            else:
                result = await model.ainvoke(history)
            assert result.additional_kwargs["reasoning_content"] == "需要查询资料"
            assert result.tool_calls[0]["name"] == "lookup"
            assert result.usage_metadata["total_tokens"] == 12
            history += messages_from_dict(messages_to_dict([result]))
            history.append(ToolMessage(content="资料内容", tool_call_id="call-1"))
            final = await model.ainvoke(history)
            assert final.content == "完成"
            assert len(calls) == 2

    asyncio.run(exercise())


def test_factory_preserves_model_capabilities_and_independent_configuration():
    first_config = LLMConfig(
        api_key="test-key", model_id="model-a", base_url="https://a.example/v1"
    )
    second_config = first_config.model_copy(update={"model_id": "model-b", "timeout": 15})
    first = create_chat_model(first_config)
    second = create_chat_model(second_config)
    assert isinstance(first, BaseChatModel)
    assert first.model_name == "model-a"
    assert second.model_name == "model-b"
    assert first.request_timeout == 60
    assert second.request_timeout == 15
    assert first.max_retries == 0
    schema = {
        "name": "extract_summary",
        "description": "Summarize the input.",
        "parameters": {"type": "object", "properties": {"summary": {"type": "string"}}},
    }
    assert isinstance(first.bind_tools([schema]), Runnable)
    assert isinstance(second.with_structured_output(schema, method="function_calling"), Runnable)


@pytest.mark.parametrize("timeout", [2.5, 15, 90])
@pytest.mark.parametrize("fail", [False, True])
def test_model_session_applies_configured_timeout_to_actual_request(monkeypatch, timeout, fail):
    clients, requests = [], []

    def handle(request):
        requests.append(request)
        assert request.extensions["timeout"] == {
            "connect": min(10, timeout),
            "read": timeout,
            "write": timeout,
            "pool": timeout,
        }
        if fail:
            raise httpx.ReadTimeout("fixture timeout", request=request)
        return httpx.Response(
            200,
            json={
                "id": "fixture",
                "model": "fixture",
                "created": 1,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    class RecordingClient(httpx.AsyncClient):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(handle), **kwargs)
            clients.append(self)

    monkeypatch.setattr("app.infrastructure.llm.factory.httpx.AsyncClient", RecordingClient)

    async def exercise():
        config = LLMConfig(
            api_key="fixture",
            model_id="fixture",
            base_url="https://fixture.invalid/v1",
            timeout=timeout,
        )
        async with model_session(config, max_tokens=100) as model:
            if fail:
                with pytest.raises(APITimeoutError):
                    await model.ainvoke("hello")
            else:
                assert (await model.ainvoke("hello")).content == "ok"

    asyncio.run(exercise())
    assert len(requests) == 1  # 超时不隐式重试。
    assert len(clients) == 1 and clients[0].is_closed


def test_cancelling_model_session_closes_transport(monkeypatch):
    clients = []

    async def exercise():
        entered = asyncio.Event()

        async def handle(request):
            entered.set()
            await asyncio.Event().wait()

        class RecordingClient(httpx.AsyncClient):
            def __init__(self, **kwargs):
                super().__init__(transport=httpx.MockTransport(handle), **kwargs)
                clients.append(self)

        monkeypatch.setattr("app.infrastructure.llm.factory.httpx.AsyncClient", RecordingClient)

        async def invoke():
            config = LLMConfig(
                api_key="fixture",
                model_id="fixture",
                base_url="https://fixture.invalid/v1",
                timeout=2.5,
            )
            async with model_session(config, max_tokens=100) as model:
                await model.ainvoke("hello")

        task = asyncio.create_task(invoke())
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
    assert len(clients) == 1 and clients[0].is_closed


def test_usage_preserves_missing_zero_and_included_detail_counts():
    assert parse_token_usage(None) is None
    zero = parse_token_usage({"input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
    assert zero.total_tokens == 0
    assert zero.cached_input_tokens is None
    usage = parse_token_usage(
        {
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
            "input_token_details": {"cache_read": 40},
            "output_token_details": {"reasoning": 5},
        }
    )
    assert usage.model_dump() == {
        "input_tokens": 100,
        "output_tokens": 20,
        "total_tokens": 120,
        "cached_input_tokens": 40,
        "reasoning_tokens": 5,
    }


def test_cumulative_usage_preserves_zero_and_cannot_recover_missing_fields():
    first = aggregate_usage(
        {},
        {"input_tokens": 0, "output_tokens": 5, "total_tokens": 5, "cached_input_tokens": 0},
        1,
    )
    assert first["input_tokens"] == first["cached_input_tokens"] == 0
    second = aggregate_usage(first, {"input_tokens": 10, "output_tokens": 0, "total_tokens": 10}, 2)
    assert second["total_tokens"] == 15 and second["output_tokens"] == 5
    assert second["cached_input_tokens"] is None
    third = aggregate_usage(
        second, {"total_tokens": 5, "cached_input_tokens": 3, "reasoning_tokens": 0}, 3
    )
    assert third["total_tokens"] == 20
    assert third["cached_input_tokens"] is third["reasoning_tokens"] is None
    assert all(value is None for value in aggregate_usage(third, None, 4).values())
    assert aggregate_usage({"total_tokens": None}, {"total_tokens": 15}, 2)["total_tokens"] is None

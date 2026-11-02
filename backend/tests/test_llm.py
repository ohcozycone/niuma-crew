"""Shared model construction and usage semantics do not depend on knowledge answers."""

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable

from app.llm.config import LLMConfig
from app.llm.factory import create_chat_model
from app.llm.usage import aggregate_usage, parse_token_usage


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

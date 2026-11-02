"""Create LangChain models without narrowing their business-facing capabilities."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.llm.config import LLMConfig


def create_chat_model(
    config: LLMConfig, *, transport: httpx.AsyncClient | None = None, max_tokens: int | None = None
) -> BaseChatModel:
    runtime_options = {}
    if transport is not None:
        runtime_options.update(
            http_async_client=transport, default_headers={"User-Agent": "AgentPlatform/0.1"}
        )
    if max_tokens is not None:
        runtime_options["max_tokens"] = max_tokens

    return ChatOpenAI(
        model=config.model_id,
        api_key=config.api_key,
        base_url=config.base_url,
        use_responses_api=False,
        stream_usage=True,
        timeout=transport.timeout if transport is not None else config.timeout,
        max_retries=config.max_retries,
        **runtime_options,
    )


@asynccontextmanager
async def model_session(
    config: LLMConfig,
    *,
    max_tokens: int,
    factory: Callable[..., BaseChatModel] | None = None,
) -> AsyncIterator[BaseChatModel]:
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(60, connect=10), follow_redirects=False, trust_env=False
    ) as transport:
        yield (factory or create_chat_model)(config, transport=transport, max_tokens=max_tokens)

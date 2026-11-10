from typing import Any

import openai
from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI


class ReasoningChatOpenAI(ChatOpenAI):
    """将供应商的 reasoning 字段保留在消息元数据中，供工具续轮及恢复使用。"""

    def _create_chat_result(
        self, response: dict | openai.BaseModel, generation_info: dict | None = None
    ) -> ChatResult:
        result = super()._create_chat_result(response, generation_info)
        data = response if isinstance(response, dict) else response.model_dump()
        for generation, choice in zip(result.generations, data["choices"], strict=True):
            reasoning = choice["message"].get("reasoning_content")
            if isinstance(reasoning, str):
                generation.message.additional_kwargs["reasoning_content"] = reasoning
        return result

    def _convert_chunk_to_generation_chunk(
        self, chunk: dict, default_chunk_class: type, base_generation_info: dict | None
    ) -> ChatGenerationChunk | None:
        result = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        choices = chunk.get("choices") or []
        if result is not None and choices:
            reasoning = (choices[0].get("delta") or {}).get("reasoning_content")
            if isinstance(reasoning, str):
                result.message.additional_kwargs["reasoning_content"] = reasoning
        return result

    def _get_request_payload(
        self, input_: LanguageModelInput, *, stop: list[str] | None = None, **kwargs: Any
    ) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        # 这些供应商要求 max_tokens，不接受 ChatOpenAI 默认改写的参数名。
        if "max_completion_tokens" in payload:
            payload["max_tokens"] = payload.pop("max_completion_tokens")
        for message, wire in zip(
            self._convert_input(input_).to_messages(), payload["messages"], strict=True
        ):
            if isinstance(message, AIMessage):
                reasoning = message.additional_kwargs.get("reasoning_content")
                if isinstance(reasoning, str):
                    wire["reasoning_content"] = reasoning
        return payload

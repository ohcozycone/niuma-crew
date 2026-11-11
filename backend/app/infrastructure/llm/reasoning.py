from typing import Any

import openai
from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI


def _preserve_reasoning(message: AIMessage, value: object) -> None:
    """沿用 SDK 的标准推理内容，仅在缺少文本时保留扩展字段。"""
    if not isinstance(value, str):
        return
    if any(
        block["type"] == "reasoning"
        and isinstance(block.get("reasoning"), str)
        and block["reasoning"]
        for block in message.content_blocks
    ):
        return
    message.additional_kwargs["reasoning_content"] = value


class ReasoningChatOpenAI(ChatOpenAI):
    """兼容聊天响应统一保留推理；请求格式兼容独立配置。"""

    legacy_request_format: bool = False

    def _create_chat_result(
        self, response: dict | openai.BaseModel, generation_info: dict | None = None
    ) -> ChatResult:
        result = super()._create_chat_result(response, generation_info)
        data = response if isinstance(response, dict) else response.model_dump()
        for generation, choice in zip(result.generations, data["choices"], strict=True):
            _preserve_reasoning(generation.message, choice["message"].get("reasoning_content"))
        return result

    def _convert_chunk_to_generation_chunk(
        self, chunk: dict, default_chunk_class: type, base_generation_info: dict | None
    ) -> ChatGenerationChunk | None:
        result = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        choices = chunk.get("choices") or []
        if result is not None and choices:
            _preserve_reasoning(
                result.message, (choices[0].get("delta") or {}).get("reasoning_content")
            )
        return result

    def _get_request_payload(
        self, input_: LanguageModelInput, *, stop: list[str] | None = None, **kwargs: Any
    ) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        if not self.legacy_request_format:
            return payload
        # 已有服务要求的参数名和思考回传，不影响通用响应字段提取。
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

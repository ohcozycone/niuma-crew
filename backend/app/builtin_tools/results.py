from collections.abc import Callable
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.types import Command
from pydantic import Field

from app.builtin_tools.bindings import ToolBinding
from app.errors import CodedFailure, FailureKind
from app.runtime.contracts.tools import RESULT_READER, ToolInvocation, ToolOutcome


def result_reader_tool(read: Callable[[str, int, int], str]) -> ToolBinding:
    def read_tool_result(
        result_id: str,
        offset: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1)] = 6000,
    ) -> str:
        return read(result_id, offset, limit)

    return ToolBinding(
        StructuredTool.from_function(
            read_tool_result,
            name=RESULT_READER,
            description=(
                "按字符分页读取本轮已保存工具结果。offset 是非负字符位置，limit 是期望的正字符数；"
                "实际正文每次最多8,000 UTF-8字节，可能少于limit。"
                "继续读取须使用返回的next_offset，不能用请求的limit推算；next_offset为空表示本地文本读完，"
                "不代表远端业务已全量返回。只接受本轮result_id，不访问任意文件。"
            ),
        ),
        normalize_feedback,
    )


def result_reader_binding() -> dict:
    return {
        "kind": "builtin",
        "binding_id": "builtin:read_tool_result",
        "tool_name": RESULT_READER,
        "exposed_name": RESULT_READER,
        "recovery": "readonly",
        "scope_policy": {"max_calls": 32},
    }


def tool_message(result: object) -> ToolMessage:
    if isinstance(result, ToolMessage):
        return result
    if isinstance(result, Command) and isinstance(result.update, dict):
        messages = result.update.get("messages", [])
        message = next(
            (value for value in reversed(messages) if isinstance(value, ToolMessage)), None
        )
        if message is not None:
            return message
    raise CodedFailure("tool_result_unknown", FailureKind.DEPENDENCY)


def feedback_outcome(
    result: object,
    *,
    data=None,
    sources=(),
    status=None,
    error_code=None,
) -> ToolOutcome:
    message = tool_message(result)
    text = message.content if isinstance(message.content, str) else str(message.text)
    status = status or ("succeeded" if message.status == "success" else "failed")
    data = dict(data or {})
    if isinstance(message.content, list):
        data["model_content"] = message.content
    message.status = "success" if status == "succeeded" else "error"
    if message.artifact is not None:
        data["artifact"] = message.artifact
    return ToolOutcome(text, status, data, tuple(sources), error_code=error_code)


async def normalize_feedback(result: object, invocation: ToolInvocation, host=None) -> ToolOutcome:
    return feedback_outcome(result)


async def normalize_builtin(result: object, invocation: ToolInvocation, host=None) -> ToolOutcome:
    message = tool_message(result)
    saved = message.artifact["builtin_outcome"]
    message.artifact = None
    return feedback_outcome(
        result,
        status=saved["status"],
        data=saved["data"],
        sources=saved["sources"],
        error_code=saved.get("error_code"),
    )


def render_feedback(saved: dict, name: str, call_id: str) -> ToolMessage:
    return ToolMessage(
        content=saved.get("data", {}).get("model_content", saved["content"]),
        artifact=saved.get("data", {}).get("artifact"),
        name=name,
        tool_call_id=call_id,
        status="success" if saved["status"] == "succeeded" else "error",
    )

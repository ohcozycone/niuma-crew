from collections.abc import Callable
from dataclasses import asdict

from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.types import Command

from app.builtin_tools.contracts import ToolBinding, ToolOutcome
from app.builtin_tools.results import normalize_builtin

SEARCH_TOOLS = "search_tools"
SEARCH_BINDING_ID = "builtin:search_tools"

SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 1, "maxLength": 1000},
        "source_id": {"type": ["string", "null"]},
        "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
    },
    "required": ["query"],
    "additionalProperties": False,
}


def search_binding() -> dict:
    return {
        "kind": "builtin",
        "binding_id": SEARCH_BINDING_ID,
        "tool_name": SEARCH_TOOLS,
        "exposed_name": SEARCH_TOOLS,
        "description": "从本轮获准的外部工具目录查找适用工具。query 使用工具可能包含的操作关键词；英文目录优先用英文或中英混合词，避免只写整段中文需求。可选 source_id 收窄服务。返回的工具将在下一次模型请求提供完整定义，同一批响应不能调用尚未提供的工具。无命中时可换关键词。",
        "input_schema": SEARCH_SCHEMA,
        "recovery": "readonly",
        "scope_policy": {"max_calls": 32},
    }


def search_tool(
    search: Callable[[str, str | None, int], ToolOutcome], validate: Callable[[dict], list[str]]
) -> ToolBinding:
    async def invoke(query: str, source_id: str | None = None, limit: int = 5):
        outcome = search(query, source_id, limit)
        return outcome.content, {"builtin_outcome": asdict(outcome)}

    def render(saved: dict, call_id: str) -> object:
        message = ToolMessage(
            content=saved["content"],
            name=SEARCH_TOOLS,
            tool_call_id=call_id,
            status="success" if saved["status"] == "succeeded" else "error",
        )
        if saved["status"] != "succeeded":
            return message
        ids = validate(saved["data"]["discovery"])
        return Command(update={"messages": [message], "discovered_tool_ids": ids})

    binding = search_binding()
    return ToolBinding(
        StructuredTool(
            name=SEARCH_TOOLS,
            description=binding["description"],
            args_schema=SEARCH_SCHEMA,
            coroutine=invoke,
            response_format="content_and_artifact",
        ),
        normalize_builtin,
        render,
    )

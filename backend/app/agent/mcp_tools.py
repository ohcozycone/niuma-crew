from langchain.agents.middleware import ToolCallRequest
from langchain_core.tools import StructuredTool

from app.agent.contracts import AgentContext
from app.builtin_tools.contracts import ToolBinding, ToolInvocation, ToolOutcome, ToolResultHost
from app.builtin_tools.result_files import result_scope
from app.builtin_tools.results import feedback_outcome, tool_message


def mcp_tool(binding: dict) -> ToolBinding:
    async def normalize(
        result: object, invocation: ToolInvocation, context: ToolResultHost
    ) -> ToolOutcome:
        message = tool_message(result)
        external = message.artifact["platform_outcome"]
        status = external["status"]
        code = external.get("error_code") or external["data"].get("code")
        data = {"file_id": message.artifact["file_id"], "query": invocation.arguments.get("query")}
        message.artifact = {"file_id": data["file_id"]}
        return feedback_outcome(
            result,
            data=data,
            status=status,
            error_code=code,
        )

    return ToolBinding(
        StructuredTool(
            name=binding["exposed_name"],
            description=binding["description"],
            args_schema=binding["input_schema"],
            response_format="content_and_artifact",
        ),
        normalize,
    )


def bind_mcp_call(
    request: ToolCallRequest, binding: dict, context: AgentContext, invocation: ToolInvocation
) -> ToolCallRequest:
    async def call(**arguments):
        outcome = await context.tools.call(
            binding, arguments, lambda: context.guard_tool(invocation)
        )
        content, data, _ = await context.preserve_tool_result(
            invocation, outcome.data, outcome.status
        )
        scope = result_scope.get()
        if scope is not None:
            scope.file_id = data["file_id"]
        original = outcome.data.get("content")
        if isinstance(original, list) and any(
            b.get("type") != "text" for b in original if isinstance(b, dict)
        ):
            content = [
                *(
                    [{"type": "text", "text": content}]
                    if any(isinstance(b, dict) and b.get("type") == "text" for b in original)
                    else []
                ),
                *[b for b in original if isinstance(b, dict) and b.get("type") != "text"],
            ]
        return content, {
            "file_id": data["file_id"],
            "platform_outcome": {
                "status": outcome.status,
                "data": outcome.data,
                "error_code": outcome.error_code,
            },
        }

    return request.override(tool=request.tool.model_copy(update={"coroutine": call}))

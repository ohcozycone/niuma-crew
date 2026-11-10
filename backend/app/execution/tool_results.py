import json

from app.execution.errors import ExecutionFailure
from app.infrastructure.concurrency import run_sync
from app.runtime.contracts.agent import AgentContext
from app.runtime.contracts.tools import ToolInvocation

PAGE_BYTES = 8000


def _legacy_result_text(data: dict) -> str:
    # 旧格式可能重复保存正文，只投影一份以保持历史游标。
    return json.dumps(_structured_payload(data) or data, ensure_ascii=False, default=str)


class ToolResults:
    def __init__(self, snapshot: dict, resources: AgentContext) -> None:
        self.resources = resources
        self.bindings = {item["binding_id"]: item for item in snapshot.get("tools", [])}

    def load(self, result_id: str) -> dict:
        # 先验证本 Run 成员关系，防止用任意文件 ID 读取附件或其他 Run。
        if not any(
            ref["id"] == result_id and ref["name"].startswith("tool-result-")
            for ref in self.resources.list_sources()
        ):
            raise ExecutionFailure("tool_not_allowed")
        try:
            envelope = json.loads(self.resources.read_file(result_id))
        except (ValueError, TypeError):
            raise ExecutionFailure("tool_result_unknown") from None
        if not isinstance(envelope, dict) or not isinstance(envelope.get("platform_result"), dict):
            raise ExecutionFailure("tool_result_unknown")
        meta = envelope["platform_result"]
        if meta.get("format_version") not in (None, 2) or (
            meta.get("format_version") == 2 and not isinstance(envelope.get("text"), str)
        ):
            raise ExecutionFailure("tool_result_unknown")
        binding = self.bindings.get(meta.get("binding_id"))
        if not binding or not isinstance(envelope.get("data"), dict):
            raise ExecutionFailure("tool_not_allowed")
        return envelope

    def read_page(self, result_id: str, offset: int = 0, limit: int = 6000) -> str:
        envelope = self.load(result_id)
        text = envelope.get("text")
        if not isinstance(text, str):
            text = _legacy_result_text(envelope["data"])
        if (
            type(offset) is not int
            or type(limit) is not int
            or not (0 <= offset <= len(text) and limit >= 1)
        ):
            raise ExecutionFailure("tool_arguments_invalid")
        # limit 是期望字符数；只按现有正文容量返回窗口，不因请求较大而中止 Run。
        # 每字符至少占一字节，先限字符可避免为很大的 limit 编码整份归档。
        chunk = (
            text[offset : offset + min(limit, PAGE_BYTES)]
            .encode()[:PAGE_BYTES]
            .decode(errors="ignore")
        )
        end = offset + len(chunk)
        return json.dumps(
            {
                "result_id": result_id,
                "offset": offset,
                "end": end,
                "total_chars": len(text),
                "next_offset": end if end < len(text) else None,
                "text": chunk,
            },
            ensure_ascii=False,
        )

    async def preserve(
        self, invocation: ToolInvocation, data: dict, status: str
    ) -> tuple[str, dict, tuple[dict, ...]]:
        raw = _result_text(data)
        if status == "failed":
            # OpenAI 工具消息不传递 ToolMessage.status；失败必须在模型正文中可见。
            raw = json.dumps({"status": status, "returned_content": raw}, ensure_ascii=False)
        binding = self.bindings[invocation.binding_id]
        envelope = {
            "platform_result": {
                "binding_id": binding["binding_id"],
                "format_version": 2,
                "status": status,
            },
            "data": data,
            "text": raw,
        }
        ref = await run_sync(
            self.resources.save_source,
            "tool-result-" + invocation.key.removeprefix("tool:")[:64] + ".json",
            json.dumps(envelope, ensure_ascii=False).encode(),
        )
        return (
            raw,
            {"file_id": ref["id"], "query": invocation.arguments.get("query")},
            (),
        )


def _structured_payload(data: dict) -> dict:
    payload = data.get("structured") or {}
    if isinstance(payload, dict):
        payload = payload.get("structured_content", payload)
    if not payload:
        content = data.get("content", [])
        text = (
            "\n".join(block.get("text", "") for block in content if isinstance(block, dict))
            if isinstance(content, list)
            else str(content)
        )
        try:
            payload = json.loads(text)
        except (TypeError, ValueError):
            payload = {}
    return payload if isinstance(payload, dict) else {}


def _result_text(data: dict) -> str:
    content = data.get("content")
    if isinstance(content, str) and content:
        return content
    if isinstance(content, list) and content:
        texts = [
            block["text"]
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        ]
        if texts:
            return "\n".join(texts)
        return json.dumps(content, ensure_ascii=False, default=str)
    return json.dumps(data.get("structured") or data, ensure_ascii=False, default=str)

"""将 SDK 长结果路径关联到既有归档；正文与权限仍由执行宿主维护。"""

import json
from collections.abc import Iterable
from contextvars import ContextVar
from dataclasses import dataclass, field

from deepagents.backends.protocol import BackendProtocol, FileDownloadResponse, WriteResult
from deepagents.backends.utils import create_file_data

from app.builtin_tools.workspace import SnapshotBackend
from app.environments.policy import checked_path
from app.errors import PermissionDeniedError
from app.infrastructure.concurrency import run_sync
from app.runtime.contracts.tools import RESULT_READER, ToolInvocation
from app.values import digest

RESULT_FILES_ROOT = "/sources/large_tool_results"


@dataclass
class ResultScope:
    invocation: ToolInvocation
    file_id: str | None = None
    aliases: dict = field(default_factory=dict)
    reads: list[dict] = field(default_factory=list)


result_scope: ContextVar[ResultScope | None] = ContextVar("tool_result_scope", default=None)


def result_read_hint(scope: ResultScope, bindings: Iterable[dict]) -> str:
    """为按行不可达的长结果提供已有字符读取入口，不改写归档正文。"""
    bindings = list(bindings)
    if not any(binding["exposed_name"] == RESULT_READER for binding in bindings):
        return ""
    # 现有字符读取许可仅支持 MCP 来源；不向知识或工作区结果承诺额外能力。
    readable = {
        binding["binding_id"]
        for binding in bindings
        if binding["kind"] in {"mcp_http", "mcp_stdio"}
    }
    ids = dict.fromkeys(
        entry["content_ref"]
        for entry in [*scope.aliases.values(), *scope.reads]
        if entry["origin_binding_id"] in readable
    )
    if not ids:
        return ""
    return (
        "完整原文也可按字符读取；read_file 的行偏移无法读取被截断单行的后半段。"
        "需要时从以下调用开始，后续使用返回的 next_offset；offset 单位是字符：\n"
        + "\n".join(
            json.dumps(
                {"tool": "read_tool_result", "arguments": {"result_id": id, "offset": 0}},
                ensure_ascii=False,
            )
            for id in ids
        )
        + "\n\n"
    )


class ToolResultBackend(BackendProtocol):
    def __init__(self, context):
        self.context = context
        self.pending = {}
        self.reader = SnapshotBackend(self._projection)

    def _aliases(self):
        return {**self.context.tool_result_aliases(), **self.pending}

    def _entry(self, path):
        path = checked_path(path)
        entry = self._aliases().get(path)
        if entry is None:
            raise PermissionDeniedError("file_path_denied")
        envelope = self.context.load_tool_result(entry["content_ref"])
        if envelope["platform_result"]["binding_id"] != entry["origin_binding_id"]:
            raise PermissionDeniedError("tool_not_allowed")
        text = envelope["text"]
        if digest(text) != entry["content_hash"]:
            raise PermissionDeniedError("file_integrity_failed")
        return entry, text

    def _projection(self):
        return {path: create_file_data(self._entry(path)[1]) for path in self._aliases()}

    def write(self, file_path, content):
        # 仅官方异步结果移存可创建别名，模型文件工具不能写来源目录。
        return WriteResult(error="file_readonly")

    async def awrite(self, file_path, content):
        scope = result_scope.get()
        if scope is None or checked_path(file_path).count("/") != 1:
            return WriteResult(error="file_readonly")
        await self.context.guard_tool(scope.invocation)
        if scope.file_id is None:
            _, data, _ = await self.context.preserve_tool_result(
                scope.invocation, {"content": content}, "unknown"
            )
            scope.file_id = data["file_id"]
        envelope = await run_sync(self.context.load_tool_result, scope.file_id)
        if envelope["text"] != content:
            return WriteResult(error="tool_result_unknown")
        entry = {
            "content_ref": scope.file_id,
            "origin_binding_id": scope.invocation.binding_id,
            "representation": "tool-result-v2.text",
            "content_hash": digest(content),
        }
        prior = (await run_sync(self._aliases)).get(file_path)
        if prior is not None and prior != entry:
            return WriteResult(error="file_readonly")
        await self.context.guard_tool(scope.invocation)
        self.pending[file_path] = scope.aliases[file_path] = entry
        return WriteResult(path=file_path)

    def read(self, file_path, offset=0, limit=2000):
        entry, _ = self._entry(file_path)
        scope = result_scope.get()
        if scope is not None:
            scope.reads.append(
                {
                    **entry,
                    "requested_window": {"unit": "sdk_line", "offset": offset, "limit": limit},
                    "source_ranges": None,
                }
            )
        return self.reader.read(file_path, offset, limit)

    def ls(self, path):
        return self.reader.ls(path)

    def grep(self, pattern, path=None, glob=None, *, max_count=None):
        return self.reader.grep(pattern, path, glob, max_count=max_count)

    def glob(self, pattern, path="/"):
        return self.reader.glob(pattern, path)

    def download_files(self, paths):
        return [
            FileDownloadResponse(path=path, content=self._entry(path)[1].encode()) for path in paths
        ]

    def sources(self):
        return [
            (RESULT_FILES_ROOT + path, self._entry(path)[1].encode()) for path in self._aliases()
        ]

    def edit(self, *args, **kwargs):
        raise PermissionDeniedError("file_readonly")

    def delete(self, *args, **kwargs):
        raise PermissionDeniedError("file_readonly")

    def upload_files(self, files):
        raise PermissionDeniedError("file_readonly")

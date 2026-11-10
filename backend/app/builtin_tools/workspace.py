from deepagents.backends import StateBackend
from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    GlobResult,
    GrepResult,
    LsResult,
    SandboxBackendProtocol,
)
from deepagents.backends.utils import create_file_data, file_data_to_string
from deepagents.middleware.filesystem import FilesystemMiddleware
from langchain_opensandbox import OpenSandboxBackend

from app.builtin_tools.contracts import ToolInvocation, ToolOutcome, WorkspaceHost
from app.builtin_tools.results import feedback_outcome, tool_message
from app.environments.open_sandbox import OpenSandboxOperations
from app.environments.policy import WRITE_TOOLS, checked_path, under
from app.errors import InvalidInputError, PermissionDeniedError
from app.values import digest


class SnapshotBackend(StateBackend):
    def __init__(self, values):
        self.values = values

    def _read_files(self):
        return self.values()

    def _send_files_update(self, update):
        raise PermissionDeniedError("file_readonly")


class LimitedStateBackend(StateBackend):
    def _read_files(self):
        return {
            path: data
            for path, data in super()._read_files().items()
            if under(path, "/workspace") or under(path, "/outputs")
        }

    def _send_files_update(self, update):
        values = self._read_files()
        for path, data in update.items():
            if not (under(checked_path(path), "/workspace") or under(path, "/outputs")):
                raise PermissionDeniedError("file_path_denied")
            if data is None:
                values.pop(path, None)
            else:
                if len(file_data_to_string(data).encode()) > 131072:
                    raise InvalidInputError("file_too_large")
                values[path] = data
        if sum(len(file_data_to_string(data).encode()) for data in values.values()) > 524288:
            raise InvalidInputError("file_quota_exceeded")
        super()._send_files_update(update)


class WorkspaceBackend(SandboxBackendProtocol):
    """保留完整虚拟路径，避免 CompositeBackend 去除前缀后技能键与沙箱路径不一致。"""

    def __init__(
        self,
        snapshot,
        prepared,
        context: WorkspaceHost,
        *,
        sandbox_factory=None,
        result_sources=None,
    ):
        self.snapshot, self.prepared, self.context = snapshot, prepared, context
        self.mode = snapshot.get("workspace", {}).get("mode", "virtual")
        self.projection_cache, self.skill_cache, self.materialized_skills = {}, {}, set()
        self.materialized_sources = set()
        workspace = snapshot.get("workspace", {})
        self.read_roots = set(workspace.get("read_roots", []))
        self.write_roots = set(workspace.get("write_roots", []))
        self.virtual = LimitedStateBackend()
        self.readonly = SnapshotBackend(self._projection)
        self.sandbox_factory = sandbox_factory or self._sandbox_backend
        self.remote = None
        self.result_sources = result_sources

    def _sandbox_backend(self, handle):
        return _SandboxFileBackend(
            sandbox=handle, timeout=self.snapshot.get("workspace", {}).get("command_seconds", 60)
        )

    def _work(self):
        if self.mode != "sandbox":
            return self.virtual
        if self.remote is None:
            if self.context.sandbox is None:
                raise InvalidInputError("sandbox_not_ready")
            self.remote = self.sandbox_factory(self.context.sandbox.acquire())
        return self.remote

    def _route(self, path, *, write=False):
        path = checked_path(path)
        roots = self.write_roots if write else (self.read_roots | {"/skills"})
        if not any(under(path, root) for root in roots):
            raise PermissionDeniedError("file_path_denied")
        if (
            under(path, "/skills")
            or under(path, "/sources")
            or (under(path, "/inputs") and self.mode == "virtual")
        ):
            if write:
                raise PermissionDeniedError("file_readonly")
            return self.readonly
        work = self._work()
        if self.mode == "sandbox":
            # 文件操作前检查沙箱内的真实路径；Shell 隔离另由环境和 UID 保证。
            work.check_path(path, write=write)
        return work

    def ls(self, path):
        if checked_path(path) == "/":
            return LsResult(
                entries=[
                    {"path": root + "/", "is_dir": True}
                    for root in sorted(self.read_roots | {"/skills"})
                ]
            )
        return self._route(path).ls(path)

    def read(self, file_path, offset=0, limit=2000):
        self._read_skill_resource(file_path)
        if under(file_path, "/sources"):
            data = self._projection().get(file_path)
            if data is not None:
                lines = file_data_to_string(data).split("\n")
                count, size = 0, 0
                for line in lines[max(offset, 0) : max(offset, 0) + max(limit, 0)]:
                    size += len(line.encode()) + 16
                    if size > 16000 and count:
                        break
                    count += 1
                limit = count
        return self._route(file_path).read(
            file_path, offset, min(limit, 2000) if not under(file_path, "/skills") else limit
        )

    def download_files(self, paths):
        result = []
        for path in paths:
            if path in self.prepared.resource_paths:
                self._route(path)
                if self.context.read_skill_blob is None:
                    raise InvalidInputError("skill_file_not_found")
                _, descriptor = self.prepared.resource_paths[path]
                result.append(
                    FileDownloadResponse(
                        path=path,
                        content=self.context.read_skill_blob(descriptor["content_hash"]),
                    )
                )
                continue
            result.extend(self._route(path).download_files([path]))
        return result

    def upload_files(self, files):
        result = []
        for path, data in files:
            result.extend(self._route(path, write=True).upload_files([(path, data)]))
        return result

    def write(self, file_path, content):
        return self._route(file_path, write=True).write(file_path, content)

    def edit(self, file_path, old_string, new_string, replace_all=False):
        return self._route(file_path, write=True).edit(
            file_path, old_string, new_string, replace_all
        )

    def delete(self, file_path):
        return self._route(file_path, write=True).delete(file_path)

    def glob(self, pattern, path=None):
        if ".." in pattern.split("/") or "\\" in pattern:
            raise PermissionDeniedError("file_path_denied")
        path = path or "/"
        if path == "/" and pattern.startswith("/"):
            path = "/" + pattern.lstrip("/").split("/")[0]
        if path != "/":
            return self._route(path).glob(pattern, path)
        matches, truncated = [], False
        for root in sorted(self.read_roots):
            result = self._route(root).glob(pattern, root)
            matches.extend(result.matches or [])
            truncated |= result.truncated
        return GlobResult(matches=matches[:256], truncated=truncated or len(matches) > 256)

    def grep(self, pattern, path=None, glob=None, *, max_count=None):
        path = path or "/"
        if path != "/":
            return self._route(path).grep(pattern, path, glob, max_count=min(max_count or 100, 100))
        matches, truncated = [], False
        for root in sorted(self.read_roots):
            result = self._route(root).grep(pattern, root, glob, max_count=100)
            matches.extend(result.matches or [])
            truncated |= result.truncated
        return GrepResult(matches=matches[:100], truncated=truncated or len(matches) > 100)

    @property
    def id(self):
        return self.mode

    def execute(self, command, *, timeout=None):
        if self.mode != "sandbox":
            raise PermissionDeniedError("sandbox_not_ready")
        ceiling = self.snapshot.get("workspace", {}).get("command_seconds", 60)
        work = self._work()
        self._materialize_skills(work)
        sources, source_ids = [], []
        for ref in self.context.list_sources():
            path = ref.get("path", f"/sources/{ref['id']}/{ref['name']}")
            if ref["id"] not in self.materialized_sources and under(checked_path(path), "/sources"):
                sources.append((path, self.context.read_file(ref["id"])))
                source_ids.append(ref["id"])
        # SDK 结果路径是归档正文的只读别名，沙箱中的同一路径也须读取相同文本。
        for path, body in self.result_sources() if self.result_sources else ():
            if path not in self.materialized_sources:
                sources.append((path, body))
                source_ids.append(path)
        if sources:
            work.materialize_readonly(sources)
            self.materialized_sources.update(source_ids)
        return work.execute(command, timeout=min(timeout or ceiling, ceiling))

    def collect_outputs(self, state):
        if self.mode == "sandbox":
            outputs = self.remote.collect_outputs() if self.remote is not None else []
        else:
            outputs = [
                (path.removeprefix("/outputs/"), file_data_to_string(value).encode())
                for path, value in state.get("files", {}).items()
                if value is not None and under(path, "/outputs")
            ]
        if len(outputs) > 32 or sum(len(data) for _, data in outputs) > 40 * 1024 * 1024:
            raise InvalidInputError("file_quota_exceeded")
        return [self.context.save_output(name, data) for name, data in outputs]

    def _projection(self):
        values = self.prepared.files
        values.update(self.skill_cache)
        refs = [*self.snapshot.get("input_files", []), *self.context.list_sources()]
        for ref in refs:
            path = ref.get("path", f"/sources/{ref['id']}/{ref['name']}")
            if under(path, "/inputs") and self.mode == "sandbox":
                continue
            if ref["id"] in self.projection_cache:
                values[path] = self.projection_cache[ref["id"]]
                continue
            try:
                text = self.context.read_file(ref["id"]).decode("utf-8")
            except UnicodeDecodeError:
                text = "此输入为二进制文件，请使用沙箱程序处理。"
            if under(path, "/sources"):
                # 只将阅读投影拆行，持久存储仍保留原始字节。
                text = "\n".join(
                    part
                    for line in text.split("\n")
                    for part in (
                        [line[index : index + 1000] for index in range(0, len(line), 1000)] or [""]
                    )
                )
            data = create_file_data(text)
            self.projection_cache[ref["id"]] = data
            values[path] = data
        return values

    def _read_skill_resource(self, path):
        item = self.prepared.resource_paths.get(path)
        if item is None or path in self.skill_cache:
            return
        _, descriptor = item
        if self.context.read_skill_blob is None:
            raise InvalidInputError("skill_file_not_found")
        body = self.context.read_skill_blob(descriptor["content_hash"])
        try:
            text = body.decode("utf-8") if descriptor.get("is_text") else None
        except UnicodeDecodeError:
            text = None
        self.skill_cache[path] = create_file_data(
            text
            if text is not None
            else "此技能资源为二进制或较大文件，请在已授权的沙箱中按此路径读取原始字节。"
        )

    def _materialize_skills(self, work):
        for path, entry in self.prepared.by_path.items():
            skill_id = entry.skill["skill_id"]
            if (
                skill_id not in self.prepared.active_skill_ids
                or skill_id in self.materialized_skills
            ):
                continue
            files = [(path, file_data_to_string(entry.data).encode())]
            for resource_path, (skill, descriptor) in self.prepared.resource_paths.items():
                if skill["skill_id"] != skill_id:
                    continue
                if self.context.read_skill_blob is None:
                    raise InvalidInputError("skill_file_not_found")
                files.append(
                    (resource_path, self.context.read_skill_blob(descriptor["content_hash"]))
                )
            work.materialize_readonly(files)
            self.materialized_skills.add(skill_id)


class _SandboxFileBackend(OpenSandboxBackend):
    def __init__(self, *, sandbox, timeout=60):
        super().__init__(sandbox=sandbox, timeout=timeout)
        self.operations = OpenSandboxOperations(sandbox, timeout)

    def execute(self, command, *, timeout=None):
        result = self.operations.execute(command, timeout=timeout)
        return ExecuteResponse(output=result.output, exit_code=result.exit_code)

    def materialize_readonly(self, files):
        self.operations.materialize_readonly(files)

    def check_path(self, path, *, write=False):
        self.operations.check_path(path, write=write)

    def collect_outputs(self):
        return self.operations.collect_outputs()


def filesystem_middleware(backend, names=None, *, context_bytes=131072):
    return FilesystemMiddleware(
        backend=backend,
        tools=names,
        max_execute_timeout=60,
        # SDK 用每 token 四字符近似；按最坏 UTF-8 宽度给正文留半份现有字节预算。
        # 这是移存阈值，不是另一道拒绝门；并行结果仍由完整请求检查兜底。
        tool_token_limit_before_evict=min(20000, max(1, context_bytes // 32)),
        human_message_token_limit_before_evict=None,
    )


def workspace_tools(workspace: dict) -> list[dict]:
    # 只读取官方定义；StateBackend 不执行命令，也不在受理时申请远端环境。
    middleware = filesystem_middleware(StateBackend())
    bindings = []
    for tool in middleware.tools:
        if tool.name == "execute" and workspace["mode"] != "sandbox":
            continue
        schema = tool.get_input_schema().model_json_schema()
        bindings.append(
            {
                "kind": "workspace",
                "binding_id": "workspace:" + tool.name,
                "tool_name": tool.name,
                "exposed_name": tool.name,
                "description": tool.description,
                "input_schema": schema,
                "descriptor_hash": digest([tool.name, tool.description, schema]),
                "recovery": "never" if tool.name in WRITE_TOOLS else "readonly",
                "scope_policy": {
                    "max_calls": 32,
                    "read_roots": workspace["read_roots"],
                    "write_roots": workspace["write_roots"],
                },
            }
        )
    return bindings


async def normalize_workspace(result: object, invocation: ToolInvocation, host=None) -> ToolOutcome:
    artifact = tool_message(result).artifact
    data, status, code = {}, None, None
    if isinstance(artifact, dict) and "exit_code" in artifact:
        data = {"exit_code": artifact["exit_code"]}
        if artifact["exit_code"] != 0:
            status, code = "failed", "command_failed"
    return feedback_outcome(result, data=data, status=status, error_code=code)

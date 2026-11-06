"""Full-path routing keeps read-only projections separate from mutable work."""

import json
import shlex
from datetime import timedelta

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
from langchain_opensandbox import OpenSandboxBackend
from opensandbox.models import WriteEntry
from opensandbox.models.execd import RunCommandOpts
from opensandbox.models.execd_sync import ExecutionHandlersSync

from app.environments.policy import checked_path, under
from app.errors import InvalidInputError, PermissionDeniedError
from app.execution.contracts import AgentContext


class SnapshotBackend(StateBackend):
    def __init__(self, values):
        self.values = values

    def _read_files(self):
        return self.values()

    def _send_files_update(self, update):
        raise PermissionDeniedError("file_readonly", "此目录为只读资料。")


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
                raise PermissionDeniedError("file_path_denied", "只能写入本轮工作区与输出目录。")
            if data is None:
                values.pop(path, None)
            else:
                if len(file_data_to_string(data).encode()) > 131072:
                    raise InvalidInputError("file_too_large", "虚拟文本文件超过 128 KiB。")
                values[path] = data
        if sum(len(file_data_to_string(data).encode()) for data in values.values()) > 524288:
            raise InvalidInputError("file_quota_exceeded", "虚拟文本工作区超过 512 KiB。")
        super()._send_files_update(update)


class WorkspaceBackend(SandboxBackendProtocol):
    """SDK backend facade; every route retains its complete virtual path.

    CompositeBackend strips prefixes. Keeping full paths here lets the existing
    frozen skill keys and sandbox paths share one meaning without copying state.
    """

    def __init__(self, snapshot, prepared, context: AgentContext, *, sandbox_factory=None):
        self.snapshot, self.prepared, self.context = snapshot, prepared, context
        self.mode = snapshot.get("workspace", {}).get("mode", "virtual")
        self.projection_cache, self.skill_cache, self.materialized_skills = {}, {}, set()
        scopes = [
            binding["scope_policy"]
            for binding in snapshot.get("tools", [])
            if binding["kind"] == "native"
        ]
        self.read_roots = set(root for scope in scopes for root in scope.get("read_roots", []))
        self.write_roots = set(root for scope in scopes for root in scope.get("write_roots", []))
        self.virtual = LimitedStateBackend()
        self.readonly = SnapshotBackend(self._projection)
        self.sandbox_factory = sandbox_factory or self._sandbox_backend
        self.remote = None

    def _sandbox_backend(self, handle):
        return _SandboxFileBackend(
            sandbox=handle, timeout=self.snapshot.get("workspace", {}).get("command_seconds", 60)
        )

    def _work(self):
        if self.mode != "sandbox":
            return self.virtual
        if self.remote is None:
            if self.context.sandbox is None:
                raise InvalidInputError("sandbox_not_ready", "沙箱尚未配置或验收。")
            self.remote = self.sandbox_factory(self.context.sandbox.acquire())
        return self.remote

    def _route(self, path, *, write=False):
        path = checked_path(path)
        roots = self.write_roots if write else (self.read_roots | {"/skills"})
        if not any(under(path, root) for root in roots):
            raise PermissionDeniedError("file_path_denied", "文件路径不在本轮许可范围内。")
        if (
            under(path, "/skills")
            or under(path, "/sources")
            or (under(path, "/inputs") and self.mode == "virtual")
        ):
            if write:
                raise PermissionDeniedError("file_readonly", "输入、来源和技能目录只读。")
            return self.readonly
        work = self._work()
        if self.mode == "sandbox":
            # Check canonical paths inside the same sandbox before file operations;
            # raw Shell is additionally confined by the execution profile/UID.
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
                    raise InvalidInputError("skill_file_not_found", "技能文件存储尚未配置。")
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
            raise PermissionDeniedError("file_path_denied", "检索模式越过目录边界。")
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
        return self.snapshot.get("workspace", {}).get("connection_id", "virtual")

    def execute(self, command, *, timeout=None):
        if self.mode != "sandbox":
            raise PermissionDeniedError("sandbox_not_ready", "当前工作区不支持代码执行。")
        ceiling = self.snapshot.get("workspace", {}).get("command_seconds", 60)
        work = self._work()
        self._materialize_skills(work)
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
            raise InvalidInputError("file_quota_exceeded", "输出文件数量或总量超过上限。")
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
                # Display is line-addressable; original bytes remain in file storage.
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
            raise InvalidInputError("skill_file_not_found", "技能文件存储尚未配置。")
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
                    raise InvalidInputError("skill_file_not_found", "技能文件存储尚未配置。")
                files.append(
                    (resource_path, self.context.read_skill_blob(descriptor["content_hash"]))
                )
            work.materialize_skills(files)
            self.materialized_skills.add(skill_id)


class _SandboxFileBackend(OpenSandboxBackend):
    def materialize_skills(self, files):
        # execd owns root; model commands run as UID 1000 and cannot mutate this
        # source tree. The content has already been frozen and hash-checked.
        parents = sorted({path.rsplit("/", 1)[0] for path, _ in files})
        script = (
            "import os; parents="
            + repr(parents)
            + "; [(os.makedirs(p,mode=0o755,exist_ok=True),os.chmod(p,0o755)) for p in parents]"
        )
        result = self._sandbox.commands.run(
            "python3 -c " + shlex.quote(script),
            opts=RunCommandOpts(uid=0, gid=0, timeout=timedelta(seconds=10)),
        )
        if result.exit_code != 0:
            raise InvalidInputError("skill_materialization_failed", "无法准备沙箱技能目录。")
        self._sandbox.files.write_files(
            [
                WriteEntry(path=path, data=body, mode=0o444, owner="root", group="root")
                for path, body in files
            ]
        )

    def execute(self, command, *, timeout=None):
        chunks = []
        size = 0

        def output(message):
            nonlocal size
            data = message.text
            size += len(data.encode())
            if size > 65536:
                raise InvalidInputError(
                    "tool_result_too_large", "命令日志超过 64 KiB，工作负载将停止。"
                )
            chunks.append(data)

        result = self._sandbox.commands.run(
            command,
            opts=RunCommandOpts(
                timeout=timedelta(seconds=min(timeout or self._default_timeout, 60)),
                uid=1000,
                gid=1000,
                working_directory="/workspace",
            ),
            handlers=ExecutionHandlersSync(
                on_stdout=output, on_stderr=output, skip_accumulation=True
            ),
        )
        if result.exit_code is None:
            raise InvalidInputError("tool_result_unknown", "命令退出状态未知，未自动重放。")
        return ExecuteResponse(output="\n".join(chunks), exit_code=result.exit_code)

    def check_path(self, path, *, write=False):
        roots = ["/workspace", "/outputs"] if write else ["/inputs", "/workspace", "/outputs"]
        script = (
            "import os,sys; p=" + repr(path) + "; roots=" + repr(roots) + "; "
            "r=os.path.realpath(p); "
            "sys.exit(0 if r==p.rstrip('/') and any(r==x or r.startswith(x+'/') for x in roots) else 13)"
        )
        result = self.execute("python3 -c " + shlex.quote(script), timeout=10)
        if result.exit_code != 0:
            raise PermissionDeniedError("file_path_denied", "路径包含符号链接或越过工作目录。")

    def collect_outputs(self):
        # Stop all workload processes before inspecting files. Trusted execd stays
        # root; every model command and child process runs as UID 1000.
        stopped = self._sandbox.commands.run(
            "pkill -KILL -u 1000 || test $? -eq 1",
            opts=RunCommandOpts(uid=0, gid=0, timeout=timedelta(seconds=10)),
        )
        if stopped.exit_code != 0:
            raise InvalidInputError("sandbox_stop_failed", "无法确认工作负载已停止，未发布输出。")
        script = """import json,os,stat
items=[]
total=0
for root,dirs,files in os.walk('/outputs',followlinks=False):
    if any(os.path.islink(os.path.join(root,d)) for d in dirs): raise ValueError('output symlink')
    for name in files:
        p=os.path.join(root,name); s=os.lstat(p)
        if not stat.S_ISREG(s.st_mode) or os.path.islink(p): raise ValueError('output type')
        total+=s.st_size
        if s.st_size>10485760 or total>41943040 or len(items)>=32: raise ValueError('output limit')
        items.append(p)
print(json.dumps(items))
"""
        listed = self.execute("python3 -c " + shlex.quote(script), timeout=10)
        if listed.exit_code != 0:
            raise InvalidInputError("output_collection_failed", "输出包含不支持的文件或超过限制。")
        paths = json.loads(listed.output)
        return [
            (path.removeprefix("/outputs/").replace("/", "_"), self._sandbox.files.read_bytes(path))
            for path in paths
        ]

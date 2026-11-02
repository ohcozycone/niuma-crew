"""Full-path routing keeps read-only projections separate from mutable work."""

from deepagents.backends import StateBackend
from deepagents.backends.protocol import (
    FileDownloadResponse,
    GlobResult,
    GrepResult,
    LsResult,
    SandboxBackendProtocol,
)
from deepagents.backends.utils import create_file_data, file_data_to_string

from app.errors import InvalidInputError, PermissionDeniedError
from app.tools.policy import checked_path, under


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

    def __init__(self, snapshot, prepared, resources, *, sandbox_factory=None):
        self.snapshot, self.prepared, self.resources = snapshot, prepared, resources
        self.mode = snapshot.get("workspace", {}).get("mode", "virtual")
        scopes = [
            binding["scope_policy"]
            for binding in snapshot.get("tools", [])
            if binding["kind"] == "native"
        ]
        self.read_roots = set(root for scope in scopes for root in scope.get("read_roots", []))
        self.write_roots = set(root for scope in scopes for root in scope.get("write_roots", []))
        self.virtual = LimitedStateBackend()
        self.readonly = SnapshotBackend(self._projection)
        self.sandbox_factory = sandbox_factory
        self.remote = None
        self.projection_cache = {}
        self.skill_cache = {}
        self.materialized_skills = set()

    def _projection(self):
        values = dict(self.prepared.files)
        values.update(self.skill_cache)
        if self.resources is not None:
            refs = [*self.snapshot.get("input_files", []), *self.resources.list_sources()]
            for ref in refs:
                path = ref.get("path", f"/sources/{ref['id']}/{ref['name']}")
                if under(path, "/inputs") and self.mode == "sandbox":
                    continue
                if ref["id"] in self.projection_cache:
                    values[path] = self.projection_cache[ref["id"]]
                    continue
                try:
                    text = self.resources.read_file(ref["id"]).decode("utf-8")
                except UnicodeDecodeError:
                    text = "此输入为二进制文件，请使用沙箱程序处理。"
                if under(path, "/sources"):
                    # Display is line-addressable; original bytes remain in file storage.
                    text = "\n".join(
                        part
                        for line in text.split("\n")
                        for part in (
                            [line[index : index + 1000] for index in range(0, len(line), 1000)]
                            or [""]
                        )
                    )
                data = create_file_data(text)
                self.projection_cache[ref["id"]] = data
                values[path] = data
        return values

    def _work(self):
        if self.mode != "sandbox":
            return self.virtual
        if self.remote is None:
            if (
                self.resources is None
                or self.resources.sandbox is None
                or self.sandbox_factory is None
            ):
                raise InvalidInputError("sandbox_not_ready", "沙箱尚未配置或验收。")
            self.remote = self.sandbox_factory(self.resources.sandbox.acquire())
        return self.remote

    def _read_skill_resource(self, path):
        item = self.prepared.resource_paths.get(path)
        if item is None or path in self.skill_cache:
            return
        _, descriptor = item
        if self.resources is None or self.resources.read_skill_blob is None:
            raise InvalidInputError("skill_file_not_found", "技能文件存储尚未配置。")
        body = self.resources.read_skill_blob(descriptor["content_hash"])
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
                if self.resources is None or self.resources.read_skill_blob is None:
                    raise InvalidInputError("skill_file_not_found", "技能文件存储尚未配置。")
                files.append(
                    (resource_path, self.resources.read_skill_blob(descriptor["content_hash"]))
                )
            work.materialize_skills(files)
            self.materialized_skills.add(skill_id)

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
                if self.resources is None or self.resources.read_skill_blob is None:
                    raise InvalidInputError("skill_file_not_found", "技能文件存储尚未配置。")
                _, descriptor = self.prepared.resource_paths[path]
                result.append(
                    FileDownloadResponse(
                        path=path,
                        content=self.resources.read_skill_blob(descriptor["content_hash"]),
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
        if self.resources is None:
            return []
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
        return [self.resources.save_output(name, data) for name, data in outputs]

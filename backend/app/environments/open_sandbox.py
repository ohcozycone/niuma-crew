import json
import shlex
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlsplit

import httpx
from opensandbox import SandboxManagerSync, SandboxSync
from opensandbox.config import ConnectionConfigSync
from opensandbox.models import NetworkPolicy, SandboxFilter, WriteEntry
from opensandbox.models.execd import RunCommandOpts
from opensandbox.models.execd_sync import ExecutionHandlersSync
from opensandbox.transport.retry import RetryPolicy

from app.errors import InvalidInputError, PermissionDeniedError, ServiceUnavailableError


class BoundedSyncStream(httpx.SyncByteStream):
    def __init__(self, stream, limit):
        self.stream, self.limit = stream, limit

    def __iter__(self):
        count = 0
        for chunk in self.stream:
            count += len(chunk)
            if count > self.limit:
                raise InvalidInputError("tool_result_too_large", "沙箱传输超过接收上限。")
            yield chunk

    def close(self):
        self.stream.close()


class BoundedSandboxTransport(httpx.BaseTransport):
    def __init__(self):
        self.inner = httpx.HTTPTransport(retries=0, trust_env=False)

    def handle_request(self, request):
        response = self.inner.handle_request(request)
        response.stream = BoundedSyncStream(response.stream, 12 * 1024 * 1024)
        return response

    def close(self):
        self.inner.close()


class OpenSandboxProvider:
    def __init__(self, config):
        self.config = config

    def connection(self, timeout_seconds=15):
        url = urlsplit(self.config.endpoint or "")
        if (
            url.scheme not in ("http", "https")
            or not url.netloc
            or url.path not in ("", "/")
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ServiceUnavailableError(
                "sandbox_not_ready", "OpenSandbox 地址必须是受信服务的完整 HTTP(S) 源地址。"
            )
        return ConnectionConfigSync(
            domain=url.netloc,
            protocol=url.scheme,
            api_key=self.config.api_key,
            request_timeout=timedelta(seconds=timeout_seconds),
            retry_policy=RetryPolicy(max_retries=0),
            transport=BoundedSandboxTransport(),
            use_server_proxy=True,
        )

    def create(self, metadata):
        return SandboxSync.create(
            self.config.image,
            timeout=timedelta(seconds=self.config.ttl_seconds),
            ready_timeout=timedelta(seconds=30),
            metadata=metadata,
            resource={"cpu": self.config.cpu, "memory": self.config.memory},
            network_policy=NetworkPolicy(defaultAction="deny"),
            connection_config=self.connection(70),
        )

    def find(self, metadata):
        manager = SandboxManagerSync.create(self.connection())
        try:
            found = manager.list_sandbox_infos(
                SandboxFilter(metadata=metadata, page_size=100, page=1)
            )
            return [
                item.id
                for item in found.sandbox_infos
                if item.status.state.lower() not in {"terminated", "deleted", "failed"}
            ]
        finally:
            manager.close()

    def kill(self, remote_id):
        manager = SandboxManagerSync.create(self.connection())
        try:
            manager.kill_sandbox(remote_id)
        finally:
            manager.close()

    def initialize(self, sandbox, inputs, read_file):
        # 目录和 UID 必须与已验收镜像一致。
        result = sandbox.commands.run(
            "install -d -o 1000 -g 1000 -m 700 /workspace /outputs && install -d -o 0 -g 0 -m 755 /inputs /sources /skills",
            opts=RunCommandOpts(timeout=timedelta(seconds=10), uid=0, gid=0),
        )
        if result.exit_code != 0:
            raise ServiceUnavailableError("sandbox_not_ready", "沙箱镜像不满足工作区初始化要求。")
        for ref in inputs:
            parent = ref["path"].rsplit("/", 1)[0]
            # ID 和输入路径由宿主生成，不接收用户 Shell 文本。
            script = "import os; os.makedirs(" + repr(parent) + ", mode=0o755, exist_ok=True)"
            result = sandbox.commands.run(
                "python3 -c " + shlex.quote(script),
                opts=RunCommandOpts(timeout=timedelta(seconds=10), uid=0, gid=0),
            )
            if result.exit_code != 0:
                raise ServiceUnavailableError("sandbox_not_ready", "无法创建输入目录。")
            sandbox.files.write_files(
                [
                    WriteEntry(
                        path=ref["path"],
                        data=read_file(ref["id"]),
                        mode=0o444,
                        owner="root",
                        group="root",
                    )
                ]
            )
        # 输入目录及文件归 root 所有，UID 1000 不可写。


def load_verification(config):
    from datetime import UTC, datetime
    from pathlib import Path

    if not config.configured:
        raise ServiceUnavailableError(
            "sandbox_not_ready", "请先配置 OpenSandbox 端点、凭证、固定镜像和主机验收文件。"
        )
    if not ("@sha256:" in config.image or config.image.startswith("sha256:")):
        raise ServiceUnavailableError(
            "sandbox_not_ready", "工作负载镜像必须使用不可变 digest 或本机 image ID。"
        )
    try:
        value = json.loads(Path(config.verified_profile).read_text())
        valid = (
            value["endpoint"] == config.endpoint
            and value["image"] == config.image
            and value["runtime"] == "runsc"
            and value["uid"] == 1000
            and value["network"] == "offline"
            and value["pids_limit"] > 0
            and value["disk_bytes"] > 0
            and value["memory_bytes"] == config.memory_bytes
            and value["cpu_limit"] == config.cpu_units
            and value["privileged"] is False
            and value["host_mounts"] is False
            and 0
            <= (datetime.now(UTC) - datetime.fromisoformat(value["verified_at"])).total_seconds()
            < 86400
        )
    except (OSError, ValueError, KeyError, TypeError):
        valid = False
    if not valid:
        raise ServiceUnavailableError(
            "sandbox_not_ready", "沙箱主机验收文件缺失、过期或与当前配置不匹配，请重新运行验收。"
        )
    return value


@dataclass(frozen=True)
class CommandResult:
    output: str
    exit_code: int


class OpenSandboxOperations:
    def __init__(self, sandbox, timeout=60):
        self._sandbox, self._default_timeout = sandbox, timeout

    def materialize_readonly(self, files):
        # execd 以 root 写入已核验的只读资源，模型命令以 UID 1000 运行。
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
            raise InvalidInputError("sandbox_materialization_failed")
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
        return CommandResult(output="\n".join(chunks), exit_code=result.exit_code)

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
        # 收集前先停止 UID 1000 的全部工作负载，避免检查期间继续修改输出。
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

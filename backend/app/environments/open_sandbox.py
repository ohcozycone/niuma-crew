"""OpenSandbox SDK lifecycle adapter with owned metadata and no hidden retries."""

import json
import shlex
from datetime import timedelta
from urllib.parse import urlsplit

import httpx
from opensandbox import SandboxManagerSync, SandboxSync
from opensandbox.config import ConnectionConfigSync
from opensandbox.models import NetworkPolicy, SandboxFilter, WriteEntry
from opensandbox.models.execd import RunCommandOpts
from opensandbox.transport.retry import RetryPolicy

from app.errors import InvalidInputError, ServiceUnavailableError


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
        # These paths and UID are properties of the trusted execution image.
        result = sandbox.commands.run(
            "install -d -o 1000 -g 1000 -m 700 /workspace /outputs && install -d -o 0 -g 0 -m 755 /inputs",
            opts=RunCommandOpts(timeout=timedelta(seconds=10), uid=0, gid=0),
        )
        if result.exit_code != 0:
            raise ServiceUnavailableError("sandbox_not_ready", "沙箱镜像不满足工作区初始化要求。")
        for ref in inputs:
            parent = ref["path"].rsplit("/", 1)[0]
            # IDs are UUIDs and input paths are host-produced; no user shell text.
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
        # Input parents and files remain root-owned and non-writable to UID 1000.


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

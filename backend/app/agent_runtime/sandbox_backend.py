"""Deep Agents adapter: execute as an unprivileged user and bound SDK streams."""

import json
import shlex
from datetime import timedelta

from deepagents.backends.protocol import ExecuteResponse
from langchain_opensandbox import OpenSandboxBackend
from opensandbox.models import WriteEntry
from opensandbox.models.execd import RunCommandOpts
from opensandbox.models.execd_sync import ExecutionHandlersSync

from app.errors import InvalidInputError, PermissionDeniedError


class SandboxFileBackend(OpenSandboxBackend):
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

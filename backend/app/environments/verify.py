"""Run on the Linux sandbox host; emit evidence only after live checks pass."""

import argparse
import json
import os
import platform
import shlex
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from opensandbox.models.execd import RunCommandOpts

from app.config import load_config
from app.environments.open_sandbox import OpenSandboxProvider


def docker(*args):
    return json.loads(subprocess.check_output(["docker", *args], timeout=15))


def verify(config, disk_bytes: int):
    if platform.system() != "Linux":
        raise RuntimeError("必须在实际运行 OpenSandbox 的 Linux Docker 主机验收。")
    if not config.image or not ("@sha256:" in config.image or config.image.startswith("sha256:")):
        raise RuntimeError("请先将工作负载镜像固定为 digest 或本机 image ID。")
    provider = OpenSandboxProvider(config)
    metadata = {"niuma_deployment": config.deployment_id, "niuma_verification": str(uuid4())}
    sandbox = None
    try:
        sandbox = provider.create(metadata)
        provider.initialize(sandbox, [], lambda _: b"")
        ids = subprocess.check_output(["docker", "ps", "-q"], text=True, timeout=15).split()
        containers = docker("inspect", *ids) if ids else []
        matches = [
            item
            for item in containers
            if item["Config"]["Image"] == config.image
            and (
                sandbox.id in item["Name"]
                or sandbox.id in (item["Config"].get("Labels") or {}).values()
            )
        ]
        if len(matches) != 1:
            raise RuntimeError("无法将 SDK 沙箱唯一对应到实际 Docker 容器。")
        item = matches[0]
        host = item["HostConfig"]
        cpu = host.get("NanoCpus", 0) / 1e9 or host.get("CpuQuota", 0) / max(
            host.get("CpuPeriod", 0), 1
        )
        no_privilege = any("no-new-privileges" in value for value in host.get("SecurityOpt") or [])
        if (
            host["Runtime"] != "runsc"
            or host["Privileged"]
            or host["NetworkMode"] == "host"
            or host.get("PidMode") == "host"
            or host.get("IpcMode") == "host"
            or not no_privilege
            or host.get("PidsLimit", 0) <= 0
            or host.get("Memory", 0) <= 0
            or cpu <= 0
        ):
            raise RuntimeError("实际容器不满足 runsc、权限、网络或资源约束。")
        if any(mount["Type"] == "bind" for mount in item.get("Mounts", [])):
            raise RuntimeError("工作负载存在主机 bind mount，请改用受控镜像/命名卷并重新验收。")
        script = """import errno,json,os,socket
assert os.getuid()==1000 and os.getgid()==1000
targets=[('1.1.1.1',443),('example.com',443),('169.254.169.254',80),('2606:4700:4700::1111',443)]
for target in targets:
    try:
        c=socket.create_connection(target,timeout=1); c.close()
    except OSError: continue
    raise RuntimeError('unexpected network access')
path='/workspace/.niuma-disk-probe'
size=0
blocked=False
try:
    with open(path,'wb',buffering=0) as f:
        while size<=DISK_LIMIT:
            try: f.write(b'x'*1048576); size+=1048576
            except OSError as e:
                if e.errno not in (errno.ENOSPC,errno.EDQUOT): raise
                blocked=True; break
finally:
    if os.path.exists(path): os.unlink(path)
assert blocked, 'no effective filesystem quota'
print(json.dumps({'uid':os.getuid(),'disk_probe_bytes':size,'network':'offline'}))
""".replace("DISK_LIMIT", str(disk_bytes))
        result = sandbox.commands.run(
            "python3 -c " + shlex.quote(script),
            opts=RunCommandOpts(
                uid=1000, gid=1000, timeout=timedelta(seconds=60), working_directory="/workspace"
            ),
        )
        if result.exit_code != 0:
            raise RuntimeError("UID、网络或磁盘实际检查未通过；不会生成可用证明。")
        return {
            "endpoint": config.endpoint,
            "image": config.image,
            "runtime": "runsc",
            "uid": 1000,
            "network": "offline",
            "pids_limit": host["PidsLimit"],
            "disk_bytes": disk_bytes,
            "memory_bytes": host["Memory"],
            "cpu_limit": cpu,
            "privileged": False,
            "host_mounts": False,
            "verified_at": datetime.now(UTC).isoformat(),
            "container_id": item["Id"],
            "image_id": item["Image"],
        }
    finally:
        if sandbox is not None:
            try:
                provider.kill(sandbox.id)
            finally:
                sandbox.close()
        else:
            for id in provider.find(metadata):
                provider.kill(id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--disk-bytes", type=int, default=256 * 1024 * 1024)
    args = parser.parse_args()
    if not 64 * 1024 * 1024 <= args.disk_bytes <= 1024 * 1024 * 1024:
        parser.error("磁盘验收上限必须在 64 MiB–1 GiB 之间。")
    evidence = verify(load_config().sandbox, args.disk_bytes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".pending")
    with temporary.open("w") as stream:
        json.dump(evidence, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o600)
    temporary.replace(args.output)
    print("沙箱验收通过；已保存不含凭证的主机依据。")


if __name__ == "__main__":
    main()

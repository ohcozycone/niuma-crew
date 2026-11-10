"""为配套自托管服务初始化私有配置，不启动服务或更换已有密钥。"""

import argparse
import fcntl
import json
import os
import secrets
import tempfile
import tomllib
from pathlib import Path

from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]
LOCAL_ENDPOINT = "http://127.0.0.1:8080"


def initialize(directory: Path, app_env: Path) -> Path:
    directory = directory.absolute()
    if directory.is_symlink() or app_env.is_symlink():
        raise ValueError("配置路径不能是符号链接。")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    # 读取与落盘共用锁，避免并发初始化生成不同密钥。
    with (directory / "init.lock").open("a") as lock:
        os.chmod(directory / "init.lock", 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        values = dotenv_values(app_env)
        endpoint = values.get("OPENSANDBOX_ENDPOINT")
        if endpoint and endpoint != LOCAL_ENDPOINT:
            raise ValueError("应用已配置其他沙箱服务，请沿用该服务的凭据，不初始化本机服务。")
        server = directory / "sandbox.toml"
        if server.is_symlink():
            raise ValueError("服务配置不能是符号链接。")
        key = values.get("OPENSANDBOX_API_KEY")
        if server.exists():
            existing = tomllib.loads(server.read_text())["server"]["api_key"]
            if not isinstance(existing, str) or not existing or existing.startswith("REPLACE_"):
                raise ValueError("已有服务配置缺少有效密钥，请由部署者修正。")
            if key and key != existing:
                raise ValueError("应用与沙箱服务密钥不一致，未覆盖配置。")
            key = existing
        else:
            key = key or secrets.token_urlsafe(32)
            template = (ROOT / "deploy/opensandbox/sandbox.example.toml").read_text()
            # JSON 字符串也是合法 TOML 基本字符串，避免特殊字符改变配置结构。
            contents = template.replace('"REPLACE_WITH_PRIVATE_RANDOM_KEY"', json.dumps(key))
            with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as stream:
                temporary = Path(stream.name)
                try:
                    stream.write(contents)
                    stream.flush()
                    os.fsync(stream.fileno())
                    os.replace(temporary, server)
                finally:
                    temporary.unlink(missing_ok=True)
        os.chmod(server, 0o600)
        app_env.parent.mkdir(parents=True, exist_ok=True)
        updates = {
            "OPENSANDBOX_ENDPOINT": LOCAL_ENDPOINT,
            "OPENSANDBOX_API_KEY": key,
            "OPENSANDBOX_VERIFIED_PROFILE": str(directory / "verified-profile.json"),
        }
        for name, value in updates.items():
            if not values.get(name):
                set_key(str(app_env), name, value)
        os.chmod(app_env, 0o600)
        return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "backend/.data/opensandbox")
    parser.add_argument("--app-env", type=Path, default=ROOT / "backend/.env")
    args = parser.parse_args()
    try:
        server = initialize(args.directory, args.app_env)
    except (OSError, ValueError, KeyError):
        parser.exit(
            1,
            "初始化未完成：请检查配置路径、已有服务地址和两端密钥是否一致；未自动更换密钥。\n",
        )
    print(f"私有配置已就绪：{server}")
    print("已有密钥保持不变。请准备固定镜像、启动服务并完成主机验收；此命令不启用代码执行。")


if __name__ == "__main__":
    main()

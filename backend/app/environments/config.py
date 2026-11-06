"""One explicitly configured, self-hosted OpenSandbox execution profile."""

import math
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SandboxConfig:
    endpoint: str | None = None
    api_key: str | None = field(default=None, repr=False)
    image: str | None = None
    deployment_id: str = "niuma-crew"
    verified_profile: str | None = None
    ttl_seconds: int = 240
    command_seconds: int = 60
    max_concurrency: int = 1
    memory: str = "512Mi"
    cpu: str = "1"
    maintenance_seconds: int = 15

    def __post_init__(self):
        if (
            not 1 <= self.command_seconds <= 60
            or not 60 <= self.ttl_seconds <= 900
            or not 1 <= self.max_concurrency <= 16
        ):
            raise ValueError("沙箱命令时限为 1–60 秒，TTL 为 60–900 秒，并发为 1–16。")
        if not self.cpu or not self.memory or not self.deployment_id:
            raise ValueError("沙箱资源和部署标识不能为空。")
        if not math.isfinite(self.cpu_units) or self.cpu_units <= 0 or self.memory_bytes <= 0:
            raise ValueError("沙箱 CPU 和内存必须为有效正数。")

    @property
    def cpu_units(self):
        return float(self.cpu[:-1]) / 1000 if self.cpu.endswith("m") else float(self.cpu)

    @property
    def memory_bytes(self):
        value = re.fullmatch(r"([1-9][0-9]*)(Mi|Gi)", self.memory)
        if value is None:
            raise ValueError("沙箱内存必须使用 Mi 或 Gi。")
        return int(value[1]) * (1024 ** (2 if value[2] == "Mi" else 3))

    @property
    def configured(self) -> bool:
        return bool(self.endpoint and self.api_key and self.image and self.verified_profile)

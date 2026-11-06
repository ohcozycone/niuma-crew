"""Storage ceilings are deployment limits, never model parameters."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileConfig:
    directory: Path | None = None
    max_file_bytes: int = 10 * 1024 * 1024
    max_run_bytes: int = 40 * 1024 * 1024
    max_text_file_bytes: int = 128 * 1024
    max_text_workspace_bytes: int = 512 * 1024
    retention_seconds: int = 86400
    max_owner_bytes: int = 256 * 1024 * 1024
    max_evidence_run_bytes: int = 64 * 1024 * 1024
    max_evidence_owner_bytes: int = 512 * 1024 * 1024

    def __post_init__(self):
        for value in (
            self.max_file_bytes,
            self.max_run_bytes,
            self.max_owner_bytes,
            self.retention_seconds,
            self.max_evidence_run_bytes,
            self.max_evidence_owner_bytes,
        ):
            if type(value) is not int or value <= 0:
                raise ValueError("文件大小、配额与保留时间必须为正整数。")

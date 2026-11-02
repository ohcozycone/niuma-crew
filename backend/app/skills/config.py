"""Shared skill assets have a lifetime separate from personal attachments."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillConfig:
    directory: Path | None = None
    library_directory: Path | None = None

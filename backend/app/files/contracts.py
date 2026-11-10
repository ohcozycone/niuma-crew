from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FileRetentionCandidate:
    id: str
    origin_run_id: str | None


@dataclass(frozen=True, slots=True)
class FileMetadata:
    id: str
    name: str
    size: int
    media_type: str
    content_hash: str
    purpose: str
    origin_run_id: str | None

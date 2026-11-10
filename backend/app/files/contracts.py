from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FileRetentionCandidate:
    id: str
    origin_run_id: str | None

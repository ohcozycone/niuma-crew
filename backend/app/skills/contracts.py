"""Plain Skill data exchanged with employee assembly and the execution runtime."""

from typing import NotRequired, TypedDict


class SkillFileManifest(TypedDict):
    path: str
    content_hash: str
    size: int
    media_type: str
    is_text: bool


class SkillExecutionEntry(TypedDict):
    """A frozen method and its employee assignment, without ORM or file bytes."""

    skill_id: str
    name: str
    description: str
    instructions: str
    instructions_hash: str
    skill_revision: int
    assignment_revision: int
    assignment_created_at: str
    parameters: dict[str, object]
    # Supported pre-package snapshots do not contain portable source or files.
    skill_md: NotRequired[str]
    compatibility: NotRequired[str]
    package_manifest: NotRequired[list[SkillFileManifest]]

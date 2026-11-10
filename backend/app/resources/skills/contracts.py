from typing import NotRequired, TypedDict


class SkillFileManifest(TypedDict):
    path: str
    content_hash: str
    size: int
    media_type: str
    is_text: bool


class SkillExecutionEntry(TypedDict):
    skill_id: str
    name: str
    description: str
    instructions: str
    instructions_hash: str
    skill_revision: int
    assignment_revision: int
    assignment_created_at: str
    parameters: dict[str, object]
    # 包格式引入前的受支持快照没有源文件或支持文件。
    skill_md: NotRequired[str]
    compatibility: NotRequired[str]
    package_manifest: NotRequired[list[SkillFileManifest]]

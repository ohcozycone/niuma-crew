"""Interpret published Skill content once for configuration and execution consumers."""

from collections.abc import Collection
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.skills.contracts import SkillFileManifest
from app.skills.models import Skill
from app.skills.packages import file_manifest, legacy_skill_md, parse_skill_md


class SkillContent(Protocol):
    id: str
    skill_md: str
    name: str
    description: str
    instructions: str
    input_description: str
    output_description: str
    example: str


def source_for(record: SkillContent) -> str:
    """Choose the portable source, compiling legacy fields only when needed."""
    return record.skill_md or legacy_skill_md(record)


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    skill_id: str
    protocol_name: str
    name: str
    description: str
    instructions: str
    skill_md: str
    compatibility: str
    package_manifest: list[SkillFileManifest]
    instructions_hash: str
    skill_revision: int
    is_active: bool
    has_method_body: bool


def definition_from_record(record: Skill) -> SkillDefinition:
    """Read a definition in the caller's transaction without loading file bytes."""
    source = source_for(record)
    metadata = parse_skill_md(source)
    return SkillDefinition(
        skill_id=record.id,
        protocol_name=metadata["name"],
        name=record.name,
        description=metadata["description"] if record.skill_md else record.description,
        instructions=metadata["body"],
        skill_md=source,
        compatibility=metadata["metadata"].get("compatibility", ""),
        package_manifest=record.package_manifest or [file_manifest("SKILL.md", source.encode())],
        instructions_hash=sha256(source.encode()).hexdigest(),
        skill_revision=record.revision,
        is_active=record.is_active,
        # Legacy input/output/example sections describe a method; they do not
        # replace its missing working instructions. Standard packages use their body.
        has_method_body=bool(
            metadata["body"].strip() if record.skill_md else record.instructions.strip()
        ),
    )


def protocol_names(session: Session, skill_ids: Collection[str]) -> dict[str, str]:
    """Read only this page's names; legacy IDs need no body or support files."""
    if not skill_ids:
        return {}
    rows = session.execute(select(Skill.id, Skill.skill_md).where(Skill.id.in_(skill_ids)))
    return {
        skill_id: parse_skill_md(source)["name"] if source else "s-" + skill_id
        for skill_id, source in rows
    }


def readiness_reason(definition: SkillDefinition) -> str | None:
    if not definition.is_active:
        return "技能已停用"
    return None if definition.has_method_body else "技能正文为空"

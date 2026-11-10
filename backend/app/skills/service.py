from __future__ import annotations

import base64
import io
import zipfile
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, defer

from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.errors import ConflictError, NotFoundError, ServiceError
from app.infrastructure.database.session import Database
from app.infrastructure.database.transactions import reserve_writer
from app.schemas import Page
from app.skills.config import SkillConfig
from app.skills.definitions import definition_from_record, source_for
from app.skills.library import SkillLibrary, fingerprint
from app.skills.models import Skill
from app.skills.packages import (
    archive_files,
    checked_package_path,
    decode_file,
    file_manifest,
    legacy_skill_md,
    package_error,
    parse_skill_md,
    validate_files,
)
from app.skills.parameters import validate_parameters
from app.skills.schemas import PublicSkill, SkillCreate, SkillPatch, SkillRead, SkillSummary
from app.skills.storage import SkillBlobStore


def require_skill(session: Session, skill_id: str) -> Skill:
    skill = session.get(Skill, skill_id)
    if skill is None:
        raise NotFoundError("skill_not_found", "技能不存在。")
    return skill


class SkillService:
    def __init__(
        self,
        database: Database,
        config: SkillConfig | None = None,
        *,
        assignment_facts,
        assignment_counts,
    ):
        self.database = database
        self.assignment_facts = assignment_facts
        self.assignment_counts = assignment_counts
        self.config = config or SkillConfig()
        self.blobs = SkillBlobStore(
            self.config.directory or Path(database.engine.url.database).parent / "skill-assets"
        )
        self.library = SkillLibrary(
            self.config.library_directory or Path.home() / ".agents" / "skills"
        )
        if self.library.root == self.blobs.directory.expanduser().resolve():
            raise ValueError("SKILL_LIBRARY_DIR 与 SKILL_STORAGE_DIR 必须使用不同目录。")

    def read_blob(self, content_hash: str) -> bytes:
        return self.blobs.read(content_hash)

    def _response(self, skill: Skill, assignment_count=0) -> SkillRead:
        definition = definition_from_record(skill)
        return SkillRead.model_validate(
            {
                **SkillRead.model_validate(skill).model_dump(),
                "skill_md": definition.skill_md,
                "protocol_name": definition.protocol_name,
                "files": definition.package_manifest,
                "source_missing": bool(
                    skill.source_path
                    and (
                        not (self.library.root / skill.source_path).is_dir()
                        or (self.library.root / skill.source_path).is_symlink()
                    )
                ),
                "assignment_count": assignment_count,
            }
        )

    def _package(self, files):
        metadata = validate_files(files)
        manifest = []
        for path, body in sorted(files.items()):
            self.blobs.put(body)
            manifest.append(file_manifest(path, body))
        return {
            "skill_md": files["SKILL.md"].decode("utf-8"),
            "instructions": metadata["body"],
            "description": metadata["description"],
            "package_manifest": manifest,
        }

    def _files_input(self, items):
        files = {}
        for item in items:
            path = checked_package_path(item.path)
            if path in files:
                raise package_error("文件路径不能重复。")
            files[path] = decode_file(item.model_dump())
        return files

    def create(self, data: SkillCreate, actor: Actor) -> SkillRead:
        require_permission(actor, "skills:create")
        values = data.model_dump(exclude={"package_files"})
        if data.package_files is not None or data.skill_md:
            files = self._files_input(data.package_files) if data.package_files is not None else {}
            if data.skill_md:
                if "SKILL.md" in files and files["SKILL.md"] != data.skill_md.encode():
                    raise package_error("SKILL.md 与文件清单中的内容不一致。")
                files["SKILL.md"] = data.skill_md.encode()
            values.update(self._package(files))
            if values["name"] is None:
                values["name"] = parse_skill_md(values["skill_md"])["name"]
        elif values["name"] is None:
            raise package_error("请提供标准 Skill 包或填写技能名称。")
        # 旧输入只编译一次，之后与标准包使用同一份源文件。
        skill = Skill(**values)
        if not skill.id:
            skill.id = str(uuid4())
        source = source_for(skill)
        files = (
            files
            if data.package_files is not None or data.skill_md
            else {"SKILL.md": source.encode()}
        )
        source_path = parse_skill_md(source)["name"]
        with self.library.locked(), self.library.replace(source_path, files, None):
            with self.database.transaction() as session:
                reserve_writer(session, Skill.__table__)
                if session.scalar(select(Skill.id).where(Skill.source_path == source_path)):
                    raise ConflictError(
                        "skill_source_conflict", "同一标准技能已入库，请编辑已有技能。"
                    )
                skill = Skill(**values, id=skill.id, source_path=source_path)
                session.add(skill)
                session.flush()
                result = self._response(skill)
        return result

    def _published_files(self, skill: SkillRead) -> dict[str, bytes]:
        return {
            item.path: skill.skill_md.encode()
            if item.path == "SKILL.md"
            else self.read_blob(item.content_hash)
            for item in skill.files
        }

    def library_directory(self, actor: Actor) -> str:
        require_permission(actor, "skills:create")
        return str(self.library.root)

    def sync_library(self, actor: Actor):
        require_permission(actor, "skills:create")
        require_permission(actor, "skills:update")
        items = []
        with self.library.locked():
            with self.database.transaction() as session:
                existing = [self._response(row) for row in session.scalars(select(Skill))]
            # 补建旧记录的目录，保留 ID 与装配关系。
            for current in existing:
                if current.source_path:
                    continue
                name = current.protocol_name
                try:
                    files = self._published_files(current)
                    if self.library.path(name).exists():
                        if fingerprint(self.library.read(name)) != fingerprint(files):
                            raise ConflictError(
                                "skill_source_conflict", "同名目录内容不同，请先处理来源冲突。"
                            )
                        replacement = ExitStack()
                    else:
                        replacement = self.library.replace(name, files, None)
                    with replacement, self.database.transaction() as session:
                        reserve_writer(session, Skill.__table__)
                        row = require_skill(session, str(current.id))
                        if row.revision != current.revision or row.source_path is not None:
                            raise ConflictError("skill_source_changed", "技能已修改，请重新同步。")
                        if session.scalar(select(Skill.id).where(Skill.source_path == name)):
                            raise ConflictError("skill_source_conflict", "此目录已关联其他技能。")
                        row.source_path = name
                except (ServiceError, OSError) as error:
                    items.append(
                        dict(
                            name=name,
                            status="error",
                            message=error.message
                            if isinstance(error, ServiceError)
                            else "无法读写技能目录。",
                        )
                    )
            for name in self.library.names():
                try:
                    files = self.library.read(name)
                    values = self._package(files)
                    with self.database.transaction() as session:
                        reserve_writer(session, Skill.__table__)
                        row = session.scalar(select(Skill).where(Skill.source_path == name))
                        if row is None:
                            # 旧记录补建失败不能产生第二份能力。
                            unlinked = list(
                                session.scalars(select(Skill).where(Skill.source_path.is_(None)))
                            )
                            if any(
                                definition_from_record(item).protocol_name == name
                                for item in unlinked
                            ):
                                raise ConflictError(
                                    "skill_source_conflict",
                                    "已有同名技能尚未关联目录，请先处理冲突。",
                                )
                            row = Skill(name=name, source_path=name, **values)
                            session.add(row)
                            status = "added"
                        elif (definition_from_record(row).package_manifest) != values[
                            "package_manifest"
                        ]:
                            for key, value in values.items():
                                setattr(row, key, value)
                            row.revision += 1
                            status = "updated"
                        else:
                            status = "unchanged"
                        session.flush()
                        items.append(dict(name=name, status=status, skill_id=row.id))
                except (ServiceError, OSError) as error:
                    items.append(
                        dict(
                            name=name,
                            status="error",
                            message=error.message
                            if isinstance(error, ServiceError)
                            else "无法读取技能目录。",
                        )
                    )
            with self.database.transaction() as session:
                for row in session.scalars(select(Skill).where(Skill.source_path.is_not(None))):
                    if (
                        not (self.library.root / row.source_path).is_dir()
                        or (self.library.root / row.source_path).is_symlink()
                    ):
                        items.append(
                            dict(
                                name=row.source_path,
                                status="missing",
                                skill_id=row.id,
                                message="源目录缺失，保留已发布内容和员工装配。",
                            )
                        )
        return dict(directory=str(self.library.root), items=items)

    def get(self, skill_id: str, actor: Actor) -> SkillRead:
        require_permission(actor, "skills:read")
        return self._get(skill_id)

    def _get(self, skill_id: str) -> SkillRead:
        with self.database.transaction() as session:
            skill = require_skill(session, skill_id)
            count = self.assignment_counts(session, [skill_id]).get(skill_id, 0)
            return self._response(skill, count)

    def read_file(self, skill_id: str, path: str, actor: Actor) -> dict:
        require_permission(actor, "skills:read")
        path = checked_package_path(path)
        skill = self._get(skill_id)
        descriptor = next((item.model_dump() for item in skill.files if item.path == path), None)
        if descriptor is None:
            raise NotFoundError("skill_file_not_found", "技能文件不存在。")
        body = (
            skill.skill_md.encode()
            if path == "SKILL.md"
            else self.read_blob(descriptor["content_hash"])
        )
        return {
            "path": path,
            "media_type": descriptor["media_type"],
            "is_text": descriptor["is_text"],
            **(
                {"content": body.decode("utf-8")}
                if descriptor["is_text"]
                else {"content_base64": base64.b64encode(body).decode()}
            ),
        }

    def preview_import(self, data, actor: Actor):
        require_permission(actor, "skills:create")
        files = archive_files(data.archive_base64)
        metadata = validate_files(files)
        return {
            "name": data.name or metadata["name"],
            "protocol_name": metadata["name"],
            "description": metadata["description"],
            "skill_md": files["SKILL.md"].decode("utf-8"),
            "files": [file_manifest(path, body) for path, body in sorted(files.items())],
            "warnings": ["导入仅保存文件，不安装依赖或执行脚本；allowed-tools 不授予平台权限。"],
        }

    def import_package(self, data, actor: Actor) -> SkillRead:
        require_permission(actor, "skills:create")
        files = archive_files(data.archive_base64)
        metadata = validate_files(files)
        return self.create(
            SkillCreate(
                name=data.name or metadata["name"],
                category=data.category,
                package_files=[
                    {"path": path, "content_base64": base64.b64encode(body).decode()}
                    for path, body in files.items()
                ],
            ),
            actor,
        )

    def export_package(self, skill_id: str, actor: Actor) -> tuple[str, bytes]:
        require_permission(actor, "skills:read")
        skill = self._get(skill_id)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            for descriptor in skill.files:
                entry = descriptor.model_dump()
                body = (
                    skill.skill_md.encode()
                    if entry["path"] == "SKILL.md"
                    else self.read_blob(entry["content_hash"])
                )
                archive.writestr(f"{skill.protocol_name}/{entry['path']}", body)
        return skill.protocol_name + ".zip", stream.getvalue()

    def get_public(self, skill_id: str, actor: Actor) -> PublicSkill:
        """仅读展示字段，不加载技能包或内部指令。"""
        require_permission(actor, "skills:read_public")
        with self.database.transaction() as session:
            skill = session.scalar(
                select(Skill)
                .options(
                    defer(Skill.instructions),
                    defer(Skill.configuration_schema),
                    defer(Skill.skill_md),
                    defer(Skill.package_manifest),
                )
                .where(Skill.id == skill_id)
            )
            if skill is None:
                raise NotFoundError("skill_not_found", "技能不存在。")
            count = self.assignment_counts(session, [skill_id]).get(skill_id, 0)
            return PublicSkill.model_validate(skill).model_copy(
                update={"assignment_count": count or 0}
            )

    def list(
        self,
        *,
        actor: Actor,
        offset: int = 0,
        limit: int = 20,
        q: str = "",
        category: str | None = None,
        summary: bool = True,
    ) -> Page[SkillSummary | PublicSkill]:
        require_permission(actor, "skills:read" if summary else "skills:read_public")
        conditions = []
        if q.strip():
            conditions.append(
                or_(
                    Skill.name.icontains(q.strip(), autoescape=True),
                    Skill.description.icontains(q.strip(), autoescape=True),
                )
            )
        if category is not None:
            conditions.append(Skill.category == category)
        with self.database.transaction() as session:
            total = session.scalar(select(func.count()).select_from(Skill).where(*conditions))
            skills = session.scalars(
                select(Skill)
                .options(
                    defer(Skill.instructions),
                    defer(Skill.configuration_schema),
                    *(
                        [
                            defer(Skill.input_description),
                            defer(Skill.output_description),
                            defer(Skill.example),
                        ]
                        if summary
                        else []
                    ),
                )
                .where(*conditions)
                .order_by(Skill.created_at.desc(), Skill.id)
                .offset(offset)
                .limit(limit)
            )
            skills = list(skills)
            counts = self.assignment_counts(session, [skill.id for skill in skills])
            return Page(
                items=[
                    SkillSummary.model_validate(skill).model_copy(
                        update={"assignment_count": counts.get(skill.id, 0)}
                    )
                    if summary
                    else PublicSkill.model_validate(skill).model_copy(
                        update={"assignment_count": counts.get(skill.id, 0)}
                    )
                    for skill in skills
                ],
                total=total,
                offset=offset,
                limit=limit,
            )

    def update(self, skill_id: str, data: SkillPatch, actor: Actor) -> SkillRead:
        require_permission(actor, "skills:update")
        current = self._get(skill_id)
        changes = data.model_dump(
            exclude_unset=True, exclude={"expected_revision", "package_files"}
        )
        if "name" in changes and changes["name"] is None:
            changes["name"] = current.protocol_name
        if "skill_md" in data.model_fields_set or "package_files" in data.model_fields_set:
            current = self._get(skill_id)
            if current.revision != data.expected_revision:
                raise ConflictError(
                    "configuration_revision_conflict",
                    "技能已被修改，请刷新后核对；当前草稿已保留。",
                )
            files = (
                self._files_input(data.package_files)
                if "package_files" in data.model_fields_set
                else {
                    entry.path: current.skill_md.encode()
                    if entry.path == "SKILL.md"
                    else self.read_blob(entry.content_hash)
                    for entry in current.files
                }
            )
            if "skill_md" in data.model_fields_set:
                if (
                    "package_files" in data.model_fields_set
                    and files.get("SKILL.md") != data.skill_md.encode()
                ):
                    raise package_error("SKILL.md 与文件清单中的内容不一致。")
                files["SKILL.md"] = data.skill_md.encode()
            changes.update(self._package(files))
        with self.library.locked(), ExitStack() as filesystem:
            if "package_manifest" in changes:
                name = parse_skill_md(changes["skill_md"])["name"]
                if current.source_path and current.source_path != name:
                    raise ConflictError(
                        "skill_source_rename",
                        "已关联目录的标准名称不能直接修改；展示别名可以单独修改。",
                    )
                filesystem.enter_context(
                    self.library.replace(
                        name,
                        files,
                        fingerprint(self._published_files(current))
                        if current.source_path
                        else None,
                    )
                )
                changes["source_path"] = name
            elif any(
                key in changes
                for key in (
                    "description",
                    "instructions",
                    "input_description",
                    "output_description",
                    "example",
                )
            ):
                with self.database.transaction() as session:
                    legacy = not require_skill(session, skill_id).skill_md
                if legacy:
                    source = legacy_skill_md(SimpleNamespace(**{**current.model_dump(), **changes}))
                    filesystem.enter_context(
                        self.library.replace(
                            current.source_path or current.protocol_name,
                            {"SKILL.md": source.encode()},
                            fingerprint(self._published_files(current))
                            if current.source_path
                            else None,
                        )
                    )
                    changes["source_path"] = current.source_path or current.protocol_name
            with self.database.transaction() as session:
                return self._update_record(session, skill_id, data, changes)

    def _update_record(self, session, skill_id, data, changes):
        reserve_writer(session, Skill.__table__)
        skill = require_skill(session, skill_id)
        if skill.revision != data.expected_revision:
            raise ConflictError(
                "configuration_revision_conflict",
                "技能已被修改，请刷新后核对；当前草稿已保留。",
            )
        if "configuration_schema" in data.model_fields_set:
            for assignment in self.assignment_facts(session, [skill_id]):
                if assignment["enabled"]:
                    validate_parameters(data.configuration_schema, assignment["parameters"])
        if (
            skill.skill_md
            and any(
                key in changes
                for key in (
                    "description",
                    "instructions",
                    "input_description",
                    "output_description",
                    "example",
                )
            )
            and "skill_md" not in data.model_fields_set
            and "package_files" not in data.model_fields_set
        ):
            raise ConflictError(
                "skill_source_required",
                "此技能已使用标准包，简介和正文请编辑 SKILL.md 后保存。",
            )
        if any(getattr(skill, key) != value for key, value in changes.items()):
            skill.revision += 1
        for key, value in changes.items():
            setattr(skill, key, value)
        session.flush()
        count = self.assignment_counts(session, [skill_id]).get(skill_id, 0)
        return self._response(skill, count)

    def delete(self, skill_id: str, actor: Actor) -> None:
        require_permission(actor, "skills:delete")
        with self.library.locked(), ExitStack() as filesystem:
            # 写锁内读取目录关联，避免并发补建留下可重新出现的旧源文件。
            current = self._get(skill_id)
            if current.source_path:
                filesystem.enter_context(
                    self.library.replace(
                        current.source_path, None, fingerprint(self._published_files(current))
                    )
                )
            with self.database.transaction() as session:
                reserve_writer(session, Skill.__table__)
                skill = require_skill(session, skill_id)
                if self.assignment_counts(session, [skill_id]).get(skill_id, 0):
                    raise ConflictError("skill_in_use", "技能仍被员工装配，请先解除关联。")
                session.delete(skill)
                session.flush()

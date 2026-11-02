"""Skill definition HTTP endpoints."""

from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.dependencies import ActorDependency, SkillDependency, require_capability
from app.api.errors import SERVICE_ERROR_RESPONSES
from app.schemas import Page
from app.skills.schemas import (
    SkillCreate,
    SkillFileContent,
    SkillImport,
    SkillImportPreview,
    SkillLibraryRead,
    SkillPatch,
    SkillRead,
    SkillSummary,
    SkillSyncResult,
)

router = APIRouter(prefix="/api/skills", tags=["skills"], responses=SERVICE_ERROR_RESPONSES)


@router.get(
    "/library",
    response_model=SkillLibraryRead,
    dependencies=[Depends(require_capability("skills:create"))],
)
def skill_library(skills: SkillDependency, actor: ActorDependency):
    return {"directory": skills.library_directory(actor)}


@router.post(
    "/sync",
    response_model=SkillSyncResult,
    dependencies=[
        Depends(require_capability("skills:create")),
        Depends(require_capability("skills:update")),
    ],
)
def sync_skills(skills: SkillDependency, actor: ActorDependency) -> SkillSyncResult:
    return SkillSyncResult.model_validate(skills.sync_library(actor))


@router.post(
    "/import/preview",
    response_model=SkillImportPreview,
    dependencies=[Depends(require_capability("skills:create"))],
)
def preview_package(data: SkillImport, skills: SkillDependency, actor: ActorDependency):
    return skills.preview_import(data, actor)


@router.post(
    "/import",
    response_model=SkillRead,
    status_code=201,
    dependencies=[Depends(require_capability("skills:create"))],
)
def import_package(data: SkillImport, skills: SkillDependency, actor: ActorDependency) -> SkillRead:
    return skills.import_package(data, actor)


@router.post(
    "",
    response_model=SkillRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_capability("skills:create"))],
)
def create_skill(data: SkillCreate, skills: SkillDependency, actor: ActorDependency) -> SkillRead:
    return skills.create(data, actor)


@router.get(
    "", response_model=Page[SkillSummary], dependencies=[Depends(require_capability("skills:read"))]
)
def list_skills(
    skills: SkillDependency,
    actor: ActorDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    q: str = "",
    category: str | None = None,
) -> Page[SkillSummary]:
    return skills.list(actor=actor, offset=offset, limit=limit, q=q, category=category)


@router.get(
    "/{skill_id}",
    response_model=SkillRead,
    dependencies=[Depends(require_capability("skills:read"))],
)
def get_skill(skill_id: UUID, skills: SkillDependency, actor: ActorDependency) -> SkillRead:
    return skills.get(str(skill_id), actor)


@router.get(
    "/{skill_id}/files",
    response_model=SkillFileContent,
    response_model_exclude_none=True,
    dependencies=[Depends(require_capability("skills:read"))],
)
def get_skill_file(skill_id: UUID, path: str, skills: SkillDependency, actor: ActorDependency):
    return skills.read_file(str(skill_id), path, actor)


@router.get(
    "/{skill_id}/export",
    response_class=Response,
    responses={
        200: {"content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}}}
    },
    dependencies=[Depends(require_capability("skills:read"))],
)
def export_skill(skill_id: UUID, skills: SkillDependency, actor: ActorDependency):
    name, body = skills.export_package(str(skill_id), actor)
    return Response(
        body,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"},
    )


@router.patch(
    "/{skill_id}",
    response_model=SkillRead,
    dependencies=[Depends(require_capability("skills:update"))],
)
def update_skill(
    skill_id: UUID, data: SkillPatch, skills: SkillDependency, actor: ActorDependency
) -> SkillRead:
    return skills.update(str(skill_id), data, actor)


@router.delete(
    "/{skill_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_capability("skills:delete"))],
)
def delete_skill(skill_id: UUID, skills: SkillDependency, actor: ActorDependency) -> Response:
    skills.delete(str(skill_id), actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

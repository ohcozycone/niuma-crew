"""Bounded uploads and conversation-authorized downloads."""

import asyncio
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from app.api.dependencies import (
    ActorDependency,
    ConversationFilesDependency,
    FileDependency,
    LimiterDependency,
)
from app.auth.permissions import require_permission
from app.errors import InvalidInputError
from app.files.schemas import FileRead
from app.schemas import RecordID

router = APIRouter(tags=["files"])


@router.post("/api/files", status_code=201, response_model=FileRead)
async def upload(
    request: Request,
    actor: ActorDependency,
    files: FileDependency,
    limiter: LimiterDependency,
    name: str = Query(min_length=1, max_length=255),
):
    require_permission(actor, "conversations:create")
    limiter.consume(f"file-upload:{actor.user_id}", 20, 60)
    limit = files.config.max_file_bytes
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > limit:
            raise InvalidInputError("file_too_large", "文件超过上传上限。")
        content.extend(chunk)
    return await asyncio.to_thread(
        files.save,
        actor.user_id,
        name,
        bytes(content),
        media_type=request.headers.get("content-type", "application/octet-stream"),
    )


@router.get("/api/conversations/{conversation_id}/files", response_model=list[FileRead])
def listing(conversation_id: RecordID, actor: ActorDependency, files: ConversationFilesDependency):
    return files.list(actor, str(conversation_id))


@router.get(
    "/api/conversations/{conversation_id}/files/{file_id}",
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            }
        }
    },
)
def download(
    conversation_id: RecordID,
    file_id: UUID,
    actor: ActorDependency,
    files: ConversationFilesDependency,
):
    ref, content = files.download(actor, str(conversation_id), str(file_id))
    return Response(
        content,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(ref["name"], safe=""),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )

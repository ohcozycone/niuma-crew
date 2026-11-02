"""Save bytes before references; never accept a caller's host path."""

import asyncio
import hashlib
import logging
import os
import tempfile
import time
from datetime import timedelta
from pathlib import Path, PurePosixPath
from uuid import uuid4

from sqlalchemy import func, or_, select

from app.errors import InvalidInputError, NotFoundError
from app.files.models import StoredFile
from app.infrastructure.database.fields import utc_now
from app.infrastructure.database.transactions import reserve_writer


def safe_name(value: str) -> str:
    name = PurePosixPath(value.replace("\\", "/")).name
    if not name or name in (".", "..") or any(ord(c) < 32 for c in name):
        raise InvalidInputError("file_name_invalid", "文件名无效。")
    return name[:180]


def file_ref(row):
    return {
        "id": row.id,
        "name": row.name,
        "size": row.size,
        "media_type": row.media_type,
        "content_hash": row.content_hash,
        "purpose": row.purpose,
    }


class FileService:
    def __init__(self, database, config):
        self.database, self.config = database, config
        self.directory = config.directory or Path(database.engine.url.database).parent / "files"
        self.cleanup_after = None
        self.maintenance_task = None
        self.stop_event = None

    def save(
        self,
        owner_id,
        name,
        data: bytes,
        *,
        purpose="input",
        run_id=None,
        media_type="application/octet-stream",
    ):
        if len(data) > self.config.max_file_bytes:
            raise InvalidInputError("file_too_large", "文件超过上传或产物大小上限。")
        name = safe_name(name)
        key = str(uuid4())
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        free = os.statvfs(self.directory)
        if free.f_bavail * free.f_frsize < len(data) + 64 * 1024 * 1024:
            raise InvalidInputError("file_quota_exceeded", "文件存储剩余空间不足。")
        fd, temporary = tempfile.mkstemp(dir=self.directory, prefix=".pending-")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.directory / key)
            directory_fd = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            with self.database.transaction() as db:
                reserve_writer(db, StoredFile.__table__)
                owned = db.scalar(
                    select(func.coalesce(func.sum(StoredFile.size), 0)).where(
                        StoredFile.owner_user_id == owner_id
                    )
                )
                if owned + len(data) > self.config.max_owner_bytes:
                    raise InvalidInputError("file_quota_exceeded", "账号持久文件总量超过部署上限。")
                if run_id:
                    total = db.scalar(
                        select(func.coalesce(func.sum(StoredFile.size), 0)).where(
                            StoredFile.origin_run_id == run_id
                        )
                    )
                    if total + len(data) > self.config.max_run_bytes:
                        raise InvalidInputError("file_quota_exceeded", "本轮工作文件总量超过上限。")
                row = StoredFile(
                    owner_user_id=owner_id,
                    origin_run_id=run_id,
                    name=name,
                    media_type=media_type[:200],
                    size=len(data),
                    content_hash=hashlib.sha256(data).hexdigest(),
                    storage_key=key,
                    purpose=purpose,
                )
                db.add(row)
                db.flush()
                return file_ref(row)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def read(self, id: str) -> bytes:
        with self.database.transaction() as db:
            row = db.get(StoredFile, id)
        if row is None:
            raise NotFoundError("file_not_found", "文件不存在。")
        fd = os.open(self.directory / row.storage_key, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            if os.fstat(stream.fileno()).st_size != row.size:
                raise InvalidInputError("file_integrity_failed", "文件大小校验失败。")
            data = stream.read(self.config.max_file_bytes + 1)
        if len(data) != row.size or hashlib.sha256(data).hexdigest() != row.content_hash:
            raise InvalidInputError("file_integrity_failed", "文件内容校验失败。")
        return data

    def capture(self, db, ids, owner_id, *, allowed_ids=()):
        if len(ids) > 16 or len(ids) != len(set(ids)):
            raise InvalidInputError("file_selection_invalid", "输入文件不能重复且最多为 16 项。")
        result = []
        for id in ids:
            row = db.get(StoredFile, id)
            if (
                not row
                or (row.owner_user_id != owner_id and id not in allowed_ids)
                or (row.purpose != "input" and id not in allowed_ids)
            ):
                raise NotFoundError("file_not_found", "输入文件不存在或尚未发布到当前对话。")
            ref = file_ref(row)
            ref["path"] = f"/inputs/{row.id}/{row.name}"
            result.append(ref)
        if sum(ref["size"] for ref in result) > self.config.max_run_bytes:
            raise InvalidInputError("file_quota_exceeded", "输入文件总量超过上限。")
        return result

    def sources(self, run_id):
        with self.database.transaction() as db:
            return [
                file_ref(row)
                for row in db.scalars(
                    select(StoredFile).where(
                        StoredFile.origin_run_id == run_id, StoredFile.purpose == "source"
                    )
                )
            ]

    def sweep(self, retained):
        cutoff = utc_now() - timedelta(seconds=self.config.retention_seconds)
        removed = []
        with self.database.transaction() as db:
            reserve_writer(db, StoredFile.__table__)
            query = select(StoredFile).where(StoredFile.created_at < cutoff)
            if self.cleanup_after:
                created_at, id = self.cleanup_after
                query = query.where(
                    or_(
                        StoredFile.created_at > created_at,
                        (StoredFile.created_at == created_at) & (StoredFile.id > id),
                    )
                )
            candidates = list(
                db.scalars(query.order_by(StoredFile.created_at, StoredFile.id).limit(128))
            )
            self.cleanup_after = (
                (candidates[-1].created_at, candidates[-1].id) if len(candidates) == 128 else None
            )
            keep = retained(db, candidates)
            for row in candidates:
                if row.id not in keep:
                    removed.append(row.storage_key)
                    db.delete(row)
        for key in removed:
            (self.directory / key).unlink(missing_ok=True)
        if self.directory.exists():
            with self.database.transaction() as db:
                known = set(db.scalars(select(StoredFile.storage_key)))
            for path in self.directory.iterdir():
                if (
                    path.name not in known
                    and path.is_file()
                    and not path.is_symlink()
                    and path.stat().st_mtime < time.time() - self.config.retention_seconds
                ):
                    path.unlink(missing_ok=True)

    async def start(self, retained):
        self.stop_event = asyncio.Event()

        async def maintain():
            while not self.stop_event.is_set():
                try:
                    await asyncio.to_thread(self.sweep, retained)
                except Exception:
                    logging.getLogger(__name__).warning("files.maintenance_failed")
                try:
                    await asyncio.wait_for(self.stop_event.wait(), timeout=60)
                except TimeoutError:
                    pass

        self.maintenance_task = asyncio.create_task(maintain())

    async def stop(self):
        if self.stop_event is not None:
            self.stop_event.set()
        if self.maintenance_task is not None:
            await self.maintenance_task

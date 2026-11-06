"""Save bytes before references; never accept a caller's host path."""

import hashlib
from pathlib import Path, PurePosixPath

from sqlalchemy import func, select

from app.errors import InvalidInputError, NotFoundError
from app.files.models import StoredFile
from app.files.storage import FileStorage
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
        self.storage = FileStorage(self.directory)

    def prepare(self, name: str, data: bytes, media_type: str = "application/json") -> dict:
        """Write immutable bytes before entering a caller-owned database transaction."""
        if len(data) > self.config.max_file_bytes:
            raise InvalidInputError("file_too_large", "文件超过上传或产物大小上限。")
        return {
            "name": safe_name(name),
            "media_type": media_type[:200],
            "size": len(data),
            "content_hash": hashlib.sha256(data).hexdigest(),
            "storage_key": self.storage.write(data),
        }

    def register(self, db, owner_id, prepared, *, purpose="input", run_id=None):
        """Register bytes in the same transaction as the business reference."""
        reserve_writer(db, StoredFile.__table__)
        evidence = purpose == "evidence"
        scope = StoredFile.purpose == "evidence" if evidence else StoredFile.purpose != "evidence"
        owned = db.scalar(
            select(func.coalesce(func.sum(StoredFile.size), 0)).where(
                StoredFile.owner_user_id == owner_id, scope
            )
        )
        owner_limit = (
            self.config.max_evidence_owner_bytes if evidence else self.config.max_owner_bytes
        )
        run_limit = self.config.max_evidence_run_bytes if evidence else self.config.max_run_bytes
        if owned + prepared["size"] > owner_limit:
            raise InvalidInputError("file_quota_exceeded", "账号持久文件总量超过部署上限。")
        if run_id:
            total = db.scalar(
                select(func.coalesce(func.sum(StoredFile.size), 0)).where(
                    StoredFile.origin_run_id == run_id, scope
                )
            )
            if total + prepared["size"] > run_limit:
                raise InvalidInputError("file_quota_exceeded", "本轮工作文件总量超过上限。")
        row = StoredFile(owner_user_id=owner_id, origin_run_id=run_id, purpose=purpose, **prepared)
        db.add(row)
        db.flush()
        return row

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
        prepared = self.prepare(name, data, media_type)
        with self.database.transaction() as db:
            row = self.register(db, owner_id, prepared, purpose=purpose, run_id=run_id)
            return file_ref(row)

    def read(self, id: str) -> bytes:
        with self.database.transaction() as db:
            row = db.get(StoredFile, id)
        if row is None:
            raise NotFoundError("file_not_found", "文件不存在。")
        return self.storage.read(
            row.storage_key, row.size, row.content_hash, self.config.max_file_bytes
        )

    def capture(self, db, ids, owner_id, *, allowed_ids=()):
        if len(ids) > 16 or len(ids) != len(set(ids)):
            raise InvalidInputError("file_selection_invalid", "输入文件不能重复且最多为 16 项。")
        result = []
        for id in ids:
            row = db.get(StoredFile, id)
            if (
                not row
                or row.purpose == "evidence"
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

    @staticmethod
    def check_outputs(db, run_id, owner_id, refs):
        for ref in refs:
            row = db.get(StoredFile, ref["id"])
            if (
                row is None
                or row.origin_run_id != run_id
                or row.owner_user_id != owner_id
                or row.purpose != "output"
                or row.content_hash != ref["content_hash"]
            ):
                raise InvalidInputError("invalid_output_file", "成果文件不属于本次执行。")

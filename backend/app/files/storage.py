"""Atomic immutable byte storage, with bounded integrity-checked reads."""

import hashlib
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from app.errors import InvalidInputError


class FileStorage:
    def __init__(self, directory: Path):
        self.directory = directory

    def write(self, data: bytes) -> str:
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        free = os.statvfs(self.directory)
        if free.f_bavail * free.f_frsize < len(data) + 64 * 1024 * 1024:
            raise InvalidInputError("file_quota_exceeded", "文件存储剩余空间不足。")
        key = str(uuid4())
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
            return key
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def read(self, key: str, size: int, content_hash: str, limit: int) -> bytes:
        fd = os.open(self.directory / key, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            if os.fstat(stream.fileno()).st_size != size:
                raise InvalidInputError("file_integrity_failed", "文件大小校验失败。")
            data = stream.read(limit + 1)
        if len(data) != size or hashlib.sha256(data).hexdigest() != content_hash:
            raise InvalidInputError("file_integrity_failed", "文件内容校验失败。")
        return data

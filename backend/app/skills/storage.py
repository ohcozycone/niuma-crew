import hashlib
import os
import tempfile
from pathlib import Path

from app.errors import NotFoundError
from app.skills.packages import HASH, MAX_FILE_BYTES, package_error


class SkillBlobStore:
    def __init__(self, directory: Path):
        self.directory = directory

    def put(self, data: bytes) -> str:
        key = hashlib.sha256(data).hexdigest()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        free = os.statvfs(self.directory)
        if free.f_bavail * free.f_frsize < len(data) + 64 * 1024 * 1024:
            raise package_error("技能存储剩余空间不足。")
        destination = self.directory / key
        if destination.exists():
            if self.read(key) != data:
                raise package_error("技能字节校验失败。")
            return key
        fd, temporary = tempfile.mkstemp(dir=self.directory, prefix=".pending-")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            dir_fd = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return key

    def read(self, key: str) -> bytes:
        if not isinstance(key, str) or not HASH.fullmatch(key):
            raise NotFoundError("skill_file_not_found", "技能文件不存在。")
        try:
            fd = os.open(self.directory / key, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as stream:
                data = stream.read(MAX_FILE_BYTES + 1)
        except FileNotFoundError:
            raise NotFoundError("skill_file_not_found", "技能文件不存在或需要恢复备份。") from None
        if len(data) > MAX_FILE_BYTES or hashlib.sha256(data).hexdigest() != key:
            raise package_error("技能文件内容校验失败。")
        return data

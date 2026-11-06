"""Validate portable skill packages and store immutable, hash-addressed bytes.

No import operation executes a package or installs its dependencies. Old blobs
are deliberately retained: a running or recoverable Run may still reference them.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import math
import mimetypes
import os
import re
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

import yaml

from app.errors import InvalidInputError, NotFoundError
from app.skills.contracts import SkillFileManifest

MAX_ARCHIVE_BYTES = 12 * 1024 * 1024
MAX_PACKAGE_BYTES = 20 * 1024 * 1024
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TEXT_BYTES = 128 * 1024
MAX_FILES = 128
HASH = re.compile(r"^[0-9a-f]{64}$")


class UniqueSafeLoader(yaml.SafeLoader):
    """Ambiguous frontmatter must not silently replace one declaration."""


def _unique_mapping(loader, node, deep=False):
    values = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in values:
            raise yaml.constructor.ConstructorError(
                None, None, "duplicate or non-string key", key_node.start_mark
            )
        values[key] = loader.construct_object(value_node, deep=deep)
    return values


UniqueSafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def _bounded_metadata(value, depth=0, ancestors=frozenset(), budget=None):
    budget = [4096] if budget is None else budget
    budget[0] -= 1
    if depth > 20 or budget[0] < 0 or (isinstance(value, (dict, list)) and id(value) in ancestors):
        raise package_error("技能元数据嵌套、循环引用或节点数量超过上限。")
    if isinstance(value, dict):
        for child in value.values():
            _bounded_metadata(child, depth + 1, ancestors | {id(value)}, budget)
    elif isinstance(value, list):
        for child in value:
            _bounded_metadata(child, depth + 1, ancestors | {id(value)}, budget)
    elif type(value) not in (str, int, float, bool, type(None)) or (
        isinstance(value, float) and not math.isfinite(value)
    ):
        raise package_error("技能元数据只允许有限的普通 YAML 值。")


def package_error(message):
    return InvalidInputError("skill_package_invalid", message)


def checked_package_path(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode()) > 240
        or "\\" in value
        or "\x00" in value
        or any(ord(c) < 32 for c in value)
        or value.startswith("/")
        or ":" in value
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise package_error("技能文件必须使用包内相对路径，不得包含越界路径或特殊字符。")
    return str(PurePosixPath(value))


def parse_skill_md(text: str) -> dict:
    if not isinstance(text, str) or len(text.encode()) > MAX_TEXT_BYTES:
        raise package_error("SKILL.md 必须为不超过 128 KiB 的 UTF-8 文本。")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
    if not match:
        raise package_error("SKILL.md 必须以 YAML 元数据开始，并提供 name 和 description。")
    try:
        metadata = yaml.load(match.group(1), Loader=UniqueSafeLoader)
    except (yaml.YAMLError, RecursionError):
        raise package_error("SKILL.md 元数据不是有效的 YAML。") from None
    if not isinstance(metadata, dict):
        raise package_error("SKILL.md 元数据必须为对象。")
    _bounded_metadata(metadata)
    name, description = metadata.get("name"), metadata.get("description")
    if (
        not isinstance(name, str)
        or not name
        or len(name) > 64
        or name.startswith("-")
        or name.endswith("-")
        or "--" in name
        or any(not ((c.isalpha() and c.islower()) or c.isdigit() or c == "-") for c in name)
    ):
        raise package_error("协议名称必须是 1–64 位小写字母、数字和单连字符。")
    if not isinstance(description, str) or not description.strip() or len(description) > 1024:
        raise package_error("description 必须为 1–1024 字的用途说明。")
    if "compatibility" in metadata and (
        not isinstance(metadata["compatibility"], str) or len(metadata["compatibility"]) > 500
    ):
        raise package_error("compatibility 必须为不超过 500 字的环境说明。")
    if "metadata" in metadata and (
        not isinstance(metadata["metadata"], dict)
        or any(
            not isinstance(k, str) or not isinstance(v, str)
            for k, v in metadata["metadata"].items()
        )
    ):
        raise package_error("metadata 必须为字符串键值对象。")
    return {
        "name": name,
        "description": description.strip(),
        "body": text[match.end() :],
        "metadata": metadata,
    }


def legacy_skill_md(skill) -> str:
    name = "s-" + str(skill.id)
    description = skill.description.strip() or skill.name
    sections = [skill.instructions]
    for heading, value in (
        ("所需输入", skill.input_description),
        ("交付内容", skill.output_description),
        ("示例任务", skill.example),
    ):
        if value.strip():
            sections.append(f"## {heading}\n\n{value}")
    return (
        f"---\nname: {name}\ndescription: {json.dumps(description[:1024], ensure_ascii=False)}\n---\n"
        + "\n\n".join(sections)
    )


def decode_file(item) -> bytes:
    content, encoded = item.get("content"), item.get("content_base64")
    if (content is None) == (encoded is None):
        raise package_error("每个文件必须提供 content 或 content_base64 其中之一。")
    if content is not None:
        return content.encode("utf-8")
    try:
        if len(encoded) > MAX_FILE_BYTES * 4 // 3 + 8:
            raise ValueError
        return base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise package_error("文件内容不是有效的 Base64 或超过大小上限。") from None


def validate_files(files: dict[str, bytes]) -> dict:
    if not files or len(files) > MAX_FILES or sum(map(len, files.values())) > MAX_PACKAGE_BYTES:
        raise package_error("技能包最多 128 个文件，展开总量不能超过 20 MiB。")
    folded = set()
    for path, data in files.items():
        checked_package_path(path)
        if path.casefold() in folded:
            raise package_error("技能包存在重复路径或仅大小写不同的路径。")
        folded.add(path.casefold())
        if len(data) > MAX_FILE_BYTES:
            raise package_error("技能包单个文件不能超过 10 MiB。")
        if any(
            str(parent) in files for parent in PurePosixPath(path).parents if str(parent) != "."
        ):
            raise package_error("技能文件路径与父目录冲突。")
    if "SKILL.md" not in files:
        raise package_error("技能包根目录缺少 SKILL.md。")
    try:
        return parse_skill_md(files["SKILL.md"].decode("utf-8"))
    except UnicodeDecodeError:
        raise package_error("SKILL.md 必须使用 UTF-8 编码。") from None


def archive_files(encoded: str) -> dict[str, bytes]:
    try:
        if len(encoded) > MAX_ARCHIVE_BYTES * 4 // 3 + 8:
            raise ValueError
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise package_error("ZIP 内容无效或超过 12 MiB。") from None
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_FILES * 2:
                raise package_error("技能 ZIP 的文件与目录数量过多。")
            total = 0
            paths = set()
            collected = {}
            for info in infos:
                path = checked_package_path(info.filename.rstrip("/"))
                if path.casefold() in paths:
                    raise package_error("ZIP 存在重复路径。")
                paths.add(path.casefold())
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode) or (
                    stat.S_IFMT(mode) and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode))
                ):
                    raise package_error("ZIP 不允许链接或特殊文件。")
                if info.flag_bits & 1:
                    raise package_error("不支持加密 ZIP。")
                if info.is_dir():
                    continue
                total += info.file_size
                if (
                    info.file_size > MAX_FILE_BYTES
                    or total > MAX_PACKAGE_BYTES
                    or info.file_size > max(info.compress_size, 1) * 500
                ):
                    raise package_error("ZIP 展开大小或压缩比超过上限。")
                with archive.open(info) as stream:
                    body = stream.read(MAX_FILE_BYTES + 1)
                if len(body) != info.file_size:
                    raise package_error("ZIP 文件大小与清单不符。")
                collected[path] = body
            roots = [path for path in collected if PurePosixPath(path).name == "SKILL.md"]
            if len(roots) != 1 or len(PurePosixPath(roots[0]).parts) > 2:
                raise package_error("请导入单个技能包：根目录或唯一一层目录中应有一份 SKILL.md。")
            prefix = roots[0].removesuffix("SKILL.md")
            if prefix:
                if any(not path.startswith(prefix) for path in collected):
                    raise package_error("ZIP 包含技能根目录之外的文件。")
                collected = {path.removeprefix(prefix): value for path, value in collected.items()}
            metadata = validate_files(collected)
            if prefix and prefix.rstrip("/") != metadata["name"]:
                raise package_error("技能目录名必须与 SKILL.md 的 name 一致。")
            return collected
    except (zipfile.BadZipFile, RuntimeError, OSError, EOFError):
        raise package_error("无法读取有效的 ZIP 技能包。") from None


def file_manifest(path: str, data: bytes) -> SkillFileManifest:
    media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    try:
        data.decode("utf-8")
        is_text = b"\x00" not in data and len(data) <= MAX_TEXT_BYTES
    except UnicodeDecodeError:
        is_text = False
    return {
        "path": path,
        "content_hash": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "media_type": media_type,
        "is_text": is_text,
    }


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

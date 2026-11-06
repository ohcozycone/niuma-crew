"""加载显式选择的资料，保留固定正文和页/章节位置。"""

import hashlib
import re
from collections.abc import Iterator
from pathlib import Path

from app.errors import InvalidInputError
from app.knowledge.contracts import KnowledgeDocument, SourceBlock
from app.values import digest

MAX_DOCUMENT_BYTES = 128 * 1024

PARSER_VERSION = "poc-parser-v1"


def normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def markdown_sections(text: str) -> Iterator[tuple[str, str]]:
    lines: list[str] = []
    label, fence = "正文", ""
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        marker = re.match(r"(`{3,}|~{3,})", stripped)
        if marker:
            run = marker.group(1)
            if not fence:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence):
                fence = ""
        heading = None if fence else re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if heading:
            if lines:
                yield "".join(lines), label
            lines = []
            label = heading.group(1)
        lines.append(line)
    if lines:
        yield "".join(lines), label


def validate_text_upload(data: bytes, filename: str) -> str:
    """Validate bounded raw text without splitting or publishing an index."""
    if Path(filename).suffix.lower() not in {".md", ".txt"}:
        raise InvalidInputError(
            "knowledge_format_invalid", "当前支持 UTF-8 Markdown（.md）和 TXT 文件。"
        )
    if len(data) > MAX_DOCUMENT_BYTES:
        raise InvalidInputError("knowledge_file_too_large", "单份知识文档不能超过 128 KiB。")
    try:
        body = normalize(data.decode("utf-8-sig"))
    except UnicodeDecodeError:
        raise InvalidInputError(
            "knowledge_encoding_invalid", "请将文件另存为 UTF-8 编码后重新上传。"
        ) from None
    if not body.strip() or "\x00" in body:
        raise InvalidInputError("knowledge_text_invalid", "文档为空或包含非文本内容。")
    return body


def text_document(data: bytes, document_id: str, filename: str) -> KnowledgeDocument:
    """Only bounded UTF-8 text is accepted at the product upload boundary."""
    body = validate_text_upload(data, filename)
    sha = hashlib.sha256(data).hexdigest()
    version = digest([document_id, sha, body, "library-text-v1"])
    cursor, blocks = 0, []
    headings: list[tuple[int, str, str]] = []
    for i, (part, locator) in enumerate(markdown_sections(body)):
        end = cursor + len(part)
        block_id = digest([version, i, cursor, end])
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*(?:\n|$)", part)
        if heading:
            level = len(heading.group(1))
            while headings and headings[-1][0] >= level:
                headings.pop()
        blocks.append(
            SourceBlock(
                id=block_id,
                start=cursor,
                end=end,
                locator=locator,
                parent_id=headings[-1][1] if heading and headings else None,
                heading_path=tuple(item[2] for item in headings) + (locator,) if heading else (),
            )
        )
        if heading:
            headings.append((level, block_id, locator))
        cursor = end
    heading = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    title = heading.group(1).strip() if heading else Path(filename).stem
    return KnowledgeDocument(
        id=document_id,
        version=version,
        title=title[:180],
        text=body,
        blocks=tuple(blocks),
        original_sha256=sha,
        parser="library-text-v1",
    )

"""加载显式选择的资料，保留固定正文和页/章节位置。"""

import hashlib
import re
import zipfile
from collections.abc import Iterator
from pathlib import Path

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

from app.errors import InvalidInputError
from app.knowledge.contracts import KnowledgeDocument, SourceBlock, digest

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


class KnowledgeLoader(BaseLoader):
    """POC 受控文件加载器；当前不作为不可信上传接口开放。"""

    def __init__(self, path: Path, *, max_bytes: int = 10 * 1024 * 1024):
        self.path, self.max_bytes = path, max_bytes
        self.warnings: list[str] = []

    def lazy_load(self) -> Iterator[Document]:
        if self.path.stat().st_size > self.max_bytes:
            raise ValueError("document exceeds POC file budget")
        suffix = self.path.suffix.lower()
        if suffix in {".md", ".txt"}:
            text = normalize(self.path.read_text(encoding="utf-8-sig"))
            for body, label in markdown_sections(text):
                yield Document(page_content=body, metadata={"locator": label})
        elif suffix == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(self.path)
            if reader.is_encrypted or len(reader.pages) > 200:
                raise ValueError("encrypted PDF or PDF page budget exceeded")
            for i, page in enumerate(reader.pages, 1):
                contents = page.get_contents()
                if contents is not None and len(contents.get_data()) > self.max_bytes:
                    raise ValueError("PDF page content stream exceeds budget")
                text = normalize(page.extract_text() or "")
                if not text.strip():
                    self.warnings.append(f"PDF 第 {i} 页未抽取到文字；未执行 OCR")
                    continue
                yield Document(page_content=text + "\n\n", metadata={"locator": f"第 {i} 页"})
        elif suffix == ".docx":
            from docx import Document as DocxDocument
            from docx.table import Table

            with zipfile.ZipFile(self.path) as archive:
                if sum(i.file_size for i in archive.infolist()) > 4 * self.max_bytes:
                    raise ValueError("DOCX decompressed size exceeds budget")
            for i, item in enumerate(DocxDocument(str(self.path)).iter_inner_content(), 1):
                if isinstance(item, Table):
                    text = "\n".join(
                        "\t".join(cell.text for cell in row.cells) for row in item.rows
                    )
                    label = f"表格块 {i}"
                else:
                    text, label = item.text, f"段落 {i}"
                yield Document(page_content=normalize(text) + "\n\n", metadata={"locator": label})
            self.warnings.append("DOCX 仅抽取正文段落与表格，未验证批注、修订与图片")
        else:
            raise ValueError(f"unsupported document type: {suffix}")


def load_document(path: Path, document_id: str, title: str | None = None) -> KnowledgeDocument:
    """返回可校验的正文快照；重复文本靠区间而非文本匹配定位。"""
    loader = KnowledgeLoader(path)
    parts = list(loader.lazy_load())
    text = "".join(p.page_content for p in parts)
    if not text.strip():
        raise ValueError("empty extracted document")
    original = hashlib.sha256(path.read_bytes()).hexdigest()
    version = digest([document_id, original, text, PARSER_VERSION])
    blocks, cursor = [], 0
    for i, part in enumerate(parts):
        if not part.page_content:
            continue
        end = cursor + len(part.page_content)
        blocks.append(
            SourceBlock(
                id=digest([version, i, cursor, end]),
                start=cursor,
                end=end,
                locator=part.metadata["locator"],
            )
        )
        cursor = end
    return KnowledgeDocument(
        id=document_id,
        version=version,
        title=title or path.stem,
        text=text,
        blocks=tuple(blocks),
        original_sha256=original,
        parser=PARSER_VERSION,
        warnings=tuple(loader.warnings),
    )


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

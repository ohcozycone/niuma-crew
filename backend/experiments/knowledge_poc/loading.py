"""实验加载器，不用于正式上传入口。"""

from __future__ import annotations

import hashlib
import zipfile
from collections.abc import Iterator
from pathlib import Path

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

from app.knowledge.contracts import KnowledgeDocument, SourceBlock
from app.knowledge.loading import PARSER_VERSION, markdown_sections, normalize
from app.values import digest


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

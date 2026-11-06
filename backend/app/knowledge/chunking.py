"""LangChain 产生无重叠切分；平台按原区间增加有出处的重叠。"""

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.knowledge.contracts import (
    Chunk,
    ChunkingRules,
    KnowledgeDocument,
    SourceBlock,
    SourceSpan,
    TokenCount,
)
from app.values import digest


class ChunkLimitExceeded(ValueError):
    """Abort bounded product work before allocating an unpublishable chunk set."""


def split_document(
    document: KnowledgeDocument,
    preset: ChunkingRules,
    count: TokenCount,
    *,
    min_section_chars: int = 0,
    max_chunks: int | None = None,
) -> tuple[Chunk, ...]:
    """保证正文可逐字符重建；位置检查失败不回退到首次字符串匹配。"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=preset.chunk_tokens - preset.overlap_tokens,
        chunk_overlap=0,
        length_function=count,
        separators=["\n\n", "\n", "。", "；", "，", " ", ""],
        keep_separator=True,
        strip_whitespace=False,
    )
    chunks: list[Chunk] = []
    rule = digest(
        ["section-split-v2", preset.chunk_tokens, preset.overlap_tokens, min_section_chars]
        if min_section_chars
        else ["poc-split-v1", preset.chunk_tokens, preset.overlap_tokens]
    )
    for group in section_groups(
        document, preset.chunk_tokens - preset.overlap_tokens, min_section_chars, count
    ):
        group_start, group_end = group[0].start, group[-1].end
        original = document.text[group_start:group_end]
        pieces = splitter.split_text(original)
        if "".join(pieces) != original:
            raise ValueError("splitter altered canonical text")
        cursor, previous_start = group_start, group_start
        for piece in pieces:
            if max_chunks is not None and len(chunks) >= max_chunks:
                raise ChunkLimitExceeded("document exceeds chunk budget")
            start, end = cursor, cursor + len(piece)
            if cursor > group_start and preset.overlap_tokens:
                start = previous_start
                while start < cursor and count(document.text[start:cursor]) > preset.overlap_tokens:
                    start += 1
                while start < cursor and count(document.text[start:end]) > preset.chunk_tokens:
                    start += 1
            text = document.text[start:end]
            if count(text) > preset.chunk_tokens:
                raise ValueError("splitter exceeded token budget")
            locator = "；".join(
                dict.fromkeys(
                    " / ".join(block.heading_path) or block.locator
                    for block in group
                    if block.start < end and block.end > start
                )
            )
            chunks.append(
                Chunk(
                    id=digest([document.version, rule, start, end]),
                    document_id=document.id,
                    document_version=document.version,
                    title=document.title,
                    locator=locator,
                    start=start,
                    end=end,
                    spans=tuple(
                        SourceSpan(
                            block_id=block.id,
                            start=max(start, block.start) - block.start,
                            end=min(end, block.end) - block.start,
                        )
                        for block in group
                        if block.start < end and block.end > start
                    ),
                    text=text,
                    index_text=f"{document.title} / {locator}\n{text}",
                )
            )
            previous_start, cursor = cursor, end
    return tuple(chunks)


def section_groups(
    document: KnowledgeDocument, budget: int, minimum: int, count: TokenCount
) -> tuple[tuple[SourceBlock, ...], ...]:
    """Combine adjacent short siblings; a real parent identity prevents cross-topic joins."""
    groups: list[list[SourceBlock]] = []
    for block in document.blocks:
        short = 0 < count(document.text[block.start : block.end]) < minimum
        previous = groups[-1] if groups else []
        if (
            short
            and block.parent_id
            and previous
            and previous[-1].parent_id == block.parent_id
            and all(count(document.text[b.start : b.end]) < minimum for b in previous)
            and count(document.text[previous[0].start : block.end]) <= budget
        ):
            previous.append(block)
        else:
            groups.append([block])
    return tuple(tuple(group) for group in groups)

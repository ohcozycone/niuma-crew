"""Bounded reads of this Run's results, with their originating grant retained."""

import json
import re
from urllib.parse import urlsplit, urlunsplit

from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool

from app.agent_runtime.contracts import RuntimeFailure

RESULT_READER = "read_tool_result"
PREVIEW_CHARS = 3000
PAGE_CHARS = 12000
PAGE_BYTES = 8000


def structured_payload(data: dict) -> dict:
    payload = data.get("structured") or {}
    if isinstance(payload, dict):
        payload = payload.get("structured_content", payload)
    if not payload:
        content = data.get("content", [])
        text = (
            "\n".join(block.get("text", "") for block in content if isinstance(block, dict))
            if isinstance(content, list)
            else str(content)
        )
        try:
            payload = json.loads(text)
        except (TypeError, ValueError):
            payload = {}
    return payload if isinstance(payload, dict) else {}


def extracted_targets(tool_name: str, data: dict, status: str) -> list[str]:
    """Recognize extraction evidence, never infer it from a model's final prose."""
    if status != "succeeded":
        return []
    targets = []
    pages = structured_payload(data).get("results", [])
    for page in pages[:16] if isinstance(pages, list) else []:
        if not isinstance(page, dict):
            continue
        text = page.get("raw_content") or (
            page.get("content") if tool_name == "tavily_extract" else None
        )
        if isinstance(text, str) and text.strip() and isinstance(page.get("url"), str):
            targets.append(page["url"])
    return targets


def result_text(data: dict) -> str:
    # SDKs may include the same page in content and structured_content. Expose
    # one representation to the model; retain the original envelope for download.
    return json.dumps(structured_payload(data) or data, ensure_ascii=False, default=str)


class ToolResults:
    def __init__(self, snapshot, resources):
        self.resources = resources
        self.bindings = {item["binding_id"]: item for item in snapshot.get("tools", [])}

    def load(self, result_id: str) -> dict:
        # Validate membership before reading any bytes; an arbitrary file id must
        # not become a way to read attachments or another Run's stored sources.
        if not any(
            ref["id"] == result_id and ref["name"].startswith("tool-result-")
            for ref in self.resources.list_sources()
        ):
            raise RuntimeFailure("tool_not_allowed")
        try:
            envelope = json.loads(self.resources.read_file(result_id))
        except (ValueError, TypeError):
            raise RuntimeFailure("tool_result_unknown") from None
        meta = envelope.get("platform_result", {})
        binding = self.bindings.get(meta.get("binding_id"))
        if not binding or binding["kind"] == "native" or not isinstance(envelope.get("data"), dict):
            raise RuntimeFailure("tool_not_allowed")
        return envelope

    def reader_tool(self):
        def read(result_id: str, offset: int = 0, limit: int = 6000) -> str:
            envelope = self.load(result_id)
            text = result_text(envelope["data"])
            if (
                type(offset) is not int
                or type(limit) is not int
                or not (0 <= offset <= len(text) and 1 <= limit <= PAGE_CHARS)
            ):
                raise RuntimeFailure("tool_arguments_invalid")
            chunk = text[offset : offset + limit].encode()[:PAGE_BYTES].decode(errors="ignore")
            end = offset + len(chunk)
            return json.dumps(
                {
                    "result_id": result_id,
                    "offset": offset,
                    "end": end,
                    "total_chars": len(text),
                    "next_offset": end if end < len(text) else None,
                    "text": chunk,
                },
                ensure_ascii=False,
            )

        return StructuredTool.from_function(
            read,
            name=RESULT_READER,
            description=(
                "分段读取本轮 MCP 已返回的结果。使用结果中的 result_id 与 next_offset；"
                "offset/limit 按字符计算，每次最多12000字符且8000字节，以返回的next_offset继续。"
                "不能读取任意文件或发起外部操作。"
            ),
        )


def normalize_url(value: str) -> str:
    parts = urlsplit(value)
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, "")
    )


def requested_web_reads(content: str) -> set[str]:
    # A narrow request class, not a general intent classifier: a URL mention or
    # URL-format question alone is not a request to retrieve a page.
    verb = r"(?:读取|阅读|读下|读一下|提取|总结|\b(?:read|extract|summarize)\b)"
    heading = re.search(verb + r"[^，。；\n]{0,8}(?:网页|页面|链接)", content, re.I)
    targets = set()
    for match in re.finditer(r"https?://[^\s<>\"'`]+", content):
        before, after = content[max(0, match.start() - 48) : match.start()], content[match.end() :]
        if (
            heading
            or re.search(
                verb + r"\s*(?:(?:这个|该|以下|此)?(?:网页|页面|链接|URL))?\s*[:：]?\s*$",
                before,
                re.I,
            )
            or re.match(r"\s*(?:页面内容|网页内容|页面|网页|的内容)?\s*" + verb, after, re.I)
        ):
            targets.add(normalize_url(match[0].rstrip(".,;!?，。；！？）)]>")))
    return targets


def verify_web_reads(content: str, messages: list, results: ToolResults) -> None:
    targets = requested_web_reads(content)
    if not targets:
        return
    coverage: dict[str, list[tuple[int, int]]] = {}
    current_ids = {item["id"] for item in results.resources.list_sources()}
    for message in messages:
        if not isinstance(message, ToolMessage) or message.status != "success":
            continue
        try:
            value = json.loads(message.content)
        except (TypeError, ValueError):
            continue
        if not isinstance(value, dict) or value.get("result_id") not in current_ids:
            continue
        if message.name == RESULT_READER:
            start, end = value.get("offset"), value.get("end")
        else:
            start, end = 0, value.get("preview_end")
        if type(start) is int and type(end) is int:
            coverage.setdefault(value["result_id"], []).append((start, end))
    confirmed = set()
    for result_id, ranges in coverage.items():
        envelope = results.load(result_id)
        text = result_text(envelope["data"])
        end = 0
        for lower, upper in sorted(ranges):
            if lower > end:
                break
            end = max(end, upper)
        if end < len(text):
            continue
        confirmed.update(
            normalize_url(url) for url in envelope["platform_result"].get("extracted_urls", [])
        )
    if not targets <= confirmed:
        raise RuntimeFailure("external_read_unverified")

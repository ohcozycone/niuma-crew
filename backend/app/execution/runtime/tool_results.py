"""Bounded reads of this Run's results, with their originating grant retained."""

import json
import re
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

from app.execution.contracts import RuntimeFailure
from app.execution.runtime.concurrency import run_sync

PREVIEW_CHARS = 3000
PAGE_CHARS = 12000
PAGE_BYTES = 8000


def _result_text(data: dict) -> str:
    # SDKs may include the same page in content and structured_content. Expose
    # one representation to the model; retain the original envelope for download.
    return json.dumps(_structured_payload(data) or data, ensure_ascii=False, default=str)


class ToolResults:
    def __init__(self, snapshot, resources):
        self.resources = resources
        self.source_files_readable = any(
            b["kind"] == "native"
            and b["tool_name"] == "read_file"
            and "/sources" in b["scope_policy"].get("read_roots", [])
            for b in snapshot.get("tools", [])
        )
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

    def read_page(self, result_id: str, offset: int = 0, limit: int = 6000) -> str:
        envelope = self.load(result_id)
        text = _result_text(envelope["data"])
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

    async def preserve(self, invocation, data, status):
        raw = _result_text(data)
        binding = self.bindings[invocation.binding_id]
        envelope = {
            "platform_result": {
                "binding_id": binding["binding_id"],
                "extracted_urls": _extracted_targets(binding["tool_name"], data, status),
            },
            "data": data,
        }
        ref = await run_sync(
            self.resources.save_source,
            "tool-result-" + invocation.key.removeprefix("tool:")[:64] + ".json",
            json.dumps(envelope, ensure_ascii=False).encode(),
        )
        raw_path = f"/sources/{ref['id']}/{ref['name']}"
        payload = _structured_payload(data)
        sources = []
        for failed, items in (
            ((False, payload.get("results", [])), (True, payload.get("failed_results", [])))
            if isinstance(payload, dict)
            else ()
        ):
            for page in items[:16] if isinstance(items, list) else []:
                if not isinstance(page, dict):
                    continue
                source = {
                    "url": page.get("url"),
                    "title": str(page.get("title", ""))[:200],
                    "retrieved_at": datetime.now(UTC).isoformat(),
                    "status": "failed" if failed else "succeeded",
                    "full_text": False,
                    "content_kind": "extracted"
                    if binding["tool_name"] == "tavily_extract"
                    else "snippet",
                    "file_id": ref["id"],
                    "path": raw_path,
                }
                text = page.get("raw_content") or page.get("content")
                source["text_obtained"] = (
                    isinstance(text, str) and bool(text.strip()) and not failed
                )
                if binding["tool_name"] == "tavily_extract" and not (
                    isinstance(text, str) and text.strip()
                ):
                    source.update(status="failed", full_text=False)
                if isinstance(text, str) and not failed:
                    page_ref = await run_sync(
                        self.resources.save_source, f"page-{len(sources) + 1}.txt", text.encode()
                    )
                    source.update(
                        file_id=page_ref["id"], path=f"/sources/{page_ref['id']}/{page_ref['name']}"
                    )
                sources.append(source)
        preview = raw[:PREVIEW_CHARS]
        # Downloadable result files do not grant the model filesystem access.
        # Only advertise paths it can actually read through the authorized tool.
        model_result = {
            "preview": preview,
            "result_id": ref["id"],
            "preview_end": len(preview),
            "total_chars": len(raw),
            "next_offset": len(preview) if len(preview) < len(raw) else None,
            "truncated": len(preview) < len(raw),
            "source_files_readable": self.source_files_readable,
            "sources": sources
            if self.source_files_readable
            else [
                {key: value for key, value in source.items() if key != "path"} for source in sources
            ],
        }
        if self.source_files_readable:
            model_result["raw_result"] = raw_path
        content = json.dumps(model_result, ensure_ascii=False)
        # Keep valid JSON even for large URLs/descriptions. Dropping optional
        # preview entries must not destroy the cursor for the immutable result.
        while len(content.encode()) > 24000:
            if model_result["sources"]:
                model_result["sources"] = model_result["sources"][:-1]
            else:
                model_result["preview"] = model_result["preview"][
                    : len(model_result["preview"]) // 2
                ]
                model_result["preview_end"] = len(model_result["preview"])
                model_result["next_offset"] = model_result["preview_end"]
                model_result["truncated"] = True
            content = json.dumps(model_result, ensure_ascii=False)
        return (
            content,
            {"file_id": ref["id"], "query": invocation.arguments.get("query")},
            tuple(sources),
        )

    def verify_web_reads(self, content: str, observations: list) -> None:
        targets = _requested_web_reads(content)
        if not targets:
            return
        coverage: dict[str, list[tuple[int, int]]] = {}
        current_ids = {item["id"] for item in self.resources.list_sources()}
        for observation in observations:
            result_id, start, end = observation.result_id, observation.start, observation.end
            if result_id in current_ids and type(start) is int and type(end) is int:
                coverage.setdefault(result_id, []).append((start, end))
        confirmed = set()
        for result_id, ranges in coverage.items():
            envelope = self.load(result_id)
            text = _result_text(envelope["data"])
            end = 0
            for lower, upper in sorted(ranges):
                if lower > end:
                    break
                end = max(end, upper)
            if end < len(text):
                continue
            confirmed.update(
                _normalize_url(url) for url in envelope["platform_result"].get("extracted_urls", [])
            )
        if not targets <= confirmed:
            raise RuntimeFailure("external_read_unverified")


def _structured_payload(data: dict) -> dict:
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


def _extracted_targets(tool_name: str, data: dict, status: str) -> list[str]:
    """Recognize extraction evidence, never infer it from a model's final prose."""
    if status != "succeeded":
        return []
    targets = []
    pages = _structured_payload(data).get("results", [])
    for page in pages[:16] if isinstance(pages, list) else []:
        if not isinstance(page, dict):
            continue
        text = page.get("raw_content") or (
            page.get("content") if tool_name == "tavily_extract" else None
        )
        if isinstance(text, str) and text.strip() and isinstance(page.get("url"), str):
            targets.append(page["url"])
    return targets


def _normalize_url(value: str) -> str:
    parts = urlsplit(value)
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, "")
    )


def _requested_web_reads(content: str) -> set[str]:
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
            targets.add(_normalize_url(match[0].rstrip(".,;!?，。；！？）)]>")))
    return targets

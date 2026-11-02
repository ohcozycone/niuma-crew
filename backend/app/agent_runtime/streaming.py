"""Run-local model content; SDK chunks merge here, writes happen at boundaries."""

from langchain_core.messages import AIMessage, AIMessageChunk

from app.agent_runtime.contracts import ContentUpdate, RuntimeFailure


def truncate(text: str, limit: int) -> str:
    return text.encode()[:limit].decode(errors="ignore")


class RunProgress:
    def __init__(self, output_limit: int, reasoning_limit: int, recovered=()):
        self.output_limit, self.reasoning_limit = output_limit, reasoning_limit
        self.bindings: dict[tuple[str, int], str] = {}
        self.chunks: dict[str, AIMessageChunk] = {}
        self.contents: dict[str, ContentUpdate] = {item.key: item for item in recovered}
        self.dirty: dict[str, ContentUpdate] = {}
        self.finished: set[str] = set()

    def bind(self, key: str, metadata: dict) -> None:
        self.bindings[(metadata["langgraph_node"], metadata["langgraph_step"])] = key

    def feed(self, chunk: AIMessageChunk, metadata: dict) -> None:
        key = self.bindings.get((metadata.get("langgraph_node"), metadata.get("langgraph_step")))
        if key is None:
            raise RuntimeFailure("sdk_stream_invalid")
        if key in self.finished:
            return  # The complete middleware response is already authoritative.
        # SDK aggregation may still own and mutate the same chunk/content dictionaries.
        chunk = chunk.model_copy(deep=True)
        previous = self.chunks.get(key)
        self.chunks[key] = previous + chunk if previous is not None else chunk
        self.record(key, self.chunks[key])

    def record(self, key: str, message: AIMessage, *, complete: bool = False) -> ContentUpdate:
        reasoning = "".join(
            block.get("reasoning", "")
            for block in message.content_blocks
            if block["type"] == "reasoning" and isinstance(block.get("reasoning"), str)
        )
        remaining = max(
            0,
            self.reasoning_limit
            - sum(
                len(value.reasoning_text.encode()) for k, value in self.contents.items() if k != key
            ),
        )
        value = ContentUpdate(
            key,
            truncate(str(message.text), self.output_limit),
            truncate(reasoning, remaining),
            len(reasoning.encode()) > remaining,
            bool(message.tool_calls or getattr(message, "tool_call_chunks", None)),
        )
        if self.contents.get(key) != value:
            self.contents[key] = self.dirty[key] = value
        if complete:
            self.finished.add(key)
            self.chunks.pop(key, None)
            self.dirty.pop(key, None)
        return value

    def pending(self) -> list[ContentUpdate]:
        return list(self.dirty.values())

    def acknowledge(self, saved: list[ContentUpdate]) -> None:
        for value in saved:
            if self.dirty.get(value.key) is value:
                self.dirty.pop(value.key)

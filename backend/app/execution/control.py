"""Per-execution authorization and durable action boundaries."""

import asyncio
from collections.abc import Callable

from app.agent_runtime.contracts import ContentUpdate
from app.execution.errors import ExecutionFailure
from app.tools.contracts import ToolInvocation, ToolOutcome, ToolPermit


def truncate(text: str, limit: int) -> str:
    return text.encode()[:limit].decode(errors="ignore")


class ContentBuffer:
    def __init__(self):
        self.contents = {}
        self.dirty = {}

    def record(self, update):
        if self.contents.get(update.key) != update:
            self.contents[update.key] = self.dirty[update.key] = update

    def pending(self):
        return list(self.dirty.values())

    def acknowledge(self, saved):
        for value in saved:
            if self.dirty.get(value.key) is value:
                self.dirty.pop(value.key)


class RunControl:
    def __init__(
        self,
        run_id: str,
        store,
        authorize: Callable[[set[str]], None],
        progress: ContentBuffer | None = None,
    ):
        self.run_id, self._store, self.authorize, self.progress = (
            run_id,
            store,
            authorize,
            progress or ContentBuffer(),
        )
        self.action_skills = {}
        self.active_skills: set[str] = set()
        self.action_keys: dict[str, str] = {}
        self.recovered_usage = None

    async def start_model(self):
        return await asyncio.to_thread(
            self._store.start_model, self.run_id, lambda db: self.authorize(self.active_skills, db)
        )

    async def guard(self, extra=()):
        state, _ = await asyncio.to_thread(self._store.state, self.run_id)
        if state != "running":
            raise ExecutionFailure(
                "user_cancelled" if state == "cancelling" else "runtime_interrupted"
            )
        await asyncio.to_thread(self.authorize, self.active_skills | set(extra))

    async def start(self, key, kind, details=None, skill_id=None, *, budget=None):
        await self.guard([skill_id] if skill_id else [])
        self.action_skills[key] = (kind, skill_id)
        self.action_keys[key] = await asyncio.to_thread(
            self._store.start_action,
            self.run_id,
            key,
            kind,
            details,
            skill_id,
            budget=budget,
            authorize=lambda db: self.authorize(
                self.active_skills | ({skill_id} if skill_id else set()), db
            ),
        )

    async def finish(
        self, key, status="succeeded", error=None, details=None, usage=None, content=None
    ):
        if content is not None:
            self.progress.record(content)
        await asyncio.to_thread(
            self._store.finish_action,
            self.run_id,
            self.action_keys.get(key, key),
            status,
            error,
            details,
            usage,
            content,
        )

        kind, skill_id = self.action_skills.get(key, (None, None))
        if kind == "skill_activation" and skill_id and status == "succeeded":
            self.active_skills.add(skill_id)

    def restore(self, restored):
        self.active_skills.update(restored["active_skills"])
        self.progress.contents.update({item.key: item for item in restored["contents"]})
        self.recovered_usage = restored["usage"]

    async def report_content(self, update: ContentUpdate):
        self.progress.record(update)

    async def checkpoint_saved(self, reference: str):
        await asyncio.to_thread(self._store.checkpoint_saved, self.run_id, reference)

    async def begin_tool(self, invocation: ToolInvocation) -> ToolPermit:
        return await asyncio.to_thread(
            self._store.begin_tool,
            self.run_id,
            invocation,
            lambda db: self.authorize(self.active_skills, db, invocation=invocation),
        )

    async def guard_tool(self, invocation: ToolInvocation) -> None:
        await self.guard()
        await asyncio.to_thread(self.authorize, self.active_skills, invocation=invocation)

    async def complete_tool(self, permit: ToolPermit, outcome: ToolOutcome) -> None:
        await asyncio.to_thread(
            self._store.finish_action,
            self.run_id,
            permit.action_key,
            outcome.status,
            "tool_upstream_failed" if outcome.status == "failed" else None,
            {
                "result_bytes": len(outcome.content.encode()),
                "sources": list(outcome.sources),
                "result_file_id": outcome.data.get("file_id"),
                "query": str(outcome.data.get("query") or "")[:2048],
            },
            result_payload={
                "content": outcome.content,
                "status": outcome.status,
                "data": outcome.data,
            },
        )

    async def flush(self):
        pending = self.progress.pending()
        if pending:
            await asyncio.to_thread(self._store.update_progress, self.run_id, pending)
            self.progress.acknowledge(pending)

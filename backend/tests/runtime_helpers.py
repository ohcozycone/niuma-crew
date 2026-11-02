"""A RuntimeControl implementation with no application database or services."""

from app.agent_runtime.contracts import ContentUpdate


class MemoryControl:
    def __init__(self):
        self.model_calls = 0
        self.actions = {}
        self.contents: list[ContentUpdate] = []
        self.references = []

    async def guard(self, extra=()):
        pass

    async def start_model(self):
        self.model_calls += 1
        key = f"model:{self.model_calls}"
        await self.start(key, "model_call")
        return self.model_calls, key

    async def start(self, key, kind, details=None, skill_id=None, *, budget=None):
        self.actions[key] = {"kind": kind, "status": "running", "budget": budget}

    async def finish(
        self, key, status="succeeded", error=None, details=None, usage=None, content=None
    ):
        self.actions[key]["status"] = status
        if content:
            self.contents.append(content)

    async def report_content(self, update):
        self.contents.append(update)

    async def checkpoint_saved(self, reference):
        self.references.append(reference)

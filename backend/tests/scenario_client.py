"""Run lifecycle scenarios through current reply URLs.

Older scenarios use execution IDs to inspect the worker. This test-only adapter
resolves those IDs and translates assertions; no compatibility routes or result
records exist in the application. New wire-contract tests use plain TestClient.
"""

import json
import re
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import URL, select

from app.conversations.models import ConversationRun
from app.execution.models import Run
from app.infrastructure.database.session import Database, DatabaseConfig


class ScenarioProtocol:
    def binding(self, run_id):
        with self.app.state.database.transaction() as db:
            return db.get(ConversationRun, run_id)

    def execution(self, value):
        with self.app.state.database.transaction() as db:
            binding = db.scalar(
                select(ConversationRun).where(ConversationRun.reply_message_id == value["id"])
            )
            row = db.get(Run, binding.run_id)
        steps = value["steps"]
        model = (
            next((step for step in reversed(steps) if step["kind"] == "model_call"), None)
            if value["status"] in ("queued", "running", "cancelling")
            else None
        )
        activity = (
            next((step for step in reversed(steps) if step["status"] == "running"), None)
            if value["status"] in ("queued", "running", "cancelling")
            else None
        )
        return {
            **value,
            "id": row.id,
            "revision": value["version"],
            "actions_revision": row.actions_revision,
            "origin_kind": row.origin_kind,
            "trigger": row.trigger,
            "mode": row.mode,
            "retry_of_run_id": row.retry_of_run_id,
            "input_message_id": binding.input_message_id,
            "output_message_id": value["id"],
            "assistant_content": value["content"]
            if value["status"] not in ("queued", "running", "cancelling")
            else "",
            "actions": steps,
            "action_count": len(steps),
            "context_truncated": value["context"]["truncated"],
            "context_pair_count": value["context"]["pair_count"],
            "current_model": {
                **model,
                "action_id": model["id"],
                "has_tool_calls": model["safe_details"].get("has_tool_calls", False),
            }
            if model
            else None,
            "current_activity": {
                "action_id": activity["id"],
                "kind": activity["kind"],
                "name": activity["safe_details"].get("name"),
                "tool": activity["safe_details"].get("tool"),
            }
            if activity
            else None,
            "result": {
                "id": value["id"],
                "output_key": "answer",
                "content_type": "text/markdown",
                "schema_version": 1,
                "content": value["content"],
            }
            if value["status"] == "succeeded"
            else None,
        }

    def normalize(self, value):
        if isinstance(value, list):
            return [self.normalize(item) for item in value]
        if not isinstance(value, dict):
            return value
        if "response" in value and "conversation" in value and "id" in value["response"]:
            return self.execution(value["response"])
        if value.get("role") == "assistant" and "steps" in value:
            execution = self.execution(value)
            return {**value, "run": execution, "published": value["status"] == "succeeded"}
        if value.get("role") == "user":
            return {**value, "run": None, "published": True}
        if "active_response_id" in value and "id" in value:
            with self.app.state.database.transaction() as db:
                run_id = (
                    db.scalar(
                        select(ConversationRun.run_id).where(
                            ConversationRun.reply_message_id == value["active_response_id"]
                        )
                    )
                    if value["active_response_id"]
                    else None
                )
            return {**value, "active_run_id": run_id}
        if (
            "question_id" in value
            and "response_id" in value
            and isinstance(value["response_id"], str)
        ):
            with self.app.state.database.transaction() as db:
                run_id = db.scalar(
                    select(ConversationRun.run_id).where(
                        ConversationRun.reply_message_id == value["response_id"]
                    )
                )
            return {
                **{key: val for key, val in value.items() if key not in ("response_id", "version")},
                "run_id": run_id,
                "output_message_id": value["response_id"],
                "revision": value["version"],
            }
        return {key: self.normalize(item) for key, item in value.items()}

    def request(self, method, url, *args, **kwargs):
        path = str(url)
        match = re.fullmatch(r"/api/runs/([^/?]+)(.*)", path)
        action_page = False
        if match:
            binding = self.binding(match[1])
            if binding:
                suffix = match[2].replace("/cancel", "/stop")
                action_page = suffix.startswith("/actions")
                path = (
                    f"/api/conversations/{binding.conversation_id}/responses/{binding.reply_message_id}"
                    + ("" if action_page else suffix)
                )
            else:
                path = f"/api/conversations/{match[1]}/responses/{match[1]}"
        path = re.sub(r"(/api/conversations/[^/]+)/runs$", r"\1/messages", path)
        response = super().request(method, path, *args, **kwargs)
        if path == "/openapi.json":
            return response
        if (
            response.headers.get("content-type", "").startswith("application/json")
            and response.status_code < 300
        ):
            raw = response.json()
            value = self.normalize(raw)
            if action_page and "response" in raw:
                from urllib.parse import parse_qs, urlsplit

                query = parse_qs(urlsplit(str(url)).query)
                params = kwargs.get("params") or {}
                offset = int(params.get("offset", query.get("offset", [0])[0]))
                limit = int(params.get("limit", query.get("limit", [50])[0]))
                steps = raw["response"]["steps"]
                value = {
                    "items": steps[offset : offset + limit],
                    "total": len(steps),
                    "offset": offset,
                    "limit": limit,
                }
            response._content = json.dumps(value).encode()
        return response


class ScenarioClient(ScenarioProtocol, TestClient):
    pass


class RemoteScenarioClient(ScenarioProtocol, httpx.Client):
    def __init__(self, *args, database, **kwargs):
        self.database = Database(
            DatabaseConfig(URL.create("sqlite+pysqlite", database=str(database)))
        )
        self.app = SimpleNamespace(state=SimpleNamespace(database=self.database))
        super().__init__(*args, **kwargs)

    def close(self):
        super().close()
        self.database.close()

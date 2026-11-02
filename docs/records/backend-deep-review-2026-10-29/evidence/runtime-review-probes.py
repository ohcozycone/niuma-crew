import asyncio
from types import SimpleNamespace

import pytest
from pydantic import PrivateAttr

pytest_plugins = ["conftest"]

from configuration_helpers import patch_current
from test_capability_runtime import ScriptedModel, execute, response, setup, submit
from app.execution.contracts import Completion
from app.execution.models import Run
from sqlalchemy import event


def test_failed_partial_after_agent_revocation(api_client):
    _, _, agent, conversation = setup(api_client)
    accepted = submit(api_client, conversation).json()
    store = api_client.app.state.execution_store
    assert store.claim(accepted["id"])
    patch_current(api_client, f"/api/agents/{agent['id']}", json={"is_active": False})
    api_client.app.state.conversation_commands.publisher(
        Completion(accepted["id"], "撤权后新增的部分正文", "failed", "output_limit_exceeded")
    )
    done = api_client.get(f"/api/runs/{accepted['id']}").json()
    assert done["assistant_content"] == "撤权后新增的部分正文", done
    print("OBSERVED partial publish after revocation:", done["status"], done["assistant_content"])


def test_real_sdk_length_partial_after_agent_revocation(api_client, monkeypatch):
    _, _, agent, conversation = setup(api_client)
    accepted = submit(api_client, conversation).json()

    class RevokingModel(ScriptedModel):
        async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
            # Let the independent watcher's initial permission check finish first.
            await asyncio.sleep(0.05)
            await asyncio.to_thread(
                patch_current, api_client, f"/api/agents/{agent['id']}", json={"is_active": False}
            )
            return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    model = RevokingModel(responses=[response("撤权后模型的部分正文").model_copy(update={"response_metadata": {"finish_reason": "length"}})])
    done = execute(api_client, monkeypatch, model, accepted)
    assert done["status"] == "failed", done
    assert done["error"]["code"] == "output_limit_exceeded", done
    assert done["assistant_content"] == "撤权后模型的部分正文", done
    print("OBSERVED real SDK partial publish:", done["status"], done["error"]["code"], done["assistant_content"])


def test_conversation_list_query_growth(api_client):
    _, _, agent, _ = setup(api_client)
    for _ in range(4):
        assert api_client.post("/api/conversations", json={"agent_id": agent["id"]}).status_code == 201
    actor = api_client.app.state.auth.resolve(api_client.cookies.get("app_session"))
    engine = api_client.app.state.database.engine
    statements = []
    def record(conn, cursor, statement, *args):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)
    event.listen(engine, "before_cursor_execute", record)
    try:
        page = api_client.app.state.conversation_queries.list(actor)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    print("OBSERVED conversation list:", len(page.items), "conversations", len(statements), "SELECTs")
    assert len(page.items) == 5 and len(statements) == 17

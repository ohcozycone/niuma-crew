"""Run initialization and transient model views preserve official message structures."""

import asyncio
from types import SimpleNamespace

import pytest
from langchain.agents.middleware import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from runtime_helpers import MemoryContext
from test_capability_runtime import ScriptedModel

from app.execution.contracts import RuntimeFailure
from app.execution.runtime.agent import _prepare_run_input
from app.execution.runtime.checkpoints import CheckpointStore
from app.execution.runtime.model_calls import ReferenceContextMiddleware
from app.execution.runtime.skills import prepare_skills
from app.execution.snapshot import RunConfiguration


def request(**overrides):
    values = dict(
        checkpoint_id=None,
        base_checkpoint_id="base",
        base_run_id="previous",
        run_id="current",
        snapshot={"memory_scope": "same", "memory_reset": False},
        messages=[{"id": "question", "role": "user", "content": "ORIGINAL"}],
    )
    return SimpleNamespace(**(values | overrides))


def state(**overrides):
    return SimpleNamespace(
        values=dict(
            app_run_id="previous",
            completed_run_id="previous",
            messages=[HumanMessage(content="past")],
        )
        | overrides
    )


def test_same_run_resume_does_not_reset_any_state_or_duplicate_input():
    assert (
        _prepare_run_input(
            request(checkpoint_id="saved"), state(app_run_id="current"), prepare_skills([], [])
        )
        is None
    )


@pytest.mark.parametrize("values", [{"app_run_id": "other"}, {"completed_run_id": "other"}])
def test_inconsistent_base_is_rejected(values):
    with pytest.raises(RuntimeFailure, match="checkpoint_unavailable"):
        _prepare_run_input(request(), state(**values), prepare_skills([], []))


def test_transient_views_preserve_blocks_pairing_and_current_user_text():
    host = MemoryContext()
    host.clean_history = lambda text: text.replace("STALE", "cleaned")
    middleware = ReferenceContextMiddleware(
        request(snapshot={"input_files": [{"name": "attachment"}]}), host
    )
    middleware.history_ids = {"old", "old-call", "old-result"}
    blocks = [
        {"type": "text", "text": "STALE"},
        {"type": "image_url", "image_url": {"url": "https://example.com/image.png"}},
    ]
    messages = [
        HumanMessage(id="old", content=blocks),
        AIMessage(
            id="old-call", content="", tool_calls=[{"name": "probe", "id": "call", "args": {}}]
        ),
        ToolMessage(id="old-result", content="STALE", tool_call_id="call"),
        HumanMessage(id="question", content="STALE user input"),
    ]
    original = ModelRequest(model=ScriptedModel(responses=[]), messages=messages)
    seen = []

    async def handler(current):
        seen.append(current.messages)
        return None

    async def scenario():
        await middleware.awrap_model_call(original, handler)
        await middleware.awrap_model_call(original, handler)

    asyncio.run(scenario())
    assert len(seen[0]) == len(seen[1]) == len(messages) + 1
    assert messages[0].content == blocks and messages[2].content == "STALE"
    assert seen[0][0].content[0]["text"] == "cleaned"
    assert seen[0][0].content[1] == blocks[1]
    assert seen[0][1].tool_calls == messages[1].tool_calls
    assert seen[0][2].tool_call_id == "call"
    assert seen[0][3].content == "STALE user input"
    assert original.messages == messages


@pytest.mark.parametrize(
    "change,invalid",
    [
        ("add_skill", False),
        ("add_tool", False),
        ("remove", True),
        ("scope", True),
        ("skill_content", True),
        ("knowledge", True),
    ],
)
def test_memory_invalidation_distinguishes_additions_from_changes(change, invalid):
    import copy

    previous = {
        "memory_scope": "same",
        "skills": [{"skill_id": "one", "instructions": "old"}],
        "tools": [
            {"binding_id": "one", "kind": "mcp_http", "scope_policy": {"read_roots": ["/allowed"]}}
        ],
    }
    current = copy.deepcopy(previous)
    if change == "add_skill":
        current["skills"].append({"skill_id": "two", "instructions": "new"})
    elif change == "add_tool":
        current["tools"].append({"binding_id": "two", "kind": "mcp_http"})
    elif change == "remove":
        current["tools"] = []
    elif change == "scope":
        current["tools"][0]["scope_policy"] = {}
    elif change == "skill_content":
        current["skills"][0]["instructions"] = "changed"
    elif change == "knowledge":
        current["memory_scope"] = "changed"
    assert RunConfiguration.invalidates_memory(previous, current) is invalid


def test_checkpoint_path_uses_the_same_db_extension_and_directory(tmp_path):
    store = CheckpointStore(str(tmp_path / "app.db"))
    assert store.path == tmp_path / "app.checkpoints.db"

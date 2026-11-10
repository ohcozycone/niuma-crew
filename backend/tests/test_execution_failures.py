import ast
import asyncio
from pathlib import Path

import httpx
import pytest
from test_capability_runtime import setup, submit
from test_run_task import queued_task

from app.agent.errors import RuntimeFailure
from app.api.errors import service_error_response
from app.errors import CodedFailure, FailureKind, InvalidInputError
from app.execution.errors import (
    ExecutionFailure,
    PersistenceFailure,
    execution_failure,
    failure_kind,
    terminal_status,
)
from app.execution.models import RunAction
from app.llm.errors import classify_error
from app.public_errors import public_error_message
from app.runtime.contracts.tools import ToolInvocation, ToolOutcome


def test_core_failures_have_types_and_no_public_message():
    agent = RuntimeFailure("tool_arguments_invalid")
    execution = ExecutionFailure("actor_session_invalid")
    assert type(agent) is not type(execution)
    assert isinstance(agent, CodedFailure) and isinstance(execution, CodedFailure)
    assert agent.kind == FailureKind.VALIDATION
    assert execution.kind == FailureKind.AUTHORIZATION
    assert str(agent) == "tool_arguments_invalid" and not hasattr(agent, "message")
    assert terminal_status(execution.code) == "cancelled"
    assert PersistenceFailure().kind == FailureKind.STORAGE


def test_service_error_can_defer_message_to_application():
    error = InvalidInputError("input_too_large")
    assert error.message == "" and str(error) == "input_too_large"
    response = service_error_response(error)
    assert response.status_code == 422
    assert public_error_message(error.code).encode() in response.body


def test_untyped_provider_code_cannot_masquerade_as_execution_failure():
    error = Exception("private upstream body")
    error.code = "actor_session_invalid"
    failure = execution_failure(error)
    assert failure.code == "execution_failed" and failure.kind == FailureKind.INTERNAL
    assert "private" not in str(failure)


def test_total_run_deadline_and_model_timeout_are_different_facts():
    assert execution_failure(TimeoutError()).code == "run_timeout"
    assert classify_error(httpx.ReadTimeout("private")) == "upstream_timeout"
    assert failure_kind("run_timeout") == FailureKind.LIMIT
    assert failure_kind("upstream_timeout") == FailureKind.DEPENDENCY


def test_public_copy_does_not_control_runner_status(api_client, monkeypatch):
    from run_helpers import read_reply

    from app import public_errors

    task = queued_task(api_client)

    async def fail(*args):
        raise RuntimeFailure("empty_response")

    monkeypatch.setattr(public_errors, "ERROR_MESSAGES", {})
    task._agent = fail
    asyncio.run(task.execute())
    row, _ = task._store.load(task.run_id)
    assert row.status == "failed" and row.error_code == "empty_response"

    assert read_reply(api_client, task.run_id)["error"] == {
        "code": "empty_response",
        "kind": "dependency",
        "message": "执行失败，请重试。",
    }
    monkeypatch.setattr(public_errors, "ERROR_MESSAGES", {"empty_response": "Different wording"})
    assert read_reply(api_client, task.run_id)["error"]["message"] == "Different wording"
    row, _ = task._store.load(task.run_id)
    assert row.status == "failed" and row.error_code == "empty_response"


def test_persistence_failure_is_not_converted_to_a_business_rejection(api_client, monkeypatch):
    from app.runtime.contracts.runs import Completion

    _, _, _, conversation = setup(api_client)
    accepted = submit(api_client, conversation).json()["response"]
    state = api_client.app.state
    assert state.run_worker.store.claim(accepted["id"])

    def fail(*args):
        raise PersistenceFailure()

    monkeypatch.setattr(state.runs, "check_outputs", fail)
    with pytest.raises(PersistenceFailure):
        state.runs.complete(Completion(accepted["id"], "answer", "succeeded"))
    row, _ = state.run_worker.store.load(accepted["id"])
    assert row.status == "running" and row.error_code is None and row.result_text is None


def test_persistence_failure_during_tool_admission_is_not_recorded_as_denial(
    api_client, monkeypatch
):
    from runtime_helpers import make_task

    _, _, _, conversation = setup(api_client)
    accepted = submit(api_client, conversation).json()["response"]
    store = api_client.app.state.run_worker.store
    context = make_task(accepted["id"], store, lambda *args, **kwargs: {})

    def fail(*args):
        raise PersistenceFailure()

    def reject(*args):
        pytest.fail("持久化故障不属于授权拒绝")

    monkeypatch.setattr(store, "begin_tool", fail)
    monkeypatch.setattr(store, "reject_tool", reject)
    with pytest.raises(PersistenceFailure):
        asyncio.run(context.begin_tool(ToolInvocation("tool:one", "binding", "probe", {})))


@pytest.mark.parametrize(
    "status,code,expected",
    [
        ("failed", "tool_arguments_invalid", "tool_arguments_invalid"),
        ("failed", "tool_auth_required", "tool_auth_required"),
        ("failed", None, "tool_upstream_failed"),
        ("unknown", None, "tool_result_unknown"),
        ("failed", "command_failed", "command_failed"),
    ],
)
def test_tool_action_preserves_failure_reason(api_client, status, code, expected):
    from runtime_helpers import bind_model_calls, make_task
    from sqlalchemy import select

    _, _, _, conversation = setup(api_client)
    accepted = submit(api_client, conversation).json()["response"]
    store = api_client.app.state.run_worker.store
    assert store.claim(accepted["id"])
    context = make_task(accepted["id"], store, lambda *args, **kwargs: {"scope_policy": {}})
    (invocation,) = bind_model_calls(
        store,
        accepted["id"],
        ToolInvocation("tool:failure", "workspace:read_file", "read_file", {}),
    )

    async def scenario():
        permit = await context.begin_tool(invocation)
        await context.complete_tool(permit, ToolOutcome("feedback", status, error_code=code))

    asyncio.run(scenario())
    with store.database.transaction() as db:
        action = db.scalar(
            select(RunAction).where(
                RunAction.run_id == accepted["id"], RunAction.kind == "tool_call"
            )
        )
        assert action.error_code == expected and action.status == status
    actor = api_client.app.state.auth.resolve(api_client.cookies.get("app_session"))
    trace = api_client.app.state.execution_queries.read(actor, accepted["id"])
    assert trace["failures"]["items"][0]["error_kind"] == failure_kind(expected)
    assert trace["failures"]["items"][0]["action_key"] == "tool:failure"


def test_core_service_rejections_do_not_embed_public_copy():
    root = Path(__file__).resolve().parents[1] / "app"
    service_types = {
        "InvalidInputError",
        "ConflictError",
        "PermissionDeniedError",
        "NotFoundError",
        "RateLimitError",
        "ServiceUnavailableError",
        "AuthenticationError",
    }
    for directory in ("agent", "execution"):
        for path in (root / directory).glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in service_types
                ):
                    assert len(node.args) == 1 and not any(
                        k.arg == "message" for k in node.keywords
                    ), path

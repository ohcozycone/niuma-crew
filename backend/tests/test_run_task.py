"""Preparation, execution, cancellation and cleanup belong to one RunTask."""

import asyncio
from threading import Event
from types import SimpleNamespace

import pytest
from test_capability_runtime import setup, submit


def queued_task(client):
    _, _, _, conversation = setup(client)
    response = submit(client, conversation).json()["response"]
    worker = client.app.state.run_worker
    return worker.task_factory(response["id"], worker._complete)


def test_failed_entry_closes_resources_even_if_recovery_loading_fails(api_client, monkeypatch):
    context = queued_task(api_client)
    closed = []

    async def close():
        closed.append(True)

    monkeypatch.setattr(context._tool_service, "for_run", lambda _: SimpleNamespace(aclose=close))

    def fail(_):
        raise RuntimeError("recovery storage failure")

    monkeypatch.setattr(context._store, "restore_control", fail)

    async def scenario():
        with pytest.raises(RuntimeError, match="recovery storage failure"):
            async with context:
                raise AssertionError("failed preparation must not enter the SDK")

    asyncio.run(scenario())
    assert closed == [True]


def test_cancelled_entry_joins_preparation_before_closing_late_resources(api_client, monkeypatch):
    context = queued_task(api_client)
    started, release = Event(), Event()
    closed = []
    resolve = context._connections.resolve

    def delayed_resolve(*args):
        started.set()
        assert release.wait(5)
        return resolve(*args)

    async def close():
        closed.append(True)

    monkeypatch.setattr(context._connections, "resolve", delayed_resolve)
    monkeypatch.setattr(context._tool_service, "for_run", lambda _: SimpleNamespace(aclose=close))

    async def scenario():
        task = asyncio.create_task(context.__aenter__())
        assert await asyncio.to_thread(started.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        assert not closed
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    try:
        asyncio.run(scenario())
    finally:
        release.set()
    assert closed == [True]


def test_cleanup_joins_release_after_repeated_cancellation(api_client):
    context = queued_task(api_client)
    started, release = Event(), Event()
    closed = []

    def release_sandbox():
        started.set()
        assert release.wait(5)
        closed.append("sandbox")

    async def close_tools():
        closed.append("tools")

    context.sandbox = SimpleNamespace(release=release_sandbox)
    context._tools = SimpleNamespace(aclose=close_tools)

    async def scenario():
        task = asyncio.create_task(context._close())
        assert await asyncio.to_thread(started.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    try:
        asyncio.run(scenario())
    finally:
        release.set()
    assert closed == ["sandbox", "tools"]


def test_cleanup_failure_preserves_shutdown_cancellation(api_client):
    context = queued_task(api_client)

    async def close_tools():
        raise RuntimeError("close failed")

    context._tools = SimpleNamespace(aclose=close_tools)

    async def scenario():
        error = asyncio.CancelledError()
        # __aexit__ must let the context manager re-raise its original cancellation.
        await context.__aexit__(type(error), error, None)

    asyncio.run(scenario())


def test_cancelled_completion_joins_commit_before_worker_can_release_lock(api_client, monkeypatch):
    started, release = Event(), Event()

    def complete(_):
        started.set()
        assert release.wait(5)

    worker = api_client.app.state.run_worker
    monkeypatch.setattr(worker.runs, "complete", complete)

    async def scenario():
        task = asyncio.create_task(worker._complete(SimpleNamespace(run_id="100000000002")))
        assert await asyncio.to_thread(started.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    try:
        asyncio.run(scenario())
    finally:
        release.set()


def test_cancelled_output_collection_finishes_before_task_closes(api_client, monkeypatch):
    from test_capability_runtime import ScriptedModel, response

    from app.execution.runtime.workspace import WorkspaceBackend

    context = queued_task(api_client)
    collecting, release = Event(), Event()
    order = []
    closed = asyncio.Event()
    close = context._close

    def collect(*args):
        collecting.set()
        assert release.wait(5)
        order.append("collected")
        return []

    async def close_resources():
        order.append("closed")
        closed.set()
        await close()

    monkeypatch.setattr(context, "_close", close_resources)
    monkeypatch.setattr(WorkspaceBackend, "collect_outputs", collect)
    monkeypatch.setattr(
        "app.llm.factory.create_chat_model",
        lambda *args, **kwargs: ScriptedModel(responses=[response("完成")]),
    )

    async def scenario():
        task = asyncio.create_task(context.execute())
        try:
            assert await asyncio.to_thread(collecting.wait, 5)
            task.cancel()
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(closed.wait(), timeout=0.05)
            assert not task.done()
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(scenario())
    assert order == ["collected", "closed"]


@pytest.mark.parametrize("fails", [False, True], ids=["success", "failure"])
def test_task_claims_runs_and_closes_resources_before_committing(api_client, monkeypatch, fails):
    from app.execution.contracts import AgentOutput
    from app.execution.errors import ExecutionFailure
    from app.execution.models import Run
    from app.infrastructure.observability import run_id_context

    work = queued_task(api_client)
    order = []
    complete = work._complete

    async def close_tools():
        order.append("closed")

    async def agent(request, control):
        assert control is work
        assert request.run_id == work.run_id == run_id_context.get()
        with api_client.app.state.database.transaction() as db:
            row = db.get(Run, work.run_id)
            assert row.status == "running" and row.started_at is not None
        order.append("executed")
        if fails:
            raise ExecutionFailure("empty_response")
        return AgentOutput("执行完成")

    async def commit(intent):
        assert order == ["executed", "closed"]
        await complete(intent)
        order.append("committed")

    monkeypatch.setattr(
        work._tool_service, "for_run", lambda _: SimpleNamespace(aclose=close_tools)
    )
    work._agent, work._complete = agent, commit
    with api_client.app.state.database.transaction() as db:
        assert db.get(Run, work.run_id).status == "queued"
    asyncio.run(work.execute())
    assert run_id_context.get() == "-"
    assert order == ["executed", "closed", "committed"]
    with api_client.app.state.database.transaction() as db:
        row = db.get(Run, work.run_id)
        assert row.status == ("failed" if fails else "succeeded")
        assert row.finished_at is not None
        assert row.error_code == ("empty_response" if fails else None)
        assert row.result_text == ("" if fails else "执行完成")


def test_task_does_not_execute_or_complete_an_already_claimed_run(api_client):
    from app.execution.models import Run

    work = queued_task(api_client)
    assert work._store.claim(work.run_id)

    async def forbidden(*args):
        raise AssertionError("A Run already claimed by another task cannot execute again")

    work._agent = work._complete = forbidden
    asyncio.run(work.execute())
    with api_client.app.state.database.transaction() as db:
        assert db.get(Run, work.run_id).status == "running"


def test_service_authorization_reuses_the_action_transaction_and_preserves_rollback(
    api_client, monkeypatch
):
    from contextlib import contextmanager

    from sqlalchemy import func, select
    from sqlalchemy.exc import OperationalError

    from app.execution.models import Run, RunAction

    work = queued_task(api_client)
    store = work._store
    assert store.claim(work.run_id)
    work.row, _ = store.load(work.run_id)
    transaction = store.database.transaction
    opened = []

    @contextmanager
    def tracked_transaction():
        opened.append(True)
        with transaction() as db:
            yield db

    def fail(*args, **kwargs):
        raise OperationalError("injected action write failure", {}, Exception("injected"))

    with monkeypatch.context() as patch:
        patch.setattr(store.database, "transaction", tracked_transaction)
        patch.setattr(store, "_start_action", fail)
        with pytest.raises(OperationalError):
            asyncio.run(work.start_model())
    assert opened == [True]
    with transaction() as db:
        assert db.get(Run, work.run_id).model_calls == 0
        assert db.scalar(select(func.count()).select_from(RunAction)) == 0

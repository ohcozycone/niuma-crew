"""Accepted work is scheduled without a global active-run ceiling."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

from app.execution.config import load_runtime_config
from app.execution.contracts import Completion, ExecutionStatus
from app.execution.runtime.worker import RunWorker


def test_worker_starts_all_accepted_runs_and_stops_them_cleanly(tmp_path: Path) -> None:
    async def scenario() -> None:
        run_ids = {f"run-{number}" for number in range(4)}
        started: set[str] = set()
        stopped: set[str] = set()
        all_started = asyncio.Event()
        release = asyncio.Event()
        completed: list[Completion] = []

        async def execute(run_id: str) -> None:
            started.add(run_id)
            if started == run_ids:
                all_started.set()
            try:
                await release.wait()
            finally:
                stopped.add(run_id)

        store = SimpleNamespace(
            recover=lambda resume: [],
            queued_metadata=lambda: [(run_id, None) for run_id in sorted(run_ids)],
        )
        settings = load_runtime_config({"RUN_POLL_INTERVAL": "0.01"})
        worker = RunWorker(
            store,
            SimpleNamespace(complete=completed.append),
            lambda run_id, complete: SimpleNamespace(execute=lambda: execute(run_id)),
            settings,
            ExecutionStatus(),
            tmp_path / "worker.lock",
        )

        await worker.start()
        try:
            await asyncio.wait_for(all_started.wait(), timeout=2)
            assert set(worker.tasks) == run_ids
            assert not completed
        finally:
            await worker.stop()

        assert stopped == run_ids
        assert not worker.tasks
        assert worker.lock_file is None

    asyncio.run(scenario())


def test_worker_retries_task_storage_failure_without_executing_it_again(tmp_path: Path) -> None:
    from sqlalchemy.exc import OperationalError

    async def scenario() -> None:
        run_id = "100000000001"
        queued = {run_id}
        started = []
        completions = []
        notifications = []
        completed = asyncio.Event()
        loop = asyncio.get_running_loop()

        async def execute():
            started.append(run_id)
            raise OperationalError("load failed", {}, Exception("injected"))

        def complete(intent):
            completions.append(intent)
            queued.discard(intent.run_id)
            loop.call_soon_threadsafe(completed.set)

        worker = RunWorker(
            SimpleNamespace(
                recover=lambda resume: [],
                queued_metadata=lambda: [(id, None) for id in queued],
            ),
            SimpleNamespace(complete=complete),
            lambda run_id, complete: SimpleNamespace(execute=execute),
            load_runtime_config({"RUN_POLL_INTERVAL": "0.01"}),
            ExecutionStatus(),
            tmp_path / "worker.lock",
        )
        worker.set_completion_notifier(lambda: notifications.append(True))
        await worker.start()
        try:
            await asyncio.wait_for(completed.wait(), 2)
            await asyncio.sleep(0.05)
            assert started == [run_id]
            assert len(completions) == 1
            assert completions[0].status == "failed"
            assert completions[0].error == "persistence_unavailable"
            assert not worker.pending_failures
            assert worker.status.phase == "ready"
            assert notifications == [True]
        finally:
            await worker.stop()

    asyncio.run(scenario())

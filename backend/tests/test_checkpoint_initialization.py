import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from app.runtime.agent.checkpoints import CheckpointStore, checkpoint_config


def test_fresh_runs_and_readers_initialize_checkpoint_storage_concurrently(tmp_path):
    async def scenario(index):
        store = CheckpointStore(str(tmp_path / f"store-{index}.db"))
        readers = Barrier(2)

        def read(run_id):
            readers.wait(timeout=5)
            return store.for_run(run_id, None, thread_id=run_id)

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert list(pool.map(read, ("first", "second"))) == [None, None]

        # 两个写入上下文须同时打开；若整轮串行化，此处会死锁。
        ready = 0
        writers = asyncio.Event()

        async def write(run_id):
            nonlocal ready
            async with store.writer(None) as saver:
                ready += 1
                if ready == 2:
                    writers.set()
                await asyncio.wait_for(writers.wait(), timeout=5)
                assert await saver.aget_tuple(checkpoint_config(run_id)) is None
                assert (
                    await asyncio.to_thread(store.for_run, run_id, None, thread_id=run_id) is None
                )

        await asyncio.gather(write("first"), write("second"))

    async def run():
        for index in range(30):
            await scenario(index)

    asyncio.run(run())

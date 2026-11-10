import asyncio
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


async def settle(task: asyncio.Task) -> None:
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
        except Exception:
            break
    if not task.cancelled():
        task.exception()


async def run_sync(call: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    task = asyncio.create_task(asyncio.to_thread(call, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except BaseException:
        # 取消等待不会停止线程或回滚其事务，释放资源前须等待结束。
        await settle(task)
        raise

"""MCP 进程由所属任务管理进入和退出；可信程序以宿主用户权限运行，不提供隔离。"""

import asyncio
import contextlib
import os
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastmcp.client.transports import StdioTransport
from langchain.mcp import MCPAdapter

from app.common.errors import ServiceUnavailableError
from app.resources.mcp.adapters.http import MCPClient


class StdioMCPClient(MCPClient):
    def __init__(self, definition, environment, config, limiter):
        super().__init__("", {}, config)
        self.definition, self.environment, self.limiter = definition, environment, limiter
        self._task = None
        self._ready = None
        self._stop = asyncio.Event()
        self._adapter = None
        self._lock = asyncio.Lock()
        self._closed = False

    async def _own_session(self):
        acquired = False
        try:
            try:
                async with asyncio.timeout(self.config.stdio_wait_seconds):
                    await self.limiter.acquire()
                acquired = True
            except TimeoutError:
                raise ServiceUnavailableError(
                    "stdio_capacity_exhausted", "本机 MCP 进程名额繁忙，请稍后重试。"
                ) from None
            with (
                tempfile.TemporaryDirectory(prefix="niuma-mcp-") as directory,
                open(os.devnull, "w") as stderr,
            ):
                # 仅继承框架安全环境；账号凭据逐进程解析，不写入快照，工作目录各自独立。
                transport = StdioTransport(
                    sys.executable,
                    [
                        str(Path(__file__).with_name("stdio_runner.py")),
                        self.definition["command"],
                        *self.definition.get("args", []),
                    ],
                    env=self.environment,
                    cwd=directory,
                    keep_alive=False,
                    log_file=stderr,
                )
                async with MCPAdapter(transport) as adapter:
                    self._adapter = adapter
                    if not self._ready.done():
                        self._ready.set_result(None)
                    await self._stop.wait()
        except BaseException as error:
            if self._ready is not None and not self._ready.done():
                self._ready.set_exception(error)
            raise
        finally:
            self._adapter = None
            if acquired:
                self.limiter.release()

    async def open(self):
        if self._closed:
            raise ServiceUnavailableError("stdio_session_closed", "本轮 MCP 会话已关闭。")
        if self._task is None:
            self._ready = asyncio.get_running_loop().create_future()
            self._task = asyncio.create_task(self._own_session())
        try:
            await asyncio.shield(self._ready)
            if self._task.done():
                self._task.result()
        except BaseException:
            await self.aclose()
            raise

    @asynccontextmanager
    async def session(self):
        async with self._lock:
            await self.open()
            yield self._adapter

    async def aclose(self):
        self._closed = True
        task = self._task
        if task is None:
            return
        self._stop.set()
        if self._ready is not None and not self._ready.done():
            task.cancel()
        # 所属任务保持到进程组清理完成，包括取消；框架负责关闭 stdin 及限时终止。
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            if not task.cancelled():
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        except Exception:
            pass
        self._task = None

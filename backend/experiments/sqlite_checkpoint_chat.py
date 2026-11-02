"""本机 checkpoint 验证后端：假模型、假制度、独立 SQLite，不装配业务应用。"""

import argparse
import asyncio
import json
import os
import socket
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pydantic import BaseModel

QUESTION = "上海住宿标准多少？"
FOLLOWUP = "住三晚呢？"
INTERNAL_MARKER = "CHECKPOINT_DEMO_INTERNAL_POLICY"


class ExpenseModel(BaseChatModel):
    """确定性测试模型；回答追问时必须从传入的历史工具结果读取金额。"""

    pause_after_lookup: bool = False
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "sqlite-checkpoint-expense-fixture"

    def bind_tools(self, tools, **kwargs):
        return self

    def _reply(self, messages) -> ChatResult:
        question = next(m.text for m in reversed(messages) if isinstance(m, HumanMessage))
        if question == QUESTION and not isinstance(messages[-1], ToolMessage):
            message = AIMessage(
                content="内部执行文字：先读取制度。",
                tool_calls=[
                    {"name": "lodging_policy", "args": {}, "id": str(uuid4()), "type": "tool_call"}
                ],
            )
        else:
            policy = next(
                (json.loads(m.content) for m in reversed(messages) if isinstance(m, ToolMessage)),
                None,
            )
            if policy is None:
                message = AIMessage(content="尚未读取住宿标准，请先查询。")
            elif question == FOLLOWUP:
                message = AIMessage(
                    content=f"按上海每晚{policy['nightly_limit']}元计算，三晚共"
                    f"{policy['nightly_limit'] * 3}元。"
                )
            else:
                message = AIMessage(content=f"上海住宿上限为{policy['nightly_limit']}元/晚。")
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.calls += 1
        return self._reply(messages)

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.calls += 1
        if self.pause_after_lookup and isinstance(messages[-1], ToolMessage):
            # 测试在工具结果已落盘后杀进程，不能用正常 shutdown 代替崩溃。
            await asyncio.Event().wait()
        return self._reply(messages)


class MessageInput(BaseModel):
    text: Literal["上海住宿标准多少？", "住三晚呢？"]


def thread_config(thread_id: UUID) -> dict:
    return {"configurable": {"thread_id": str(thread_id)}, "recursion_limit": 64}


def create_app(database: Path, *, pause_after_lookup: bool = False) -> FastAPI:
    """创建仅用于隔离验证的 HTTP 后端，恢复由显式 resume 请求触发。"""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.parent.mkdir(parents=True, exist_ok=True)
        model = ExpenseModel(pause_after_lookup=pause_after_lookup)
        counters = {"tool_calls": 0}

        def lodging_policy() -> str:
            """返回虚构的上海住宿制度，仅供 checkpoint 实验使用。"""
            counters["tool_calls"] += 1
            return json.dumps(
                {"nightly_limit": 500, "internal": INTERNAL_MARKER, "receipt": str(uuid4())}
            )

        async with AsyncSqliteSaver.from_conn_string(str(database)) as saver:
            app.state.agent = create_agent(model=model, tools=[lodging_policy], checkpointer=saver)
            app.state.model = model
            app.state.counters = counters
            app.state.tasks = {}
            app.state.errors = {}
            app.state.submission_lock = asyncio.Lock()
            try:
                yield
            finally:
                tasks = tuple(app.state.tasks.values())
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(title="SQLite checkpoint 隔离验证", lifespan=lifespan)

    async def consume(thread_id: UUID, input):
        key = str(thread_id)
        try:
            async for _ in app.state.agent.astream(
                input,
                thread_config(thread_id),
                stream_mode=["messages", "updates"],
                version="v2",
                durability="sync",
            ):
                pass
        except Exception as error:
            app.state.errors[key] = type(error).__name__
        finally:
            app.state.tasks.pop(key, None)

    async def launch(thread_id: UUID, input, *, resume: bool):
        key = str(thread_id)
        async with app.state.submission_lock:
            if key in app.state.tasks:
                raise HTTPException(409, "该对话正在执行。")
            snapshot = await app.state.agent.aget_state(thread_config(thread_id))
            if resume and not snapshot.next:
                raise HTTPException(409, "没有待恢复的执行。")
            if not resume and snapshot.next:
                raise HTTPException(409, "请先恢复未完成执行。")
            app.state.errors.pop(key, None)
            app.state.tasks[key] = asyncio.create_task(consume(thread_id, input))
        return {"thread_id": key}

    @app.get("/health")
    async def health():
        return {"pid": os.getpid(), "model_calls": app.state.model.calls, **app.state.counters}

    @app.post("/threads/{thread_id}/messages", status_code=202)
    async def send_message(thread_id: UUID, body: MessageInput):
        return await launch(
            thread_id,
            {"messages": [HumanMessage(id=str(uuid4()), content=body.text)]},
            resume=False,
        )

    @app.post("/threads/{thread_id}/resume", status_code=202)
    async def resume(thread_id: UUID):
        return await launch(thread_id, None, resume=True)

    @app.get("/threads/{thread_id}/history")
    async def history(thread_id: UUID, request: Request):
        snapshot = await request.app.state.agent.aget_state(thread_config(thread_id))
        messages = []
        for message in snapshot.values.get("messages", []):
            if isinstance(message, HumanMessage):
                role = "user"
            elif isinstance(message, AIMessage) and not message.tool_calls:
                role = "assistant"
            else:
                continue
            messages.append({"id": message.id, "role": role, "text": str(message.text)})
        key = str(thread_id)
        return {
            "messages": messages,
            "checkpoint_id": snapshot.config.get("configurable", {}).get("checkpoint_id"),
            "pending_nodes": list(snapshot.next),
            "running": key in app.state.tasks,
            "error": app.state.errors.get(key),
        }

    return app


def main() -> None:
    # 隔离实验不沿用终端里可能开启的远端 tracing。
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="独立实验数据库文件")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--fd", type=int, help="测试传入的已监听 socket，避免端口争抢")
    parser.add_argument("--pause-after-lookup", action="store_true")
    args = parser.parse_args()
    app = create_app(args.db.resolve(), pause_after_lookup=args.pause_after_lookup)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning")
    )
    if args.fd is None:
        server.run()
    else:
        with socket.socket(fileno=args.fd) as listener:
            server.run(sockets=[listener])


if __name__ == "__main__":
    main()

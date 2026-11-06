"""正式应用的进程测试入口，只把模型供应商替换为离线替身。"""

import argparse
import asyncio
import socket
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from sqlalchemy import URL

from app.bootstrap import create_app
from app.config import AppConfig, DatabaseConfig
from app.execution.config import RuntimeConfig
from app.llm import factory


class CheckpointModel(BaseChatModel):
    path: str
    pause: bool = False
    forbidden: bool = False

    @property
    def _llm_type(self):
        return "production-checkpoint-fixture"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.forbidden:
            raise AssertionError("不应再次调用模型。")
        user = next(m.text for m in reversed(messages) if isinstance(m, HumanMessage))
        if user == "失败问题" and isinstance(messages[-1], ToolMessage):
            raise RuntimeError("fixture failure after checkpoint")
        if user in ("第一问", "失败问题") and not isinstance(messages[-1], ToolMessage):
            result = AIMessage(
                content="失败分支内容" if user == "失败问题" else "",
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {"file_path": self.path},
                        "id": "read-one",
                        "type": "tool_call",
                    }
                ],
            )
        elif user == "第二问":
            known = any(isinstance(m, AIMessage) and m.text == "回答一" for m in messages)
            result = AIMessage(content="回答二：记得回答一" if known else "缺少历史")
        else:
            result = AIMessage(content="回答一")
        result.usage_metadata = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        result.response_metadata = {"finish_reason": "tool_calls" if result.tool_calls else "stop"}
        return ChatResult(generations=[ChatGeneration(message=result)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.pause and isinstance(messages[-1], ToolMessage):
            await asyncio.Event().wait()
        return self._generate(messages, stop, run_manager, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--skill", required=True)
    parser.add_argument("--fd", type=int, required=True)
    parser.add_argument("--pause-after-lookup", action="store_true")
    parser.add_argument("--pause-before-commit", action="store_true")
    parser.add_argument("--forbid-model", action="store_true")
    args = parser.parse_args()
    factory.create_chat_model = lambda *a, **k: CheckpointModel(
        path=f"/skills/s-{args.skill}/SKILL.md",
        pause=args.pause_after_lookup,
        forbidden=args.forbid_model,
    )
    app = create_app(
        AppConfig(
            database=DatabaseConfig(url=URL.create("sqlite+pysqlite", database=str(args.db))),
            model_encryption_key_file=args.key,
            runner_lock_file=args.lock,
            runtime=RuntimeConfig(poll_interval=0.01, flush_interval=0.01, auth_interval=0.03),
        )
    )
    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        async with original(app):
            if args.pause_before_commit:
                complete = app.state.run_worker.runs.complete

                def blocked(intent):
                    if intent.status == "succeeded":
                        threading.Event().wait()
                    return complete(intent)

                app.state.run_worker.runs.complete = blocked
            yield

    app.router.lifespan_context = lifespan
    with socket.socket(fileno=args.fd) as listener:
        uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=[listener])


if __name__ == "__main__":
    main()

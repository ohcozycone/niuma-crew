"""固定真实执行链路的末轮上下文，只对比回答证据说明；工具操作均使用合成返回。"""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import benchmark_result_delivery as delivery
from fastapi.testclient import TestClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    ToolMessage,
    messages_from_dict,
    messages_to_dict,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field, PrivateAttr
from pytest import MonkeyPatch

from app.infrastructure.llm.config import LLMConfig
from app.infrastructure.llm.errors import classify_error
from app.infrastructure.llm.factory import model_session, observe_model_request
from app.infrastructure.llm.usage import parse_token_usage
from app.resources.model_connections.presets import PRESETS
from app.runtime.agent import prompts
from app.runtime.execution.models import Run

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/records/data/回答证据边界-基线.json"


def sha(value):
    body = value if isinstance(value, bytes) else delivery.encoded(value).encode()
    return hashlib.sha256(body).hexdigest()


def cases():
    small = json.loads(delivery.fixture("complete"))
    more = copy.deepcopy(small)
    more["notices"] = [
        "This is one page of the current search query, not a complete workspace listing."
    ]
    more.update(has_more=True, next_cursor="fixture-next-page")
    ended = copy.deepcopy(more)
    ended.update(has_more=False, next_cursor=None)
    ended["notices"] = ["The current search query has ended. This is not a workspace-wide export."]
    total = copy.deepcopy(more)
    total.update(
        total_count=137,
        counted_type="article",
        total_scope="all articles visible to this connection",
    )
    zero = {
        "results": [],
        "total_count": 0,
        "counted_type": "article",
        "total_scope": "all articles visible to this connection",
        "has_more": False,
    }
    return [
        {
            "id": "recent_limit",
            "raw": delivery.fixture("recent"),
            "expected": {
                "returned_pages": 50,
                "article_total": None,
                "upstream_truncated": None,
                "more_results": None,
            },
        },
        {
            "id": "more",
            "raw": delivery.encoded(more),
            "expected": {"returned_articles": 8, "article_total": None, "more_results": True},
        },
        {
            "id": "query_ended",
            "raw": delivery.encoded(ended),
            "expected": {
                "returned_articles": 8,
                "article_total": None,
                "more_for_current_query": False,
                "workspace_complete": None,
            },
        },
        {
            "id": "complete",
            "raw": delivery.fixture("complete"),
            "expected": {"article_total": 8, "scope": "visible to this connection"},
        },
        {
            "id": "explicit_total",
            "raw": delivery.encoded(total),
            "expected": {"article_total": 137, "returned_articles": 8, "more_results": True},
        },
        {
            "id": "explicit_zero",
            "raw": delivery.encoded(zero),
            "expected": {"article_total": 0, "scope": "visible to this connection"},
        },
    ]


class CaptureModel(BaseChatModel):
    search_name: str
    requests: list = Field(default_factory=list)
    tools_view: list = Field(default_factory=list)
    _index: int = PrivateAttr(default=0)

    @property
    def _llm_type(self):
        return "evidence-boundary-capture"

    def bind_tools(self, tools, **kwargs):
        self.tools_view = [convert_to_openai_tool(tool) for tool in tools]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.requests.append(
            {"messages": messages_to_dict(messages), "tools": copy.deepcopy(self.tools_view)}
        )
        if self._index == 0:
            call = {"name": "search_tools", "id": "boundary-discover", "args": {"query": "Notion"}}
        elif self._index == 1:
            call = {
                "name": self.search_name,
                "id": "boundary-search",
                "args": {"query": "", "sort": "last_edited", "page_size": 50},
            }
        else:
            call = None
        self._index += 1
        response = AIMessage(
            content="" if call else "已冻结合成验收上下文。", tool_calls=[call] if call else []
        )
        return ChatResult(generations=[ChatGeneration(message=response)])


def collect(client, employee, case, baseline):
    delivery.FixedClient.text = case["raw"]
    conversation = delivery.empty_conversation(client, employee)
    result = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": delivery.QUESTION, "client_request_id": str(uuid4())},
    )
    assert result.status_code == 202, result.text
    identifier = result.json()["response"]["id"]
    with client.app.state.database.transaction() as db:
        row = db.get(Run, identifier)
        names = {t["exposed_name"]: t["tool_name"] for t in row.config_snapshot["tools"]}
        search_name = next(name for name, original in names.items() if original == "notion-search")
    model = CaptureModel(search_name=search_name)
    with MonkeyPatch.context() as patch:
        patch.setattr(prompts, "RESULT_READING_POLICY", baseline)
        patch.setattr("app.infrastructure.llm.factory.create_chat_model", lambda *a, **kw: model)
        asyncio.run(delivery.execute_run(client, identifier))
    assert len(model.requests) == 3, "Capture must be exactly discovery, search, answer"
    client.app.state.conversation_acceptance.sweep()
    assert delivery.read_reply(client, identifier, conversation["id"])["status"] == "succeeded"
    captured = model.requests[-1]
    tool_message = next(
        m for m in reversed(messages_from_dict(captured["messages"])) if isinstance(m, ToolMessage)
    )
    assert tool_message.content == case["raw"], "The complete fixed result must reach the model"
    actual = {
        names[t["function"]["name"]]
        for t in captured["tools"]
        if names[t["function"]["name"]].startswith("notion-")
    }
    assert len(actual) == 5, actual
    systems = [m for m in captured["messages"] if m["type"] == "system"]
    assert len(systems) == 1 and systems[0]["data"]["content"].count(baseline) == 1
    return {**case, **captured, "tool_hash": sha(captured["tools"]), "notion_tools": sorted(actual)}


def prepare_messages(captured, old, new):
    value = copy.deepcopy(captured["messages"])
    system = next(m["data"] for m in value if m["type"] == "system")
    assert system["content"].count(old) == 1
    system["content"] = system["content"].replace(old, new)
    return messages_from_dict(value)


async def compare(runtime, captures, baseline, candidate, output, main_repeats, other_repeats):
    rows = output["results"]
    async with model_session(runtime, max_tokens=4096) as model:
        for captured in captures:
            repeats = main_repeats if captured["id"] == "recent_limit" else other_repeats
            bound = model.bind_tools(captured["tools"])
            for block in range(1, repeats + 1):
                for variant in ("before", "after") if block % 2 else ("after", "before"):
                    policy = baseline if variant == "before" else candidate
                    messages = prepare_messages(captured, baseline, policy)
                    row = {
                        "case": captured["id"],
                        "block": block,
                        "variant": variant,
                        "tool_hash": captured["tool_hash"],
                        "raw_hash": sha(captured["raw"]),
                        "expected": captured["expected"],
                    }
                    sent = []

                    async def capture(payload):
                        sent.append(payload)

                    start = time.monotonic()
                    try:
                        with observe_model_request(capture):
                            reply = await bound.ainvoke(messages)
                        row.update(
                            answer=str(reply.text),
                            tool_calls=reply.tool_calls,
                            finish_reason=reply.response_metadata.get("finish_reason"),
                            usage=parse_token_usage(reply.usage_metadata).model_dump()
                            if reply.usage_metadata
                            else None,
                            raw_usage=reply.usage_metadata,
                            status="responded",
                        )
                    except Exception as error:
                        row.update(
                            status="failed",
                            error_code=classify_error(error) or type(error).__name__,
                            usage=None,
                        )
                    row["seconds"] = time.monotonic() - start
                    assert len(sent) == 1, "No hidden retry or repair calls"
                    wire = copy.deepcopy(sent[0])
                    assert len(wire["tools"]) == len(captured["tools"])
                    for message in wire["messages"]:
                        if message["role"] == "system":
                            assert message["content"].count(policy) == 1
                            message["content"] = message["content"].replace(
                                policy, "<EVIDENCE_POLICY>"
                            )
                    row["wire_without_policy_hash"] = sha(wire)
                    peer = next(
                        (r for r in rows if r["case"] == row["case"] and r["block"] == block), None
                    )
                    row["only_policy_diff"] = (
                        peer["wire_without_policy_hash"] == row["wire_without_policy_hash"]
                        if peer is not None
                        else None
                    )
                    rows.append(row)
                    Path(output["output_file"]).write_text(
                        json.dumps(output, ensure_ascii=False, indent=2, default=str)
                    )
                    print(
                        delivery.encoded(
                            {
                                k: v
                                for k, v in row.items()
                                if k not in ["answer", "tool_calls", "raw_usage", "expected"]
                            }
                        ),
                        flush=True,
                    )
                    if row.get("error_code") == "upstream_rate_limited":
                        output["stopped"] = "upstream_rate_limited"
                        Path(output["output_file"]).write_text(
                            json.dumps(output, ensure_ascii=False, indent=2, default=str)
                        )
                        return
                    assert row["only_policy_diff"] is not False, "Only the policy may differ"


def main(args):
    baseline = json.loads(BASELINE.read_text())
    candidate = (
        json.loads(args.candidate_report.read_text())["after"]
        if args.candidate_report
        else prompts.RESULT_READING_POLICY
    )
    if not args.dry_run and candidate == baseline["policy"]:
        raise ValueError("当前规则与基线相同；复现未采纳版本请显式指定 --candidate-report。")
    for path, expected in baseline["frozen_sources"].items():
        assert sha((ROOT / "backend" / path).read_bytes()) == expected, path
    if args.dry_run:
        fixture = json.loads((ROOT / "docs/records/data/工具结果交付验收样本.json").read_text())
        credentials = ("kimi-code", fixture["model"], "fixture-key-no-network", fixture["catalog"])
    else:
        credentials = delivery.load_authorized()
    presets = PRESETS[credentials[0]]
    runtime = LLMConfig(
        model_id=credentials[1],
        api_key=credentials[2],
        base_url=presets.base_url,
        provider=presets.provider,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output = {
        "method": "真实链路假模型捕获末轮上下文，保持发现、已加载的5个Notion工具、结果交付和全部消息不变；旧/新证据说明交错串行，真实HTTP投影移除该说明后的哈希必须相同。真实工具调用为0，无隐藏修复。",
        "model": credentials[1],
        "output_file": str(args.output),
        "before": baseline["policy"],
        "after": candidate,
        "frozen_sources": baseline["frozen_sources"],
        "results": [],
        "captures": [],
        "scope": "只验证末轮证据推断，不代表完整Run耗时或端到端工具选择成功率。",
    }
    with tempfile.TemporaryDirectory(prefix="niuma-evidence-boundary-") as temporary:
        cfg = delivery.setup(Path(temporary))
        with TestClient(
            delivery.create_app(cfg),
            headers={"Origin": "http://localhost:3000", "Content-Type": "application/json"},
        ) as client:
            employee = delivery.configure(client, credentials, credentials[3])
            captures = [collect(client, employee, case, baseline["policy"]) for case in cases()]
            output["captures"] = captures
            assert len({c["tool_hash"] for c in captures}) == 1
            args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str))
            if not args.dry_run:
                asyncio.run(
                    compare(
                        runtime,
                        captures,
                        baseline["policy"],
                        candidate,
                        output,
                        args.main_repeats,
                        args.other_repeats,
                    )
                )
    print(
        delivery.encoded(
            {
                "captured": len(output["captures"]),
                "responses": len(output["results"]),
                "dry_run": args.dry_run,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--candidate-report", type=Path, help="显式复现报告中的after规则，不修改生产说明"
    )
    parser.add_argument("--main-repeats", type=int, default=10)
    parser.add_argument("--other-repeats", type=int, default=5)
    parser.add_argument(
        "--output", type=Path, default=Path("/tmp/niuma-evidence-boundary/results.json")
    )
    main(parser.parse_args())

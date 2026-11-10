"""真实 Kimi 的结果交付对照；业务应用、MCP 返回与文件均隔离。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar
from uuid import uuid4

from alembic import command
from alembic.config import Config
from deepagents.middleware.filesystem import FilesystemMiddleware
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import URL, select

from app.auth.service import AuthService
from app.bootstrap.app import create_app
from app.common.values import digest
from app.config import AppConfig, DatabaseConfig, load_config
from app.infrastructure.credentials import CredentialVault
from app.infrastructure.database.session import Database
from app.resources.skills.config import SkillConfig
from app.runtime.agent import engine, prompts
from app.runtime.execution.config import RuntimeConfig
from app.runtime.execution.models import RunAction
from app.runtime.execution.tool_results import ToolResults

ROOT = Path(__file__).resolve().parents[1]

QUESTION = "查看一下这个Notion连接里有多少篇文章？"
STOP = prompts.RESULT_READING_POLICY


def empty_conversation(client, employee):
    from app.applications.conversations.queries import read_conversation
    from app.applications.conversations.writes import create_conversation

    actor = client.app.state.auth.resolve(client.cookies.get("app_session"))
    with client.app.state.database.transaction() as db:
        return read_conversation(db, create_conversation(db, employee, actor.user_id)).model_dump(
            mode="json"
        )


async def execute_run(client, identifier):
    worker = client.app.state.run_worker
    await worker.task_factory(identifier, worker._complete).execute()


def read_reply(client, identifier, conversation):
    return client.get(f"/api/conversations/{conversation}/responses/{identifier}").json()[
        "response"
    ]


def encoded(x):
    return json.dumps(x, ensure_ascii=False, separators=(",", ":"))


def fixture(case):
    if case == "tail":
        return (
            "\n".join([f"ROW-{i:04d} synthetic filler " + ("data " * 30) for i in range(2000)])
            + "\nFINAL_VERIFIED_ARTICLE_COUNT=137\n"
        )
    count = 50 if case == "recent" else 8
    rows = [
        {
            "id": f"synthetic-{i:03d}",
            "title": f"合成测试资料{i:03d}",
            "url": f"https://example.com/synthetic/{i:03d}",
            "type": "page" if case == "recent" else "article",
            "highlight": "Generated fixture content for a counting test, not actual user data.",
        }
        for i in range(count)
    ]
    value = {
        "results": rows,
        "type": "workspace_search",
        "notices": [
            "These are recently viewed pages only, not a complete workspace listing."
            if case == "recent"
            else "This is the complete export of all articles visible to this connection."
        ],
    }
    if case == "recent":
        difference = 10988 - len(encoded(value))
        for i in range(count):
            rows[i]["highlight"] += "x" * (difference // count + (i < difference % count))
    return encoded(value)


def load_authorized():
    cfg = load_config()
    path = Path(cfg.database.url.database)
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        snapshot = json.loads(
            db.execute("SELECT config_snapshot FROM runs WHERE id=100000000158").fetchone()[0]
        )
        row = db.execute(
            "SELECT preset_id,model_id,encrypted_api_key FROM model_connections WHERE id=?",
            (snapshot["connection_id"],),
        ).fetchone()
    assert row[0] == "kimi-code"
    key = CredentialVault(cfg.model_encryption_key_file, cfg.model_encryption_key).decrypt(row[2])
    tools = [b for b in snapshot["tools"] if b["kind"] in ("mcp_http", "mcp_stdio")]
    return (
        row[0],
        row[1],
        key,
        [
            {
                **{k: b[k] for k in ("tool_name", "description", "input_schema", "recovery")},
                "source_id": b["connection_id"],
                "source": snapshot["tool_catalog"]["sources"][b["connection_id"]],
            }
            for b in tools
        ],
    )


class FixedClient:
    catalogs: ClassVar[dict] = {}
    text = ""
    calls: ClassVar[list] = []

    def __init__(self, url, *args, **kwargs):
        self.catalog, self.instructions = self.catalogs[url]

    async def discover(self):
        return self.catalog

    async def invoke(self, name, arguments, expected_hash, guard):
        await guard()
        self.calls.append({"name": name, "arguments": arguments})
        if name != "notion-search":
            text = (
                "此操作在本次隔离验收中未执行，结果未知；不能据此推断连接的工具、权限或业务数据。"
            )
        else:
            text = self.text
        return (
            [{"type": "text", "text": text}],
            {},
            "success" if name == "notion-search" else "error",
        )


@contextmanager
def variant_mode(variant):
    save = ToolResults.preserve
    old = prompts.tool_instructions
    with MonkeyPatch.context() as patch:
        # 同一工具目录与基础提示，B 仅改变交付；C 只在末尾增加读取/证据说明。
        def instructions(snapshot):
            text = old(snapshot).removesuffix(STOP)
            return text + (STOP if variant == "C" else "")

        patch.setattr(prompts, "tool_instructions", instructions)
        if variant == "A":

            async def preserve(self, invocation, data, status):
                raw, meta, sources = await save(self, invocation, data, status)
                ref = next(r for r in self.resources.list_sources() if r["id"] == meta["file_id"])
                readable = any(
                    t["kind"] == "workspace"
                    and t["tool_name"] == "read_file"
                    and "/sources" in t["scope_policy"].get("read_roots", [])
                    for t in self.bindings.values()
                )
                preview = raw[:3000]
                output = {
                    "status": status,
                    "preview": preview,
                    "result_id": meta["file_id"],
                    "preview_end": len(preview),
                    "total_chars": len(raw),
                    "next_offset": len(preview) if len(preview) < len(raw) else None,
                    "truncated": len(preview) < len(raw),
                    "source_files_readable": readable,
                    "sources": [],
                }
                if readable:
                    output["raw_result"] = f"/sources/{ref['id']}/{ref['name']}"
                return encoded(output), meta, sources

            patch.setattr(ToolResults, "preserve", preserve)
            patch.setattr(
                engine,
                "filesystem_middleware",
                lambda backend, names, **kw: FilesystemMiddleware(
                    backend=backend,
                    tools=names,
                    max_execute_timeout=60,
                    tool_token_limit_before_evict=None,
                    human_message_token_limit_before_evict=None,
                ),
            )
        yield


def setup(root):
    cfg = AppConfig(
        database=DatabaseConfig(url=URL.create("sqlite+pysqlite", database=str(root / "app.db"))),
        model_encryption_key_file=root / "key",
        runner_lock_file=root / "runner.lock",
        runtime=RuntimeConfig(enabled=False),
        skills=SkillConfig(library_directory=root / "skills"),
    )
    with MonkeyPatch.context() as patch:
        patch.setenv("DATABASE_URL", cfg.database.url.render_as_string(hide_password=False))
        command.upgrade(Config(str(ROOT / "backend/alembic.ini")), "head")
    db = Database(cfg.database)
    try:
        AuthService(db, cfg.auth).initialize_admin("benchmark", "synthetic-password")
    finally:
        db.close()
    return cfg


def configure(client, credentials, tools):
    assert (
        client.post(
            "/api/auth/login",
            json={"username": "benchmark", "password": "synthetic-password"},
        ).status_code
        == 200
    )
    model = client.post(
        "/api/model-connections",
        json={
            "name": "隔离验收模型",
            "preset_id": credentials[0],
            "model_id": credentials[1],
            "api_key": credentials[2],
        },
    ).json()
    employee = client.post(
        "/api/agents",
        json={
            "name": "结果交付验收员工",
            "avatar_id": "admin",
            "model_connection_id": model["id"],
            "system_prompt": "依据已取得的内容回答用户问题。",
        },
    ).json()
    grouped = {}
    for tool in tools:
        grouped.setdefault(tool["source_id"], []).append(tool)
    client.app.state.tool_invocation.client_factory = FixedClient
    grants = []
    for entries in grouped.values():
        source = entries[0]["source"]
        url = (
            "https://mcp.notion.com/mcp"
            if entries[0]["tool_name"].startswith("notion-")
            else "https://mcp.tavily.com/mcp"
        )
        catalog = [
            {
                "name": b["tool_name"],
                "description": b["description"],
                "input_schema": b["input_schema"],
                "recovery": b["recovery"],
                "descriptor_hash": digest([b["tool_name"], b["description"], b["input_schema"]]),
            }
            for b in entries
        ]
        FixedClient.catalogs[url] = (catalog, source["server_instructions"])
        connection = client.post(
            "/api/tool-connections",
            json={
                "name": source["connection_name"],
                "kind": "mcp_http",
                "auth_type": "none",
                "public_config": {"url": url},
            },
        ).json()
        candidate = client.post(f"/api/tool-connections/{connection['id']}/discover").json()
        approved = client.post(
            f"/api/tool-connections/{connection['id']}/approve",
            json={
                "expected_config_revision": candidate["config_revision"],
                "expected_catalog_revision": candidate["catalog_revision"],
                "candidate_hash": candidate["discovery_candidate"]["hash"],
            },
        )
        assert approved.status_code == 200, approved.text
        grants.append(
            {
                "connection_id": connection["id"],
                "tools": [t["name"] for t in catalog],
                "expected_descriptors": {t["name"]: t["descriptor_hash"] for t in catalog},
                "scope_policy": {"mode": "provider", "max_calls": 5},
            }
        )
    result = client.patch(
        f"/api/agents/{employee['id']}",
        json={"expected_revision": employee["revision"], "tool_grants": grants},
    )
    assert result.status_code == 200, result.text
    return employee["id"]


def run(client, employee, variant, case, block):
    FixedClient.text = fixture(case)
    FixedClient.calls = []
    conversation = empty_conversation(client, employee)
    question = (
        QUESTION
        if case != "tail"
        else "请读取 Notion 搜索结果末尾的 FINAL_VERIFIED_ARTICLE_COUNT，并给出已核验文章总数。"
    )
    reply = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": question, "client_request_id": str(uuid4())},
    )
    assert reply.status_code == 202, reply.text
    identifier = reply.json()["response"]["id"]
    started = time.monotonic()
    with variant_mode(variant):
        asyncio.run(execute_run(client, identifier))
    elapsed = time.monotonic() - started
    client.app.state.conversation_acceptance.sweep()
    result = read_reply(client, identifier, conversation["id"])
    with client.app.state.database.transaction() as db:
        actions = list(
            db.scalars(
                select(RunAction).where(RunAction.run_id == identifier).order_by(RunAction.sequence)
            )
        )
        trace = [
            {
                "kind": a.kind,
                "status": a.status,
                "name": a.safe_details.get("model_tool"),
                "seconds": (a.finished_at - a.started_at).total_seconds()
                if a.finished_at and a.started_at
                else None,
                "usage": a.safe_details.get("usage"),
                "feedback": a.result_payload,
                "error": a.error_code,
            }
            for a in actions
        ]
    return {
        "block": block,
        "variant": variant,
        "case": case,
        "question": question,
        "fixture_sha256": hashlib.sha256(FixedClient.text.encode()).hexdigest(),
        "answer": result.get("content"),
        "status": result["status"],
        "error": result.get("error"),
        "seconds": elapsed,
        "usage": result.get("usage"),
        "model_calls": sum(a.kind == "model_call" for a in actions),
        "reads": sum(
            a.safe_details.get("model_tool") in ("read_tool_result", "read_file", "grep")
            for a in actions
        ),
        "business_calls": FixedClient.calls,
        "trace": trace,
    }


def main(args):
    credentials = load_authorized()
    tools = credentials[3]
    out = {
        "method": "隔离真实应用链路；同一员工、模型、问题、固定合成回包；每次新对话，交错串行。A=旧3000字符交付，B=官方交付，C=B+简短读取证据提示。发现实现不变。A为测试适配重建，不是旧版本全量部署。",
        "model": credentials[1],
        "prices": None,
        "cached_price_sensitivity": [0, 0.1, 0.5, 1],
        "reading_policy": STOP,
        "variants": args.variants,
        "catalog": tools,
        "catalog_layout": "原冻结目录的来源分组、连接名称与服务说明分别保留；临时新建两个独立连接，不合并来源。",
        "quality_gate": "recent必须说明返回50页面、非全量、文章总数未知；完整列表8；长结果137；不得编造更多或不支持的能力。关键错误任一次不通过。主例10次/组，其他5次/组；正式样本不调参。",
        "source_hashes": {
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
            for p in [
                "backend/app/runtime/agent/tool_discovery.py",
                "backend/app/runtime/agent/engine.py",
                "backend/app/runtime/tools/result_files.py",
            ]
        },
        "results": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="niuma-delivery-benchmark-") as temporary:
        cfg = setup(Path(temporary))
        with TestClient(
            create_app(cfg),
            headers={
                "Origin": "http://localhost:3000",
                "Content-Type": "application/json",
            },
        ) as client:
            employee = configure(client, credentials, tools)
            for case, repeats in [
                ("recent", args.repeats),
                ("complete", args.secondary_repeats),
                ("tail", args.secondary_repeats),
            ]:
                for block in range(1, repeats + 1):
                    order = [("A", "B", "C"), ("C", "B", "A"), ("B", "A", "C")][(block - 1) % 3]
                    if len(args.variants) == 2:
                        order = args.variants if block % 2 else args.variants[::-1]
                    for variant in order:
                        if variant not in args.variants:
                            continue
                        row = run(client, employee, variant, case, block)
                        out["results"].append(row)
                        args.output.write_text(
                            json.dumps(out, ensure_ascii=False, indent=2, default=str)
                        )
                        print(
                            encoded(
                                {
                                    k: v
                                    for k, v in row.items()
                                    if k not in ("trace", "answer", "business_calls")
                                }
                            ),
                            flush=True,
                        )
    print(encoded({"completed": len(out["results"])}), flush=True)


def summarize(path):
    import math
    import statistics

    data = json.loads(path.read_text())
    groups = {}
    for row in data["results"]:
        groups.setdefault((row["case"], row["variant"]), []).append(row)
    output = {
        "source": path.name,
        "scope": "所有已完成轨迹均纳入；失败不剔除。缺用量保持未知。P90 使用最近秩。",
        "cost_scope": "无已确认 Kimi Code 额度权重；敏感性数值不是实际账单。输出已包含推理，不重复相加。",
        "groups": [],
    }
    for (case, variant), rows in sorted(groups.items()):
        durations = sorted(r["seconds"] for r in rows)
        item = {
            "case": case,
            "variant": variant,
            "n": len(rows),
            "succeeded": sum(r["status"] == "succeeded" for r in rows),
            "seconds_median": statistics.median(durations),
            "seconds_p90": durations[math.ceil(0.9 * len(rows)) - 1],
            "model_calls_median": statistics.median(r["model_calls"] for r in rows),
            "reads_median": statistics.median(r["reads"] for r in rows),
            "tokens": {},
            "conditional_cost": [],
        }
        fields = ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens")
        for field in fields:
            values = [(r.get("usage") or {}).get(field) for r in rows]
            known = [v for v in values if v is not None]
            item["tokens"][field] = {
                "known_count": len(known),
                "mean": statistics.mean(known) if known else None,
            }
        for cached_weight in [0, 0.1, 0.5, 1]:
            for output_weight in [1, 3]:
                values = []
                for row in rows:
                    usage = row.get("usage") or {}
                    inputs, cached, outputs = (usage.get(k) for k in fields[:3])
                    if all(v is not None for v in (inputs, cached, outputs)):
                        values.append(
                            inputs - cached + cached_weight * cached + output_weight * outputs
                        )
                item["conditional_cost"].append(
                    {
                        "cached_weight": cached_weight,
                        "output_weight": output_weight,
                        "known_count": len(values),
                        "mean": statistics.mean(values) if values else None,
                    }
                )
        output["groups"].append(item)
    target = path.with_name(path.stem + "-summary.json")
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(encoded(output))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variants", default="ABC", choices=["ABC", "AC", "C"])
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--secondary-repeats", type=int, default=5)
    parser.add_argument(
        "--output", type=Path, default=Path("/tmp/niuma-result-delivery-benchmark.json")
    )
    parser.add_argument("--summarize", type=Path, help="只离线汇总指定报告，不访问模型或开发配置")
    args = parser.parse_args()
    if args.summarize:
        summarize(args.summarize)
    else:
        main(args)

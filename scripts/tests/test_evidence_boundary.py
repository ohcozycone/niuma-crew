"""验证试验遇到429立即保存并结束，不访问真实模型或业务存储。"""

import asyncio
import importlib.util
import json
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parents[1]


def test_rate_limit_stops_benchmark_after_first_saved_request(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "boundary_probe", SCRIPTS / "benchmark_evidence_boundary.py"
    )
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    calls = []
    observer = {}

    @contextmanager
    def observe(callback):
        observer["capture"] = callback
        yield

    class FakeModel:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            calls.append(messages)
            await observer["capture"](
                {"tools": [], "messages": [{"role": "system", "content": messages[0].content}]}
            )
            raise RuntimeError("synthetic rate limit")

    @asynccontextmanager
    async def session(*args, **kwargs):
        yield FakeModel()

    monkeypatch.setattr(probe, "observe_model_request", observe)
    monkeypatch.setattr(probe, "model_session", session)
    monkeypatch.setattr(probe, "classify_error", lambda _: "upstream_rate_limited")
    captured = {
        "id": "recent_limit",
        "raw": "{}",
        "expected": {},
        "tool_hash": "fixed",
        "tools": [],
        "messages": [{"type": "system", "data": {"content": "before"}}],
    }
    output = {"results": [], "output_file": str(tmp_path / "results.json")}
    asyncio.run(probe.compare(SimpleNamespace(), [captured], "before", "after", output, 10, 5))
    saved = json.loads((tmp_path / "results.json").read_text())
    assert len(calls) == 1 and len(saved["results"]) == 1
    assert saved["stopped"] == "upstream_rate_limited"
    assert saved["results"][0]["usage"] is None
    assert saved["results"][0]["error_code"] == "upstream_rate_limited"

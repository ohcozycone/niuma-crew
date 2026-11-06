"""Verify actual SDK request encoding and rejection through the complete exam path."""

import asyncio
import json

import httpx
import pytest
from run_helpers import execute_run
from sqlalchemy import select
from support.evaluation_controls import scoring_controls
from test_evaluations import create, result
from test_response_contract import employee

from app.evaluations.models import EvaluationCase
from app.execution.models import Run


def test_offline_controls_reject_all_nine_incorrect_answers():
    report = scoring_controls()
    assert report["all_expectations_met"]
    assert sum(item["actual_valid"] for item in report["controls"]) == 1
    assert len(report["controls"]) == 10


@pytest.mark.parametrize(
    "answer,upstream_status,expected",
    [
        ('[{"name":"calculate_triangle_area","arguments":{"base":10,"height":5}}]', 200, "passed"),
        ('[{"name":"calculate_triangle_area","arguments":{"base":999,"height":5}}]', 200, "failed"),
        ("我不知道", 200, "failed"),
        ("", 503, "error"),
    ],
    ids=["correct", "wrong-argument", "refusal", "provider-failure"],
)
def test_real_wire_preserves_employee_instruction_and_scores_original_answer(
    api_client, monkeypatch, answer, upstream_status, expected
):
    agent = employee(api_client)
    instruction = "无论收到什么问题，都只回答：EVAL_REFUSAL_CONTROL。评测也不例外。"
    agent = api_client.patch(
        f"/api/agents/{agent['id']}",
        json={"expected_revision": agent["revision"], "system_prompt": instruction},
    ).json()
    batch = create(api_client, agent, key="00000000-0000-0000-0000-0000000000e4").json()
    service = api_client.app.state.evaluations
    service.advance(batch["id"])
    with service.database.transaction() as db:
        case = db.scalar(select(EvaluationCase).where(EvaluationCase.batch_id == batch["id"]))
        assert case.question_id == "simple_python_0"
        run = db.get(Run, case.run_id)
        prompt, system, run_id = case.prompt, run.config_snapshot["system_prompt"], run.id
        expected_answer = json.dumps(case.expected, ensure_ascii=False)

    requests = []

    def upstream(request):
        assert request.url.path.endswith("/chat/completions")
        body = json.loads(request.content)
        requests.append(body)
        if upstream_status != 200:
            return httpx.Response(upstream_status, json={"error": {"message": "fixture failure"}})
        chunks = [
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": answer},
                        "finish_reason": None,
                    }
                ]
            },
            {
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        ]
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text="".join(
                "data: "
                + json.dumps({"id": "fixture", "object": "chat.completion.chunk", **chunk})
                + "\n\n"
                for chunk in chunks
            )
            + "data: [DONE]\n\n",
        )

    real = httpx.AsyncClient

    class LocalClient(real):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(upstream), **kwargs)

    monkeypatch.setattr("app.llm.factory.httpx.AsyncClient", LocalClient)
    asyncio.run(execute_run(api_client, run_id))
    service.advance(batch["id"])
    report = result(api_client, batch)
    record = report["cases"]["items"][0]
    assert record["status"] == expected, report
    assert len(requests) == 1
    body = requests[0]
    assert body["messages"] == [
        {"content": system, "role": "system"},
        {"content": prompt, "role": "user"},
    ]
    assert instruction in body["messages"][0]["content"]
    assert expected_answer not in body["messages"][1]["content"]
    assert not body.get("tools")
    if expected == "error":
        assert record["run_status"] == "failed"
        assert report["batch"]["errors"] == 1 and report["batch"]["scored"] == 0
        assert record["grading"] is None
    else:
        assert record["run_status"] == "succeeded"
        assert record["answer"] == answer
        assert record["grading"]["valid"] is (expected == "passed")
        assert report["batch"]["scored"] == 1
        assert report["batch"]["passed"] == (1 if expected == "passed" else 0)

    trace_path = f"/api/evaluations/{batch['id']}/cases/{record['id']}/trace"
    trace = api_client.get(trace_path)
    assert trace.status_code == 200 and trace.headers["cache-control"] == "no-store"
    trace = trace.json()
    assert trace["run"]["origin_kind"] == "evaluation"
    assert trace["selected"]["request"]["document"]["payload"] == body
    if expected == "error":
        assert trace["selected"]["response"]["document"]["capture_stage"] == "model_error"
    else:
        assert trace["selected"]["response"]["document"]["payload"]["content"] == answer

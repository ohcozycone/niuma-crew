"""Independent exams, versioned inputs, cancellation and BFCL score provenance."""

import ast
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

from run_helpers import execute_run
from sqlalchemy import func, select
from test_capability_runtime import ScriptedModel, response
from test_response_contract import employee

from app.conversations.models import Conversation, Message
from app.evaluations.benchmark import DATA, SUITE_ID, grade, load_suite
from app.evaluations.models import EvaluationBatch, EvaluationCase
from app.evaluations.service import EvaluationService
from app.execution.contracts import Completion
from app.execution.models import Run


def create(client, agent, count=1, key=None):
    return client.post(
        "/api/evaluations",
        json={
            "agent_id": agent["id"],
            "suite_id": SUITE_ID,
            "sample_count": count,
            "client_request_id": key or str(uuid4()),
        },
    )


def result(client, batch):
    response = client.get(f"/api/evaluations/{batch['id']}")
    assert response.status_code == 200, response.text
    return response.json()


def acceptable(function, expected):
    parameters = next(iter(expected.values()))
    required = function["parameters"]["required"]
    args = {
        name: next((v for v in values if v != ""), "")
        for name, values in parameters.items()
        if name in required or "" not in values
    }
    return {function["name"]: args}


def test_pinned_bfcl_python_rules_match_upstream_on_all_400_cases():
    source = ast.parse((DATA / "upstream_ast_checker.py.txt").read_text())
    source.body = [n for n in source.body if not isinstance(n, ast.ImportFrom)]
    language = SimpleNamespace(PYTHON="python", JAVA="java", JAVASCRIPT="javascript")
    namespace = {
        "Language": language,
        "MODEL_CONFIG_MAPPING": {"niuma": SimpleNamespace(underscore_to_dot=False)},
    }
    # Only the fixed, licensed repository source is executed, never test answers.
    exec(compile(source, "pinned-bfcl", "exec"), namespace)
    _, cases = load_suite()
    for case in cases:
        function = case["functions"][0]
        call = acceptable(function, case["expected"][0])
        name, arguments = next(iter(call.items()))
        for args in [arguments, {**arguments, "__unexpected": 1}]:
            official = namespace["simple_function_checker"](
                deepcopy(function),
                {name: deepcopy(args)},
                deepcopy(case["expected"][0]),
                language.PYTHON,
                "niuma",
            )
            adapted = grade(
                case["functions"], case["expected"], json.dumps([{"name": name, "arguments": args}])
            )
            assert adapted == official, case["id"]


def test_json_only_protocol_rejects_multiple_calls_extra_arguments_and_bool_for_int():
    case = load_suite()[1][0]
    name, args = next(iter(acceptable(case["functions"][0], case["expected"][0]).items()))
    call = {"name": name, "arguments": args}
    assert grade(case["functions"], case["expected"], json.dumps([call]))["valid"]
    assert not grade(case["functions"], case["expected"], json.dumps([call, call]))["valid"]
    assert not grade(case["functions"], case["expected"], "__import__('os').system('true')")[
        "valid"
    ]
    assert not grade(
        case["functions"],
        case["expected"],
        json.dumps([{"name": name, "arguments": {**args, "base": True}}]),
    )["valid"]


def test_creation_is_idempotent_private_and_does_not_create_chat(api_client):
    agent = employee(api_client)
    key = str(uuid4())
    first = create(api_client, agent, 2, key)
    assert first.status_code == 202, first.text
    batch = first.json()
    assert create(api_client, agent, 2, key).json()["id"] == batch["id"]
    assert create(api_client, agent, 1, key).status_code == 409
    report = result(api_client, batch)
    assert report["cases"]["items"][0]["expected"] is None
    assert "configuration_snapshot" not in report["batch"]
    assert "api_key" not in json.dumps(report)
    with api_client.app.state.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(Conversation)) == 0
        assert db.scalar(select(func.count()).select_from(Message)) == 0
    assert api_client.delete(f"/api/agents/{agent['id']}").status_code == 409


def test_real_sdk_execution_and_score_are_independent_without_tools_or_messages(
    api_client, monkeypatch
):
    agent = employee(api_client)
    skill = api_client.post(
        "/api/skills",
        json={
            "name": "原岗位方法",
            "description": "岗位原有能力",
            "instructions": "核对工作材料。",
        },
    ).json()
    agent = api_client.patch(
        f"/api/agents/{agent['id']}",
        json={
            "expected_revision": agent["revision"],
            "skill_assignments": [{"skill_id": skill["id"]}],
        },
    ).json()
    with api_client.app.state.database.transaction() as db:
        normal, _ = api_client.app.state.runs.configuration.prepare(
            db,
            agent["id"],
            "普通工作",
            [],
            agent["created_by_user_id"],
        )
        assert normal["skills"]
    batch = create(api_client, agent).json()
    service = api_client.app.state.evaluations
    service.advance(batch["id"])
    service.advance(batch["id"])
    with api_client.app.state.database.transaction() as db:
        case = db.scalar(select(EvaluationCase).where(EvaluationCase.batch_id == batch["id"]))
        row = db.get(Run, case.run_id)
        assert row.origin_kind == "evaluation"
        assert row.config_snapshot["tools"] == [] and row.config_snapshot["skills"] == []
        assert not row.config_snapshot.get("knowledge")
        assert db.scalar(select(func.count()).select_from(Run)) == 1
        call = acceptable(case.functions[0], case.expected[0])
        name, args = next(iter(call.items()))
        text = json.dumps([{"name": name, "arguments": args}])
        run_id = row.id
    model = ScriptedModel(responses=[response(text)])
    monkeypatch.setattr("app.llm.factory.create_chat_model", lambda *a, **kw: model)
    asyncio.run(execute_run(api_client, run_id))
    service.advance(batch["id"])
    report = result(api_client, batch)
    assert report["batch"]["status"] == "completed"
    assert report["batch"]["passed"] == 1, report
    assert report["cases"]["items"][0]["run_status"] == "succeeded"
    with api_client.app.state.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(Message)) == 0


def test_wrong_answer_does_not_fail_the_successful_run_and_restart_does_not_resubmit(api_client):
    batch = create(api_client, employee(api_client), 2).json()
    service = api_client.app.state.evaluations
    service.advance(batch["id"])
    run_id = result(api_client, batch)["cases"]["items"][0]["run_id"]
    api_client.app.state.runs.complete(Completion(run_id, "错误答卷", "succeeded"))
    restarted = EvaluationService(service.database, service.runs)
    restarted.advance(batch["id"])
    report = result(api_client, batch)
    assert report["batch"]["failed"] == 1
    assert report["cases"]["items"][0]["run_status"] == "succeeded"
    assert report["cases"]["items"][0]["grading"]["error_type"] == "answer_format"
    with service.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(Run)) == 1


def test_cancel_keeps_records_and_never_submits_remaining_questions(api_client):
    batch = create(api_client, employee(api_client), 3).json()
    service = api_client.app.state.evaluations
    service.advance(batch["id"])
    assert api_client.post(f"/api/evaluations/{batch['id']}/cancel").status_code == 200
    for _ in range(3):
        service.advance(batch["id"])
    report = result(api_client, batch)
    assert report["batch"]["status"] == "cancelled"
    assert report["batch"]["cancelled"] == 3
    assert report["batch"]["scored"] == 0
    with service.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(Run)) == 1


def test_cancel_scores_already_completed_answer_before_cancelling_remaining_work(api_client):
    batch = create(api_client, employee(api_client), 3).json()
    service = api_client.app.state.evaluations
    service.advance(batch["id"])
    run_id = result(api_client, batch)["cases"]["items"][0]["run_id"]
    with service.database.transaction() as db:
        case = db.scalar(select(EvaluationCase).where(EvaluationCase.run_id == run_id))
        name, args = next(iter(acceptable(case.functions[0], case.expected[0]).items()))
        answer = json.dumps([{"name": name, "arguments": args}])
    api_client.app.state.runs.complete(Completion(run_id, answer, "succeeded"))
    assert api_client.post(f"/api/evaluations/{batch['id']}/cancel").status_code == 200
    report = result(api_client, batch)
    assert report["batch"]["status"] == "cancelled"
    assert report["batch"]["passed"] == 1
    assert report["batch"]["cancelled"] == 2
    assert report["cases"]["items"][0]["answer"] == answer
    assert report["cases"]["items"][0]["run_status"] == "succeeded"
    assert api_client.post(f"/api/evaluations/{batch['id']}/cancel").json() == report["batch"]


def test_scoring_failure_preserves_answer_and_does_not_change_run_success(api_client, monkeypatch):
    batch = create(api_client, employee(api_client)).json()
    service = api_client.app.state.evaluations
    service.advance(batch["id"])
    run_id = result(api_client, batch)["cases"]["items"][0]["run_id"]
    api_client.app.state.runs.complete(Completion(run_id, "原始答卷", "succeeded"))

    def broken(*args):
        raise RuntimeError("Injected scoring failure")

    monkeypatch.setattr("app.evaluations.service.grade", broken)
    service.advance(batch["id"])
    report = result(api_client, batch)
    assert report["batch"]["errors"] == 1 and report["batch"]["scored"] == 0
    assert report["batch"]["pass_rate"] is None
    case = report["cases"]["items"][0]
    assert case["answer"] == "原始答卷" and case["run_status"] == "succeeded"
    assert case["error_code"] == "grading_failed" and case["expected"] is None


def test_concurrent_creation_and_scanners_submit_each_question_once(api_client):
    agent = employee(api_client)
    actor = api_client.app.state.auth.resolve(api_client.cookies.get("app_session"))
    service = api_client.app.state.evaluations
    key = str(uuid4())

    def submit(_):
        return service.create(actor, agent["id"], SUITE_ID, 2, key)

    with ThreadPoolExecutor(max_workers=4) as pool:
        batches = list(pool.map(submit, range(4)))
        assert len({batch["id"] for batch in batches}) == 1
        list(pool.map(service.advance, [batches[0]["id"]] * 4))
    with service.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(EvaluationBatch)) == 1
        assert db.scalar(select(func.count()).select_from(EvaluationCase)) == 2
        assert db.scalar(select(func.count()).select_from(Run)) == 1


def test_config_change_stops_exam_before_running_new_questions(api_client):
    agent = employee(api_client)
    batch = create(api_client, agent, 2).json()
    changed = api_client.patch(
        f"/api/agents/{agent['id']}",
        json={
            "expected_revision": agent["revision"],
            "system_prompt": "职责已改变",
        },
    )
    assert changed.status_code == 200
    api_client.app.state.evaluations.advance(batch["id"])
    report = result(api_client, batch)
    assert report["batch"]["status"] == "failed"
    assert report["batch"]["error_code"] == "evaluation_config_changed"
    assert report["batch"]["errors"] == 2
    with api_client.app.state.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(Run)) == 0


def test_revoked_session_stops_new_exam_work(api_client):
    batch = create(api_client, employee(api_client)).json()
    actor = api_client.app.state.auth.resolve(api_client.cookies.get("app_session"))
    from app.auth.models import AuthSession
    from app.values import utc_now

    with api_client.app.state.database.transaction() as db:
        db.get(AuthSession, actor.session_id).revoked_at = utc_now()
    api_client.app.state.evaluations.advance(batch["id"])
    with api_client.app.state.database.transaction() as db:
        assert db.get(EvaluationBatch, batch["id"]).error_code == "actor_session_invalid"
        assert db.scalar(select(func.count()).select_from(Run)) == 0


def test_other_user_and_guest_cannot_read_private_exam(api_client):
    batch = create(api_client, employee(api_client)).json()
    _, token = api_client.app.state.auth.github_login("other-user-fixture", "other", None)
    api_client.cookies.set("app_session", token)
    assert api_client.get(f"/api/evaluations/{batch['id']}").status_code == 404
    api_client.cookies.clear()
    assert api_client.get(f"/api/evaluations/{batch['id']}").status_code == 401

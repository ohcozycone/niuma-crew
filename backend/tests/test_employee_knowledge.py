import json
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_knowledge_library import create, process, upload
from test_knowledge_vectors import build, connection
from test_knowledge_vectors import upstream as upstream

from app.auth.actor import Actor
from app.auth.models import AuthSession, User
from app.employees.knowledge import capture_knowledge
from app.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    ServiceUnavailableError,
)
from app.execution.models import Run
from app.infrastructure.database.identifiers import allocate_id
from app.knowledge.models import LibraryChunk, RunKnowledgeEvidence
from app.knowledge.schemas import LibraryCreate
from app.runtime.contracts.tools import ToolInvocation
from app.values import new_uuid, utc_now


def agent(client):
    result = client.post(
        "/api/agents", json={"name": "知识员工-" + str(uuid4())[:8], "avatar_id": "default"}
    )
    assert result.status_code == 201, result.text
    return result.json()["id"]


def assemble(client, employee, ids, revision=None, **kwargs):
    if revision is None:
        revision = client.get(f"/api/agents/{employee}").json()["revision"]
    return client.patch(
        f"/api/agents/{employee}",
        json={
            "expected_revision": revision,
            "knowledge": {"knowledge_base_ids": ids, "mode": "on_demand", "top_k": 6, **kwargs},
        },
    )


def run(client, employee, *, owner=None):
    with client.app.state.database.transaction() as db:
        session = db.scalar(select(AuthSession).where(AuthSession.kind == "user"))
        snapshot = {
            "agent_id": employee,
            "knowledge": capture_knowledge(db, employee),
            "run_timeout": 120,
        }
        snapshot["tools"] = [
            {
                "kind": "knowledge",
                "binding_id": "knowledge:search",
                "tool_name": "search_knowledge",
                "exposed_name": "search_knowledge",
            }
        ]
        row = Run(
            id=allocate_id(db),
            thread_id=new_uuid(),
            agent_id=employee,
            owner_user_id=owner or session.user_id,
            initiated_by_user_id=session.user_id,
            initiated_by_session_id=session.id,
            origin_kind="conversation",
            operation="knowledge-test",
            client_request_id=new_uuid(),
            request_hash="test",
            config_snapshot=snapshot,
            input_snapshot=[],
            status="running",
            started_at=utc_now(),
        )
        db.add(row)
        db.flush()
        return row.id, snapshot


def member(db):
    user = User(id=new_uuid(), username="member", role="member", password_hash=None, is_active=True)
    db.add(user)
    db.flush()
    return Actor("user", "", user.id, user.username, user.role, utc_now() + timedelta(hours=1))


def ready(client, kb, body="# 差旅制度\n住宿需要发票和逐晚明细。", name="制度.md"):
    doc = upload(client, kb, body, name).json()
    result = process(client, kb)
    assert result.status_code == 200 and result.json()["status"] == "succeeded"
    return doc


def test_employee_binding_revision_guard_and_retired_personal_endpoint(api_client):
    employee = agent(api_client)
    kb = create(api_client)["id"]
    before = api_client.get(f"/api/agents/{employee}").json()
    assert before["knowledge"]["knowledge_base_ids"] == []
    changed = assemble(api_client, employee, [kb], mode="always", top_k=3)
    assert changed.status_code == 200 and changed.json()["knowledge"]["mode"] == "always"
    assert assemble(api_client, employee, [], revision=before["revision"]).status_code == 409
    assert assemble(api_client, employee, [kb, kb]).status_code == 422
    assert assemble(api_client, employee, [kb], top_k=13).status_code == 422
    assert api_client.get(f"/api/knowledge-bases/employee-bindings/{employee}").status_code == 404
    assert assemble(api_client, employee, []).json()["resource_counts"]["knowledge_bases"] == 0


def test_organization_libraries_are_manager_owned_and_employee_scope_is_shared(api_client):
    employee = agent(api_client)
    kb = create(api_client)["id"]
    assert assemble(api_client, employee, [kb]).status_code == 200
    service = api_client.app.state.knowledge
    with service.database.transaction() as db:
        other = member(db)
        captured = capture_knowledge(db, employee)
        assert [item["id"] for item in captured["libraries"]] == [kb]
        assert "user_id" not in captured
    with pytest.raises(PermissionDeniedError):
        service.create(other, LibraryCreate(name="无权创建", client_request_id=uuid4()))
    with pytest.raises(PermissionDeniedError):
        service.libraries(other)


def test_multilibrary_retrieval_global_limit_and_pending_sources_are_distinct(api_client):
    employee = agent(api_client)
    ids = [create(api_client, name)["id"] for name in ("交通", "住宿", "仅原件")]
    ready(api_client, ids[0], "# 交通\n住宿出差需要高铁发票。")
    ready(api_client, ids[1], "# 住宿\n住宿需要酒店发票。")
    upload(api_client, ids[2], "# 机密未处理\n住宿原件不得送给模型。")
    assert assemble(api_client, employee, ids, top_k=2).status_code == 200
    run_id, snapshot = run(api_client, employee)
    service = api_client.app.state.knowledge
    result = service.retrieval.call(run_id, "search_knowledge", {"query": "住宿"})
    payload = json.loads(result.content)
    assert result.status == "succeeded" and len(payload["hits"]) == 2
    assert {hit["knowledge_base_id"] for hit in payload["hits"]} == set(ids[:2])
    assert {state["id"]: state["status"] for state in payload["libraries"]}[ids[2]] == "pending"
    assert "不得送给模型" not in result.content
    assert all(state["strategy"] == "bm25" for state in payload["libraries"])
    assert len(result.content.encode()) < 20000
    with api_client.app.state.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(RunKnowledgeEvidence)) == 2
        assert (
            service.access.authorize(
                db,
                snapshot,
                ToolInvocation("tool:1", "knowledge:search", "search_knowledge", {"query": "住宿"}),
            )["recovery"]
            == "readonly"
        )
    restricted = json.loads(
        service.retrieval.call(
            run_id, "search_knowledge", {"query": "住宿", "library_ids": [ids[0]]}
        ).content
    )
    assert len(restricted["hits"]) == 1


def test_unknown_scope_extra_arguments_and_unmounted_run_are_refused(api_client):
    employee = agent(api_client)
    kb = create(api_client)["id"]
    assemble(api_client, employee, [kb])
    run_id, snapshot = run(api_client, employee)
    service = api_client.app.state.knowledge
    with pytest.raises(InvalidInputError, match="检索范围"):
        service.retrieval.call(
            run_id, "search_knowledge", {"query": "住宿", "library_ids": [kb, kb]}
        )
    with pytest.raises(InvalidInputError):
        service.retrieval.call(run_id, "search_knowledge", {"query": "住宿", "user_id": "other"})
    with pytest.raises(InvalidInputError):
        service.retrieval.call(
            run_id, "search_knowledge", {"query": "住宿", "library_ids": [str(uuid4())]}
        )
    with api_client.app.state.database.transaction() as db:
        with pytest.raises(InvalidInputError):
            service.access.authorize(
                db,
                snapshot,
                ToolInvocation(
                    "tool:2",
                    "knowledge:search",
                    "search_knowledge",
                    {"query": "住宿", "library_ids": [str(uuid4())]},
                ),
            )
    assemble(api_client, employee, [])
    no_run, _ = run(api_client, employee)
    with pytest.raises(ConflictError, match="本轮没有挂载"):
        service.retrieval.call(no_run, "search_knowledge", {"query": "住宿"})


def test_snapshot_cannot_forge_policy_or_tool_registration(api_client):
    employee = agent(api_client)
    kb = create(api_client)["id"]
    assemble(api_client, employee, [kb])
    _, snapshot = run(api_client, employee)
    service = api_client.app.state.knowledge
    invocation = ToolInvocation("tool:1", "knowledge:search", "search_knowledge", {"query": "住宿"})
    with api_client.app.state.database.transaction() as db:
        with pytest.raises(ConflictError):
            service.access.authorize(db, {**snapshot, "tools": []}, invocation)
        for key, value in (("mode", "always"), ("top_k", 12)):
            with pytest.raises(ConflictError):
                service.access.assert_current(
                    db, {**snapshot, "knowledge": {**snapshot["knowledge"], key: value}}
                )


def test_empty_match_and_global_result_byte_budget(api_client):
    employee = agent(api_client)
    kb = create(api_client)["id"]
    ready(api_client, kb, "# 制度\n" + "住宿需要发票😀。" * 1500)
    assemble(api_client, employee, [kb], top_k=12)
    run_id, _ = run(api_client, employee)
    service = api_client.app.state.knowledge
    result = service.retrieval.call(run_id, "search_knowledge", {"query": "住宿"})
    payload = json.loads(result.content)
    assert 1 <= len(payload["hits"]) <= 12 and len(result.content.encode()) < 20000
    assert len(result.sources) == len(payload["hits"])
    empty = json.loads(
        service.retrieval.call(
            run_id, "search_knowledge", {"query": "完全不存在的航天器零件"}
        ).content
    )
    assert empty["status"] == "no_match" and empty["hits"] == []


def test_evidence_read_and_citations_are_run_scoped(api_client):
    employee = agent(api_client)
    kb = create(api_client)["id"]
    ready(api_client, kb, "# 制度\n" + "住宿需要发票。" * 150)
    assemble(api_client, employee, [kb])
    run_id, _ = run(api_client, employee)
    other, _ = run(api_client, employee)
    service = api_client.app.state.knowledge
    hit = json.loads(service.retrieval.call(run_id, "search_knowledge", {"query": "住宿"}).content)[
        "hits"
    ][0]
    read = json.loads(
        service.retrieval.call(
            run_id, "read_knowledge_source", {"evidence_id": hit["evidence_id"], "offset": 10}
        ).content
    )
    assert read["offset"] == 10 and read["source_url"] == hit["source_url"]
    service.evidence.finalize_answer(run_id, f"依据 [{hit['evidence_id']}]({hit['source_url']})。")
    canonical = f"依据 [{hit['evidence_id']}]({hit['source_url']})。"
    missing_slash = canonical.replace("](/knowledge/", "](knowledge/")
    assert service.evidence.finalize_answer(run_id, missing_slash) == canonical
    assert service.evidence.finalize_answer(run_id, canonical) == canonical
    # 公开网页不会仅因路径含 knowledge 就获得私人证据资格。
    service.evidence.finalize_answer(
        run_id, "公开参考：[文档](https://docs.example/knowledge/introduction)。"
    )
    for answer in (
        "[伪造](" + hit["source_url"].replace(str(run_id), "999999999999") + ")",
        "K-deadbeefdeadbeef",
        f"[篡改]({hit['source_url']}#fake)",
        f"[前缀](sandbox:{hit['source_url']})",
        f"[相对]({hit['source_url'].lstrip('/')})",
        f"[相对](.{hit['source_url']})",
        f"[外站](https://evil.example{hit['source_url']})",
        f"sandbox:{hit['source_url']}",
    ):
        with pytest.raises(InvalidInputError) as error:
            service.evidence.finalize_answer(run_id, answer)
        assert error.value.code == "knowledge_citation_invalid"
        with pytest.raises(InvalidInputError):
            service.evidence.finalize_answer(run_id, answer)
    with pytest.raises(NotFoundError):
        service.retrieval.call(other, "read_knowledge_source", {"evidence_id": hit["evidence_id"]})
    with pytest.raises(InvalidInputError):
        service.evidence.finalize_answer(other, f"[{hit['evidence_id']}]({hit['source_url']})")
    with pytest.raises(InvalidInputError):
        service.evidence.finalize_answer(other, missing_slash)


def test_finalization_cannot_pair_one_evidence_id_with_another_registered_source(api_client):
    employee = agent(api_client)
    kb = create(api_client)["id"]
    ready(api_client, kb, "# 住宿标准\n住宿需要发票。", "标准.md")
    ready(api_client, kb, "# 住宿材料\n住宿需要审批。", "材料.md")
    assemble(api_client, employee, [kb])
    run_id, _ = run(api_client, employee)
    service = api_client.app.state.knowledge
    hits = json.loads(
        service.retrieval.call(run_id, "search_knowledge", {"query": "住宿"}).content
    )["hits"]
    assert len(hits) == 2
    for target in (hits[1]["source_url"], hits[1]["source_url"].lstrip("/")):
        with pytest.raises(InvalidInputError) as error:
            service.evidence.finalize_answer(run_id, f"[{hits[0]['evidence_id']}]({target})")
        assert error.value.code == "knowledge_citation_invalid"


@pytest.mark.parametrize("mutation", ["unbind", "delete", "reprocess", "cancel", "session"])
def test_live_authorization_rejects_revoked_or_changed_evidence(api_client, mutation):
    employee = agent(api_client)
    kb = create(api_client)["id"]
    doc = ready(api_client, kb, "# 制度\n" + "住宿需要发票。" * 150)
    assemble(api_client, employee, [kb])
    run_id, snapshot = run(api_client, employee)
    service = api_client.app.state.knowledge
    hit = json.loads(service.retrieval.call(run_id, "search_knowledge", {"query": "住宿"}).content)[
        "hits"
    ][0]
    if mutation == "unbind":
        assemble(api_client, employee, [])
    elif mutation == "delete":
        actor = Actor(
            "user",
            "",
            str(uuid4()),
            "admin",
            "admin",
            utc_now() + timedelta(hours=1),
        )
        service.remove(actor, kb, doc["id"])
    elif mutation == "reprocess":
        with api_client.app.state.database.transaction() as db:
            chunk = db.get(LibraryChunk, hit["chunk_id"])
            chunk.snapshot = {**chunk.snapshot, "text": "同文档版本但规则重切"}
    else:
        with api_client.app.state.database.transaction() as db:
            row = db.get(Run, run_id)
            if mutation == "cancel":
                row.status = "cancelling"
            else:
                db.get(AuthSession, row.initiated_by_session_id).revoked_at = utc_now()
    with pytest.raises(ConflictError):
        service.retrieval.call(run_id, "read_knowledge_source", {"evidence_id": hit["evidence_id"]})
    with pytest.raises(ConflictError):
        service.evidence.finalize_answer(run_id, "[来源](" + hit["source_url"] + ")")
    with pytest.raises(ConflictError):
        service.evidence.finalize_answer(
            run_id, f"[{hit['evidence_id']}]({hit['source_url'].lstrip('/')})"
        )
    if mutation in {"unbind", "delete", "reprocess"}:
        with api_client.app.state.database.transaction() as db:
            with pytest.raises(ConflictError):
                service.access.assert_current(db, snapshot, run_id)


def test_authorized_admin_can_use_fixed_employee_knowledge_in_another_owned_conversation(
    api_client,
):
    employee = agent(api_client)
    kb = create(api_client)["id"]
    ready(api_client, kb)
    assemble(api_client, employee, [kb])
    with api_client.app.state.database.transaction() as db:
        other = member(db)
    run_id, _ = run(api_client, employee, owner=other.user_id)
    result = api_client.app.state.knowledge.retrieval.call(
        run_id, "search_knowledge", {"query": "住宿"}
    )
    assert result.status == "succeeded"


def test_automatic_upstream_failure_is_not_no_match(api_client, monkeypatch):
    employee = agent(api_client)
    kb = create(api_client)["id"]
    ready(api_client, kb)
    assemble(api_client, employee, [kb])
    run_id, _ = run(api_client, employee)
    service = api_client.app.state.knowledge

    def fail(*args, **kwargs):
        raise ServiceUnavailableError("upstream_unavailable", "检索服务暂不可用。")

    monkeypatch.setattr(service.retrieval, "query", fail)
    failure = service.retrieval.call(run_id, "search_knowledge", {"query": "住宿"})
    assert failure.status == "failed" and "upstream_unavailable" in failure.content


def test_auto_uses_real_partial_hybrid_and_does_not_hide_embedding_failure(api_client, upstream):
    employee = agent(api_client)
    kb = create(api_client)["id"]
    ready(api_client, kb, "# 已有住宿\n住宿标准每晚400元。", "旧制度.md")
    model = connection(api_client)
    assert build(api_client, kb, model["id"]).status_code == 200
    ready(api_client, kb, "# 新增住宿\n酒店住宿需要发票。", "新增制度.md")
    assemble(api_client, employee, [kb])
    run_id, _ = run(api_client, employee)
    service = api_client.app.state.knowledge
    before = len(upstream["requests"])
    result = service.retrieval.call(run_id, "search_knowledge", {"query": "住宿"})
    payload = json.loads(result.content)
    state = payload["libraries"][0]
    assert result.status == "succeeded" and len(payload["hits"]) == 2
    assert state["strategy"] == "hybrid" and state["status"] == "partial"
    assert state["vector_chunks"] == 1 and state["chunks"] == 2
    assert len(upstream["requests"]) == before + 1
    upstream["status"] = 503
    failed = service.retrieval.call(run_id, "search_knowledge", {"query": "住宿"})
    assert failed.status == "failed" and json.loads(failed.content)["status"] == "failed"


@pytest.mark.parametrize("strategy", ["auto", "bm25", "vector", "hybrid"])
def test_retired_employee_strategy_is_rejected_without_saving(api_client, strategy):
    employee = agent(api_client)
    kb = create(api_client)["id"]
    assert assemble(api_client, employee, [kb], strategy=strategy).status_code == 422
    settings = api_client.get(f"/api/agents/{employee}").json()["knowledge"]
    assert settings["knowledge_base_ids"] == []
    assert "strategy" not in settings


def test_mixed_library_capabilities_use_the_same_automatic_query_path(api_client, upstream):
    employee = agent(api_client)
    keyword = create(api_client, "关键词资料")["id"]
    semantic = create(api_client, "语义资料")["id"]
    ready(api_client, keyword)
    ready(api_client, semantic, "# 住宿规定\n酒店报销上限400元。")
    model = connection(api_client)
    assert build(api_client, semantic, model["id"]).status_code == 200
    assert assemble(api_client, employee, [keyword, semantic]).status_code == 200
    run_id, snapshot = run(api_client, employee)
    assert "strategy" not in snapshot["knowledge"]
    result = api_client.app.state.knowledge.retrieval.call(
        run_id, "search_knowledge", {"query": "住宿"}
    )
    assert result.status == "succeeded"
    states = {item["id"]: item["strategy"] for item in json.loads(result.content)["libraries"]}
    assert states == {keyword: "bm25", semantic: "hybrid"}

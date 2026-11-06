"""Employee knowledge travels through the real SDK, host actions and reply persistence."""

import asyncio
import json
import re
from collections.abc import Callable

import pytest
from configuration_helpers import set_submission_limits
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field, PrivateAttr
from run_helpers import complete_run, read_reply
from runtime_helpers import make_task
from sqlalchemy import func, select
from test_capability_runtime import ScriptedModel, execute, response
from test_conversations import send, setup_agent
from test_knowledge_library import create, process, upload

from app.auth.models import User
from app.conversations.models import Conversation, Message
from app.execution.contracts import Completion
from app.execution.models import Run, RunAction
from app.execution.runtime.tool_calls import presearch

MARKER = "合成验证：住宿每晚最高400元，发票和审批记录齐全后提交。"


class KnowledgeModel(BaseChatModel):
    """A deterministic chat model reads the actual tool envelope before choosing its citation."""

    mode: str = "on_demand"
    read_source: bool = True
    invalid_citation: bool = False
    source_prefix: str = ""
    omit_source_slash: bool = False
    mutation: Callable[[], None] | None = Field(default=None, exclude=True)
    prompts: list[str] = Field(default_factory=list)
    bindings: list[list[str]] = Field(default_factory=list)
    _round: int = PrivateAttr(default=0)
    _hit: dict = PrivateAttr(default_factory=dict)

    @property
    def _llm_type(self):
        return "employee-knowledge-fixture"

    def bind_tools(self, tools, **kwargs):
        self.bindings.append([getattr(tool, "name", "unknown") for tool in tools])
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.prompts.append("\n".join(str(message.content) for message in messages))
        self._round += 1
        if self.mode == "on_demand" and self._round == 1:
            answer = response(
                "先查本公司的住宿制度。",
                [
                    {
                        "id": "knowledge-search",
                        "name": "search_knowledge",
                        "args": {"query": "住宿 发票 审批"},
                    }
                ],
            )
        else:
            tool_messages = [message for message in messages if isinstance(message, ToolMessage)]
            for message in tool_messages:
                payload = json.loads(str(message.content))
                if payload.get("hits"):
                    self._hit = next(
                        (hit for hit in payload["hits"] if "400" in hit["content"]),
                        payload["hits"][0],
                    )
            if self.mode == "on_demand" and self._round == 2 and self.read_source:
                answer = response(
                    "补读本轮证据。",
                    [
                        {
                            "id": "knowledge-read",
                            "name": "read_knowledge_source",
                            "args": {"evidence_id": self._hit["evidence_id"], "offset": 0},
                        }
                    ],
                )
            else:
                if self.mode == "always":
                    prompt = self.prompts[-1]
                    identifier = re.search(r"K-[a-f0-9]{16}", prompt)
                    url = re.search(
                        r"/knowledge/[a-f0-9-]+/documents/[a-f0-9-]+\?chunk=[a-f0-9]{64}", prompt
                    )
                    assert identifier is not None and url is not None, prompt
                    self._hit = {"evidence_id": identifier.group(), "source_url": url.group()}
                if self.mutation:
                    self.mutation()
                identifier = (
                    "K-0000000000000000" if self.invalid_citation else self._hit["evidence_id"]
                )
                target = self._hit["source_url"]
                if self.omit_source_slash:
                    target = target.lstrip("/")
                answer = response(
                    f"住宿每晚最高400元。[{identifier}]({self.source_prefix}{target})"
                )
        return ChatResult(generations=[ChatGeneration(message=answer)])


def configure(client, *, mode="on_demand", processed=True):
    _, agent, conversation = setup_agent(client)
    base = create(client, "差旅制度")
    document = upload(client, base["id"], "# 差旅制度\n## 住宿\n" + MARKER, "差旅制度.md").json()
    if processed:
        process(client, base["id"])
    payload = {
        "expected_revision": 0,
        "knowledge_base_ids": [base["id"]],
        "mode": mode,
        "strategy": "auto",
        "top_k": 6,
    }
    accepted = client.put(f"/api/knowledge-bases/employee-bindings/{agent['id']}", json=payload)
    assert accepted.status_code == 200, accepted.text
    return agent, conversation, base, document, accepted.json()


def actions(client, run_id):
    return read_reply(client, run_id)["steps"]


def assert_unpublished(client, reply_id):
    with client.app.state.database.transaction() as db:
        assert db.get(Message, reply_id).body is None
        assert db.get(Run, reply_id).status in {
            "failed",
            "cancelled",
            "interrupted",
        }


def test_no_mount_does_not_offer_knowledge_tools_or_change_system_prompt(api_client, monkeypatch):
    _, agent, conversation = setup_agent(api_client)
    model = ScriptedModel(responses=[response("你好，我是你的数字员工。")])
    accepted = send(api_client, conversation).json()["response"]
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "succeeded", result
    assert all(
        "search_knowledge" not in names and "read_knowledge_source" not in names
        for names in model.bindings
    )
    assert "可用知识库" not in model.prompts[0]
    assert (
        api_client.get(f"/api/agents/{agent['id']}").json()["system_prompt"] == "仅使用中文回答。"
    )


def test_on_demand_search_and_source_read_are_real_host_actions(api_client, monkeypatch):
    agent, conversation, base, document, _ = configure(api_client)
    model = KnowledgeModel()
    accepted = send(api_client, conversation, "本公司住宿和报销材料要求是什么？").json()["response"]
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "succeeded", result
    assert result["content"].startswith("住宿每晚最高400元。")
    assert MARKER not in model.prompts[0] and MARKER in model.prompts[1]
    assert all(
        "search_knowledge" in names and "read_knowledge_source" in names for names in model.bindings
    )
    assert all("read_file" not in names for names in model.bindings)
    steps = actions(api_client, accepted["id"])
    assert [step["kind"] for step in steps] == [
        "model_call",
        "tool_call",
        "model_call",
        "tool_call",
        "model_call",
    ]
    assert [step["safe_details"]["name"] for step in steps if step["kind"] == "tool_call"] == [
        "search_knowledge",
        "read_knowledge_source",
    ]
    assert all(step["status"] == "succeeded" for step in steps)
    assert f"/knowledge/{base['id']}/documents/{document['id']}?chunk=" in result["content"]
    assert (
        api_client.get(f"/api/agents/{agent['id']}").json()["system_prompt"] == "仅使用中文回答。"
    )
    assert any(step["safe_details"].get("sources") for step in steps)


@pytest.mark.parametrize("mode", ["on_demand", "always"])
def test_missing_source_slash_publishes_without_repeating_model_calls(
    api_client, monkeypatch, mode
):
    _, conversation, base, document, _ = configure(api_client, mode=mode)
    model = KnowledgeModel(mode=mode, read_source=False, omit_source_slash=True)
    accepted = send(api_client, conversation, "住宿标准是多少？").json()["response"]
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "succeeded", result
    canonical = f"/knowledge/{base['id']}/documents/{document['id']}?chunk="
    assert "](" + canonical in result["content"]
    expected_calls = 2 if mode == "on_demand" else 1
    steps = actions(api_client, accepted["id"])
    model_steps = [step for step in steps if step["kind"] == "model_call"]
    assert len(model_steps) == len(model.prompts) == expected_calls
    assert "](knowledge/" in model_steps[-1]["output_text"]
    with api_client.app.state.database.transaction() as db:
        assert db.get(Message, accepted["id"]).body == result["content"]


def test_always_retrieves_before_first_model_and_records_its_own_action(api_client, monkeypatch):
    _, conversation, _, _, _ = configure(api_client, mode="always")
    model = KnowledgeModel(mode="always")
    accepted = send(api_client, conversation, "住宿标准是多少？").json()["response"]
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "succeeded", result
    assert len(model.prompts) == 1 and MARKER in model.prompts[0]
    steps = actions(api_client, accepted["id"])
    assert [step["kind"] for step in steps] == ["tool_call", "model_call"]
    assert steps[0]["safe_details"]["name"] == "search_knowledge"
    with api_client.app.state.database.transaction() as db:
        stored = db.scalar(
            select(RunAction).where(
                RunAction.run_id == accepted["id"],
                RunAction.kind == "tool_call",
            )
        )
        assert stored.call_key == "knowledge:presearch"
        assert stored.result_payload and MARKER in stored.result_payload["content"]


def test_pending_library_never_sends_unprocessed_original_to_the_model(api_client, monkeypatch):
    _, conversation, _, _, _ = configure(api_client, mode="always", processed=False)
    model = ScriptedModel(responses=[response("目前资料尚未处理，无法确认公司标准。")])
    accepted = send(api_client, conversation, "住宿标准是多少？").json()["response"]
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "succeeded", result
    assert MARKER not in model.prompts[0]
    assert "pending" in model.prompts[0] or "待处理" in model.prompts[0]
    assert [step["kind"] for step in actions(api_client, accepted["id"])] == [
        "tool_call",
        "model_call",
    ]


def test_always_bounds_a_long_user_message_before_querying_knowledge(api_client, monkeypatch):
    _, conversation, _, _, _ = configure(api_client, mode="always")
    service = api_client.app.state.knowledge
    native = service.retrieval.call
    arguments_seen = []

    def call(run_id, name, arguments):
        arguments_seen.append(arguments)
        return native(run_id, name, arguments)

    monkeypatch.setattr(service.retrieval, "call", call)
    accepted = send(api_client, conversation, "住宿标准" * 350).json()["response"]
    result = execute(api_client, monkeypatch, KnowledgeModel(mode="always"), accepted)
    assert result["status"] == "succeeded", result
    assert len(arguments_seen) == 1 and len(arguments_seen[0]["query"]) == 1000


def test_fabricated_knowledge_citation_does_not_publish_trustworthy_partial(
    api_client, monkeypatch
):
    _, conversation, _, _, _ = configure(api_client)
    accepted = send(api_client, conversation, "住宿标准是多少？").json()["response"]
    result = execute(
        api_client, monkeypatch, KnowledgeModel(read_source=False, invalid_citation=True), accepted
    )
    assert result["status"] == "failed", result
    assert result["error"]["code"] == "knowledge_citation_invalid"
    assert not result["content"]
    assert_unpublished(api_client, accepted["id"])


def test_made_up_tool_does_not_get_a_knowledge_permission(api_client, monkeypatch):
    _, conversation, _, _, _ = configure(api_client)
    model = ScriptedModel(
        responses=[
            response(
                "", [{"id": "forged", "name": "search_all_knowledge", "args": {"query": "secret"}}]
            )
        ]
    )
    accepted = send(api_client, conversation).json()["response"]
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "failed", result
    assert result["error"]["code"] == "tool_not_allowed"
    assert not result["content"]


def test_knowledge_calls_share_the_existing_tool_budget(api_client, monkeypatch):
    _, conversation, _, _, _ = configure(api_client)
    set_submission_limits(api_client.app.state.conversation_commands, max_tool_calls=1)
    accepted = send(api_client, conversation, "住宿标准是多少？").json()["response"]
    result = execute(api_client, monkeypatch, KnowledgeModel(), accepted)
    assert result["status"] == "failed", result
    assert result["error"]["code"] == "agent_budget_exceeded"
    calls = [step for step in actions(api_client, accepted["id"]) if step["kind"] == "tool_call"]
    assert len([step for step in calls if step["safe_details"].get("executed") is not False]) == 1
    denied = [step for step in calls if step["safe_details"].get("executed") is False]
    assert len(denied) == 1 and denied[0]["error_code"] == "agent_budget_exceeded"


def test_removing_mount_after_acceptance_stops_run_before_reading_private_data(
    api_client, monkeypatch
):
    agent, conversation, _, _, settings = configure(api_client)
    accepted = send(api_client, conversation, "住宿标准是多少？").json()["response"]
    removed = api_client.put(
        f"/api/knowledge-bases/employee-bindings/{agent['id']}",
        json={
            "expected_revision": settings["revision"],
            "knowledge_base_ids": [],
            "mode": "on_demand",
            "strategy": "auto",
            "top_k": 6,
        },
    )
    assert removed.status_code == 200, removed.text
    model = KnowledgeModel()
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] in {"failed", "cancelled"}, result
    assert not model.prompts and not result["content"]
    assert_unpublished(api_client, accepted["id"])


def test_deleted_evidence_after_lookup_is_not_published_from_model_or_checkpoint(
    api_client, monkeypatch
):
    _, conversation, base, document, _ = configure(api_client)

    def remove():
        result = api_client.delete(f"/api/knowledge-bases/{base['id']}/documents/{document['id']}")
        assert result.status_code == 204, result.text

    accepted = send(api_client, conversation, "住宿标准是多少？").json()["response"]
    model = KnowledgeModel(read_source=False, mutation=remove)
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] in {"failed", "cancelled"}, result
    assert not result["content"]
    assert_unpublished(api_client, accepted["id"])


def test_admin_private_knowledge_cannot_be_accepted_in_another_users_conversation(api_client):
    _, conversation, _, _, _ = configure(api_client)
    with api_client.app.state.database.transaction() as db:
        other = User(username="other-user", password_hash=None, role="member")
        db.add(other)
        db.flush()
        db.get(Conversation, conversation["id"]).owner_user_id = other.id
    rejected = send(api_client, conversation, "把管理员私库的住宿制度回答在这里")
    assert 400 <= rejected.status_code < 500, rejected.text
    with api_client.app.state.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(Run)) == 0


def test_always_reuses_a_durable_action_but_reauthorizes_before_returning_cached_evidence(
    api_client,
    monkeypatch,
):
    agent, conversation, _, _, settings = configure(api_client, mode="always")
    accepted = send(api_client, conversation, "住宿标准是多少？").json()["response"]
    store = api_client.app.state.run_worker.store
    coordinator = api_client.app.state.runs
    row, _ = store.load(accepted["id"])
    assert store.claim(row.id)
    calls = []

    def authorize(active, db=None, invocation=None):
        return coordinator.authorize(row, active, db=db, invocation=invocation)

    def lookup(name, arguments):
        calls.append(name)
        return api_client.app.state.knowledge.retrieval.call(row.id, name, arguments)

    context = make_task(row.id, store, authorize)
    monkeypatch.setattr(context, "knowledge_call", lookup)
    first = asyncio.run(presearch(row.config_snapshot, context, "住宿标准是多少？"))
    cached = asyncio.run(presearch(row.config_snapshot, context, "住宿标准是多少？"))
    assert first == cached and calls == ["search_knowledge"]
    assert len(actions(api_client, accepted["id"])) == 1
    removed = api_client.put(
        f"/api/knowledge-bases/employee-bindings/{agent['id']}",
        json={
            "expected_revision": settings["revision"],
            "knowledge_base_ids": [],
            "mode": "always",
            "strategy": "auto",
            "top_k": 6,
        },
    )
    assert removed.status_code == 200, removed.text
    try:
        asyncio.run(presearch(row.config_snapshot, context, "住宿标准是多少？"))
    except Exception as error:
        assert getattr(error, "code", "").startswith("knowledge_"), error
    else:
        raise AssertionError("Old cached evidence must not survive mount revocation")
    assert calls == ["search_knowledge"]


def test_publication_rechecks_citations_even_when_the_sdk_boundary_is_bypassed(api_client):
    _, conversation, _, _, _ = configure(api_client)
    accepted = send(api_client, conversation, "住宿标准是多少？").json()["response"]
    assert api_client.app.state.run_worker.store.claim(accepted["id"])
    complete_run(api_client)(
        Completion(
            accepted["id"],
            "未经本轮检索却伪造引用[K-0000000000000000]",
            "succeeded",
        )
    )
    result = read_reply(api_client, accepted["id"])
    assert result["status"] == "failed" and result["error"]["code"] == "knowledge_citation_invalid"
    assert not result["content"]
    assert_unpublished(api_client, accepted["id"])


def test_publication_finalizes_exact_evidence_links_when_sdk_is_bypassed(api_client):
    _, conversation, _, _, _ = configure(api_client)
    accepted = send(api_client, conversation, "住宿标准是多少？").json()["response"]
    assert api_client.app.state.run_worker.store.claim(accepted["id"])
    service = api_client.app.state.knowledge
    hit = json.loads(
        service.retrieval.call(accepted["id"], "search_knowledge", {"query": "住宿"}).content
    )["hits"][0]
    raw = f"住宿每晚最高400元。[{hit['evidence_id']}]({hit['source_url'].lstrip('/')})"
    complete_run(api_client)(Completion(accepted["id"], raw, "succeeded"))
    result = read_reply(api_client, accepted["id"])
    assert result["status"] == "succeeded", result
    assert result["content"] == raw.replace("](knowledge/", "](/knowledge/")


@pytest.mark.parametrize("prefix", ["sandbox:", "https://untrusted.example"])
def test_rewritten_scheme_or_host_is_not_a_valid_platform_knowledge_citation(
    api_client, monkeypatch, prefix
):
    _, conversation, _, _, _ = configure(api_client)
    accepted = send(api_client, conversation, "住宿标准是多少？").json()["response"]
    result = execute(
        api_client, monkeypatch, KnowledgeModel(read_source=False, source_prefix=prefix), accepted
    )
    assert result["status"] == "failed", result
    assert result["error"]["code"] == "knowledge_citation_invalid"
    assert not result["content"]
    assert_unpublished(api_client, accepted["id"])

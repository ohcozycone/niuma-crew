from __future__ import annotations

import json
from math import isfinite
from typing import Any, cast

from sqlalchemy.orm import Session

from app.agent.config import AgentConfig
from app.agent.errors import RuntimeFailure
from app.agent.prompts import compose_system_prompt
from app.builtin_tools.knowledge import knowledge_instructions
from app.builtin_tools.knowledge import tool_bindings as knowledge_bindings
from app.builtin_tools.results import result_reader_binding
from app.builtin_tools.tool_search import search_binding
from app.builtin_tools.workspace import workspace_tools
from app.employees.access import configured_agent
from app.employees.assembly import capture_skills, capture_tools
from app.employees.knowledge import capture_knowledge
from app.employees.organization_rules import current_rules
from app.errors import ConflictError, InvalidInputError, ServiceUnavailableError
from app.execution.config import RuntimeConfig
from app.model_connections.models import ModelConnection
from app.model_connections.presets import PRESETS
from app.runtime.contracts.agent import AgentSnapshot
from app.runtime.contracts.runs import RUN_SNAPSHOT_VERSION, RunSpec
from app.runtime.contracts.tools import TOOL_CATALOG_VERSION, catalog_hash
from app.values import digest


def validate_snapshot(value: dict) -> AgentSnapshot:
    """解析凭据和调用模型前拒绝无效快照。"""
    valid = all(
        isinstance(value.get(key), str) for key in ("agent_id", "connection_id", "system_prompt")
    ) and all(
        type(value.get(key)) is int and value[key] > 0
        for key in (
            "schema_version",
            "connection_config_revision",
            "connection_credential_revision",
            "recursion_limit",
            "max_model_calls",
            "max_skill_reads",
            "max_output_tokens",
            "max_output_bytes",
            "max_reasoning_bytes",
            "context_bytes",
        )
    )
    if value.get("schema_version") in (4, 5, RUN_SNAPSHOT_VERSION) and (
        any(
            type(value.get(key)) is not int or value[key] <= 0
            for key in ("summary_trigger_tokens", "summary_keep_tokens")
        )
        or value.get("summary_keep_tokens", 0) >= value.get("summary_trigger_tokens", 0)
        or not isinstance(value.get("memory_scope"), str)
        or not isinstance(value.get("memory_reset"), bool)
    ):
        raise RuntimeFailure("checkpoint_unavailable")
    skills = value.get("skills")
    selected = value.get("selected_skill_ids")
    if not valid or not isinstance(skills, list) or not isinstance(selected, list):
        raise RuntimeFailure("checkpoint_unavailable")
    if not all(isinstance(item, str) for item in selected):
        raise RuntimeFailure("checkpoint_unavailable")
    for skill in skills:
        if (
            not isinstance(skill, dict)
            or not all(
                isinstance(skill.get(key), str)
                for key in (
                    "skill_id",
                    "name",
                    "description",
                    "instructions",
                    "instructions_hash",
                    "assignment_created_at",
                )
            )
            or not all(
                type(skill.get(key)) is int and skill[key] > 0
                for key in ("skill_revision", "assignment_revision")
            )
            or not isinstance(skill.get("parameters"), dict)
        ):
            raise RuntimeFailure("checkpoint_unavailable")
    if (
        type(value.get("run_timeout")) not in (int, float)
        or not isfinite(value["run_timeout"])
        or value["run_timeout"] <= 0
    ):
        raise RuntimeFailure("checkpoint_unavailable")
    return cast(AgentSnapshot, value)


class RunConfiguration:
    def __init__(
        self,
        settings: RuntimeConfig,
        *,
        agent: AgentConfig = AgentConfig(),
        files: Any = None,
        sandboxes: Any = None,
        knowledge: Any = None,
    ) -> None:
        self.settings, self.files, self.agent = settings, files, agent
        self.sandboxes, self.knowledge = sandboxes, knowledge

    def prepare(
        self,
        db: Session,
        agent_id: str,
        content: str,
        selected_skill_ids: list[str],
        *,
        tools_enabled: bool = True,
    ) -> tuple[RunSpec, int]:
        agent = configured_agent(db, agent_id)
        connection = db.get(ModelConnection, agent.model_connection_id)
        if connection is None or not connection.enabled or connection.capability != "chat":
            raise ConflictError("model_not_configured")
        preset = PRESETS[connection.preset_id]
        if len(content.encode()) > self.settings.max_input_bytes:
            raise InvalidInputError("input_too_large")
        rules = current_rules(db)
        system_prompt = compose_system_prompt(
            rules.instructions, agent.system_prompt, agent_name=agent.name
        )
        knowledge = capture_knowledge(db, agent.id) if self.knowledge and tools_enabled else None
        if knowledge:
            system_prompt += knowledge_instructions(knowledge)
        skills = capture_skills(db, agent, selected_skill_ids) if tools_enabled else []
        size = len(system_prompt.encode()) + len(content.encode())
        if size > self.agent.context_bytes:
            raise InvalidInputError("context_limit_exceeded")
        snapshot = RunSpec(
            schema_version=RUN_SNAPSHOT_VERSION,
            checkpoint_resumable=True,
            allow_partial_output=True,
            agent_revision=agent.revision,
            skills=[dict(item) for item in skills],
            authorized_skill_ids=[item["skill_id"] for item in skills],
            selected_skill_ids=selected_skill_ids,
            recursion_limit=self.agent.recursion_limit,
            max_model_calls=self.settings.max_model_calls,
            max_skill_reads=self.settings.max_skill_reads,
            agent_id=agent.id,
            agent_name=agent.name,
            agent_updated_at=agent.updated_at.isoformat(),
            system_prompt=system_prompt,
            agent_system_prompt=agent.system_prompt,
            organization_rules={
                "instructions": rules.instructions,
                "revision": rules.revision,
                "updated_at": rules.updated_at.isoformat().replace("+00:00", "Z"),
            },
            connection_id=connection.id,
            connection_name=connection.name,
            connection_config_revision=connection.config_revision,
            connection_credential_revision=connection.credential_revision,
            preset_id=connection.preset_id,
            provider=preset.provider,
            protocol=preset.protocol,
            base_url=preset.base_url,
            model_id=connection.model_id,
            run_timeout=self.settings.run_timeout,
            max_output_tokens=self.agent.max_output_tokens,
            max_output_bytes=self.settings.max_output_bytes,
            max_reasoning_bytes=self.settings.max_reasoning_bytes,
            context_bytes=self.agent.context_bytes,
        )
        bindings, resumable = capture_tools(db, agent.id) if tools_enabled else ([], True)
        workspace: dict[str, Any] = {"mode": "virtual", "read_roots": [], "write_roots": []}
        if tools_enabled:
            workspace.update(
                {
                    "read_roots": ["/inputs", "/sources", "/workspace", "/outputs", "/skills"],
                    "write_roots": ["/workspace", "/outputs"],
                    "execution_error": "sandbox_not_ready",
                }
            )
            if self.sandboxes is not None:
                try:
                    profile = self.sandboxes.capture_profile()
                except ServiceUnavailableError as error:
                    workspace["execution_error"] = error.code
                else:
                    workspace.update(profile)
                    workspace.update({"mode": "sandbox", "execution_error": None})
                    resumable = False
            bindings.extend(workspace_tools(workspace))
        snapshot.update(
            {
                "tools": bindings,
                "workspace": workspace,
                "input_files": [],
                "max_tool_calls": self.settings.max_tool_calls,
                "checkpoint_resumable": resumable,
            }
        )
        if knowledge:
            snapshot["knowledge"] = knowledge
            snapshot["tools"].extend(knowledge_bindings())
            snapshot["allow_partial_output"] = False
        candidates = [item for item in bindings if item["kind"] in {"mcp_http", "mcp_stdio"}]
        if len(candidates) > 128:
            raise InvalidInputError("tool_candidate_count_exceeded")
        sources: dict[str, dict] = {}
        for item in candidates:
            key = item["connection_id"]
            source = {
                "service_name": item["service_name"],
                "connection_name": item["connection_name"],
                "instructions_hash": item["instructions_hash"],
                "server_instructions": item.get("server_instructions", ""),
            }
            prior = sources.get(key)
            if prior and prior["instructions_hash"] != source["instructions_hash"]:
                raise ConflictError("tool_catalog_changed")
            if (
                prior
                and prior["server_instructions"]
                and source["server_instructions"]
                and prior["server_instructions"] != source["server_instructions"]
            ):
                raise ConflictError("tool_catalog_changed")
            if prior and not source["server_instructions"]:
                source["server_instructions"] = prior["server_instructions"]
            sources[key] = source
        if any(
            source["server_instructions"]
            and digest(source["server_instructions"]) != source["instructions_hash"]
            for source in sources.values()
        ):
            raise ConflictError("tool_catalog_changed")
        projected = []
        keys = {
            "binding_id",
            "agent_id",
            "grant_id",
            "grant_revision",
            "connection_id",
            "config_revision",
            "credential_revision",
            "catalog_revision",
            "tool_name",
            "exposed_name",
            "description",
            "input_schema",
            "descriptor_hash",
            "scope_policy",
            "kind",
            "auth_required",
            "instructions_hash",
            "recovery",
        }
        for item in snapshot["tools"]:
            projected.append(
                {key: value for key, value in item.items() if key in keys}
                if item["kind"] in {"mcp_http", "mcp_stdio"}
                else item
            )
        if (
            len(json.dumps({"tools": projected, "sources": sources}, ensure_ascii=False).encode())
            > 1048576
        ):
            raise InvalidInputError("tool_candidate_bytes_exceeded")
        if candidates:
            projected.extend((result_reader_binding(), search_binding()))
        snapshot["tools"] = projected
        snapshot["tool_catalog"] = {
            "version": TOOL_CATALOG_VERSION,
            "catalog_hash": catalog_hash(projected, sources),
            "sources": sources,
        }
        snapshot["summary_trigger_tokens"] = self.agent.summary_trigger_tokens
        snapshot["summary_keep_tokens"] = self.agent.summary_keep_tokens
        snapshot["memory_scope"] = digest(
            [
                agent.id,
                self.knowledge.evidence.context_revision(db, knowledge) if knowledge else None,
            ]
        )
        snapshot["memory_reset"] = False
        return snapshot, size

    @staticmethod
    def invalidates_memory(previous: dict, current: dict) -> bool:
        """新增能力可保留记忆；既有资源删除或变化时使其失效。"""
        if any(
            previous.get(key) != current.get(key)
            for key in ("memory_scope", "system_prompt", "connection_id", "protocol", "model_id")
        ):
            return True

        def resources(snapshot: dict) -> dict[str, str]:
            result = {
                "skill:" + skill["skill_id"]: digest(skill) for skill in snapshot.get("skills", [])
            }
            for binding in snapshot.get("tools", []):
                if binding["kind"] == "knowledge":
                    continue
                # 新增工具也会改变目录或许可修订，不能仅凭全局修订使旧资源失效。
                result["tool:" + binding["binding_id"]] = digest(
                    {
                        key: binding.get(key)
                        for key in (
                            "descriptor_hash",
                            "instructions_hash",
                            "scope_policy",
                            "connection_id",
                            "config_revision",
                            "credential_revision",
                            "auth_required",
                        )
                    }
                )
            return result

        before, after = resources(previous), resources(current)
        return any(after.get(key) != value for key, value in before.items())

    def bind_history(self, db: Session, row: Any) -> None:
        self.knowledge.evidence.bind_history(db, row)

    def capture_evidence(
        self,
        db: Session,
        snapshot: RunSpec,
        sources: list[tuple[str, str]],
        size: int,
        *,
        owner_user_id: str,
        thread_id: str,
    ) -> None:
        if snapshot.get("knowledge"):
            if self.knowledge is None:
                raise ConflictError("knowledge_unavailable")
            evidence = self.knowledge.evidence.capture_history(
                db,
                snapshot["knowledge"],
                sources,
                max(0, self.agent.context_bytes - size - 1024),
                owner_user_id=owner_user_id,
                thread_id=thread_id,
            )
            snapshot["knowledge"] = {**snapshot["knowledge"], "history_evidence": evidence}

    def capture_files(
        self,
        db: Session,
        snapshot: RunSpec,
        file_ids: list[str],
        owner_id: str | None,
        *,
        allowed_ids: set[str] | None = None,
    ) -> int:
        snapshot["input_files"] = self.files.capture(
            db, file_ids, owner_id, allowed_ids=allowed_ids or ()
        )
        if not any(
            item["kind"] == "workspace"
            and (
                item["tool_name"] == "execute"
                or (
                    item["tool_name"] == "read_file"
                    and "/inputs" in item["scope_policy"].get("read_roots", [])
                )
            )
            for item in snapshot.get("tools", [])
        ):
            raise InvalidInputError("file_tool_required")
        if snapshot["workspace"]["mode"] == "virtual" and (
            any(ref["size"] > 131072 for ref in snapshot["input_files"])
            or sum(ref["size"] for ref in snapshot["input_files"]) > 524288
        ):
            raise InvalidInputError("file_too_large")
        return len(json.dumps(snapshot["input_files"], ensure_ascii=False).encode())

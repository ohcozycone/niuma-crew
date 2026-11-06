"""Capture fixed employee configuration without choosing conversation history."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.employees.access import configured_agent
from app.employees.assembly import capture_skills, capture_tools
from app.employees.organization_rules import current_rules
from app.errors import ConflictError, InvalidInputError
from app.execution.config import RuntimeConfig
from app.execution.contracts import RUN_SNAPSHOT_VERSION, RunSpec
from app.execution.prompts import compose_system_prompt, knowledge_instructions
from app.model_connections.models import ModelConnection
from app.model_connections.presets import PRESETS
from app.values import digest


class RunConfiguration:
    def __init__(
        self,
        settings: RuntimeConfig,
        *,
        files: Any = None,
        sandboxes: Any = None,
        knowledge: Any = None,
    ) -> None:
        self.settings, self.files = settings, files
        self.sandboxes, self.knowledge = sandboxes, knowledge

    def prepare(
        self,
        db: Session,
        agent_id: str,
        content: str,
        selected_skill_ids: list[str],
        user_id: str | None = None,
        *,
        tools_enabled: bool = True,
    ) -> tuple[RunSpec, int]:
        agent = configured_agent(db, agent_id)
        connection = db.get(ModelConnection, agent.model_connection_id)
        if connection is None or not connection.enabled or connection.capability != "chat":
            raise ConflictError("model_not_configured", "所选大脑未启用或不支持聊天。")
        preset = PRESETS[connection.preset_id]
        if len(content.encode()) > self.settings.max_input_bytes:
            raise InvalidInputError("input_too_large", "消息过长，请缩短后再发送。")
        rules = current_rules(db)
        system_prompt = compose_system_prompt(
            rules.instructions, agent.system_prompt, agent_name=agent.name
        )
        knowledge = (
            self.knowledge.assignments.capture(db, agent.id, user_id)
            if self.knowledge and tools_enabled
            else None
        )
        if knowledge:
            system_prompt += knowledge_instructions(knowledge)
        skills = capture_skills(db, agent, selected_skill_ids) if tools_enabled else []
        size = len(system_prompt.encode()) + len(content.encode())
        if size > self.settings.context_bytes:
            raise InvalidInputError("context_limit_exceeded", "系统提示词与消息超过输入限制。")
        snapshot = RunSpec(
            schema_version=RUN_SNAPSHOT_VERSION,
            checkpoint_resumable=True,
            allow_partial_output=True,
            agent_revision=agent.revision,
            skills=[dict(item) for item in skills],
            authorized_skill_ids=[item["skill_id"] for item in skills],
            selected_skill_ids=selected_skill_ids,
            recursion_limit=self.settings.recursion_limit,
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
            max_output_tokens=self.settings.max_output_tokens,
            max_output_bytes=self.settings.max_output_bytes,
            max_reasoning_bytes=self.settings.max_reasoning_bytes,
            context_bytes=self.settings.context_bytes,
        )
        bindings, workspace, resumable = (
            capture_tools(db, agent.id, user_id)
            if tools_enabled
            else ([], {"mode": "virtual"}, True)
        )
        if workspace["mode"] == "sandbox":
            if self.sandboxes is None:
                raise ConflictError("sandbox_not_ready", "沙箱尚未配置。")
            workspace.update(self.sandboxes.capture_profile())
        snapshot.update(
            {
                "tools": bindings,
                "tool_user_id": user_id,
                "workspace": workspace,
                "input_files": [],
                "max_tool_calls": self.settings.max_tool_calls,
                "checkpoint_resumable": resumable,
            }
        )
        if knowledge:
            from app.knowledge.search import tool_bindings as knowledge_bindings

            snapshot["knowledge"] = knowledge
            snapshot["tools"].extend(knowledge_bindings())
            snapshot["allow_partial_output"] = False
        snapshot["summary_trigger_tokens"] = self.settings.summary_trigger_tokens
        snapshot["summary_keep_tokens"] = self.settings.summary_keep_tokens
        snapshot["memory_scope"] = digest(
            [
                agent.id,
                user_id,
                self.knowledge.evidence.context_revision(db, knowledge) if knowledge else None,
            ]
        )
        snapshot["memory_reset"] = False
        return snapshot, size

    @staticmethod
    def invalidates_memory(previous: dict, current: dict) -> bool:
        """Additions keep memory; removed or changed prior resources invalidate it."""
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
                # Global catalog/grant revisions can change when only a new tool is added.
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
                            "personal_binding_id",
                            "personal_binding_revision",
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
        self, db: Session, snapshot: RunSpec, sources: list[tuple[str, str]], size: int
    ) -> None:
        """Revalidate selected execution evidence without importing business messages."""
        if snapshot.get("knowledge"):
            if self.knowledge is None:
                raise ConflictError("knowledge_unavailable", "知识服务尚未装配。")
            evidence = self.knowledge.evidence.capture_history(
                db,
                snapshot["knowledge"],
                sources,
                max(0, self.settings.context_bytes - size - 1024),
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
        """Capture authorized file metadata and enforce the configured workspace limits."""
        snapshot["input_files"] = self.files.capture(
            db, file_ids, owner_id, allowed_ids=allowed_ids or ()
        )
        if not any(
            item["kind"] == "native"
            and (
                item["tool_name"] == "execute"
                or (
                    item["tool_name"] == "read_file"
                    and "/inputs" in item["scope_policy"].get("read_roots", [])
                )
            )
            for item in snapshot.get("tools", [])
        ):
            raise InvalidInputError("file_tool_required", "请先为员工授予输入目录的文件读取工具。")
        if snapshot["workspace"]["mode"] == "virtual" and (
            any(ref["size"] > 131072 for ref in snapshot["input_files"])
            or sum(ref["size"] for ref in snapshot["input_files"]) > 524288
        ):
            raise InvalidInputError(
                "file_too_large",
                "虚拟文本工作区仅支持单文件 128 KiB、总量 512 KiB；大文件请启用沙箱。",
            )
        return len(json.dumps(snapshot["input_files"], ensure_ascii=False).encode())

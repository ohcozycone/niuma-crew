from __future__ import annotations

from math import isfinite
from typing import cast

from app.common.values import digest
from app.runtime.contracts.agent import AgentSnapshot
from app.runtime.contracts.runs import RUN_SNAPSHOT_VERSION
from app.runtime.execution.errors import ExecutionFailure


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
        raise ExecutionFailure("checkpoint_unavailable")
    skills = value.get("skills")
    selected = value.get("selected_skill_ids")
    if not valid or not isinstance(skills, list) or not isinstance(selected, list):
        raise ExecutionFailure("checkpoint_unavailable")
    if not all(isinstance(item, str) for item in selected):
        raise ExecutionFailure("checkpoint_unavailable")
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
            raise ExecutionFailure("checkpoint_unavailable")
    if (
        type(value.get("run_timeout")) not in (int, float)
        or not isfinite(value["run_timeout"])
        or value["run_timeout"] <= 0
    ):
        raise ExecutionFailure("checkpoint_unavailable")
    return cast(AgentSnapshot, value)


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

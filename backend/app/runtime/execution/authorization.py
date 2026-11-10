from collections.abc import Iterable
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.work_authorizations import authorize_work
from app.common.errors import AuthenticationError, ConflictError, PermissionDeniedError
from app.common.values import digest
from app.resources.employees.access import assert_binding, authorize_execution
from app.resources.environments.policy import authorize_workspace_arguments
from app.resources.knowledge.sources import context_revision
from app.resources.mcp.policy import authorize_arguments
from app.runtime.contracts.tools import ToolInvocation
from app.runtime.execution.errors import ExecutionFailure
from app.runtime.execution.models import Run, RunAction
from app.runtime.execution.store import assert_tool_exposure, require_run


def authorize_run(
    db: Session,
    row: Run,
    active: Iterable[str] = (),
    invocation: ToolInvocation | None = None,
    *,
    connections: Any,
    knowledge: Any,
    exposed_tool_ids: Iterable[str] = (),
) -> Any:
    try:
        authorize_work(db, row.initiated_by_user_id, row.initiated_by_session_id)
    except (AuthenticationError, PermissionDeniedError) as error:
        raise ExecutionFailure("actor_session_invalid") from error
    used = cast(
        set[str],
        set(
            db.scalars(
                select(RunAction.skill_id).where(
                    RunAction.run_id == row.id,
                    RunAction.kind == "skill_activation",
                    RunAction.status == "succeeded",
                    RunAction.skill_id.is_not(None),
                )
            )
        ),
    )
    snapshot = row.config_snapshot
    inherited = (
        require_run(db, row.base_run_id).config_snapshot
        if row.base_run_id and not snapshot.get("memory_reset")
        else {}
    )
    if snapshot.get("knowledge"):
        if knowledge is None:
            raise ExecutionFailure("knowledge_access_revoked")
        knowledge.assert_current(db, snapshot, row.id)
        current_scope = digest(
            [
                snapshot["agent_id"],
                context_revision(db, snapshot["knowledge"]),
            ]
        )
        if current_scope != snapshot["memory_scope"]:
            raise ExecutionFailure("knowledge_source_changed")
    # 旧线程消息可能包含本轮未再次调用的资源，仍须复核其许可。
    inherited_skills = {skill["skill_id"] for skill in inherited.get("skills", [])}
    authorize_execution(db, snapshot, used | set(active) | inherited_skills)
    connections.assert_current(
        snapshot["connection_id"],
        snapshot["connection_config_revision"],
        snapshot["connection_credential_revision"],
        db=db,
    )
    used_tools = {
        action.safe_details.get("binding_id")
        for action in db.scalars(
            select(RunAction).where(RunAction.run_id == row.id, RunAction.kind == "tool_call")
        )
    }
    used_tools.update(binding["binding_id"] for binding in inherited.get("tools", []))
    used_tools.update(exposed_tool_ids)
    for binding in snapshot.get("tools", []):
        if binding["binding_id"] in used_tools and binding["kind"] not in {
            "knowledge",
            "workspace",
            "builtin",
        }:
            assert_binding(db, snapshot, binding)
    if invocation is not None:
        assert_tool_exposure(db, row, invocation)
        if invocation.binding_id == "builtin:search_tools" and invocation.name == "search_tools":
            binding = next(
                (
                    item
                    for item in snapshot.get("tools", [])
                    if item["binding_id"] == invocation.binding_id
                ),
                None,
            )
            if binding is None:
                raise ExecutionFailure("tool_not_allowed")
            return binding
        if invocation.binding_id.startswith("knowledge:"):
            if knowledge is None:
                raise ExecutionFailure("tool_not_allowed")
            return knowledge.authorize(db, snapshot, invocation)
        return authorize_tool(db, snapshot, invocation)


def authorize_tool(db: Session, snapshot: dict, invocation: ToolInvocation) -> dict:
    if invocation.skill_id:
        authorize_execution(db, snapshot, [invocation.skill_id])
        root = f"/skills/s-{invocation.skill_id}/"
        skill = next(item for item in snapshot["skills"] if item["skill_id"] == invocation.skill_id)
        allowed = {root + "SKILL.md"} | {
            root + item["path"] for item in skill.get("package_manifest", [])
        }
        if invocation.name != "read_file" or invocation.arguments.get("file_path") not in allowed:
            raise ConflictError("skill_not_allowed")
        return {"recovery": "readonly", "scope_policy": {"max_calls": 32}}
    result_read = invocation.name == "read_tool_result" and invocation.binding_id.startswith(
        "result:"
    )
    origin_id = (
        invocation.binding_id.removeprefix("result:") if result_read else invocation.binding_id
    )
    binding = next(
        (item for item in snapshot.get("tools", []) if item["binding_id"] == origin_id),
        None,
    )
    if not binding or (
        binding["kind"] == "workspace"
        if result_read
        else binding["exposed_name"] != invocation.name
    ):
        raise ConflictError("tool_not_allowed")
    if binding["kind"] == "workspace":
        authorize_workspace_arguments(binding, invocation.arguments)
        return cast(dict, binding)
    assert_binding(db, snapshot, binding)
    if result_read:
        # 分页不调用上游，但仍检查来源工具当前许可并独立扣减读取预算。
        return {**binding, "recovery": "readonly", "scope_policy": {"max_calls": 32}}
    authorize_arguments(binding, invocation.arguments)
    # MCP 的默认单工具限次属于许可策略，不给其他工具附加隐式限次。
    return {**binding, "scope_policy": {"max_calls": 32, **binding["scope_policy"]}}

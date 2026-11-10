from collections.abc import Iterable
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.work_authorizations import authorize_work
from app.builtin_tools.contracts import ToolInvocation
from app.employees.access import assert_binding, authorize_execution, authorize_tool
from app.errors import AuthenticationError, PermissionDeniedError
from app.execution.errors import ExecutionFailure
from app.execution.models import Run, RunAction
from app.execution.store import assert_tool_exposure, require_run
from app.values import digest


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
        knowledge.access.assert_current(db, snapshot, row.id)
        current_scope = digest(
            [
                snapshot["agent_id"],
                knowledge.evidence.context_revision(db, snapshot["knowledge"]),
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
            return knowledge.access.authorize(db, snapshot, invocation)
        return authorize_tool(db, snapshot, invocation)

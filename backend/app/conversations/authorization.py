"""Compose current identity, employee assembly, model and tool permissions."""

from sqlalchemy import select

from app.agents.execution_config import authorize_execution
from app.agents.tool_grants import assert_binding, authorize_tool
from app.auth.permissions import require_permission
from app.errors import AuthenticationError, PermissionDeniedError
from app.execution.errors import ExecutionFailure
from app.execution.models import RunAction


class ConversationAuthorization:
    def __init__(self, database, auth, connections, knowledge=None):
        self.database, self.auth, self.connections = database, auth, connections
        self.knowledge = knowledge

    def check(self, row, active=(), db=None, invocation=None):
        if db is None:
            with self.database.transaction() as session:
                return self.check(row, active, session, invocation)
        try:
            require_permission(
                self.auth.validate_session(db, row.initiated_by_session_id), "runs:create"
            )
        except (AuthenticationError, PermissionDeniedError) as error:
            raise ExecutionFailure("actor_session_invalid") from error
        used = set(
            db.scalars(
                select(RunAction.skill_id).where(
                    RunAction.run_id == row.id,
                    RunAction.kind == "skill_activation",
                    RunAction.status == "succeeded",
                    RunAction.skill_id.is_not(None),
                )
            )
        )
        snapshot = row.config_snapshot
        if snapshot.get("knowledge"):
            if self.knowledge is None or snapshot["knowledge"]["user_id"] != row.owner_user_id:
                raise ExecutionFailure("knowledge_access_revoked")
            self.knowledge.assert_current(db, snapshot, row.id)
        authorize_execution(db, snapshot, used | set(active))
        self.connections.assert_current(
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
        for binding in snapshot.get("tools", []):
            if binding["binding_id"] in used_tools and binding["kind"] != "knowledge":
                assert_binding(db, snapshot, binding)
        if invocation is not None:
            if invocation.binding_id.startswith("knowledge:"):
                if self.knowledge is None:
                    raise ExecutionFailure("tool_not_allowed")
                return self.knowledge.authorize(db, snapshot, invocation)
            return authorize_tool(db, snapshot, invocation)

"""Creator edit policy for shared employee definitions."""

from app.errors import PermissionDeniedError


def edit_agent(agent, user_id: str, *, admin: bool = False):
    if agent.created_by_user_id != user_id and not (admin and agent.created_by_user_id is None):
        raise PermissionDeniedError(
            "agent_edit_denied", "只有创建者可以修改此员工；历史员工由管理员维护。"
        )

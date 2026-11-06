"""Pure capability and resource-scope policies for an already resolved Actor."""

from app.auth.actor import Actor
from app.errors import NotFoundError, PermissionDeniedError

PUBLIC_PERMISSIONS = frozenset({"agents:read_public", "skills:read_public"})
ADMIN_PERMISSIONS = PUBLIC_PERMISSIONS | {
    "knowledge:use",
    "conversations:create",
    "conversations:read",
    "runs:create",
    "runs:read",
    "runs:cancel",
    "resources:all",
    "agents:read",
    "agents:create",
    "agents:update",
    "agents:delete",
    "agents:assign_skills",
    "agents:assign_model",
    "tools:read",
    "tools:update",
    "model_connections:read",
    "model_connections:create",
    "model_connections:update",
    "model_connections:delete",
    "model_connections:test",
    "organization_rules:read",
    "organization_rules:update",
    "skills:read",
    "skills:create",
    "skills:update",
    "skills:delete",
}
ROLE_PERMISSIONS = {
    "admin": ADMIN_PERMISSIONS,
    "member": PUBLIC_PERMISSIONS
    | {
        "knowledge:use",
        "conversations:create",
        "conversations:read",
        "runs:create",
        "runs:read",
        "runs:cancel",
        "tools:read",
        "tools:update",
    },
    "guest": PUBLIC_PERMISSIONS,
}


def permissions_for(actor: Actor) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(actor.role, frozenset())


def require_permission(actor: Actor, permission: str) -> None:
    if permission not in permissions_for(actor):
        raise PermissionDeniedError("permission_denied", "当前身份无权执行此操作。")


def require_resource_access(actor: Actor, owner_user_id: str) -> None:
    if "resources:all" not in permissions_for(actor) and actor.user_id != owner_user_id:
        raise NotFoundError("resource_not_found", "记录不存在。")

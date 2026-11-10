from app.auth.actor import Actor
from app.errors import NotFoundError, PermissionDeniedError

PUBLIC_PERMISSIONS = frozenset({"agents:read_public", "skills:read_public"})
GUEST_PERMISSIONS = PUBLIC_PERMISSIONS | {
    "resources:read_all",
    "agents:read",
    "skills:read",
    "tools:read",
    "model_connections:read",
    "organization_rules:read",
    "knowledge:read",
    "conversations:read",
    "runs:read",
}
ADMIN_PERMISSIONS = PUBLIC_PERMISSIONS | {
    "knowledge:manage",
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
    },
    "guest": GUEST_PERMISSIONS,
}


def permissions_for(actor: Actor) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(actor.role, frozenset())


def require_permission(actor: Actor, permission: str) -> None:
    if permission not in permissions_for(actor):
        raise PermissionDeniedError("permission_denied", "当前身份无权执行此操作。")


def require_resource_access(actor: Actor, owner_user_id: str) -> None:
    if not can_read_all_resources(actor) and actor.user_id != owner_user_id:
        raise NotFoundError("resource_not_found", "记录不存在。")


def can_read_all_resources(actor: Actor) -> bool:
    """仅判断跨所有者读取权，不授予写权限。"""
    return bool({"resources:all", "resources:read_all"} & permissions_for(actor))

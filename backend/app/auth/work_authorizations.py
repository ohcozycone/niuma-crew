from app.auth.actor import Actor
from app.auth.models import AuthSession, User
from app.auth.permissions import require_permission
from app.errors import AuthenticationError
from app.values import utc_now


def authorize_work(
    db, user_id: str, session_id: str | None, *, permission: str = "runs:create"
) -> Actor:
    """以发起会话和当前角色复核执行权，会话过期或撤销即失效。"""
    session = db.get(AuthSession, session_id) if session_id else None
    user = db.get(User, user_id)
    if (
        session is None
        or session.kind != "user"
        or session.user_id != user_id
        or session.revoked_at is not None
        or session.expires_at <= utc_now()
        or user is None
        or not user.is_active
    ):
        raise AuthenticationError("actor_session_invalid", "发起工作授权已失效。")
    actor = Actor("user", session.id, user.id, user.username, user.role, session.expires_at)
    require_permission(actor, permission)
    return actor

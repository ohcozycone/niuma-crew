"""Current work authority, separate from HTTP identity resolution and resource policy."""

from app.auth.actor import Actor
from app.auth.models import AuthSession, User
from app.auth.permissions import require_permission
from app.errors import AuthenticationError
from app.values import utc_now


def authorize_work(
    db, user_id: str, session_id: str | None, *, permission: str = "runs:create"
) -> Actor:
    """Recheck the existing expiring, revocable grant and its current user role.

    The current grant is the originating server session. This function owns that
    policy so execution and knowledge do not duplicate session-table interpretation.
    Offline delegation is a separate product policy, not inferred from a package move.
    """
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

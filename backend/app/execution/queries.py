"""Safe execution reads; no product history or SDK state is loaded here."""

from sqlalchemy.orm import Session

from app.auth.actor import Actor
from app.auth.permissions import require_resource_access
from app.errors import NotFoundError
from app.execution.models import Run


def require_run(db: Session, id: str, actor: Actor | None = None) -> Run:
    row = db.get(Run, id)
    if not row:
        raise NotFoundError("run_not_found", "执行记录不存在。")
    if actor:
        require_resource_access(actor, row.owner_user_id)
    return row

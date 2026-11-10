from sqlalchemy.orm import Session

from app.applications.conversations.projections import context_candidates


def accepted_run_id(db: Session, conversation_id: str) -> str | None:
    """只有已正式接纳的成功回复才能成为后续记忆依据。"""
    return next(
        (
            id
            for id, status, accepted, error in context_candidates(db, conversation_id)
            if status == "succeeded" and accepted is not None and error is None
        ),
        None,
    )

"""Allocate durable twelve-digit identifiers in the caller's write transaction."""

from sqlalchemy import CheckConstraint, Integer, update
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.errors import ServiceUnavailableError
from app.infrastructure.database.base import Base

MIN_ID = 100_000_000_000
MAX_ID = 999_999_999_999


class IdentifierSequence(Base):
    __tablename__ = "identifier_sequence"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint("next_value BETWEEN 100000000000 AND 1000000000000", name="range_valid"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    next_value: Mapped[int] = mapped_column(Integer, nullable=False)


def allocate_id(db: Session) -> str:
    """Reserve one key shared by conversations, messages and runs; never commit here."""
    value = db.scalar(
        update(IdentifierSequence)
        .where(IdentifierSequence.id == 1, IdentifierSequence.next_value <= MAX_ID)
        .values(next_value=IdentifierSequence.next_value + 1)
        .returning(IdentifierSequence.next_value - 1)
    )
    if value is None:
        raise ServiceUnavailableError("identifier_exhausted", "标识号段不可用。")
    return str(value)

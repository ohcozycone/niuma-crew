"""Application-owned shell configuration summary."""

from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import func, select

from app.employees.models import Agent
from app.skills.models import Skill


class ConfigurationSummary(BaseModel):
    agents: int
    skills: int
    favorites: int


def configuration_summary(database):
    with database.transaction() as db:
        values = db.execute(
            select(
                select(func.count()).select_from(Agent).scalar_subquery(),
                select(func.count()).select_from(Skill).scalar_subquery(),
                select(func.count())
                .select_from(Agent)
                .where(Agent.is_favorite.is_(True))
                .scalar_subquery(),
            )
        ).one()
        return ConfigurationSummary(agents=values[0], skills=values[1], favorites=values[2])

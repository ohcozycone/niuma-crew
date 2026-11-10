from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.dependencies import DatabaseDependency, require_capability
from app.employees.models import Agent
from app.skills.models import Skill

router = APIRouter(tags=["configuration"])


class ConfigurationSummary(BaseModel):
    agents: int
    skills: int
    favorites: int


@router.get(
    "/api/configuration-summary",
    response_model=ConfigurationSummary,
    dependencies=[
        Depends(require_capability("agents:read")),
        Depends(require_capability("skills:read")),
    ],
)
@router.get(
    "/api/public/configuration-summary",
    response_model=ConfigurationSummary,
    dependencies=[
        Depends(require_capability("agents:read_public")),
        Depends(require_capability("skills:read_public")),
    ],
)
def summary(database: DatabaseDependency) -> ConfigurationSummary:
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

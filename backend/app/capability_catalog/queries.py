"""Read a single ordered page across Skill and MCP definitions."""

from sqlalchemy import case, func, literal, select, union_all
from sqlalchemy.sql.elements import ColumnElement

from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.capability_catalog.schemas import CapabilityRead
from app.errors import InvalidInputError
from app.infrastructure.database.session import Database
from app.mcp.models import McpService
from app.schemas import Page
from app.skills.definitions import protocol_names
from app.skills.models import Skill


def list_capabilities(
    database: Database,
    actor: Actor,
    *,
    q: str = "",
    kind: str = "all",
    offset: int = 0,
    limit: int = 20,
) -> Page[CapabilityRead]:
    """Apply visibility before counting and paging the combined catalog."""
    require_permission(actor, "skills:read_public")
    if offset < 0 or not 1 <= limit <= 100 or kind not in {"all", "skill", "mcp_http", "mcp_stdio"}:
        raise InvalidInputError("capability_query_invalid", "能力列表筛选或分页无效。")
    skill = select(
        Skill.id,
        Skill.name,
        Skill.description,
        literal("skill").label("kind"),
        Skill.is_active.label("enabled"),
        Skill.created_at,
    )
    mcp = select(
        McpService.id,
        McpService.name,
        McpService.description,
        case((McpService.transport == "stdio", "mcp_stdio"), else_="mcp_http").label("kind"),
        McpService.enabled,
        McpService.created_at,
    )
    query = union_all(skill, mcp).subquery()
    conditions: list[ColumnElement[bool]] = [
        query.c.name.icontains(q.strip(), autoescape=True)
        | query.c.description.icontains(q.strip(), autoescape=True)
    ]
    if kind != "all":
        conditions.append(query.c.kind == kind)
    if actor.role == "guest":
        conditions.append(query.c.kind == "skill")
    with database.transaction() as db:
        total = db.scalar(select(func.count()).select_from(query).where(*conditions)) or 0
        rows = list(
            db.execute(
                select(query)
                .where(*conditions)
                .order_by(query.c.created_at.desc(), query.c.id)
                .offset(offset)
                .limit(limit)
            ).mappings()
        )
        sources = protocol_names(db, [item["id"] for item in rows if item["kind"] == "skill"])
        return Page[CapabilityRead](
            items=[
                CapabilityRead.model_validate(dict(row, protocol_name=sources.get(row["id"])))
                for row in rows
            ],
            total=total,
            offset=offset,
            limit=limit,
        )

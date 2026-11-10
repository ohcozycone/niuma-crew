from sqlalchemy import update
from sqlalchemy.orm import Session

from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.common.errors import ConflictError
from app.common.values import utc_now
from app.infrastructure.database.session import Database
from app.resources.organization_rules.models import OrganizationRules
from app.resources.organization_rules.schemas import OrganizationRulesRead, OrganizationRulesUpdate


def current_rules(session: Session) -> OrganizationRulesRead:
    row = session.get(OrganizationRules, 1)
    if row is None:
        raise RuntimeError("缺少规章制度记录，请检查数据库迁移。")
    return OrganizationRulesRead.model_validate(row)


class OrganizationRulesService:
    def __init__(self, database: Database):
        self.database = database

    def get(self, actor: Actor) -> OrganizationRulesRead:
        require_permission(actor, "organization_rules:read")
        with self.database.transaction() as session:
            return OrganizationRulesRead.model_validate(current_rules(session))

    def update(self, data: OrganizationRulesUpdate, actor: Actor) -> OrganizationRulesRead:
        require_permission(actor, "organization_rules:update")
        with self.database.transaction() as session:
            # 先条件写再读，避免并发写入基于过期快照更新。
            result = session.execute(
                update(OrganizationRules)
                .where(OrganizationRules.id == 1, OrganizationRules.revision == data.revision)
                .where(OrganizationRules.instructions != data.instructions)
                .values(
                    instructions=data.instructions,
                    revision=OrganizationRules.revision + 1,
                    updated_at=utc_now(),
                )
            )
            row = current_rules(session)
            if not result.rowcount and row.revision != data.revision:
                raise ConflictError(
                    "rules_revision_conflict",
                    "规章制度已被其他管理员修改，请核对最新版本后再保存。",
                )
            return OrganizationRulesRead.model_validate(row)

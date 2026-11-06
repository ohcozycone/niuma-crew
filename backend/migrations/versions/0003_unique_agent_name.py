"""Keep employee names unique without changing existing identities or references."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not op.get_context().as_sql:
        duplicate = (
            op.get_bind()
            .execute(sa.text("SELECT 1 FROM agents GROUP BY name HAVING count(*) > 1 LIMIT 1"))
            .first()
        )
        if duplicate is not None:
            raise RuntimeError("现有员工名称重复，请先在员工配置中改名，再重试升级。")
    op.create_index("ix_agents_name", "agents", ["name"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_agents_name", table_name="agents")

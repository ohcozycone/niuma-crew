"""退役可装配的原生工作区，保留历史引用。"""

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = depends_on = None


def upgrade():
    # 使旧页面草稿失效，避免迁移后重新提交已退役的装配。
    op.execute("""
        UPDATE agents SET revision = revision + 1
        WHERE id IN (
            SELECT agent_id FROM agent_tool_grants
            WHERE tool_connection_id IN (SELECT id FROM tool_connections WHERE kind = 'native')
        )
    """)
    op.execute("""
        UPDATE agent_tool_grants SET enabled = 0, revision = revision + 1
        WHERE tool_connection_id IN (SELECT id FROM tool_connections WHERE kind = 'native')
    """)
    op.execute("""
        UPDATE tool_connections SET enabled = 0, config_revision = config_revision + 1
        WHERE kind = 'native'
    """)


def downgrade():
    raise RuntimeError("工作区装配已退役，不支持有损降级，请恢复升级前备份。")

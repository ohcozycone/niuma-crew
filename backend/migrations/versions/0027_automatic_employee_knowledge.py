"""员工统一按知识库能力自动检索，退役装配算法配置。"""

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = depends_on = None


def upgrade():
    # 强制策略改为自动会改变行为；使旧草稿和在途任务通过修订检查失效。
    op.execute("""
        UPDATE knowledge_employee_settings
        SET revision = revision + 1,
            updated_at = strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'
        WHERE strategy != 'auto'
    """)
    # SQLite原生删列保留选库外键，不重建被引用的设置表。
    op.drop_column("knowledge_employee_settings", "strategy")


def downgrade():
    raise RuntimeError("员工检索方式已统一自动，不能还原旧强制策略，请恢复升级前备份。")

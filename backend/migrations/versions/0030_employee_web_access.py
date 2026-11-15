"""员工使用一个默认关闭的许可控制内置网页搜索和读取。"""

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = depends_on = None


def upgrade():
    # SQLite 原生增列保留员工的外键引用，旧员工不会自动取得外网访问许可。
    op.execute("""
        ALTER TABLE agents ADD COLUMN allow_web_access BOOLEAN NOT NULL DEFAULT 0
        CONSTRAINT ck_agents_allow_web_access_boolean CHECK (allow_web_access IN (0, 1))
    """)


def downgrade():
    op.drop_column("agents", "allow_web_access")

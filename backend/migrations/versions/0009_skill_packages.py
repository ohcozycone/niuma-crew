"""Canonical Skill source and immutable asset manifests, preserving existing IDs."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = depends_on = None


def baseline(packaged=False):
    # Frozen 0008 definition; offline SQL generation cannot reflect SQLite.
    table = sa.Table(
        "skills",
        sa.MetaData(),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("configuration_schema", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False, server_default="其他"),
        *[
            sa.Column(key, sa.Text(), nullable=False, server_default="")
            for key in (
                "description",
                "instructions",
                "input_description",
                "output_description",
                "example",
            )
        ],
        sa.Column("id", sa.Text(), primary_key=True),
        *[
            sa.Column(
                key,
                sa.Text(),
                nullable=False,
                server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z')"),
            )
            for key in ("created_at", "updated_at")
        ],
        sa.CheckConstraint(
            "json_valid(configuration_schema) AND json_type(configuration_schema) = 'object'",
            name="ck_skills_configuration_schema_object",
        ),
        sa.CheckConstraint("is_active IN (0, 1)", name="ck_skills_is_active_boolean"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_skills_name_not_blank"),
        sa.CheckConstraint("revision > 0", name="ck_skills_revision_positive"),
    )
    if packaged:
        table.append_column(sa.Column("skill_md", sa.Text(), nullable=False, server_default=""))
        table.append_column(
            sa.Column("package_manifest", sa.JSON(), nullable=False, server_default="[]")
        )
        table.append_constraint(
            sa.CheckConstraint(
                "json_valid(package_manifest) AND json_type(package_manifest) = 'array'",
                name="ck_skills_package_manifest_array",
            )
        )
    return table


def upgrade():
    with op.batch_alter_table("skills", copy_from=baseline()) as batch:
        batch.add_column(sa.Column("skill_md", sa.Text(), nullable=False, server_default=""))
        batch.add_column(
            sa.Column("package_manifest", sa.JSON(), nullable=False, server_default="[]")
        )
        batch.create_check_constraint(
            "package_manifest_array",
            "json_valid(package_manifest) AND json_type(package_manifest) = 'array'",
        )


def downgrade():
    with op.batch_alter_table("skills", copy_from=baseline(True)) as batch:
        batch.drop_constraint("package_manifest_array", type_="check")
        batch.drop_column("package_manifest")
        batch.drop_column("skill_md")

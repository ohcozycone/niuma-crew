"""Create the Agent platform schema and constraints from a clean database."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_connections",
        sa.Column("enabled", sa.BOOLEAN(), server_default=sa.text("'1'"), nullable=False),
        sa.Column("capability", sa.TEXT(), server_default=sa.text("'chat'"), nullable=False),
        sa.Column("config_revision", sa.INTEGER(), server_default=sa.text("'1'"), nullable=False),
        sa.Column(
            "credential_revision", sa.INTEGER(), server_default=sa.text("'1'"), nullable=False
        ),
        sa.Column("name", sa.TEXT(), nullable=False),
        sa.Column("preset_id", sa.TEXT(), nullable=False),
        sa.Column("model_id", sa.TEXT(), nullable=False),
        sa.Column("encrypted_api_key", sa.TEXT(), nullable=False),
        sa.Column("id", sa.TEXT(), nullable=False),
        sa.Column(
            "created_at",
            sa.TEXT(),
            server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TEXT(),
            server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "capability IN ('chat', 'embedding')", name="ck_model_connections_capability_valid"
        ),
        sa.CheckConstraint(
            "config_revision > 0", name="ck_model_connections_config_revision_positive"
        ),
        sa.CheckConstraint(
            "credential_revision > 0", name="ck_model_connections_credential_revision_positive"
        ),
        sa.CheckConstraint("enabled IN (0, 1)", name="ck_model_connections_enabled_boolean"),
        sa.CheckConstraint(
            "length(encrypted_api_key) > 0", name="ck_model_connections_credential_not_blank"
        ),
        sa.CheckConstraint(
            "length(trim(model_id)) > 0", name="ck_model_connections_model_id_not_blank"
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_model_connections_name_not_blank"),
        sa.PrimaryKeyConstraint("id", name="pk_model_connections"),
        sa.UniqueConstraint("name", name="uq_model_connections_name"),
    )
    op.create_table(
        "organization_rules",
        sa.Column("id", sa.INTEGER(), nullable=False),
        sa.Column("instructions", sa.TEXT(), server_default=sa.text("''"), nullable=False),
        sa.Column("revision", sa.INTEGER(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "updated_at",
            sa.TEXT(),
            server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_organization_rules_singleton"),
        sa.CheckConstraint(
            "length(instructions) <= 20000", name="ck_organization_rules_instructions_length"
        ),
        sa.CheckConstraint("revision >= 0", name="ck_organization_rules_revision_valid"),
        sa.PrimaryKeyConstraint("id", name="pk_organization_rules"),
    )
    op.create_table(
        "skills",
        sa.Column("revision", sa.INTEGER(), server_default=sa.text("'1'"), nullable=False),
        sa.Column("is_active", sa.BOOLEAN(), server_default=sa.text("'1'"), nullable=False),
        sa.Column(
            "configuration_schema", sa.JSON(), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("name", sa.TEXT(), nullable=False),
        sa.Column("category", sa.TEXT(), server_default=sa.text("'其他'"), nullable=False),
        sa.Column("description", sa.TEXT(), server_default=sa.text("''"), nullable=False),
        sa.Column("instructions", sa.TEXT(), server_default=sa.text("''"), nullable=False),
        sa.Column("input_description", sa.TEXT(), server_default=sa.text("''"), nullable=False),
        sa.Column("output_description", sa.TEXT(), server_default=sa.text("''"), nullable=False),
        sa.Column("example", sa.TEXT(), server_default=sa.text("''"), nullable=False),
        sa.Column("id", sa.TEXT(), nullable=False),
        sa.Column(
            "created_at",
            sa.TEXT(),
            server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TEXT(),
            server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "json_valid(configuration_schema) AND json_type(configuration_schema) = 'object'",
            name="ck_skills_configuration_schema_object",
        ),
        sa.CheckConstraint("is_active IN (0, 1)", name="ck_skills_is_active_boolean"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_skills_name_not_blank"),
        sa.CheckConstraint("revision > 0", name="ck_skills_revision_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_skills"),
    )
    op.create_table(
        "users",
        sa.Column("username", sa.TEXT(), nullable=False),
        sa.Column("password_hash", sa.TEXT(), nullable=True),
        sa.Column("role", sa.TEXT(), nullable=False),
        sa.Column("is_active", sa.BOOLEAN(), server_default=sa.text("1"), nullable=False),
        sa.Column("id", sa.TEXT(), nullable=False),
        sa.Column(
            "created_at",
            sa.TEXT(),
            server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TEXT(),
            server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(role = 'admin' AND password_hash IS NOT NULL) OR (role = 'member' AND password_hash IS NULL)",
            name="ck_users_credential_valid",
        ),
        sa.CheckConstraint("role IN ('admin', 'member')", name="ck_users_role_valid"),
        sa.CheckConstraint("is_active IN (0, 1)", name="ck_users_is_active_boolean"),
        sa.CheckConstraint("length(trim(username)) > 0", name="ck_users_username_not_blank"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index(
        "uq_users_admin_username",
        "users",
        ["username"],
        unique=1,
        sqlite_where=sa.text("role = 'admin'"),
    )
    op.create_table(
        "agents",
        sa.Column("revision", sa.INTEGER(), server_default=sa.text("'1'"), nullable=False),
        sa.Column("code", sa.TEXT(), nullable=True),
        sa.Column("name", sa.TEXT(), nullable=False),
        sa.Column("category", sa.TEXT(), server_default=sa.text("'其他'"), nullable=False),
        sa.Column("description", sa.TEXT(), server_default=sa.text("''"), nullable=False),
        sa.Column("role_label", sa.TEXT(), nullable=True),
        sa.Column("avatar_id", sa.TEXT(), nullable=False),
        sa.Column("system_prompt", sa.TEXT(), server_default=sa.text("''"), nullable=False),
        sa.Column("ci_repository", sa.TEXT(), nullable=True),
        sa.Column("model_connection_id", sa.TEXT(), nullable=True),
        sa.Column("is_active", sa.BOOLEAN(), server_default=sa.text("1"), nullable=False),
        sa.Column("is_favorite", sa.BOOLEAN(), server_default=sa.text("0"), nullable=False),
        sa.Column("example_tasks", sa.TEXT(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("deliverables", sa.TEXT(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("id", sa.TEXT(), nullable=False),
        sa.Column(
            "created_at",
            sa.TEXT(),
            server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TEXT(),
            server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "CASE WHEN json_valid(deliverables) THEN json_type(deliverables) = 'array' ELSE 0 END",
            name="ck_agents_deliverables_array",
        ),
        sa.CheckConstraint(
            "CASE WHEN json_valid(example_tasks) THEN json_type(example_tasks) = 'array' ELSE 0 END",
            name="ck_agents_example_tasks_array",
        ),
        sa.CheckConstraint(
            "code IS NULL OR length(trim(code)) > 0", name="ck_agents_code_not_blank"
        ),
        sa.CheckConstraint("is_active IN (0, 1)", name="ck_agents_is_active_boolean"),
        sa.CheckConstraint("is_favorite IN (0, 1)", name="ck_agents_is_favorite_boolean"),
        sa.CheckConstraint("length(trim(avatar_id)) > 0", name="ck_agents_avatar_id_not_blank"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_agents_name_not_blank"),
        sa.CheckConstraint("revision > 0", name="ck_agents_revision_positive"),
        sa.ForeignKeyConstraint(
            ["model_connection_id"],
            ["model_connections.id"],
            name="fk_agents_model_connection_id_model_connections",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agents"),
        sa.UniqueConstraint("code", name="uq_agents_code"),
    )
    op.create_index(
        "ix_agents_model_connection_id", "agents", ["model_connection_id"], unique=False
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.TEXT(), nullable=False),
        sa.Column("token_hash", sa.TEXT(), nullable=False),
        sa.Column("kind", sa.TEXT(), nullable=False),
        sa.Column("user_id", sa.TEXT(), nullable=True),
        sa.Column(
            "created_at",
            sa.TEXT(),
            server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.TEXT(),
            server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.TEXT(), nullable=False),
        sa.Column("revoked_at", sa.TEXT(), nullable=True),
        sa.CheckConstraint(
            "(kind = 'user' AND user_id IS NOT NULL) OR (kind = 'guest' AND user_id IS NULL)",
            name="ck_auth_sessions_identity_valid",
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_auth_sessions_expiry_valid"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_auth_sessions_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_auth_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
    )
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"], unique=False)
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"], unique=False)
    op.create_table(
        "external_identities",
        sa.Column("user_id", sa.TEXT(), nullable=False),
        sa.Column("provider", sa.TEXT(), nullable=False),
        sa.Column("provider_user_id", sa.TEXT(), nullable=False),
        sa.Column("id", sa.TEXT(), nullable=False),
        sa.Column(
            "created_at",
            sa.TEXT(),
            server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TEXT(),
            server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'"),
            nullable=False,
        ),
        sa.CheckConstraint("provider = 'github'", name="ck_external_identities_provider_valid"),
        sa.CheckConstraint(
            "length(trim(provider_user_id)) > 0", name="ck_external_identities_subject_not_blank"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_external_identities_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_external_identities"),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_external_identities_provider"),
        sa.UniqueConstraint("user_id", "provider", name="uq_external_identities_user_id"),
    )
    op.create_index(
        "ix_external_identities_user_id", "external_identities", ["user_id"], unique=False
    )
    op.create_table(
        "agent_skills",
        sa.Column("agent_id", sa.TEXT(), nullable=False),
        sa.Column("skill_id", sa.TEXT(), nullable=False),
        sa.Column(
            "created_at",
            sa.TEXT(),
            server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TEXT(),
            server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'"),
            nullable=False,
        ),
        sa.Column("enabled", sa.BOOLEAN(), server_default=sa.text("'1'"), nullable=False),
        sa.Column("parameters", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("revision", sa.INTEGER(), server_default=sa.text("'1'"), nullable=False),
        sa.CheckConstraint(
            "json_valid(parameters) AND json_type(parameters) = 'object'",
            name="ck_agent_skills_parameters_object",
        ),
        sa.CheckConstraint("enabled IN (0, 1)", name="ck_agent_skills_enabled_boolean"),
        sa.CheckConstraint("revision > 0", name="ck_agent_skills_revision_positive"),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["agents.id"], name="fk_agent_skills_agent_id_agents", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name="fk_agent_skills_skill_id_skills", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("agent_id", "skill_id", name="pk_agent_skills"),
    )
    op.create_index("ix_agent_skills_skill_id", "agent_skills", ["skill_id"], unique=False)
    op.create_table(
        "conversations",
        sa.Column("agent_id", sa.TEXT(), nullable=False),
        sa.Column("owner_user_id", sa.TEXT(), nullable=False),
        sa.Column("title", sa.TEXT(), nullable=False),
        sa.Column(
            "last_message_sequence", sa.INTEGER(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("checkpoint_id", sa.TEXT(), nullable=True),
        sa.Column("id", sa.TEXT(), nullable=False),
        sa.Column(
            "created_at",
            sa.TEXT(),
            server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TEXT(),
            server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'"),
            nullable=False,
        ),
        sa.CheckConstraint("last_message_sequence >= 0", name="ck_conversations_sequence_valid"),
        sa.CheckConstraint("length(title) BETWEEN 1 AND 100", name="ck_conversations_title_length"),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["agents.id"], name="fk_conversations_agent_id_agents"
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], name="fk_conversations_owner_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
    )
    op.create_index(
        "ix_conversations_agent_updated",
        "conversations",
        ["agent_id", "updated_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_conversations_owner_user_id", "conversations", ["owner_user_id"], unique=False
    )
    op.create_index("ix_conversations_updated", "conversations", ["updated_at", "id"], unique=False)
    op.create_table(
        "runs",
        sa.Column("conversation_id", sa.TEXT(), nullable=False),
        sa.Column("input_message_id", sa.TEXT(), nullable=False),
        sa.Column("output_message_id", sa.TEXT(), nullable=False),
        sa.Column("input_sequence", sa.INTEGER(), nullable=False),
        sa.Column("output_sequence", sa.INTEGER(), nullable=False),
        sa.Column("input_text", sa.TEXT(), nullable=False),
        sa.Column("input_created_at", sa.TEXT(), nullable=False),
        sa.Column("base_checkpoint_id", sa.TEXT(), nullable=True),
        sa.Column("checkpoint_id", sa.TEXT(), nullable=True),
        sa.Column("output_checkpoint_id", sa.TEXT(), nullable=True),
        sa.Column("model_calls", sa.INTEGER(), server_default=sa.text("'0'"), nullable=False),
        sa.Column("skill_reads", sa.INTEGER(), server_default=sa.text("'0'"), nullable=False),
        sa.Column("initiated_by_user_id", sa.TEXT(), nullable=False),
        sa.Column("initiated_by_session_id", sa.TEXT(), nullable=True),
        sa.Column("client_request_id", sa.TEXT(), nullable=False),
        sa.Column("request_hash", sa.TEXT(), nullable=False),
        sa.Column("retry_of_run_id", sa.TEXT(), nullable=True),
        sa.Column("model_connection_id", sa.TEXT(), nullable=True),
        sa.Column("status", sa.TEXT(), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("revision", sa.INTEGER(), server_default=sa.text("1"), nullable=False),
        sa.Column("steps_revision", sa.INTEGER(), server_default=sa.text("1"), nullable=False),
        sa.Column("config_snapshot", sa.JSON(), nullable=False),
        sa.Column("context_message_ids", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.TEXT(), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=True),
        sa.Column("ci_result", sa.JSON(), nullable=True),
        sa.Column("ci_feedback", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.TEXT(), nullable=True),
        sa.Column("cancel_requested_at", sa.TEXT(), nullable=True),
        sa.Column("finished_at", sa.TEXT(), nullable=True),
        sa.Column("id", sa.TEXT(), nullable=False),
        sa.Column(
            "created_at",
            sa.TEXT(),
            server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TEXT(),
            server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status IN ('queued','running','cancelling') AND finished_at IS NULL) OR (status IN ('succeeded','failed','cancelled','interrupted') AND finished_at IS NOT NULL)",
            name="ck_runs_finish_valid",
        ),
        sa.CheckConstraint(
            "ci_feedback IS NULL OR (json_valid(ci_feedback) AND json_type(ci_feedback) = 'object')",
            name="ck_runs_ci_feedback_object",
        ),
        sa.CheckConstraint(
            "ci_result IS NULL OR (json_valid(ci_result) AND json_type(ci_result) = 'object')",
            name="ck_runs_ci_result_object",
        ),
        sa.CheckConstraint(
            "json_valid(config_snapshot) AND json_type(config_snapshot) = 'object'",
            name="ck_runs_snapshot_valid",
        ),
        sa.CheckConstraint(
            "json_valid(context_message_ids) AND json_type(context_message_ids) = 'array'",
            name="ck_runs_context_valid",
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','cancelling','succeeded','failed','cancelled','interrupted')",
            name="ck_runs_status_valid",
        ),
        sa.CheckConstraint(
            "input_message_id != output_message_id", name="ck_runs_messages_distinct"
        ),
        sa.CheckConstraint(
            "input_sequence > 0 AND output_sequence > input_sequence",
            name="ck_runs_sequences_valid",
        ),
        sa.CheckConstraint("model_calls >= 0 AND skill_reads >= 0", name="ck_runs_budgets_valid"),
        sa.CheckConstraint("revision > 0", name="ck_runs_revision_valid"),
        sa.CheckConstraint("steps_revision > 0", name="ck_runs_steps_revision_valid"),
        sa.CheckConstraint("usage IS NULL OR json_valid(usage)", name="ck_runs_usage_valid"),
        sa.ForeignKeyConstraint(
            ["conversation_id", "retry_of_run_id"],
            ["runs.conversation_id", "runs.id"],
            name="fk_runs_conversation_id_runs",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], name="fk_runs_conversation_id_conversations"
        ),
        sa.ForeignKeyConstraint(
            ["initiated_by_session_id"],
            ["auth_sessions.id"],
            name="fk_runs_initiated_by_session_id_auth_sessions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["initiated_by_user_id"], ["users.id"], name="fk_runs_initiated_by_user_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["model_connection_id"],
            ["model_connections.id"],
            name="fk_runs_model_connection_id_model_connections",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_runs"),
        sa.UniqueConstraint("conversation_id", "id", name="uq_runs_conversation_id"),
        sa.UniqueConstraint(
            "initiated_by_user_id", "client_request_id", name="uq_runs_initiated_by_user_id"
        ),
        sa.UniqueConstraint("output_message_id", name="uq_runs_output_message_id"),
    )
    op.create_index(
        "ix_runs_conversation_created",
        "runs",
        ["conversation_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_runs_initiated_by_session_id", "runs", ["initiated_by_session_id"], unique=False
    )
    op.create_index("ix_runs_model_connection_id", "runs", ["model_connection_id"], unique=False)
    op.create_index("ix_runs_status_created", "runs", ["status", "created_at", "id"], unique=False)
    op.create_index(
        "uq_runs_active_conversation",
        "runs",
        ["conversation_id"],
        unique=1,
        sqlite_where=sa.text("status IN ('queued','running','cancelling')"),
    )
    op.create_table(
        "run_steps",
        sa.Column("run_id", sa.TEXT(), nullable=False),
        sa.Column("sequence", sa.INTEGER(), nullable=False),
        sa.Column("step_key", sa.TEXT(), nullable=False),
        sa.Column("kind", sa.TEXT(), nullable=False),
        sa.Column("status", sa.TEXT(), server_default=sa.text("'running'"), nullable=False),
        sa.Column("skill_id", sa.TEXT(), nullable=True),
        sa.Column("safe_details", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("output_text", sa.TEXT(), server_default=sa.text("''"), nullable=False),
        sa.Column("reasoning_text", sa.TEXT(), server_default=sa.text("''"), nullable=False),
        sa.Column("reasoning_truncated", sa.BOOLEAN(), server_default=sa.text("0"), nullable=False),
        sa.Column("result_ref", sa.TEXT(), nullable=True),
        sa.Column("error_code", sa.TEXT(), nullable=True),
        sa.Column("started_at", sa.TEXT(), nullable=False),
        sa.Column("finished_at", sa.TEXT(), nullable=True),
        sa.Column("id", sa.TEXT(), nullable=False),
        sa.Column(
            "created_at",
            sa.TEXT(),
            server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TEXT(),
            server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'running' AND finished_at IS NULL) OR (status != 'running' AND finished_at IS NOT NULL)",
            name="ck_run_steps_finish_valid",
        ),
        sa.CheckConstraint(
            "json_valid(safe_details) AND json_type(safe_details) = 'object'",
            name="ck_run_steps_safe_details_object",
        ),
        sa.CheckConstraint(
            "kind IN ('skill_activation','model_call','tool_call','knowledge','validation')",
            name="ck_run_steps_kind_valid",
        ),
        sa.CheckConstraint(
            "status IN ('running','succeeded','failed','cancelled','interrupted')",
            name="ck_run_steps_status_valid",
        ),
        sa.CheckConstraint("length(trim(step_key)) > 0", name="ck_run_steps_step_key_not_blank"),
        sa.CheckConstraint(
            "reasoning_truncated IN (0, 1)", name="ck_run_steps_reasoning_truncated_boolean"
        ),
        sa.CheckConstraint("sequence > 0", name="ck_run_steps_sequence_positive"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name="fk_run_steps_run_id_runs", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name="fk_run_steps_skill_id_skills", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_run_steps"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_run_steps_sequence"),
        sa.UniqueConstraint("run_id", "step_key", name="uq_run_steps_key"),
    )

    op.bulk_insert(
        sa.table("organization_rules", sa.column("id", sa.Integer())),
        [{"id": 1}],
    )


def downgrade() -> None:
    op.drop_table("run_steps")
    op.drop_index(
        "uq_runs_active_conversation",
        table_name="runs",
        sqlite_where=sa.text("status IN ('queued','running','cancelling')"),
    )
    op.drop_index("ix_runs_status_created", table_name="runs")
    op.drop_index("ix_runs_model_connection_id", table_name="runs")
    op.drop_index("ix_runs_initiated_by_session_id", table_name="runs")
    op.drop_index("ix_runs_conversation_created", table_name="runs")
    op.drop_table("runs")
    op.drop_index("ix_conversations_updated", table_name="conversations")
    op.drop_index("ix_conversations_owner_user_id", table_name="conversations")
    op.drop_index("ix_conversations_agent_updated", table_name="conversations")
    op.drop_table("conversations")
    op.drop_index("ix_agent_skills_skill_id", table_name="agent_skills")
    op.drop_table("agent_skills")
    op.drop_index("ix_external_identities_user_id", table_name="external_identities")
    op.drop_table("external_identities")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_agents_model_connection_id", table_name="agents")
    op.drop_table("agents")
    op.drop_index(
        "uq_users_admin_username", table_name="users", sqlite_where=sa.text("role = 'admin'")
    )
    op.drop_table("users")
    op.drop_table("skills")
    op.drop_table("organization_rules")
    op.drop_table("model_connections")

"""将员工固定资源迁为组织资产；保留历史快照与资源字节。"""

import json
from pathlib import Path

import sqlalchemy as sa
from alembic import context, op

revision = "0028"
down_revision = "0027"
branch_labels = depends_on = None


def _manifest(db):
    connections = {
        row["id"]: row
        for row in db.execute(
            sa.text(
                "SELECT id, service_id, approved_catalog FROM tool_connections WHERE kind != 'native'"
            )
        ).mappings()
    }
    libraries = {row[0] for row in db.execute(sa.text("SELECT id FROM knowledge_bases"))}
    grants = list(
        db.execute(
            sa.text(
                "SELECT g.id,g.agent_id,g.tool_connection_id,g.tools FROM agent_tool_grants g JOIN tool_connections c ON c.id=g.tool_connection_id WHERE c.kind!='native'"
            )
        ).mappings()
    )
    settings = list(
        db.execute(
            sa.text("SELECT id,agent_id,mode,top_k FROM knowledge_employee_settings")
        ).mappings()
    )
    if db.scalar(
        sa.text("SELECT count(*) FROM runs WHERE status IN ('queued','running','cancelling')")
    ):
        raise RuntimeError("组织资源切换前必须排空活动任务。")
    if not (connections or libraries or grants or settings):
        return {}, [], []
    path = context.get_x_argument(as_dictionary=True).get("org_assets")
    if not path:
        raise RuntimeError(
            "存在旧资源；先审核接纳清单，再使用 alembic -x org_assets=<清单路径> upgrade head。"
        )
    data = json.loads(Path(path).read_text())
    if data.get("schema_version") != 1:
        raise RuntimeError("组织资源接纳清单格式无效。")
    for key, expected in (("connections", set(connections)), ("knowledge_bases", libraries)):
        values = data.get(key)
        if (
            not isinstance(values, list)
            or len(set(values)) != len(values)
            or set(values) != expected
        ):
            raise RuntimeError(
                "接纳清单必须逐项覆盖全部活动资源；未接纳资源须先显式导出或受保护归档：" + key
            )
    tools = data.get("employee_tools", {})
    chosen = data.get("employee_knowledge", {})
    if (
        not isinstance(tools, dict)
        or set(tools) != {g["id"] for g in grants}
        or not isinstance(chosen, dict)
        or set(chosen) != {s["agent_id"] for s in settings}
    ):
        raise RuntimeError("接纳清单未明确每名员工最终使用的连接和知识配置。")
    for grant in grants:
        target = connections.get(tools[grant["id"]])
        original = connections[grant["tool_connection_id"]]
        if target is None or target["service_id"] != original["service_id"]:
            raise RuntimeError("员工固定连接必须来自原许可对应的同一服务。")
        catalog = {
            item["name"]: item["descriptor_hash"] for item in json.loads(target["approved_catalog"])
        }
        if any(
            catalog.get(item["name"]) != item["descriptor_hash"]
            for item in json.loads(grant["tools"])
        ):
            raise RuntimeError("员工固定连接的已确认工具定义与许可不一致。")
    by_id = {s["id"]: s for s in settings}
    selected = []
    for agent, identifier in chosen.items():
        setting = by_id.get(identifier)
        if setting is None or setting["agent_id"] != agent:
            raise RuntimeError("员工知识配置选择无效；冲突配置不能自动合并。")
        selected.append(setting)
    return tools, grants, selected


def upgrade():
    if context.is_offline_mode():
        # 离线SQL仅用于空库初始化；有旧资源的部署必须在线审核显式清单。
        op.execute("CREATE TEMP TABLE org_assets_require_explicit_manifest (n INTEGER CHECK(n=0))")
        op.execute(
            "INSERT INTO org_assets_require_explicit_manifest SELECT (SELECT count(*) FROM tool_connections WHERE kind!='native')+(SELECT count(*) FROM knowledge_bases)+(SELECT count(*) FROM knowledge_employee_settings)+(SELECT count(*) FROM runs WHERE status IN ('queued','running','cancelling'))"
        )
        op.execute("DROP TABLE org_assets_require_explicit_manifest")
        tools, grants, settings = {}, [], []
    else:
        tools, grants, settings = _manifest(op.get_bind())
    op.execute(
        "ALTER TABLE agents ADD COLUMN knowledge_mode TEXT DEFAULT 'on_demand' NOT NULL CONSTRAINT ck_agents_knowledge_mode_valid CHECK(knowledge_mode IN ('on_demand','always'))"
    )
    op.execute(
        "ALTER TABLE agents ADD COLUMN knowledge_top_k INTEGER DEFAULT '6' NOT NULL CONSTRAINT ck_agents_knowledge_top_k_valid CHECK(knowledge_top_k BETWEEN 1 AND 12)"
    )
    op.create_table(
        "agent_knowledge_libraries",
        sa.Column(
            "agent_id", sa.Text(), sa.ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "knowledge_base_id",
            sa.Text(),
            sa.ForeignKey("knowledge_bases.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )
    db = op.get_bind()
    for setting in settings:
        db.execute(
            sa.text(
                "UPDATE agents SET knowledge_mode=:mode,knowledge_top_k=:top_k,revision=revision+1 WHERE id=:agent_id"
            ),
            dict(setting),
        )
        db.execute(
            sa.text(
                "INSERT INTO agent_knowledge_libraries SELECT :agent_id,knowledge_base_id FROM knowledge_employee_libraries WHERE settings_id=:id"
            ),
            dict(setting),
        )
    for grant in grants:
        db.execute(
            sa.text(
                "UPDATE agent_tool_grants SET tool_connection_id=:connection,revision=revision+1 WHERE id=:id"
            ),
            {"connection": tools[grant["id"]], "id": grant["id"]},
        )
    if grants:
        op.execute(
            "UPDATE agents SET revision=revision+1 WHERE id IN (SELECT agent_id FROM agent_tool_grants)"
        )
    op.drop_table("personal_tool_bindings")
    op.drop_table("knowledge_employee_libraries")
    op.drop_table("knowledge_employee_settings")
    op.drop_column("agent_tool_grants", "account_mode")
    # 以下DDL冻结自0027，不依赖实时ORM；重建时不改变ID、凭据、目录或派生索引。
    op.execute(
        "CREATE TABLE _org_tool_connections (\n\tname TEXT NOT NULL, \n\tkind TEXT NOT NULL, \n\tprovider_key TEXT, \n\tauth_type TEXT NOT NULL, \n\tpublic_config JSON NOT NULL, \n\tencrypted_credentials TEXT, \n\tapproved_catalog JSON NOT NULL, \n\tdiscovery_candidate JSON, \n\tenabled BOOLEAN NOT NULL, \n\tconfig_revision INTEGER NOT NULL, \n\tcredential_revision INTEGER NOT NULL, \n\tcatalog_revision INTEGER NOT NULL, \n\tcreated_by_user_id TEXT, \n\tid TEXT NOT NULL, \n\tcreated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tupdated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tservice_id TEXT, \n\ttool_annotations JSON DEFAULT '{}' NOT NULL, \n\tannotations_revision INTEGER DEFAULT '1' NOT NULL, \n\tapproved_instructions TEXT DEFAULT ('') NOT NULL, \n\toauth_status TEXT, \n\toauth_storage_revision INTEGER DEFAULT '1' NOT NULL, \n\tCONSTRAINT pk_tool_connections PRIMARY KEY (id), \n\tCONSTRAINT ck_tool_connections_kind_valid CHECK (kind IN ('native','mcp_http','mcp_stdio')), \n\tCONSTRAINT ck_tool_connections_revisions_positive CHECK (config_revision > 0 AND credential_revision > 0 AND catalog_revision > 0), \n\tCONSTRAINT fk_tool_connections_service_id_mcp_services FOREIGN KEY(service_id) REFERENCES mcp_services (id), \n\tCONSTRAINT fk_tool_connections_created_by_user_id_users FOREIGN KEY(created_by_user_id) REFERENCES users (id), \n\tCONSTRAINT ck_tool_connections_enabled_boolean CHECK (enabled IN (0, 1)), \n\tCONSTRAINT ck_tool_connections_auth_valid CHECK (auth_type IN ('none','bearer','header','env','oauth')), \n\tCONSTRAINT ck_tool_connections_oauth_revision_positive CHECK (oauth_storage_revision > 0), \n\tCONSTRAINT ck_tool_connections_oauth_state_valid CHECK ((auth_type='oauth' AND kind='mcp_http' AND oauth_status IS NOT NULL AND oauth_status IN ('disconnected','connected','reauth_required')) OR (auth_type!='oauth' AND oauth_status IS NULL))\n)"
    )
    op.execute(
        "INSERT INTO _org_tool_connections (name,kind,provider_key,auth_type,public_config,encrypted_credentials,approved_catalog,discovery_candidate,enabled,config_revision,credential_revision,catalog_revision,created_by_user_id,id,created_at,updated_at,service_id,tool_annotations,annotations_revision,approved_instructions,oauth_status,oauth_storage_revision) SELECT name,kind,provider_key,auth_type,public_config,encrypted_credentials,approved_catalog,discovery_candidate,enabled,config_revision,credential_revision,catalog_revision,created_by_user_id,id,created_at,updated_at,service_id,tool_annotations,annotations_revision,approved_instructions,oauth_status,oauth_storage_revision FROM tool_connections"
    )
    op.drop_table("tool_connections")
    op.rename_table("_org_tool_connections", "tool_connections")
    op.execute(
        "CREATE TABLE _org_knowledge_bases (\n\tid TEXT NOT NULL, \n\tcreated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tupdated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tcreated_by_user_id TEXT NOT NULL, \n\tclient_request_id TEXT NOT NULL, \n\tname TEXT NOT NULL, \n\tdescription TEXT NOT NULL, revision INTEGER DEFAULT '1' NOT NULL, chunk_size INTEGER, chunk_overlap INTEGER, min_section_chars INTEGER, \n\tCONSTRAINT pk_knowledge_bases PRIMARY KEY (id), \n\tCONSTRAINT ck_knowledge_bases_name_valid CHECK (length(trim(name)) BETWEEN 1 AND 100), \n\tCONSTRAINT uq_knowledge_bases_created_by_user_id UNIQUE (created_by_user_id, client_request_id), \n\tCONSTRAINT fk_knowledge_bases_created_by_user_id_users FOREIGN KEY(created_by_user_id) REFERENCES users (id)\n)"
    )
    op.execute(
        "INSERT INTO _org_knowledge_bases (id,created_at,updated_at,created_by_user_id,client_request_id,name,description,revision,chunk_size,chunk_overlap,min_section_chars) SELECT id,created_at,updated_at,owner_user_id,client_request_id,name,description,revision,chunk_size,chunk_overlap,min_section_chars FROM knowledge_bases"
    )
    op.drop_table("knowledge_bases")
    op.rename_table("_org_knowledge_bases", "knowledge_bases")
    op.create_index(
        "ix_knowledge_bases_created_by_user_id", "knowledge_bases", ["created_by_user_id"]
    )
    op.execute(
        "CREATE TABLE _org_mcp_services (\n\tid TEXT NOT NULL, \n\tname TEXT NOT NULL, \n\tdescription TEXT NOT NULL, \n\turl TEXT, \n\tcreated_by_user_id TEXT, \n\trevision INTEGER NOT NULL, \n\tenabled BOOLEAN NOT NULL, \n\tcreated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tupdated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\ttransport TEXT DEFAULT 'http' NOT NULL, \n\tcommand TEXT, \n\targs JSON DEFAULT '[]' NOT NULL, \n\tenv_keys JSON DEFAULT '[]' NOT NULL, input_fields JSON DEFAULT '[]' NOT NULL, \n\tCONSTRAINT pk_mcp_services PRIMARY KEY (id), \n\tCONSTRAINT fk_mcp_services_created_by_user_id_users FOREIGN KEY(created_by_user_id) REFERENCES users (id), \n\tCONSTRAINT ck_mcp_services_transport_valid CHECK (transport IN ('http','stdio')), \n\tCONSTRAINT ck_mcp_services_transport_definition_valid CHECK ((transport='http' AND url IS NOT NULL AND command IS NULL) OR (transport='stdio' AND url IS NULL AND command IS NOT NULL))\n)"
    )
    op.execute(
        "INSERT INTO _org_mcp_services (id,name,description,url,created_by_user_id,revision,enabled,created_at,updated_at,transport,command,args,env_keys,input_fields) SELECT id,name,description,url,owner_user_id,revision,enabled,created_at,updated_at,transport,command,args,env_keys,input_fields FROM mcp_services"
    )
    op.drop_table("mcp_services")
    op.rename_table("_org_mcp_services", "mcp_services")


def downgrade():
    raise RuntimeError("组织资源与个人配置已合并，不能无损降级；请恢复切换前完整备份。")

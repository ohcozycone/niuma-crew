"""Resource management cannot be reached through trusted execution reads."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.auth.actor import Actor
from app.auth.models import User
from app.employees.access import authorize_execution, configured_agent
from app.employees.assembly import capture_skills
from app.employees.models import AgentSkill, AgentToolGrant
from app.employees.organization_rules import OrganizationRulesService, current_rules
from app.employees.schemas import (
    AgentCreate,
    AgentPatch,
    OrganizationRulesUpdate,
    ToolAccountBindingInput,
)
from app.employees.service import AgentService
from app.employees.tool_account_bindings import ToolAccountBindingService
from app.errors import ConflictError, NotFoundError, PermissionDeniedError, ServiceUnavailableError
from app.infrastructure.credentials import CredentialUnavailableError, CredentialVault
from app.infrastructure.database.session import Database
from app.mcp.models import McpService, ToolConnection
from app.model_connections.models import ModelConnection
from app.model_connections.schemas import ConnectionCreate, ConnectionPatch
from app.model_connections.service import ModelConnectionService
from app.skills.definitions import definition_from_record, protocol_names, readiness_reason
from app.skills.models import Skill
from app.skills.schemas import SkillCreate, SkillImport, SkillPatch
from app.skills.service import SkillService


@pytest.fixture
def resources(migrated_config):
    database = Database(migrated_config.database)
    with database.transaction() as db:
        admin = User(username="resource-admin", role="admin", password_hash="unused")
        member = User(username="resource-member", role="member", password_hash=None)
        db.add_all([admin, member])
        db.flush()
        expires = datetime.now(UTC) + timedelta(hours=1)
        actors = {
            user.role: Actor("user", str(uuid4()), user.id, user.username, user.role, expires)
            for user in (admin, member)
        }
        actors["guest"] = Actor("guest", str(uuid4()), None, None, "guest", expires)
    services = SimpleNamespace(
        database=database,
        skills=SkillService(database, migrated_config.skills),
        agents=AgentService(database),
        bindings=ToolAccountBindingService(database),
        rules=OrganizationRulesService(database),
        models=ModelConnectionService(
            database, CredentialVault(migrated_config.model_encryption_key_file)
        ),
        **actors,
    )
    try:
        yield services
    finally:
        database.close()


MISSING = "b3d1b9eb-1d63-4a59-9652-6b08939f0f7e"


@pytest.mark.parametrize(
    "operation",
    [
        lambda r: r.skills.create(SkillCreate(name="denied", instructions="secret"), r.member),
        lambda r: r.skills.get(MISSING, r.member),
        lambda r: r.skills.list(actor=r.member),
        lambda r: r.skills.update(MISSING, SkillPatch(expected_revision=1), r.member),
        lambda r: r.skills.delete(MISSING, r.member),
        lambda r: r.skills.read_file(MISSING, "SKILL.md", r.member),
        lambda r: r.skills.export_package(MISSING, r.member),
        lambda r: r.skills.preview_import(SkillImport(archive_base64="invalid"), r.member),
        lambda r: r.skills.import_package(SkillImport(archive_base64="invalid"), r.member),
        lambda r: r.skills.sync_library(r.member),
        lambda r: r.skills.library_directory(r.member),
        lambda r: r.models.create(ConnectionCreate(name="denied", api_key="secret"), r.member),
        lambda r: r.models.get(MISSING, r.member),
        lambda r: r.models.list(actor=r.member),
        lambda r: r.models.update(
            MISSING,
            ConnectionPatch(expected_config_revision=1, expected_credential_revision=1),
            r.member,
        ),
        lambda r: r.models.delete(MISSING, r.member),
        lambda r: r.models.test(MISSING, r.member),
        lambda r: r.models.presets(r.member),
        lambda r: r.rules.get(r.member),
        lambda r: r.rules.update(
            OrganizationRulesUpdate(instructions="denied", revision=0), r.member
        ),
        lambda r: r.agents.get(MISSING, r.member),
        lambda r: r.agents.list(actor=r.member),
        lambda r: r.agents.get_usage(MISSING, r.guest),
    ],
)
def test_management_rejects_before_lookup_filesystem_or_provider_work(resources, operation):
    with pytest.raises(PermissionDeniedError):
        operation(resources)
    with resources.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(Skill)) == 0
        assert db.scalar(select(func.count()).select_from(ModelConnection)) == 0
        assert current_rules(db).revision == 0
    assert not resources.skills.library.root.exists()
    assert not resources.models.vault.path.exists()


def test_member_execution_reads_fixed_definitions_without_management_privileges(resources):
    connection = resources.models.create(
        ConnectionCreate(name="runtime", api_key="runtime-key"), resources.admin
    )
    skill = resources.skills.create(
        SkillCreate(name="Legacy method", instructions="Complete the permitted work."),
        resources.admin,
    )
    agent = resources.agents.create(
        AgentCreate(
            name="worker",
            avatar_id="worker",
            model_connection_id=connection.id,
            skill_assignments=[{"skill_id": skill.id, "parameters": {}, "enabled": True}],
        ),
        resources.admin,
    )
    with pytest.raises(PermissionDeniedError):
        resources.skills.get(str(skill.id), resources.member)
    assert resources.skills.get_public(str(skill.id), resources.member).name == skill.name
    assert resources.agents.get_usage(str(agent.id), resources.member).skill_assignments[0].ready
    config = resources.models.resolve(
        str(connection.id), connection.config_revision, connection.credential_revision
    )
    assert config.api_key.get_secret_value() == "runtime-key"
    with resources.database.transaction() as db:
        captured = capture_skills(db, configured_agent(db, str(agent.id)), [str(skill.id)])
        definition = definition_from_record(db.get(Skill, str(skill.id)))
        assert captured[0]["skill_md"] == definition.skill_md
        assert captured[0]["instructions_hash"] == definition.instructions_hash
        assert captured[0]["package_manifest"] == definition.package_manifest
        snapshot = {
            "agent_id": str(agent.id),
            "connection_id": str(connection.id),
            "skills": captured,
        }
        authorize_execution(db, snapshot, [str(skill.id)])
        db.get(AgentSkill, (str(agent.id), str(skill.id))).enabled = False
    with resources.database.transaction() as db, pytest.raises(ConflictError) as error:
        authorize_execution(db, snapshot, [str(skill.id)])
    assert error.value.code == "skill_access_revoked"


def test_catalog_names_and_execution_use_the_same_standard_and_legacy_sources(
    resources, monkeypatch
):
    source = "---\nname: portable-method\ndescription: portable method\n---\nDo the work."
    standard = resources.skills.create(
        SkillCreate(name="显示别名", skill_md=source), resources.admin
    )
    legacy = resources.skills.create(
        SkillCreate(name="旧格式", instructions="旧方法正文"), resources.admin
    )

    def no_file_bytes(*args):
        pytest.fail("Listing protocol names must not load support files")

    monkeypatch.setattr(resources.skills.blobs, "read", no_file_bytes)
    with resources.database.transaction() as db:
        names = protocol_names(db, [str(standard.id), str(legacy.id)])
        assert names == {
            str(standard.id): "portable-method",
            str(legacy.id): "s-" + str(legacy.id),
        }
        assert protocol_names(db, []) == {}
        definition = definition_from_record(db.get(Skill, str(standard.id)))
        assert definition.protocol_name == names[str(standard.id)]
        assert definition.instructions == "Do the work."
        assert definition.skill_md == source


def test_legacy_example_sections_do_not_replace_missing_working_instructions(resources):
    skill = resources.skills.create(
        SkillCreate(name="incomplete", input_description="a ticket", example="an example"),
        resources.admin,
    )
    with resources.database.transaction() as db:
        definition = definition_from_record(db.get(Skill, str(skill.id)))
        assert "an example" in definition.instructions
        assert readiness_reason(definition) == "技能正文为空"


def test_credential_failure_has_model_semantics_and_rolls_back_changes(resources, monkeypatch):
    connection = resources.models.create(
        ConnectionCreate(name="original", api_key="original-key"), resources.admin
    )

    def unavailable(*args, **kwargs):
        raise CredentialUnavailableError()

    monkeypatch.setattr(resources.models.vault, "decrypt", unavailable)
    with pytest.raises(ServiceUnavailableError) as error:
        resources.models.resolve(str(connection.id), 1, 1)
    assert error.value.code == "model_credentials_unavailable"
    with pytest.raises(ServiceUnavailableError):
        resources.models.update(
            str(connection.id),
            ConnectionPatch(
                expected_config_revision=1,
                expected_credential_revision=1,
                name="must-roll-back",
                api_key="new-key",
            ),
            resources.admin,
        )
    saved = resources.models.get(str(connection.id), resources.admin)
    assert (saved.name, saved.config_revision, saved.credential_revision) == ("original", 1, 1)


def test_account_choice_changes_only_the_users_binding_not_the_employee_grant(resources):
    employee = resources.agents.create(
        AgentCreate(name="ticket helper", avatar_id="worker"), resources.admin
    )
    descriptor = {"name": "read_ticket", "descriptor_hash": "confirmed-definition"}
    with resources.database.transaction() as db:
        service = McpService(
            name="tickets", url="https://tickets.example/mcp", owner_user_id=resources.admin.user_id
        )
        db.add(service)
        db.flush()
        template = ToolConnection(
            service_id=service.id,
            name="creator account",
            kind="mcp_http",
            auth_type="none",
            public_config={"url": service.url},
            approved_catalog=[descriptor],
            created_by_user_id=resources.admin.user_id,
        )
        own = ToolConnection(
            service_id=service.id,
            name="member account",
            kind="mcp_http",
            auth_type="none",
            public_config={"url": service.url},
            approved_catalog=[descriptor],
            created_by_user_id=resources.member.user_id,
        )
        db.add_all([template, own])
        db.flush()
        grant = AgentToolGrant(
            agent_id=str(employee.id),
            tool_connection_id=template.id,
            account_mode="personal",
            tools=[descriptor],
            scope_policy={"mode": "provider", "max_calls": 1},
        )
        db.add(grant)
        db.flush()
        grant_id, own_id, creator_id = grant.id, own.id, template.id
    result = resources.bindings.bind(
        str(employee.id),
        grant_id,
        ToolAccountBindingInput(connection_id=own_id, expected_revision=0),
        resources.member,
    )
    assert result["items"][0]["connected"]
    assert result["items"][0]["connection_id"] == own_id
    with pytest.raises(NotFoundError):
        resources.bindings.bind(
            str(employee.id),
            grant_id,
            ToolAccountBindingInput(connection_id=creator_id, expected_revision=1),
            resources.member,
        )
    with resources.database.transaction() as db:
        assert db.get(AgentToolGrant, grant_id).tools == [descriptor]
        assert db.get(AgentToolGrant, grant_id).revision == 1
    resources.bindings.bind(
        str(employee.id),
        grant_id,
        ToolAccountBindingInput(connection_id=None, expected_revision=1),
        resources.member,
    )
    assert not resources.bindings.get(str(employee.id), resources.member)["items"][0]["connected"]
    creator = resources.bindings.get(str(employee.id), resources.admin)["items"][0]
    assert creator["connected"] and creator["connection_id"] == creator_id


@pytest.mark.parametrize("model", [AgentCreate, AgentPatch])
def test_retired_employee_field_is_rejected(model):
    fields = (
        {"name": "worker", "avatar_id": "worker"}
        if model is AgentCreate
        else {"expected_revision": 1}
    )
    with pytest.raises(ValidationError):
        model.model_validate({**fields, "ci_repository": "owner/repository"})


def test_binding_requires_an_explicit_valid_connection_or_null():
    with pytest.raises(ValidationError):
        ToolAccountBindingInput.model_validate({"expected_revision": 0})
    with pytest.raises(ValidationError):
        ToolAccountBindingInput(connection_id="", expected_revision=0)
    assert ToolAccountBindingInput(connection_id=None, expected_revision=0).connection_id is None

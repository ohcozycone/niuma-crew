"""Public account/catalog operations authorize users; runtime secrets stay inside transports."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.actor import Actor
from app.auth.models import User
from app.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    ServiceUnavailableError,
)
from app.infrastructure.credentials import CredentialUnavailableError, CredentialVault
from app.infrastructure.database.session import Database
from app.mcp.catalogs import ToolCatalogService
from app.mcp.config import ToolConfig
from app.mcp.connections import ToolConnectionService
from app.mcp.definitions import McpDefinitionService
from app.mcp.invocation import ToolInvocationService
from app.mcp.models import McpService, ToolConnection
from app.mcp.schemas import (
    CatalogAnnotations,
    CatalogApprove,
    McpConfigImport,
    McpServiceCreate,
    McpServicePatch,
    ToolConnectionCreate,
    ToolConnectionPatch,
)
from app.values import digest


def actor(user_id=None, role="guest"):
    return Actor(
        "user" if user_id else "guest",
        str(uuid4()),
        user_id,
        role,
        role,
        datetime.now(UTC) + timedelta(hours=1),
    )


@pytest.fixture
def tool_services(migrated_config, tmp_path):
    database = Database(migrated_config.database)
    with database.transaction() as db:
        owner = User(username="tool-owner", role="member", password_hash=None)
        other = User(username="other-owner", role="member", password_hash=None)
        admin = User(username="tool-admin", role="admin", password_hash="test-only-hash")
        db.add_all([owner, other, admin])
        db.flush()
    config = ToolConfig(stdio_enabled=True)
    vault = CredentialVault(tmp_path / "private" / "tools.key")
    connections = ToolConnectionService(
        database, vault, config, check_references=lambda db, ids: None
    )
    invocation = ToolInvocationService(connections)
    catalogs = ToolCatalogService(connections, invocation)
    definitions = McpDefinitionService(database, config, check_references=lambda db, ids: None)
    yield SimpleNamespace(
        database=database,
        connections=connections,
        invocation=invocation,
        catalogs=catalogs,
        definitions=definitions,
        owner=actor(owner.id, "member"),
        other=actor(other.id, "member"),
        admin=actor(admin.id, "admin"),
        vault=vault,
    )
    asyncio.run(invocation.close())
    database.close()


def create_http(services):
    return services.connections.create(
        services.owner,
        ToolConnectionCreate(
            name="Personal search account",
            kind="mcp_http",
            auth_type="bearer",
            credential="fixture-token",
            public_config={"url": "https://mcp.tavily.com/mcp"},
        ),
    )


def patch(row, **changes):
    return ToolConnectionPatch(
        expected_config_revision=row.config_revision,
        expected_credential_revision=row.credential_revision,
        **changes,
    )


@pytest.mark.parametrize(
    "operation",
    [
        "list_connections",
        "create_connection",
        "update_connection",
        "delete_connection",
        "discover_catalog",
        "approve_catalog",
        "annotate_catalog",
        "discard_catalog",
        "list_definitions",
        "create_definition",
        "update_definition",
        "delete_definition",
        "preview_definition",
    ],
)
def test_public_operations_reject_guest_before_accessing_storage_or_secrets(
    tool_services, operation
):
    services, guest, missing_id = tool_services, actor(), str(uuid4())
    approval = CatalogApprove(
        expected_config_revision=1, expected_catalog_revision=1, candidate_hash="unused"
    )
    calls = {
        "list_connections": lambda: services.connections.list(guest),
        "create_connection": lambda: services.connections.create(
            guest,
            ToolConnectionCreate(
                name="Denied account",
                kind="mcp_http",
                auth_type="bearer",
                credential="must-never-be-encrypted",
                public_config={"url": "https://mcp.tavily.com/mcp"},
            ),
        ),
        "update_connection": lambda: services.connections.update(
            guest,
            missing_id,
            ToolConnectionPatch(expected_config_revision=1, expected_credential_revision=1),
        ),
        "delete_connection": lambda: services.connections.delete(guest, missing_id, 1, 1),
        "discover_catalog": lambda: asyncio.run(services.catalogs.discover(guest, missing_id)),
        "approve_catalog": lambda: services.catalogs.approve(guest, missing_id, approval),
        "annotate_catalog": lambda: services.catalogs.annotate(
            guest, missing_id, CatalogAnnotations(expected_annotations_revision=1, annotations={})
        ),
        "discard_catalog": lambda: services.catalogs.discard(guest, missing_id, approval),
        "list_definitions": lambda: services.definitions.list(guest),
        "create_definition": lambda: services.definitions.create(
            guest, McpServiceCreate(name="Denied", url="https://mcp.tavily.com/mcp")
        ),
        "update_definition": lambda: services.definitions.update(
            guest, missing_id, McpServicePatch(expected_revision=1, enabled=False)
        ),
        "delete_definition": lambda: services.definitions.delete(guest, missing_id, 1),
        "preview_definition": lambda: services.definitions.import_config(
            guest, McpConfigImport(configuration="{not valid JSON}")
        ),
    }
    with pytest.raises(PermissionDeniedError):
        calls[operation]()
    assert not services.vault.path.exists()
    with services.database.transaction() as db:
        assert list(db.scalars(select(ToolConnection))) == []
        assert list(db.scalars(select(McpService))) == []


def test_account_owner_check_applies_before_remote_catalog_access(tool_services):
    services = tool_services
    connection = create_http(services)
    with pytest.raises(NotFoundError):
        services.connections.update(services.other, connection.id, patch(connection, enabled=False))
    with pytest.raises(NotFoundError):
        asyncio.run(services.catalogs.discover(services.other, connection.id))
    assert next(
        row for row in services.connections.list(services.owner) if row.id == connection.id
    ).enabled
    assert services.connections.list(services.other) == []


def test_stdio_registration_uses_actor_role_without_trusting_a_caller_flag(tool_services):
    request = McpServiceCreate(name="Local MCP", transport="stdio", command="npx", args=[])
    with pytest.raises(PermissionDeniedError) as failure:
        tool_services.definitions.create(tool_services.owner, request)
    assert failure.value.code == "stdio_registration_denied"
    created = tool_services.definitions.create(tool_services.admin, request)
    assert created["transport"] == "stdio"


def test_credential_change_and_catalog_invalidation_roll_back_together(tool_services, monkeypatch):
    services = tool_services
    connection = create_http(services)
    with services.database.transaction() as db:
        row = db.get(ToolConnection, connection.id)
        row.approved_catalog = [{"name": "search", "descriptor_hash": "approved"}]
        row.approved_instructions = "Approved account instructions"
        row.discovery_candidate = {"hash": "candidate"}
        ciphertext = row.encrypted_credentials
    original_flush = Session.flush

    def fail_changed_connection(session, *args, **kwargs):
        if any(
            isinstance(row, ToolConnection) and row.credential_revision == 2
            for row in session.dirty
        ):
            raise RuntimeError("injected persistence failure")
        return original_flush(session, *args, **kwargs)

    monkeypatch.setattr(Session, "flush", fail_changed_connection)
    with pytest.raises(RuntimeError, match="injected persistence"):
        services.connections.update(
            services.owner, connection.id, patch(connection, credential="replacement-token")
        )
    with services.database.transaction() as db:
        row = db.get(ToolConnection, connection.id)
        assert row.credential_revision == 1 and row.catalog_revision == 1
        assert row.encrypted_credentials == ciphertext
        assert row.approved_catalog == [{"name": "search", "descriptor_hash": "approved"}]
        assert row.approved_instructions == "Approved account instructions"
        assert row.discovery_candidate == {"hash": "candidate"}


def test_discovery_does_not_save_a_catalog_for_a_changed_account(tool_services):
    services = tool_services
    connection = create_http(services)

    class ChangedAccountClient:
        instructions = "Remote instructions"

        def __init__(self, *args):
            pass

        async def discover(self):
            services.connections.update(
                services.owner, connection.id, patch(connection, name="Renamed during discovery")
            )
            return [{"name": "search", "input_schema": {"type": "object"}}]

    services.invocation.client_factory = ChangedAccountClient
    with pytest.raises(ConflictError) as failure:
        asyncio.run(services.catalogs.discover(services.owner, connection.id))
    assert failure.value.code == "tool_connection_changed"
    stored = next(
        row for row in services.connections.list(services.owner) if row.id == connection.id
    )
    assert stored.discovery_candidate is None and stored.approved_catalog == []
    assert stored.name == "Renamed during discovery"


@pytest.mark.parametrize("path", ["http_transport", "stdio_transport", "result_redaction"])
def test_all_tool_secret_paths_map_neutral_vault_failure_to_tool_error(tool_services, path):
    services = tool_services
    row = SimpleNamespace(
        kind="mcp_stdio" if path == "stdio_transport" else "mcp_http",
        auth_type="env" if path == "stdio_transport" else "bearer",
        public_config={"url": "https://mcp.tavily.com/mcp"},
        encrypted_credentials="old-encrypted-value",
    )
    with pytest.raises(ServiceUnavailableError) as failure:
        if path == "result_redaction":
            services.connections.secrets_for_redaction(row)
        else:
            services.invocation.client_for_connection(row)
    assert failure.value.code == "tool_credentials_unavailable"
    assert "model" not in failure.value.code
    assert not services.vault.path.exists()


def test_existing_key_and_ciphertext_survive_shared_vault_move(tmp_path):
    key = Fernet.generate_key()
    ciphertext = Fernet(key).encrypt(b"existing-credential").decode()
    path = tmp_path / "existing.key"
    path.write_bytes(key)
    vault = CredentialVault(path)
    assert vault.decrypt(ciphertext) == "existing-credential"
    assert Fernet(key).decrypt(vault.encrypt("new-credential", allow_create=False).encode()) == (
        b"new-credential"
    )
    assert path.read_bytes() == key
    with pytest.raises(CredentialUnavailableError) as failure:
        vault.decrypt("damaged")
    assert not hasattr(failure.value, "code")


def test_run_close_attempts_every_client_and_releases_registry_on_failure(tool_services):
    services, closed = tool_services, []

    class Client:
        def __init__(self, name, failed=False):
            self.name, self.failed = name, failed

        async def aclose(self):
            closed.append(self.name)
            if self.failed:
                raise RuntimeError("injected close failure")

    async def close():
        caller = services.invocation.for_run("isolated-run")
        caller.clients = {"first": Client("first", True), "second": Client("second")}
        services.invocation._run_callers.add(caller)
        with pytest.raises(RuntimeError, match="injected close failure"):
            await caller.aclose()
        assert caller.closed and caller.clients == {}
        assert not services.invocation._run_callers

    asyncio.run(close())
    assert sorted(closed) == ["first", "second"]


def test_policy_change_blocks_stdio_discovery_and_invocation(tool_services):
    services = tool_services
    definition = services.definitions.create(
        services.admin,
        McpServiceCreate(name="Local MCP", transport="stdio", command="npx", args=[]),
    )
    connection = services.connections.create(
        services.owner,
        ToolConnectionCreate(
            name="Local account",
            kind="mcp_stdio",
            service_id=definition["id"],
            public_config={"command": "npx", "args": [], "env_keys": []},
        ),
    )
    services.connections.config = replace(services.connections.config, stdio_enabled=False)
    with services.database.transaction() as db:
        row = db.get(ToolConnection, connection.id)
    with pytest.raises(InvalidInputError) as invocation_failure:
        services.invocation.client_for_connection(row)
    assert invocation_failure.value.code == "stdio_disabled"
    with pytest.raises(InvalidInputError) as discovery_failure:
        asyncio.run(services.catalogs.discover(services.owner, connection.id))
    assert discovery_failure.value.code == "stdio_disabled"


@pytest.mark.parametrize("changed", [False, True])
def test_discovery_approval_and_runtime_share_catalog_and_secret_boundaries(tool_services, changed):
    services = tool_services
    connection = create_http(services)
    descriptor = {
        "name": "search",
        "description": "Search the public index",
        "input_schema": {"type": "object"},
        "descriptor_hash": "approved-definition",
    }
    guards = []

    class Client:
        instructions = "Approved account guidance"

        def __init__(self, url, headers, config):
            self.headers = headers

        async def discover(self):
            return [descriptor]

        async def invoke(self, name, arguments, expected_hash, guard):
            assert name == "search" and expected_hash == descriptor["descriptor_hash"]
            await guard()
            if changed:
                error = InvalidInputError("tool_catalog_changed", "Remote tool changed")
                error.catalog = [{**descriptor, "descriptor_hash": "changed-definition"}]
                error.instructions = self.instructions
                raise error
            return self.headers["Authorization"], {"value": "fixture-token"}, "success"

    services.invocation.client_factory = Client
    found = asyncio.run(services.catalogs.discover(services.owner, connection.id))
    approved = services.catalogs.approve(
        services.owner,
        connection.id,
        CatalogApprove(
            expected_config_revision=found.config_revision,
            expected_catalog_revision=found.catalog_revision,
            candidate_hash=found.discovery_candidate["hash"],
        ),
    )
    binding = {
        "kind": "mcp_http",
        "connection_id": connection.id,
        "tool_name": descriptor["name"],
        "input_schema": descriptor["input_schema"],
        "descriptor_hash": descriptor["descriptor_hash"],
        "instructions_hash": digest(Client.instructions),
        "config_revision": approved.config_revision,
        "credential_revision": approved.credential_revision,
        "scope_policy": {"mode": "provider"},
    }

    async def execute():
        async def guard():
            guards.append("checked")

        async with services.invocation.for_run("approved-runtime") as caller:
            return await caller.call(binding, {}, guard)

    if changed:
        with pytest.raises(InvalidInputError) as failure:
            asyncio.run(execute())
        assert failure.value.code == "tool_catalog_changed"
        stored = next(
            row for row in services.connections.list(services.owner) if row.id == connection.id
        )
        assert stored.approved_catalog == [descriptor]
        assert stored.discovery_candidate["tools"][0]["descriptor_hash"] == "changed-definition"
    else:
        result = asyncio.run(execute())
        assert result.status == "succeeded"
        assert "fixture-token" not in result.content and "[REDACTED]" in result.content
        assert "fixture-token" not in str(result.data)
    assert guards == ["checked"]

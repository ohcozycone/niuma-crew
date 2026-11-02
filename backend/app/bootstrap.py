"""Assemble the HTTP application and its dependencies."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.agent_runtime.checkpoints import CheckpointStore
from app.agent_runtime.langchain import execute_agent
from app.agents.service import AgentService
from app.agents.tool_account_bindings import ToolAccountBindingService
from app.agents.tool_grants import ToolGrantService
from app.api.errors import register_error_handlers
from app.api.failure_boundary import FailureBoundaryMiddleware
from app.api.frontend_delivery import mount_frontend
from app.api.rate_limit import RateLimiter
from app.api.router import router
from app.api.security import BrowserSecurityMiddleware
from app.auth.github import GitHubOAuth
from app.auth.service import AuthService
from app.config import AppConfig, load_config
from app.conversations.authorization import ConversationAuthorization
from app.conversations.files import ConversationFiles, retained_file_ids
from app.conversations.preparation import ConversationPreparation
from app.conversations.publication import PublishRun
from app.conversations.queries import ConversationQueries
from app.conversations.service import ConversationService
from app.execution.admission import RunAdmission
from app.execution.contracts import ExecutionStatus
from app.execution.coordinator import ExecutionCoordinator
from app.execution.scheduler import Runner
from app.execution.store import RunStore
from app.files.service import FileService
from app.infrastructure.credentials import CredentialVault
from app.infrastructure.database.session import Database
from app.knowledge.service import KnowledgeService
from app.knowledge.service import retained_file_ids as retained_knowledge_files
from app.knowledge.worker import KnowledgeWorker
from app.model_connections.service import ModelConnectionService
from app.organization_rules.service import OrganizationRulesService
from app.sandboxes.service import SandboxService
from app.skills.service import SkillService
from app.tools.catalogs import ToolCatalogService
from app.tools.connections import ToolConnectionService
from app.tools.definitions import McpDefinitionService
from app.tools.invocation import ToolInvocationService


def create_app(config: AppConfig | None = None) -> FastAPI:
    settings = config if config is not None else load_config()
    application_logger = logging.getLogger("app")
    if not application_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        application_logger.addHandler(handler)
    application_logger.setLevel(logging.INFO)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = Database(settings.database)
        app.state.database = database
        app.state.auth = AuthService(database, settings.auth)
        app.state.rate_limiter = RateLimiter()
        app.state.github_oauth = GitHubOAuth(settings.github_oauth)
        app.state.model_connections = ModelConnectionService(
            database,
            CredentialVault(
                settings.model_encryption_key_file,
                settings.model_encryption_key,
            ),
        )
        app.state.agents = AgentService(database)
        app.state.tool_account_bindings = ToolAccountBindingService(database)
        app.state.organization_rules = OrganizationRulesService(database)
        app.state.tool_grants = ToolGrantService(database)
        check_references = app.state.tool_grants.assert_connections_unused
        app.state.mcp_definitions = McpDefinitionService(
            database, settings.tools, check_references=check_references
        )
        app.state.tool_connections = ToolConnectionService(
            database,
            CredentialVault(
                settings.model_encryption_key_file.with_name(
                    settings.model_encryption_key_file.name + ".tools"
                ),
                settings.model_encryption_key,
            ),
            settings.tools,
            check_references=check_references,
        )
        app.state.tool_invocation = ToolInvocationService(app.state.tool_connections)
        app.state.tool_catalogs = ToolCatalogService(
            app.state.tool_connections, app.state.tool_invocation
        )
        app.state.skills = SkillService(database, settings.skills)
        app.state.files = FileService(database, settings.files)
        app.state.knowledge = KnowledgeService(
            database, app.state.files, app.state.model_connections
        )
        app.state.knowledge_worker = KnowledgeWorker(
            app.state.knowledge.processing,
            settings.runner_lock_file.with_name(settings.runner_lock_file.name + ".knowledge"),
        )

        def retained_files(session, candidates):
            return retained_file_ids(session, candidates) | retained_knowledge_files(
                session, candidates
            )

        app.state.conversation_files = ConversationFiles(database, app.state.files)
        app.state.sandboxes = SandboxService(
            database, settings.sandbox, lambda: app.state.execution_store.active_ids()
        )
        status = ExecutionStatus("starting" if settings.runtime.enabled else "ready")
        app.state.runtime_status = status
        app.state.runtime_settings = settings.runtime
        app.state.conversation_queries = ConversationQueries(database)
        app.state.subscriptions = {}

        authorization = ConversationAuthorization(
            database, app.state.auth, app.state.model_connections, app.state.knowledge.employee
        )
        publisher = PublishRun(
            database,
            authorization.check,
            prepare_content=lambda db, row, text: (
                app.state.knowledge.employee.finalize_answer(row.id, text, db=db)
                if row.config_snapshot.get("knowledge")
                else text
            ),
        )
        checkpoints = CheckpointStore(database.engine.url.database)
        app.state.checkpoints = checkpoints
        preparation = ConversationPreparation(
            settings.runtime,
            connections=app.state.model_connections,
            checkpoints=checkpoints,
            execute_agent=execute_agent,
            tools=app.state.tool_invocation,
            files=app.state.files,
            sandboxes=app.state.sandboxes,
            skills=app.state.skills,
            knowledge=app.state.knowledge.employee,
        )
        app.state.conversation_commands = ConversationService(
            database,
            settings.runtime,
            RunAdmission(settings.runtime, status),
            preparation,
            publisher,
        )
        store = RunStore(database)
        app.state.execution_store = store
        coordinator = ExecutionCoordinator(
            store, preparation.execution, authorization.check, publisher, settings.runtime, status
        )
        app.state.runner = Runner(
            store,
            coordinator,
            settings.runtime,
            status,
            settings.runner_lock_file,
        )
        try:
            if settings.runtime.enabled:
                await app.state.runner.start()
                await app.state.knowledge_worker.start()
                await app.state.sandboxes.start()
                await app.state.files.start(retained_files)
            yield
        finally:
            if settings.runtime.enabled:
                await app.state.knowledge_worker.stop()
                await app.state.runner.stop()
                await app.state.sandboxes.stop()
                await app.state.files.stop()
            await app.state.tool_invocation.close()
            database.close()

    app = FastAPI(
        version=__version__,
        title="NiumaCrew Platform API",
        description="NiumaCrew 数字员工管理平台 API，提供员工配置、技能管理、技能装配和健康检查。",
        redoc_url=None,
        openapi_url=None if settings.auth.cookie_secure else "/openapi.json",
        docs_url=None if settings.auth.cookie_secure else "/docs",
        lifespan=lifespan,
    )
    app.include_router(router)
    app.add_middleware(BrowserSecurityMiddleware, config=settings.auth)
    app.add_middleware(FailureBoundaryMiddleware)
    register_error_handlers(app)
    mount_frontend(app, settings.frontend_dist)
    return app

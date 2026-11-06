"""Assemble the HTTP application and its dependencies."""

import logging
from contextlib import AsyncExitStack, asynccontextmanager
from functools import partial

from fastapi import FastAPI

from app import __version__
from app.api.errors import register_error_handlers
from app.api.failure_boundary import FailureBoundaryMiddleware
from app.api.frontend_delivery import mount_frontend
from app.api.oauth_logging import install_oauth_access_filter
from app.api.rate_limit import RateLimiter
from app.api.router import router
from app.api.security import BrowserSecurityMiddleware
from app.auth.github import GitHubOAuth
from app.auth.service import AuthService
from app.config import AppConfig, load_config
from app.conversations.acceptance import ConversationAcceptance
from app.conversations.files import ConversationFiles, retained_file_ids
from app.conversations.queries import ConversationQueries
from app.conversations.service import ConversationService
from app.employees.organization_rules import OrganizationRulesService
from app.employees.service import AgentService
from app.employees.tool_account_bindings import ToolAccountBindingService
from app.employees.tool_grants import assert_connections_unused
from app.environments.profiles import WorkspaceProfileService
from app.environments.service import SandboxService
from app.evaluations.service import EvaluationService
from app.evaluations.worker import EvaluationWorker
from app.execution.assembly import build_execution
from app.execution.queries import ExecutionQueries
from app.execution.service import active_run_ids
from app.execution.store import retained_file_ids as retained_run_files
from app.files.cleanup import FileCleanup
from app.files.service import FileService
from app.infrastructure.credentials import CredentialVault
from app.infrastructure.database.session import Database
from app.infrastructure.observability import CorrelationFilter, ExecutionLogs
from app.knowledge.service import KnowledgeService
from app.knowledge.service import retained_file_ids as retained_knowledge_files
from app.knowledge.worker import KnowledgeWorker
from app.mcp.catalogs import ToolCatalogService
from app.mcp.connections import ToolConnectionService
from app.mcp.definitions import McpDefinitionService
from app.mcp.invocation import ToolInvocationService
from app.mcp.oauth import OAuthService
from app.model_connections.service import ModelConnectionService
from app.skills.service import SkillService


def create_app(config: AppConfig | None = None) -> FastAPI:
    settings = config if config is not None else load_config()
    install_oauth_access_filter()
    application_logger = logging.getLogger("app")
    if not application_logger.handlers:
        handler = logging.StreamHandler()
        handler.addFilter(CorrelationFilter())
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s run_id=%(run_id)s %(message)s"
            )
        )
        application_logger.addHandler(handler)
    application_logger.setLevel(logging.INFO)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with AsyncExitStack() as cleanup:
            database = Database(settings.database)
            cleanup.callback(database.close)
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
            check_references = assert_connections_unused
            app.state.mcp_definitions = McpDefinitionService(
                database, settings.tools, check_references=check_references
            )
            app.state.workspace_profiles = WorkspaceProfileService(database, check_references)
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
            app.state.tool_oauth = OAuthService(app.state.tool_connections, app.state.auth)
            cleanup.push_async_callback(app.state.tool_oauth.close)
            app.state.tool_invocation = ToolInvocationService(
                app.state.tool_connections, oauth=app.state.tool_oauth
            )
            cleanup.push_async_callback(app.state.tool_invocation.close)
            app.state.tool_catalogs = ToolCatalogService(
                app.state.tool_connections, app.state.tool_invocation
            )
            app.state.skills = SkillService(database, settings.skills)
            app.state.files = FileService(database, settings.files)
            execution_logs = ExecutionLogs(settings.runner_lock_file.parent / "logs")
            if settings.runtime.enabled:
                cleanup.callback(execution_logs.install())
            app.state.execution_queries = ExecutionQueries(
                database, app.state.files, execution_logs
            )
            app.state.file_cleanup = FileCleanup(database, app.state.files.storage, settings.files)
            app.state.knowledge = KnowledgeService(
                database,
                app.state.files,
                app.state.model_connections,
                settings.knowledge_vector_dir,
            )
            cleanup.callback(app.state.knowledge.close)
            app.state.knowledge_worker = KnowledgeWorker(
                app.state.knowledge.processing,
                settings.runner_lock_file.with_name(settings.runner_lock_file.name + ".knowledge"),
            )

            def retained_files(session, candidates):
                return (
                    retained_file_ids(session, candidates)
                    | retained_run_files(session, candidates)
                    | retained_knowledge_files(session, candidates)
                )

            app.state.conversation_files = ConversationFiles(database, app.state.files)
            app.state.sandboxes = SandboxService(
                database, settings.sandbox, partial(active_run_ids, database)
            )
            runs, worker = build_execution(
                database=database,
                runtime=settings.runtime,
                lock_file=settings.runner_lock_file,
                model_connections=app.state.model_connections,
                files=app.state.files,
                skills=app.state.skills,
                knowledge=app.state.knowledge,
                tools=app.state.tool_invocation,
                sandboxes=app.state.sandboxes,
            )
            app.state.runs, app.state.run_worker = runs, worker
            app.state.evaluations = EvaluationService(database, runs)
            app.state.evaluation_worker = EvaluationWorker(app.state.evaluations)
            app.state.runtime_status = worker.status
            app.state.runtime_settings = settings.runtime
            app.state.conversation_queries = ConversationQueries(database)
            app.state.subscriptions = {}
            acceptance = ConversationAcceptance(
                database, runs.authorize, settings.runtime.poll_interval
            )
            worker.set_completion_notifier(acceptance.wake)
            app.state.conversation_acceptance = acceptance
            app.state.conversation_commands = ConversationService(
                database, settings.runtime, runs, acceptance
            )
            # Producers stop before the resource services they use. Register each
            # stop before its start so partial startup is covered without sweeping
            # services whose startup was never attempted.
            async with AsyncExitStack() as resources, AsyncExitStack() as workers:
                if settings.runtime.enabled:
                    workers.push_async_callback(app.state.run_worker.stop)
                    await app.state.run_worker.start()
                    workers.push_async_callback(acceptance.stop)
                    await acceptance.start()
                    workers.push_async_callback(app.state.evaluation_worker.stop)
                    await app.state.evaluation_worker.start()
                    workers.push_async_callback(app.state.knowledge_worker.stop)
                    await app.state.knowledge_worker.start()
                    resources.push_async_callback(app.state.sandboxes.stop)
                    await app.state.sandboxes.start()
                    resources.push_async_callback(app.state.file_cleanup.stop)
                    await app.state.file_cleanup.start(retained_files)
                yield

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

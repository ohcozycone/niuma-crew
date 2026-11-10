import logging
from contextlib import AsyncExitStack, asynccontextmanager
from functools import partial
from pathlib import Path

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
from app.bootstrap.services import check_employee_history, check_model_references
from app.config import AppConfig, load_config
from app.conversations.acceptance import ConversationAcceptance
from app.conversations.files import ConversationFiles, retained_file_ids
from app.conversations.queries import ConversationQueries
from app.conversations.service import ConversationService
from app.employees.organization_rules import OrganizationRulesService
from app.employees.references import model_employees, skill_assignments
from app.employees.service import AgentService
from app.employees.tool_grants import assert_connections_unused
from app.environments.service import SandboxService
from app.evaluations.service import EvaluationService
from app.evaluations.worker import EvaluationWorker
from app.execution.assembly import build_execution
from app.execution.knowledge import KnowledgeAccess, RunKnowledgeSearch
from app.execution.knowledge_evidence import KnowledgeEvidence
from app.execution.queries import ExecutionQueries
from app.execution.service import active_run_ids
from app.execution.store import retained_file_ids as retained_run_files
from app.files.cleanup import FileCleanup
from app.files.service import FileService
from app.infrastructure.credentials import CredentialVault
from app.infrastructure.database.session import Database
from app.infrastructure.observability import CorrelationFilter, ExecutionLogs
from app.knowledge.documents import KnowledgeDocuments
from app.knowledge.libraries import KnowledgeLibraries
from app.knowledge.processing import KnowledgeProcessingService
from app.knowledge.references import retained_file_ids as retained_knowledge_files
from app.knowledge.search import KnowledgeSearch
from app.knowledge.vectors import KnowledgeVectorService
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
                employee_references=model_employees,
                check_references=check_model_references,
            )
            app.state.agents = AgentService(database, check_history=check_employee_history)
            app.state.organization_rules = OrganizationRulesService(database)
            check_references = assert_connections_unused
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
            app.state.tool_oauth = OAuthService(app.state.tool_connections, app.state.auth)
            cleanup.push_async_callback(app.state.tool_oauth.close)
            app.state.tool_invocation = ToolInvocationService(
                app.state.tool_connections, oauth=app.state.tool_oauth
            )
            cleanup.push_async_callback(app.state.tool_invocation.close)
            app.state.tool_catalogs = ToolCatalogService(
                app.state.tool_connections, app.state.tool_invocation
            )
            app.state.skills = SkillService(
                database, settings.skills, assignment_facts=skill_assignments
            )
            app.state.files = FileService(database, settings.files)
            execution_logs = ExecutionLogs(settings.runner_lock_file.parent / "logs")
            if settings.runtime.enabled:
                cleanup.callback(execution_logs.install())
            app.state.execution_queries = ExecutionQueries(
                database, app.state.files, execution_logs
            )
            app.state.file_cleanup = FileCleanup(database, app.state.files.storage, settings.files)
            app.state.knowledge_libraries = KnowledgeLibraries(database)
            app.state.knowledge_vectors = KnowledgeVectorService(
                database,
                app.state.knowledge_libraries,
                app.state.model_connections,
                settings.knowledge_vector_dir
                or Path(str(database.engine.url.database)).parent / "knowledge-vectors",
            )
            cleanup.callback(app.state.knowledge_vectors.store.close)
            app.state.knowledge_documents = KnowledgeDocuments(
                database,
                app.state.files,
                app.state.knowledge_libraries,
                prune_vectors=app.state.knowledge_vectors.prune,
            )
            app.state.knowledge_processing = KnowledgeProcessingService(
                database,
                app.state.knowledge_libraries,
                app.state.files,
                document_read=app.state.knowledge_documents.document_read,
                prune_vectors=app.state.knowledge_vectors.prune,
            )
            app.state.knowledge_search = KnowledgeSearch(
                database,
                app.state.knowledge_libraries,
                app.state.knowledge_vectors,
            )
            app.state.knowledge_access = KnowledgeAccess(database)
            app.state.knowledge_evidence = KnowledgeEvidence(
                database,
                run_scope=app.state.knowledge_access.run_scope,
            )
            app.state.run_knowledge = RunKnowledgeSearch(
                database,
                app.state.knowledge_access,
                app.state.knowledge_libraries,
                app.state.knowledge_search,
                app.state.knowledge_evidence,
            )
            app.state.knowledge_worker = KnowledgeWorker(
                app.state.knowledge_processing,
                settings.runner_lock_file.with_name(settings.runner_lock_file.name + ".knowledge"),
                reconcile=app.state.knowledge_vectors.reconcile,
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
                agent_settings=settings.agent,
                lock_file=settings.runner_lock_file,
                model_connections=app.state.model_connections,
                files=app.state.files,
                skills=app.state.skills,
                knowledge_access=app.state.knowledge_access,
                knowledge_evidence=app.state.knowledge_evidence,
                knowledge_search=app.state.run_knowledge,
                tools=app.state.tool_invocation,
                sandboxes=app.state.sandboxes,
            )
            app.state.runs, app.state.run_worker = runs, worker
            app.state.evaluations = EvaluationService(database, runs)
            app.state.evaluation_worker = EvaluationWorker(app.state.evaluations)
            app.state.runtime_status = worker.status
            app.state.stream_settings = settings.stream
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
            # 先登记停止再启动，以覆盖部分启动失败；生产任务须先于资源服务停止。
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

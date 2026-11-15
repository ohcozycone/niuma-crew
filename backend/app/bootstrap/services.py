from functools import partial
from pathlib import Path

from app.api.rate_limit import RateLimiter
from app.applications.conversations.acceptance import ConversationAcceptance
from app.applications.conversations.commands import ConversationService
from app.applications.conversations.files import ConversationFiles, retained_file_ids
from app.applications.conversations.queries import ConversationQueries
from app.applications.conversations.references import assert_employee_unused as conversation_history
from app.applications.evaluations.commands import EvaluationCommands
from app.applications.evaluations.progression import EvaluationProgression
from app.applications.evaluations.queries import EvaluationQueries
from app.applications.evaluations.references import assert_employee_unused as evaluation_history
from app.applications.evaluations.worker import EvaluationWorker
from app.auth.github import GitHubOAuth
from app.auth.service import AuthService
from app.bootstrap.model_registry import register_models
from app.common.errors import ConflictError
from app.infrastructure.credentials import CredentialVault
from app.infrastructure.database.session import Database
from app.infrastructure.observability import ExecutionLogs
from app.resources.employees.references import assert_model_unused as employee_model
from app.resources.employees.references import (
    model_employees,
    skill_assignment_counts,
    skill_assignments,
)
from app.resources.employees.service import AgentService
from app.resources.employees.tool_grants import assert_connections_unused
from app.resources.environments.service import SandboxService
from app.resources.files.cleanup import FileCleanup
from app.resources.files.service import FileService
from app.resources.knowledge.documents import KnowledgeDocuments
from app.resources.knowledge.libraries import KnowledgeLibraries
from app.resources.knowledge.processing import KnowledgeProcessingService
from app.resources.knowledge.references import assert_model_unused as knowledge_model
from app.resources.knowledge.references import retained_file_ids as retained_knowledge_files
from app.resources.knowledge.search import KnowledgeSearch
from app.resources.knowledge.vectors import KnowledgeVectorService
from app.resources.knowledge.worker import KnowledgeWorker
from app.resources.mcp.catalogs import ToolCatalogService
from app.resources.mcp.connections import ToolConnectionService
from app.resources.mcp.definitions import McpDefinitionService
from app.resources.mcp.invocation import ToolInvocationService
from app.resources.mcp.oauth import OAuthService
from app.resources.model_connections.service import ModelConnectionService
from app.resources.organization_rules.service import OrganizationRulesService
from app.resources.skills.service import SkillService
from app.runtime.assembly import build_execution
from app.runtime.execution.knowledge import KnowledgeAccess, RunKnowledgeSearch
from app.runtime.execution.knowledge_evidence import KnowledgeEvidence
from app.runtime.execution.queries import ExecutionQueries
from app.runtime.execution.references import model_in_use as execution_model
from app.runtime.execution.references import retained_file_ids as retained_run_files
from app.runtime.execution.service import active_run_ids


def check_employee_history(db, agent_id):
    evaluation_history(db, agent_id)
    conversation_history(db, agent_id)


def check_model_references(db, connection_id):
    knowledge_model(db, connection_id)
    if execution_model(db, connection_id):
        raise ConflictError("model_connection_in_use", "仍有执行使用这个大脑，请等待结束或停止。")
    employee_model(db, connection_id)


def build_services(app, settings, cleanup):
    register_models()
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
        database,
        settings.skills,
        assignment_facts=skill_assignments,
        assignment_counts=skill_assignment_counts,
    )
    app.state.files = FileService(database, settings.files)
    execution_logs = ExecutionLogs(settings.runner_lock_file.parent / "logs")
    if settings.runtime.enabled:
        cleanup.callback(execution_logs.install())
    app.state.execution_queries = ExecutionQueries(database, app.state.files, execution_logs)
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
        vectors=app.state.knowledge_vectors,
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
        web_config=settings.web,
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
    app.state.evaluation_commands = EvaluationCommands(database, runs)
    app.state.evaluation_queries = EvaluationQueries(
        database, executions=app.state.execution_queries
    )
    app.state.evaluation_progression = EvaluationProgression(database, runs)
    app.state.evaluation_worker = EvaluationWorker(app.state.evaluation_progression)
    app.state.runtime_status = worker.status
    app.state.stream_settings = settings.stream
    app.state.conversation_queries = ConversationQueries(
        database, executions=app.state.execution_queries, knowledge=app.state.knowledge_evidence
    )
    app.state.subscriptions = {}
    acceptance = ConversationAcceptance(database, runs.authorize, settings.runtime.poll_interval)
    worker.set_completion_notifier(acceptance.wake)
    app.state.conversation_acceptance = acceptance
    app.state.conversation_commands = ConversationService(
        database, settings.runtime, runs, acceptance
    )
    return acceptance, retained_files

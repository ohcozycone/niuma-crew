from functools import partial
from pathlib import Path

from app.api.rate_limit import RateLimiter
from app.auth.github import GitHubOAuth
from app.auth.service import AuthService
from app.conversations.acceptance import ConversationAcceptance
from app.conversations.files import ConversationFiles, retained_file_ids
from app.conversations.queries import ConversationQueries
from app.conversations.references import assert_employee_unused as conversation_history
from app.conversations.service import ConversationService
from app.employees.organization_rules import OrganizationRulesService
from app.employees.references import assert_model_unused as employee_model
from app.employees.references import model_employees, skill_assignment_counts, skill_assignments
from app.employees.service import AgentService
from app.employees.tool_grants import assert_connections_unused
from app.environments.service import SandboxService
from app.errors import ConflictError
from app.evaluations.commands import EvaluationCommands
from app.evaluations.progression import EvaluationProgression
from app.evaluations.queries import EvaluationQueries
from app.evaluations.references import assert_employee_unused as evaluation_history
from app.evaluations.worker import EvaluationWorker
from app.execution.assembly import build_execution
from app.execution.knowledge import KnowledgeAccess, RunKnowledgeSearch
from app.execution.knowledge_evidence import KnowledgeEvidence
from app.execution.queries import ExecutionQueries
from app.execution.references import model_in_use as execution_model
from app.execution.references import retained_file_ids as retained_run_files
from app.execution.service import active_run_ids
from app.files.cleanup import FileCleanup
from app.files.service import FileService
from app.infrastructure.credentials import CredentialVault
from app.infrastructure.database.session import Database
from app.infrastructure.observability import ExecutionLogs
from app.knowledge.documents import KnowledgeDocuments
from app.knowledge.libraries import KnowledgeLibraries
from app.knowledge.processing import KnowledgeProcessingService
from app.knowledge.references import assert_model_unused as knowledge_model
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


def check_employee_history(db, agent_id):
    evaluation_history(db, agent_id)
    conversation_history(db, agent_id)


def check_model_references(db, connection_id):
    knowledge_model(db, connection_id)
    if execution_model(db, connection_id):
        raise ConflictError("model_connection_in_use", "仍有执行使用这个大脑，请等待结束或停止。")
    employee_model(db, connection_id)


def build_services(app, settings, cleanup):
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
    app.state.evaluation_commands = EvaluationCommands(database, runs)
    app.state.evaluation_queries = EvaluationQueries(database)
    app.state.evaluation_progression = EvaluationProgression(database, runs)
    app.state.evaluation_worker = EvaluationWorker(app.state.evaluation_progression)
    app.state.runtime_status = worker.status
    app.state.stream_settings = settings.stream
    app.state.conversation_queries = ConversationQueries(database)
    app.state.subscriptions = {}
    acceptance = ConversationAcceptance(database, runs.authorize, settings.runtime.poll_interval)
    worker.set_completion_notifier(acceptance.wake)
    app.state.conversation_acceptance = acceptance
    app.state.conversation_commands = ConversationService(
        database, settings.runtime, runs, acceptance
    )
    return acceptance, retained_files

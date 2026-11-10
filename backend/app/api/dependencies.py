from __future__ import annotations

import re
from typing import Annotated

from fastapi import Depends, Request

from app.api.rate_limit import RateLimiter
from app.applications.conversations.commands import ConversationService
from app.applications.conversations.files import ConversationFiles
from app.applications.conversations.queries import ConversationQueries
from app.applications.evaluations.commands import EvaluationCommands
from app.applications.evaluations.queries import EvaluationQueries
from app.auth.actor import Actor
from app.auth.github import GitHubOAuth
from app.auth.permissions import require_permission
from app.auth.service import AuthService
from app.common.errors import PermissionDeniedError
from app.infrastructure.database.session import Database
from app.resources.employees.service import AgentService
from app.resources.environments.service import SandboxService
from app.resources.files.service import FileService
from app.resources.knowledge.documents import KnowledgeDocuments
from app.resources.knowledge.libraries import KnowledgeLibraries
from app.resources.knowledge.processing import KnowledgeProcessingService
from app.resources.knowledge.search import KnowledgeSearch
from app.resources.knowledge.vectors import KnowledgeVectorService
from app.resources.mcp.catalogs import ToolCatalogService
from app.resources.mcp.connections import ToolConnectionService
from app.resources.mcp.definitions import McpDefinitionService
from app.resources.mcp.oauth import OAuthService
from app.resources.model_connections.service import ModelConnectionService
from app.resources.organization_rules.service import OrganizationRulesService
from app.resources.skills.service import SkillService
from app.runtime.contracts.runs import ExecutionStatus


def get_database(request: Request) -> Database:
    return request.app.state.database


DatabaseDependency = Annotated[Database, Depends(get_database)]


def get_auth(request: Request) -> AuthService:
    return request.app.state.auth


AuthDependency = Annotated[AuthService, Depends(get_auth)]


def get_agents(request: Request) -> AgentService:
    return request.app.state.agents


AgentDependency = Annotated[AgentService, Depends(get_agents)]


def get_skills(request: Request) -> SkillService:
    return request.app.state.skills


SkillDependency = Annotated[SkillService, Depends(get_skills)]


def get_tool_connections(request: Request) -> ToolConnectionService:
    return request.app.state.tool_connections


ToolConnectionDependency = Annotated[ToolConnectionService, Depends(get_tool_connections)]


def get_tool_catalogs(request: Request) -> ToolCatalogService:
    return request.app.state.tool_catalogs


ToolCatalogDependency = Annotated[ToolCatalogService, Depends(get_tool_catalogs)]


def get_mcp_definitions(request: Request) -> McpDefinitionService:
    return request.app.state.mcp_definitions


McpDefinitionDependency = Annotated[McpDefinitionService, Depends(get_mcp_definitions)]


def get_tool_oauth(request: Request) -> OAuthService:
    return request.app.state.tool_oauth


OAuthDependency = Annotated[OAuthService, Depends(get_tool_oauth)]


def get_model_connections(request: Request) -> ModelConnectionService:
    return request.app.state.model_connections


ModelConnectionDependency = Annotated[ModelConnectionService, Depends(get_model_connections)]


def get_organization_rules(request: Request) -> OrganizationRulesService:
    return request.app.state.organization_rules


OrganizationRulesDependency = Annotated[OrganizationRulesService, Depends(get_organization_rules)]


def get_conversation_commands(request: Request) -> ConversationService:
    return request.app.state.conversation_commands


ConversationDependency = Annotated[ConversationService, Depends(get_conversation_commands)]


def get_conversation_queries(request: Request) -> ConversationQueries:
    return request.app.state.conversation_queries


ConversationQueriesDependency = Annotated[ConversationQueries, Depends(get_conversation_queries)]


def get_conversation_files(request: Request) -> ConversationFiles:
    return request.app.state.conversation_files


ConversationFilesDependency = Annotated[ConversationFiles, Depends(get_conversation_files)]


def get_files(request: Request) -> FileService:
    return request.app.state.files


FileDependency = Annotated[FileService, Depends(get_files)]


def get_knowledge_libraries(request: Request) -> KnowledgeLibraries:
    return request.app.state.knowledge_libraries


KnowledgeLibrariesDependency = Annotated[KnowledgeLibraries, Depends(get_knowledge_libraries)]


def get_knowledge_documents(request: Request) -> KnowledgeDocuments:
    return request.app.state.knowledge_documents


KnowledgeDocumentsDependency = Annotated[KnowledgeDocuments, Depends(get_knowledge_documents)]


def get_knowledge_processing(request: Request) -> KnowledgeProcessingService:
    return request.app.state.knowledge_processing


KnowledgeProcessingDependency = Annotated[
    KnowledgeProcessingService, Depends(get_knowledge_processing)
]


def get_knowledge_vectors(request: Request) -> KnowledgeVectorService:
    return request.app.state.knowledge_vectors


KnowledgeVectorsDependency = Annotated[KnowledgeVectorService, Depends(get_knowledge_vectors)]


def get_knowledge_search(request: Request) -> KnowledgeSearch:
    return request.app.state.knowledge_search


KnowledgeSearchDependency = Annotated[KnowledgeSearch, Depends(get_knowledge_search)]


def get_rate_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter


LimiterDependency = Annotated[RateLimiter, Depends(get_rate_limiter)]


def get_github_oauth(request: Request) -> GitHubOAuth:
    return request.app.state.github_oauth


GitHubDependency = Annotated[GitHubOAuth, Depends(get_github_oauth)]


def get_runtime_status(request: Request) -> ExecutionStatus:
    return request.app.state.runtime_status


ExecutionStatusDependency = Annotated[ExecutionStatus, Depends(get_runtime_status)]


def get_actor(request: Request, auth: AuthDependency) -> Actor:
    actor = auth.resolve(request.cookies.get("app_session"))
    # 搜索通过 POST 传问题，但不修改数据；具体检索策略还由知识服务授权。
    readonly_search = request.method == "POST" and re.fullmatch(
        r"/api/knowledge-bases/[0-9a-f-]+/search", request.url.path
    )
    if (
        actor.kind == "guest"
        and request.method not in {"GET", "HEAD", "OPTIONS"}
        and not readonly_search
    ):
        raise PermissionDeniedError("permission_denied", "游客仅可查看，不能修改数据或发起执行。")
    return actor


ActorDependency = Annotated[Actor, Depends(get_actor)]


def require_capability(permission: str):
    def check(actor: ActorDependency) -> Actor:
        require_permission(actor, permission)
        return actor

    return check


def get_evaluation_commands(request: Request) -> EvaluationCommands:
    return request.app.state.evaluation_commands


EvaluationCommandsDependency = Annotated[EvaluationCommands, Depends(get_evaluation_commands)]


def get_evaluation_queries(request: Request) -> EvaluationQueries:
    return request.app.state.evaluation_queries


EvaluationQueriesDependency = Annotated[EvaluationQueries, Depends(get_evaluation_queries)]


def get_sandboxes(request: Request) -> SandboxService:
    return request.app.state.sandboxes


SandboxDependency = Annotated[SandboxService, Depends(get_sandboxes)]

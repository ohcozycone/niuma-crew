"""Typed HTTP access to application-owned services; sessions stay inside operations."""

from typing import Annotated

from fastapi import Depends, Request

from app.agents.service import AgentService
from app.agents.tool_account_bindings import ToolAccountBindingService
from app.agents.tool_grants import ToolGrantService
from app.api.rate_limit import RateLimiter
from app.auth.actor import Actor
from app.auth.github import GitHubOAuth
from app.auth.permissions import require_permission
from app.auth.service import AuthService
from app.conversations.files import ConversationFiles
from app.conversations.queries import ConversationQueries
from app.conversations.service import ConversationService
from app.execution.contracts import ExecutionStatus
from app.files.service import FileService
from app.infrastructure.database.session import Database
from app.knowledge.service import KnowledgeService
from app.model_connections.service import ModelConnectionService
from app.organization_rules.service import OrganizationRulesService
from app.sandboxes.service import SandboxService
from app.skills.service import SkillService
from app.tools.catalogs import ToolCatalogService
from app.tools.connections import ToolConnectionService
from app.tools.definitions import McpDefinitionService


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


def get_tool_grants(request: Request) -> ToolGrantService:
    return request.app.state.tool_grants


ToolGrantDependency = Annotated[ToolGrantService, Depends(get_tool_grants)]


def get_tool_account_bindings(request: Request) -> ToolAccountBindingService:
    return request.app.state.tool_account_bindings


ToolAccountBindingDependency = Annotated[
    ToolAccountBindingService, Depends(get_tool_account_bindings)
]


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


def get_knowledge(request: Request) -> KnowledgeService:
    return request.app.state.knowledge


KnowledgeDependency = Annotated[KnowledgeService, Depends(get_knowledge)]


def get_sandboxes(request: Request) -> SandboxService:
    return request.app.state.sandboxes


SandboxDependency = Annotated[SandboxService, Depends(get_sandboxes)]


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
    return auth.resolve(request.cookies.get("app_session"))


ActorDependency = Annotated[Actor, Depends(get_actor)]


def require_capability(permission: str):
    def check(actor: ActorDependency) -> Actor:
        require_permission(actor, permission)
        return actor

    return check

"""Typed HTTP access to application-owned services; sessions stay inside operations."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.api.rate_limit import RateLimiter
from app.auth.actor import Actor
from app.auth.github import GitHubOAuth
from app.auth.permissions import require_permission
from app.auth.service import AuthService
from app.conversations.files import ConversationFiles
from app.conversations.queries import ConversationQueries
from app.conversations.service import ConversationService
from app.employees.organization_rules import OrganizationRulesService
from app.employees.service import AgentService
from app.employees.tool_account_bindings import ToolAccountBindingService
from app.environments.profiles import WorkspaceProfileService
from app.evaluations.service import EvaluationService
from app.execution.contracts import ExecutionStatus
from app.execution.queries import ExecutionQueries
from app.files.service import FileService
from app.infrastructure.database.session import Database
from app.knowledge.service import KnowledgeService
from app.mcp.catalogs import ToolCatalogService
from app.mcp.connections import ToolConnectionService
from app.mcp.definitions import McpDefinitionService
from app.mcp.oauth import OAuthService
from app.model_connections.service import ModelConnectionService
from app.skills.service import SkillService


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


def get_profiles(request: Request) -> WorkspaceProfileService:
    return request.app.state.workspace_profiles


ProfileDependency = Annotated[WorkspaceProfileService, Depends(get_profiles)]


def get_evaluations(request: Request) -> EvaluationService:
    return request.app.state.evaluations


EvaluationDependency = Annotated[EvaluationService, Depends(get_evaluations)]


def get_execution_queries(request: Request) -> ExecutionQueries:
    return request.app.state.execution_queries


ExecutionQueriesDependency = Annotated[ExecutionQueries, Depends(get_execution_queries)]

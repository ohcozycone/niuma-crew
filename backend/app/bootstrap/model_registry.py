"""应用与迁移共享的模型注册；业务代码仍从所属模块导入模型。"""

from app.applications.conversations.models import (
    Conversation,
    ConversationRun,
    Message,
    MessageFile,
)
from app.applications.evaluations.models import EvaluationBatch, EvaluationCase
from app.auth.models import AuthSession, ExternalIdentity, User
from app.infrastructure.database.base import Base
from app.infrastructure.database.identifiers import IdentifierSequence
from app.resources.employees.models import Agent, AgentKnowledgeLibrary, AgentSkill, AgentToolGrant
from app.resources.environments.legacy_models import WorkspaceProfile
from app.resources.environments.models import SandboxResource
from app.resources.files.models import StoredFile
from app.resources.knowledge.models import (
    KnowledgeBase,
    LibraryChunk,
    LibraryDocument,
    LibraryVectorIndex,
    LibraryVectorMembership,
    ProcessingBatch,
    ProcessingItem,
    VectorEmbedding,
    VectorJob,
)
from app.resources.mcp.models import McpService, ToolConnection
from app.resources.model_connections.models import ModelConnection
from app.resources.organization_rules.models import OrganizationRules
from app.resources.skills.models import Skill
from app.runtime.execution.evidence_models import RunKnowledgeEvidence
from app.runtime.execution.models import Run, RunAction

__all__ = [
    "register_models",
    "WorkspaceProfile",
    "EvaluationBatch",
    "EvaluationCase",
    "IdentifierSequence",
    "RunKnowledgeEvidence",
    "KnowledgeBase",
    "LibraryDocument",
    "LibraryChunk",
    "LibraryVectorMembership",
    "LibraryVectorIndex",
    "ProcessingBatch",
    "ProcessingItem",
    "VectorEmbedding",
    "VectorJob",
    "Conversation",
    "Run",
    "RunAction",
    "Message",
    "ConversationRun",
    "Base",
    "Agent",
    "AgentSkill",
    "Skill",
    "User",
    "AuthSession",
    "ExternalIdentity",
    "ModelConnection",
    "OrganizationRules",
    "AgentToolGrant",
    "ToolConnection",
    "McpService",
    "AgentKnowledgeLibrary",
    "StoredFile",
    "MessageFile",
    "SandboxResource",
]


def register_models() -> None:
    """每个应用进程独立完成映射注册，包括历史多态记录。"""
    Base.registry.configure()

"""Register all persistent models for migrations and database tooling."""

from app.auth.models import AuthSession, ExternalIdentity, User
from app.conversations.models import Conversation, ConversationRun, Message, MessageFile
from app.employees.models import (
    Agent,
    AgentSkill,
    AgentToolGrant,
    OrganizationRules,
    PersonalToolBinding,
)
from app.environments.models import SandboxResource
from app.evaluations.models import EvaluationBatch, EvaluationCase
from app.execution.models import Run, RunAction
from app.files.models import StoredFile
from app.infrastructure.database.base import Base
from app.infrastructure.database.identifiers import IdentifierSequence
from app.knowledge.models import (
    EmployeeKnowledgeLibrary,
    EmployeeKnowledgeSettings,
    KnowledgeBase,
    LibraryChunk,
    LibraryDocument,
    LibraryVectorIndex,
    LibraryVectorMembership,
    ProcessingBatch,
    ProcessingItem,
    RunKnowledgeEvidence,
)
from app.mcp.models import McpService, ToolConnection
from app.model_connections.models import ModelConnection
from app.skills.models import Skill

__all__ = [
    "EvaluationBatch",
    "EvaluationCase",
    "IdentifierSequence",
    "EmployeeKnowledgeSettings",
    "EmployeeKnowledgeLibrary",
    "RunKnowledgeEvidence",
    "KnowledgeBase",
    "LibraryDocument",
    "LibraryChunk",
    "LibraryVectorMembership",
    "LibraryVectorIndex",
    "ProcessingBatch",
    "ProcessingItem",
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
    "PersonalToolBinding",
    "StoredFile",
    "MessageFile",
    "SandboxResource",
]

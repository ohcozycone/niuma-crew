"""Register all persistent models for migrations and database tooling."""

from app.agents.models import Agent, AgentSkill, AgentToolGrant, PersonalToolBinding
from app.auth.models import AuthSession, ExternalIdentity, User
from app.conversations.models import Conversation, ConversationRun, Message, MessageFile
from app.execution.models import Run, RunAction
from app.files.models import StoredFile
from app.infrastructure.database.base import Base
from app.knowledge.models import (
    EmployeeKnowledgeLibrary,
    EmployeeKnowledgeSettings,
    KnowledgeBase,
    LibraryChunk,
    LibraryDocument,
    LibraryVector,
    LibraryVectorIndex,
    ProcessingBatch,
    ProcessingItem,
    RunKnowledgeEvidence,
)
from app.model_connections.models import ModelConnection
from app.organization_rules.models import OrganizationRules
from app.sandboxes.models import SandboxResource
from app.skills.models import Skill
from app.tools.models import McpService, ToolConnection

__all__ = [
    "EmployeeKnowledgeSettings",
    "EmployeeKnowledgeLibrary",
    "RunKnowledgeEvidence",
    "KnowledgeBase",
    "LibraryDocument",
    "LibraryChunk",
    "LibraryVector",
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

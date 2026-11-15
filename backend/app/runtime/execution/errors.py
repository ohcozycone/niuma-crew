from app.common.errors import (
    AGENT_ERROR_KINDS,
    CodedFailure,
    FailureKind,
    ServiceError,
    failure_code,
    service_failure_kind,
)

EXECUTION_ERROR_KINDS = {
    **AGENT_ERROR_KINDS,
    "knowledge_access_revoked": FailureKind.AUTHORIZATION,
    "knowledge_owner_mismatch": FailureKind.AUTHORIZATION,
    "skill_access_revoked": FailureKind.AUTHORIZATION,
    "tool_access_revoked": FailureKind.AUTHORIZATION,
    "web_access_revoked": FailureKind.AUTHORIZATION,
    "web_not_configured": FailureKind.CONFIGURATION,
    "file_path_denied": FailureKind.AUTHORIZATION,
    "file_readonly": FailureKind.AUTHORIZATION,
    "actor_session_invalid": FailureKind.AUTHORIZATION,
    "workspace_tools_invalid": FailureKind.CONFIGURATION,
    "tool_scope_invalid": FailureKind.CONFIGURATION,
    "skill_not_ready": FailureKind.CONFIGURATION,
    "tool_credentials_unavailable": FailureKind.CONFIGURATION,
    "sandbox_not_ready": FailureKind.CONFIGURATION,
    "sandbox_configuration_changed": FailureKind.CONFIGURATION,
    "sandbox_materialization_failed": FailureKind.DEPENDENCY,
    "agent_inactive": FailureKind.CONFIGURATION,
    "model_credentials_unavailable": FailureKind.CONFIGURATION,
    "model_configuration_changed": FailureKind.CONFIGURATION,
    "skill_file_not_found": FailureKind.CONFIGURATION,
    "knowledge_citation_invalid": FailureKind.VALIDATION,
    "knowledge_evidence_not_found": FailureKind.VALIDATION,
    "file_too_large": FailureKind.VALIDATION,
    "tool_result_too_large": FailureKind.VALIDATION,
    "input_required": FailureKind.VALIDATION,
    "input_too_large": FailureKind.VALIDATION,
    "knowledge_source_changed": FailureKind.CONFLICT,
    "execution_host_locked": FailureKind.CONFLICT,
    "idempotency_conflict": FailureKind.CONFLICT,
    "retry_not_allowed": FailureKind.CONFLICT,
    "file_quota_exceeded": FailureKind.LIMIT,
    "tool_candidate_count_exceeded": FailureKind.LIMIT,
    "tool_candidate_bytes_exceeded": FailureKind.LIMIT,
    "sandbox_capacity_exceeded": FailureKind.LIMIT,
    "queue_timeout": FailureKind.LIMIT,
    "run_timeout": FailureKind.LIMIT,
    "command_failed": FailureKind.OPERATION,
    "knowledge_search_failed": FailureKind.DEPENDENCY,
    "run_capacity_exceeded": FailureKind.LIMIT,
    "tool_upstream_failed": FailureKind.DEPENDENCY,
    "tool_result_unknown": FailureKind.DEPENDENCY,
    "runtime_unavailable": FailureKind.DEPENDENCY,
    "tool_auth_required": FailureKind.CONFIGURATION,
    "skill_materialization_failed": FailureKind.DEPENDENCY,
    "file_integrity_failed": FailureKind.STORAGE,
    "sandbox_stop_failed": FailureKind.STORAGE,
    "output_collection_failed": FailureKind.STORAGE,
    "persistence_unavailable": FailureKind.STORAGE,
    "user_cancelled": FailureKind.CANCELLED,
    "execution_failed": FailureKind.INTERNAL,
    "run_not_found": FailureKind.NOT_FOUND,
    "action_not_found": FailureKind.NOT_FOUND,
    "evidence_not_found": FailureKind.NOT_FOUND,
    "model_not_configured": FailureKind.CONFLICT,
    "file_tool_required": FailureKind.VALIDATION,
    "knowledge_unavailable": FailureKind.CONFLICT,
}


class ExecutionFailure(CodedFailure):
    def __init__(
        self, code: str, partial_text: str | None = None, *, kind: FailureKind | None = None
    ) -> None:
        super().__init__(code, kind or failure_kind(code) or FailureKind.INTERNAL, partial_text)


class PersistenceFailure(CodedFailure):
    """成果事务回滚后必须停止后续动作。"""

    def __init__(self) -> None:
        super().__init__("persistence_unavailable", FailureKind.STORAGE)


def failure_kind(code: str | None) -> FailureKind | None:
    return EXECUTION_ERROR_KINDS.get(code) if code else None


def execution_failure(error: Exception) -> CodedFailure:
    if isinstance(error, TimeoutError):
        return ExecutionFailure("run_timeout")
    code = failure_code(error)
    if isinstance(error, CodedFailure) and code == error.code:
        return error
    if isinstance(error, ServiceError) and code == error.code:
        return ExecutionFailure(code, kind=failure_kind(code) or service_failure_kind(error))
    return ExecutionFailure("execution_failed")


def terminal_status(code: str) -> str:
    if code in ("user_cancelled", "actor_session_invalid"):
        return "cancelled"
    if code in ("runtime_interrupted", "checkpoint_unavailable"):
        return "interrupted"
    return "failed"

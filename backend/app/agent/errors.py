from app.errors import CodedFailure, FailureKind

AGENT_ERROR_KINDS = {
    "tool_arguments_invalid": FailureKind.VALIDATION,
    "tool_not_allowed": FailureKind.AUTHORIZATION,
    "skill_not_allowed": FailureKind.AUTHORIZATION,
    "tool_catalog_changed": FailureKind.CONFIGURATION,
    "agent_budget_exceeded": FailureKind.LIMIT,
    "context_limit_exceeded": FailureKind.LIMIT,
    "output_limit_exceeded": FailureKind.LIMIT,
    "upstream_auth_failed": FailureKind.DEPENDENCY,
    "upstream_forbidden": FailureKind.DEPENDENCY,
    "upstream_rate_limited": FailureKind.DEPENDENCY,
    "upstream_unavailable": FailureKind.DEPENDENCY,
    "upstream_stream_error": FailureKind.DEPENDENCY,
    "upstream_timeout": FailureKind.DEPENDENCY,
    "empty_response": FailureKind.DEPENDENCY,
    "skill_load_failed": FailureKind.DEPENDENCY,
    "runtime_interrupted": FailureKind.INTERRUPTED,
    "checkpoint_unavailable": FailureKind.INTERRUPTED,
    "sdk_stream_invalid": FailureKind.INTERNAL,
}


class RuntimeFailure(CodedFailure):
    def __init__(self, code: str, partial_text: str | None = None) -> None:
        super().__init__(code, AGENT_ERROR_KINDS.get(code, FailureKind.INTERNAL), partial_text)

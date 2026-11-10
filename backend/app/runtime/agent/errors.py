from app.common.errors import AGENT_ERROR_KINDS, CodedFailure, FailureKind


class RuntimeFailure(CodedFailure):
    def __init__(self, code: str, partial_text: str | None = None) -> None:
        super().__init__(code, AGENT_ERROR_KINDS.get(code, FailureKind.INTERNAL), partial_text)

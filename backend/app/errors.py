import re
from enum import StrEnum


class FailureKind(StrEnum):
    VALIDATION = "validation"
    AUTHORIZATION = "authorization"
    CONFIGURATION = "configuration"
    CONFLICT = "conflict"
    NOT_FOUND = "not_found"
    LIMIT = "limit"
    DEPENDENCY = "dependency"
    OPERATION = "operation"
    STORAGE = "storage"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"
    INTERNAL = "internal"


class CodedFailure(Exception):
    def __init__(
        self,
        code: str,
        kind: FailureKind = FailureKind.INTERNAL,
        partial_text: str | None = None,
    ) -> None:
        self.code, self.kind, self.partial_text = code, kind, partial_text
        super().__init__(code)


class ServiceError(Exception):
    """code 供程序识别，message 可省略，由应用出口映射；retry_after 是建议等待秒数。"""

    def __init__(self, code: str, message: str = "", *, retry_after: int | None = None):
        super().__init__(message or code)
        self.code = code
        self.message = message
        self.retry_after = retry_after


class AuthenticationError(ServiceError):
    """未能确认有效身份，例如凭据错误或登录会话失效。"""


class PermissionDeniedError(ServiceError):
    """身份已确认，但当前操作不在许可范围内。"""


class NotFoundError(ServiceError):
    """资源不存在或不可见；不向调用方区分这两种情况。"""


class ConflictError(ServiceError):
    """输入可以成立，但资源当前状态不允许该操作。"""


class InvalidInputError(ServiceError):
    """输入内容、大小或参数组合不符合要求。"""


class RateLimitError(ServiceError):
    """请求频率或可同时接受的执行数量达到上限。"""


class ServiceUnavailableError(ServiceError):
    """本服务或必要依赖当前无法提供能力；重试前可能需要修复配置。"""


def failure_code(error: BaseException) -> str:
    # 只接受受控异常的短代码，避免上游任意字段冒充平台失败。
    code = error.code if isinstance(error, (CodedFailure, ServiceError)) else None
    return (
        code
        if isinstance(code, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,79}", code)
        else "execution_failed"
    )


def service_failure_kind(error: ServiceError) -> FailureKind:
    kinds = {
        AuthenticationError: FailureKind.AUTHORIZATION,
        PermissionDeniedError: FailureKind.AUTHORIZATION,
        NotFoundError: FailureKind.NOT_FOUND,
        ConflictError: FailureKind.CONFLICT,
        InvalidInputError: FailureKind.VALIDATION,
        RateLimitError: FailureKind.LIMIT,
        ServiceUnavailableError: FailureKind.DEPENDENCY,
    }
    return next((kinds[cls] for cls in type(error).__mro__ if cls in kinds), FailureKind.INTERNAL)

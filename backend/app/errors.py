"""应用错误只表达失败含义；HTTP 状态与响应格式由 API 层决定。"""


class ServiceError(Exception):
    """code 供程序识别，message 是可公开说明；retry_after 是建议等待秒数。"""

    def __init__(self, code: str, message: str, *, retry_after: int | None = None):
        super().__init__(message)
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

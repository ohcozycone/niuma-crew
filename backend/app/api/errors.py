"""Translate service and SQLite contention errors without exposing SQL or parameters."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError

from app.errors import (
    AuthenticationError,
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServiceError,
    ServiceUnavailableError,
)
from app.infrastructure.database.errors import is_database_busy


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    detail: ErrorDetail


class ValidationIssue(BaseModel):
    type: str
    loc: list[str | int]
    msg: str


class InputErrorResponse(BaseModel):
    # 语义校验有业务错误码，字段校验保留定位列表；两者都不回显原始输入。
    detail: ErrorDetail | list[ValidationIssue]


SERVICE_ERROR_RESPONSES = {
    401: {"model": ErrorResponse, "description": "需要有效登录或游客会话"},
    403: {"model": ErrorResponse, "description": "无操作权限或请求来源无效"},
    404: {"model": ErrorResponse, "description": "资源不存在或不可见"},
    409: {"model": ErrorResponse, "description": "资源当前状态不允许操作或配置修订冲突"},
    422: {"model": InputErrorResponse, "description": "输入内容、字段或参数组合不合法"},
    429: {"model": ErrorResponse, "description": "请求频率或执行容量达到上限"},
    500: {"model": ErrorResponse, "description": "未预期的服务器错误，提供安全说明和请求关联 ID"},
    503: {"model": ErrorResponse, "description": "服务或依赖暂不可用，可能提供 Retry-After"},
}


SERVICE_ERROR_STATUS_CODES = {
    AuthenticationError: 401,
    PermissionDeniedError: 403,
    NotFoundError: 404,
    ConflictError: 409,
    InvalidInputError: 422,
    RateLimitError: 429,
    ServiceUnavailableError: 503,
}


def service_error_response(error: ServiceError) -> JSONResponse:
    """沿 MRO 继承最近的已知分类；未知类型不能伪装成业务拒绝。"""
    status = next(
        (
            SERVICE_ERROR_STATUS_CODES[cls]
            for cls in type(error).__mro__
            if cls in SERVICE_ERROR_STATUS_CODES
        ),
        None,
    )
    if status is None:
        raise TypeError("Unclassified service error")
    headers = {"Retry-After": str(error.retry_after)} if error.retry_after is not None else {}
    return JSONResponse(
        status_code=status,
        headers=headers,
        content={"detail": {"code": error.code, "message": error.message}},
    )


def register_error_handlers(app: FastAPI) -> None:
    async def service_error(request: Request, error: ServiceError) -> JSONResponse:
        return service_error_response(error)

    for error_type in SERVICE_ERROR_STATUS_CODES:
        app.add_exception_handler(error_type, service_error)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        # Pydantic inputs/context can include passwords, even when an unrelated field failed.
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {key: value for key, value in item.items() if key in {"type", "loc", "msg"}}
                    for item in error.errors()
                ]
            },
        )

    @app.exception_handler(OperationalError)
    async def database_error(request: Request, error: OperationalError) -> JSONResponse:
        if is_database_busy(error):
            return service_error_response(
                ServiceUnavailableError("database_busy", "数据库暂时繁忙，请重试。", retry_after=1)
            )
        raise error

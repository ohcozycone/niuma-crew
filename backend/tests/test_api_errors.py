"""Verify application failure categories at HTTP and identity-check boundaries."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.errors import SERVICE_ERROR_RESPONSES, InputErrorResponse, register_error_handlers
from app.auth.models import AuthSession
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
from app.execution.errors import ExecutionFailure
from app.schemas import NonBlankText, RequestModel


@pytest.mark.parametrize("specialized", [False, True])
@pytest.mark.parametrize(
    "error,status,wait",
    [
        (AuthenticationError("session_expired", "请重新登录。"), 401, None),
        (PermissionDeniedError("permission_denied", "无权操作。"), 403, None),
        (NotFoundError("agent_not_found", "员工不存在。"), 404, None),
        (ConflictError("conversation_busy", "对话正在执行。"), 409, None),
        (InvalidInputError("input_too_large", "消息过长。"), 422, None),
        (RateLimitError("run_capacity_exceeded", "名额已满。", retry_after=2), 429, "2"),
        (ServiceUnavailableError("runtime_unavailable", "暂不可用。", retry_after=1), 503, "1"),
    ],
)
def test_application_errors_have_stable_http_shape_and_safe_details(
    error, status, wait, specialized
):
    if specialized:
        subclass = type("SpecializedError", (type(error),), {})
        error = subclass(error.code, error.message, retry_after=error.retry_after)
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/failure")
    def fail():
        raise error from RuntimeError("private-credential-and-sql")

    with TestClient(app) as client:
        response = client.get("/failure")
    assert response.status_code == status
    assert response.json() == {"detail": {"code": error.code, "message": error.message}}
    assert response.headers.get("Retry-After") == wait
    assert "private-credential-and-sql" not in response.text


@pytest.mark.parametrize(
    "error", [RuntimeError("private-defect"), ServiceError("unknown", "private")]
)
def test_unclassified_failures_remain_server_errors(error):
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/failure")
    def fail():
        raise error

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/failure")
    assert response.status_code == 500
    assert "private" not in response.text


def test_input_error_contract_covers_semantic_and_redacted_field_errors():
    app = FastAPI()
    register_error_handlers(app)

    class Input(RequestModel):
        password: NonBlankText

    @app.post("/input", responses=SERVICE_ERROR_RESPONSES)
    def submit(data: Input):
        raise InvalidInputError("invalid_combination", "参数组合不合法。")

    with TestClient(app) as client:
        semantic = client.post("/input", json={"password": "private-password"})
        fields = client.post("/input", json={"password": "private-password", "extra": "private"})
        for response in (semantic, fields):
            assert response.status_code == 422
            InputErrorResponse.model_validate(response.json())
            assert "private" not in response.text
        assert set(fields.json()["detail"][0]) == {"type", "loc", "msg"}
        schema = client.get("/openapi.json").json()["components"]["schemas"]
        assert len(schema["InputErrorResponse"]["properties"]["detail"]["anyOf"]) == 2


def test_guest_fallback_does_not_issue_a_session_on_service_failure(api_client, monkeypatch):
    auth = api_client.app.state.auth
    with auth.database.transaction() as db:
        before = db.scalar(select(func.count()).select_from(AuthSession))

    def unavailable(_):
        raise ServiceUnavailableError("identity_unavailable", "身份服务暂不可用。")

    monkeypatch.setattr(auth, "resolve", unavailable)
    response = api_client.post("/api/auth/guest", json={})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "identity_unavailable"
    with auth.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(AuthSession)) == before


@pytest.mark.parametrize("consumer", ["execution", "publication"])
@pytest.mark.parametrize("failure", ["authentication", "permission", "dependency"])
def test_identity_rechecks_only_convert_lost_authorization(
    api_client, monkeypatch, consumer, failure
):
    state = api_client.app.state
    actor = state.auth.resolve(api_client.cookies.get("app_session"))

    def resolve(*_):
        if failure == "authentication":
            raise AuthenticationError("session_expired", "登录已失效。")
        if failure == "permission":
            raise PermissionDeniedError("permission_denied", "身份权限已失效。")
        raise ServiceUnavailableError("identity_unavailable", "身份服务暂不可用。")

    monkeypatch.setattr("app.execution.service.authorize_work", resolve)

    def recheck():
        if consumer == "execution":
            state.runs.authorize(
                SimpleNamespace(
                    initiated_by_user_id=actor.user_id, initiated_by_session_id=actor.session_id
                )
            )
        else:
            state.runs.authorize(
                SimpleNamespace(
                    initiated_by_user_id=actor.user_id, initiated_by_session_id=actor.session_id
                )
            )

    if failure == "dependency":
        with pytest.raises(ServiceUnavailableError) as raised:
            recheck()
        assert raised.value.code == "identity_unavailable"
    else:
        with pytest.raises(ExecutionFailure) as raised:
            recheck()
        assert raised.value.code == "actor_session_invalid"

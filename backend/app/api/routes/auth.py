"""Cookie transport and public identity responses."""

from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, StringConstraints
from sqlalchemy.exc import OperationalError

from app.api.dependencies import (
    ActorDependency,
    AuthDependency,
    GitHubDependency,
    LimiterDependency,
)
from app.auth.actor import Actor
from app.auth.config import normalize_origin
from app.auth.github import OAUTH_COOKIE, OAUTH_COOKIE_PATH, OAUTH_TTL
from app.auth.permissions import permissions_for
from app.errors import InvalidInputError, ServiceError
from app.schemas import RequestModel

COOKIE_NAME = "app_session"
router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(RequestModel):
    username: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=64)]
    password: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=128)]


class EmptyRequest(RequestModel):
    pass


class GitHubLoginRequest(RequestModel):
    next: Annotated[str, StringConstraints(strict=True, max_length=2048)] = "/"


class GitHubAuthorization(BaseModel):
    authorization_url: str


class ProviderStatus(BaseModel):
    enabled: bool


class AuthProviders(BaseModel):
    github: ProviderStatus


class UserIdentity(BaseModel):
    id: str
    username: str


class ActorIdentity(BaseModel):
    kind: Literal["user", "guest"]
    user: UserIdentity | None


class IdentityResponse(BaseModel):
    actor: ActorIdentity
    permissions: list[str]
    expires_at: datetime


def identity(actor: Actor) -> IdentityResponse:
    return IdentityResponse(
        actor=ActorIdentity(
            kind=actor.kind,
            user=UserIdentity(id=actor.user_id, username=actor.username) if actor.user_id else None,
        ),
        permissions=sorted(permissions_for(actor)),
        expires_at=actor.expires_at,
    )


def write_cookie(response: Response, token: str, actor: Actor, auth) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=max(1, int((actor.expires_at - auth.clock()).total_seconds())),
        httponly=True,
        secure=auth.config.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.get("/providers", response_model=AuthProviders)
def providers(github: GitHubDependency):
    return AuthProviders(github=ProviderStatus(enabled=github.config.enabled))


@router.post("/github", response_model=GitHubAuthorization)
def github_start(
    data: GitHubLoginRequest,
    request: Request,
    response: Response,
    auth: AuthDependency,
    github: GitHubDependency,
    limiter: LimiterDependency,
):
    source = request.client.host if request.client else "unknown"
    limiter.consume(f"github:source:{source}", 20, 60)
    if github.config.enabled:
        callback = urlsplit(github.config.callback_url)
        if normalize_origin(request.headers.get("origin", "")) != normalize_origin(
            f"{callback.scheme}://{callback.netloc}"
        ):
            raise InvalidInputError(
                "github_origin_mismatch", "请从 GitHub 回调配置的站点地址登录。"
            )
    url, cookie = github.start(data.next)
    response.set_cookie(
        OAUTH_COOKIE,
        cookie,
        max_age=OAUTH_TTL,
        httponly=True,
        secure=auth.config.cookie_secure,
        samesite="lax",
        path=OAUTH_COOKIE_PATH,
    )
    return GitHubAuthorization(authorization_url=url)


@router.get("/github/callback", include_in_schema=False)
def github_callback(
    request: Request, auth: AuthDependency, github: GitHubDependency, limiter: LimiterDependency
):
    next_path = "/"
    actor = token = None
    try:
        source = request.client.host if request.client else "unknown"
        limiter.consume(f"github:callback:{source}", 40, 60)
        context = github.context(
            request.cookies.get(OAUTH_COOKIE), request.query_params.get("state")
        )
        next_path = context["next"]
        if request.query_params.get("error"):
            raise InvalidInputError("github_cancelled", "GitHub 登录未完成。")
        subject, username = github.identity(
            request.query_params.get("code", ""), context["verifier"]
        )
        actor, token = auth.github_login(subject, username, request.cookies.get(COOKIE_NAME))
        response = RedirectResponse(next_path, status_code=303)
    except ServiceError as error:
        # OAuth 用跳转报告已知失败，并继续清理临时 Cookie；代码缺陷不进入此分支。
        response = RedirectResponse(
            "/signin?" + urlencode({"auth_error": error.code, "next": next_path}), status_code=303
        )
        if error.retry_after:
            response.headers["Retry-After"] = str(error.retry_after)
    except OperationalError:
        response = RedirectResponse(
            "/signin?" + urlencode({"auth_error": "github_failed", "next": next_path}),
            status_code=303,
        )
    response.delete_cookie(
        OAUTH_COOKIE,
        path=OAUTH_COOKIE_PATH,
        secure=auth.config.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    if actor is not None and token is not None:
        write_cookie(response, token, actor, auth)
    return response


@router.post("/login", response_model=IdentityResponse)
def login(
    data: LoginRequest,
    request: Request,
    response: Response,
    auth: AuthDependency,
    limiter: LimiterDependency,
):
    # Uvicorn forwarding trust is disabled in the supplied run command; never read XFF here.
    source = request.client.host if request.client else "unknown"
    limiter.consume(f"login:source:{source}", 20, 60)
    limiter.consume(f"login:user:{data.username.strip().lower()}", 10, 900)
    actor, token = auth.login(data.username, data.password, request.cookies.get(COOKIE_NAME))
    write_cookie(response, token, actor, auth)
    return identity(actor)


@router.post("/logout", status_code=204)
def logout(data: EmptyRequest, request: Request, auth: AuthDependency):
    auth.logout(request.cookies.get(COOKIE_NAME))
    response = Response(status_code=204)
    response.delete_cookie(
        COOKIE_NAME, path="/", secure=auth.config.cookie_secure, httponly=True, samesite="lax"
    )
    return response


@router.post("/guest", response_model=IdentityResponse)
def guest(
    data: EmptyRequest,
    request: Request,
    response: Response,
    auth: AuthDependency,
    limiter: LimiterDependency,
):
    source = request.client.host if request.client else "unknown"
    limiter.consume(f"guest:{source}", 20, 60)
    actor, token = auth.guest(request.cookies.get(COOKIE_NAME))
    if token:
        write_cookie(response, token, actor, auth)
    return identity(actor)


@router.get("/me", response_model=IdentityResponse)
def me(actor: ActorDependency):
    return identity(actor)

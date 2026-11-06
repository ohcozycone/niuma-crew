"""User-owned tool authorization; callback codes never enter frontend state."""

from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import Field, StrictInt

from app.api.dependencies import ActorDependency, AuthDependency, OAuthDependency
from app.errors import ServiceError
from app.schemas import RequestModel

router = APIRouter(tags=["tools"])


class OAuthStart(RequestModel):
    expected_config_revision: StrictInt = Field(gt=0)
    expected_credential_revision: StrictInt = Field(gt=0)


@router.post("/api/tool-connections/{id}/oauth/sessions", status_code=202)
async def start(
    id: UUID, data: OAuthStart, request: Request, actor: ActorDependency, oauth: OAuthDependency
):
    return await oauth.start(
        actor,
        str(id),
        data.expected_config_revision,
        data.expected_credential_revision,
        request.headers.get("origin", ""),
    )


@router.get("/api/tool-connections/{id}/oauth/sessions/{session_id}")
async def status(id: UUID, session_id: UUID, actor: ActorDependency, oauth: OAuthDependency):
    return (await oauth.session(actor, str(id), str(session_id))).read()


@router.delete("/api/tool-connections/{id}/oauth/sessions/{session_id}", status_code=204)
async def cancel(id: UUID, session_id: UUID, actor: ActorDependency, oauth: OAuthDependency):
    await oauth.cancel(actor, str(id), str(session_id))
    return Response(status_code=204)


@router.post("/api/tool-connections/{id}/oauth/disconnect")
async def disconnect(id: UUID, data: OAuthStart, actor: ActorDependency, oauth: OAuthDependency):
    return await oauth.disconnect(
        actor, str(id), data.expected_config_revision, data.expected_credential_revision
    )


@router.get("/api/tool-connections/oauth/callback", include_in_schema=False)
async def callback(request: Request, auth: AuthDependency, oauth: OAuthDependency):
    import asyncio

    try:
        actor = await asyncio.to_thread(auth.resolve, request.cookies.get("app_session"))
        session, service_id = await oauth.callback(
            actor,
            state=request.query_params.get("state"),
            code=request.query_params.get("code"),
            issuer=request.query_params.get("iss"),
            error=request.query_params.get("error"),
        )

        # The returned page polls an opaque handle; code/state stay on this route.
        params = {
            "service": service_id,
            "oauth_connection": session.connection_id,
            "oauth_session": session.id,
        }
    except ServiceError as error:
        params = {"oauth_error": error.code}
    return RedirectResponse(
        "/tools?" + urlencode(params),
        status_code=303,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )

import time

from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from app.resources.mcp.tokens import OAuthTokenStore


class OAuthStorage:
    def __init__(self, connections, row, **options):
        self.tokens = OAuthTokenStore(connections, row, **options)

    @property
    def payload(self):
        return self.tokens.payload

    @property
    def row(self):
        return self.tokens.row

    async def observe(self, url, data):
        await self.tokens.observe(url, data)

    async def invalidate(self, *, status="reauth_required", clear_catalog=False):
        await self.tokens.invalidate(status=status, clear_catalog=clear_catalog)

    async def get_tokens(self) -> OAuthToken | None:
        data = self.tokens.payload.get("tokens")
        return OAuthToken.model_validate(data) if data else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self.tokens.payload["tokens"] = tokens.model_dump(mode="json", exclude_none=True)
        self.tokens.payload["expires_at"] = (
            time.time() + tokens.expires_in if tokens.expires_in is not None else None
        )
        await self.tokens.save(connected=True)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        data = self.tokens.payload.get("client_info")
        if data:
            return OAuthClientInformationFull.model_validate(data)
        client_id = self.tokens.row.public_config.get("oauth", {}).get("client_id")
        if not client_id:
            return None
        return OAuthClientInformationFull(
            client_id=client_id,
            client_secret=self.tokens.payload.get("client_secret"),
            redirect_uris=[self.tokens.payload["callback_url"]],
            token_endpoint_auth_method="client_secret_post"
            if self.tokens.payload.get("client_secret")
            else "none",
        )

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self.tokens.payload["client_info"] = client_info.model_dump(mode="json", exclude_none=True)
        await self.tokens.save()

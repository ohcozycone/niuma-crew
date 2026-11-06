"""Persist the public SDK's OAuth storage with grant and write-version checks."""

from __future__ import annotations

import asyncio
import json
import time

from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from app.errors import ConflictError, InvalidInputError
from app.mcp.connections import require_connection
from app.mcp.models import McpService


class OAuthStorage:
    def __init__(
        self,
        connections,
        row,
        *,
        callback_url,
        interactive=False,
        allow_callback_change=False,
        active=lambda: True,
        validate=lambda db: None,
    ):
        self.connections, self.row = connections, row
        self.interactive, self.active = interactive, active
        self.validate = validate
        try:
            self.payload = (
                json.loads(connections._decrypt(row))
                if row.encrypted_credentials
                else {"version": 1}
            )
        except (ValueError, TypeError):
            raise InvalidInputError(
                "tool_auth_required", "OAuth 凭据格式无效，请重新配置账号。"
            ) from None
        if not isinstance(self.payload, dict) or self.payload.get("version") != 1:
            raise InvalidInputError("tool_auth_required", "OAuth 凭据格式无效，请重新连接。")
        if self.payload.get("callback_url", callback_url) != callback_url:
            if not allow_callback_change:
                raise InvalidInputError(
                    "tool_auth_required", "OAuth 回调配置已改变，请重新连接账号。"
                )
            for key in ("client_info", "metadata"):
                self.payload.pop(key, None)
        self.payload["callback_url"] = callback_url

    def checked(self, db, *, require_enabled=True):
        self.validate(db)
        row = require_connection(db, self.row.id)
        service = db.get(McpService, row.service_id) if row.service_id else None
        if (
            not self.active()
            or (require_enabled and not row.enabled)
            or row.auth_type != "oauth"
            or (require_enabled and service and not service.enabled)
            or (row.config_revision, row.credential_revision, row.oauth_storage_revision)
            != (
                self.row.config_revision,
                self.row.credential_revision,
                self.row.oauth_storage_revision,
            )
        ):
            raise ConflictError("tool_connection_changed", "OAuth 连接已改变，请刷新后重新连接。")
        return row

    async def save(self, *, connected=False):
        payload = dict(self.payload)
        encrypted = await asyncio.to_thread(self.connections.encrypt_oauth, payload)

        def write():
            from app.infrastructure.database.transactions import reserve_writer
            from app.mcp.models import ToolConnection

            with self.connections.database.transaction() as db:
                reserve_writer(db, ToolConnection.__table__)
                row = self.checked(db)
                row.encrypted_credentials = encrypted
                row.oauth_storage_revision += 1
                if connected:
                    if self.interactive:
                        row.credential_revision += 1
                    row.oauth_status = "connected"
                db.flush()
                return row

        commit = asyncio.create_task(asyncio.to_thread(write))
        try:
            self.row = await asyncio.shield(commit)
        except asyncio.CancelledError:
            # Cancelling to_thread cannot stop SQLite. Join its final result so
            # the cancelling owner can invalidate a grant that already committed.
            self.row = await commit
            raise

    async def get_tokens(self) -> OAuthToken | None:
        data = self.payload.get("tokens")
        return OAuthToken.model_validate(data) if data else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self.payload["tokens"] = tokens.model_dump(mode="json", exclude_none=True)
        self.payload["expires_at"] = (
            time.time() + tokens.expires_in if tokens.expires_in is not None else None
        )
        await self.save(connected=True)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        data = self.payload.get("client_info")
        if data:
            return OAuthClientInformationFull.model_validate(data)
        client_id = self.row.public_config.get("oauth", {}).get("client_id")
        if not client_id:
            return None
        return OAuthClientInformationFull(
            client_id=client_id,
            client_secret=self.payload.get("client_secret"),
            redirect_uris=[self.payload["callback_url"]],
            token_endpoint_auth_method="client_secret_post"
            if self.payload.get("client_secret")
            else "none",
        )

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self.payload["client_info"] = client_info.model_dump(mode="json", exclude_none=True)
        await self.save()

    async def observe(self, url: str, data: dict) -> None:
        if isinstance(data, dict) and data.get("issuer") and data.get("token_endpoint"):
            previous = self.payload.get("metadata", {}).get("issuer")
            if previous and previous.rstrip("/") != str(data["issuer"]).rstrip("/"):
                raise InvalidInputError(
                    "tool_auth_required", "OAuth 授权服务器已改变，请重新配置账号。"
                )
            self.payload["metadata"] = {key: data[key] for key in ("issuer", "token_endpoint")}

    async def invalidate(self, *, status="reauth_required", clear_catalog=False) -> None:
        self.payload.pop("tokens", None)
        self.payload.pop("expires_at", None)
        encrypted = await asyncio.to_thread(self.connections.encrypt_oauth, self.payload)

        def write():
            from app.infrastructure.database.transactions import reserve_writer
            from app.mcp.models import ToolConnection

            with self.connections.database.transaction() as db:
                reserve_writer(db, ToolConnection.__table__)
                row = self.checked(db, require_enabled=False)
                row.encrypted_credentials = encrypted
                row.oauth_status = status
                row.credential_revision += 1
                row.oauth_storage_revision += 1
                row.discovery_candidate = None
                if clear_catalog:
                    row.approved_catalog = []
                    row.approved_instructions = ""
                    row.catalog_revision += 1
                db.flush()
                return row

        self.row = await asyncio.to_thread(write)

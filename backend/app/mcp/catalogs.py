"""Discover, confirm and annotate connection tool catalogs without invoking business tools."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta

from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.errors import ConflictError, InvalidInputError, ServiceUnavailableError
from app.infrastructure.database.transactions import reserve_writer
from app.mcp.access import own_connection
from app.mcp.adapters.stdio import StdioMCPClient
from app.mcp.connections import connection_read, require_connection
from app.mcp.models import ToolConnection
from app.values import digest, utc_now


def save_candidate(connections, row, catalog, instructions=""):
    """Save a transport-discovered candidate after rechecking its captured revisions."""
    encoded = json.dumps({"tools": catalog, "instructions": instructions}, ensure_ascii=False)
    if len(encoded.encode()) > connections.config.max_catalog_bytes:
        raise InvalidInputError(
            "tool_catalog_too_large",
            f"工具目录及服务说明超过 {connections.config.max_catalog_bytes / 1024:.0f} KiB 保存上限。",
        )
    if row.encrypted_credentials and any(
        secret in encoded or json.dumps(secret, ensure_ascii=False)[1:-1] in encoded
        for secret in connections.secrets_for_redaction(row)
    ):
        raise InvalidInputError("tool_catalog_invalid", "工具目录包含敏感凭证，未保存。")
    candidate = {
        "tools": catalog,
        "instructions": instructions,
        "hash": digest({"tools": catalog, "instructions": instructions}),
        "config_revision": row.config_revision,
        "credential_revision": row.credential_revision,
        "expires_at": (utc_now() + timedelta(minutes=10)).isoformat(),
    }
    with connections.database.transaction() as db:
        reserve_writer(db, ToolConnection.__table__)
        current = require_connection(db, row.id)
        if (
            current.config_revision != row.config_revision
            or current.credential_revision != row.credential_revision
            or not current.enabled
        ):
            raise ConflictError("tool_connection_changed", "发现期间连接已改变，请重试。")
        current.discovery_candidate = (
            None
            if current.approved_catalog == catalog and current.approved_instructions == instructions
            else candidate
        )
        db.flush()
        return connection_read(current)


class ToolCatalogService:
    def __init__(self, connections, invocation):
        self.connections, self.invocation = connections, invocation
        self.database = connections.database

    @property
    def config(self):
        return self.connections.config

    def _discovery_connection(self, actor: Actor, id: str) -> ToolConnection:
        with self.database.transaction() as db:
            return own_connection(db, id, actor.user_id)

    async def discover(self, actor: Actor, id: str):
        require_permission(actor, "tools:update")
        row = await asyncio.to_thread(self._discovery_connection, actor, id)
        if row.kind == "native":
            return connection_read(row)
        if not row.enabled:
            raise ConflictError("tool_connection_disabled", "请先启用工具连接。")
        try:
            async with asyncio.timeout(self.config.timeout_seconds):
                client = await asyncio.to_thread(self.invocation.client_for_connection, row)
                try:
                    catalog = await client.discover()
                finally:
                    if isinstance(client, StdioMCPClient):
                        await client.aclose()
        except (InvalidInputError, ServiceUnavailableError):
            raise
        except TimeoutError:
            raise ServiceUnavailableError(
                "tool_connection_timeout", "读取工具目录超时，请检查服务及本机程序启动状态。"
            ) from None
        except Exception:
            raise ServiceUnavailableError(
                "tool_connection_failed", "未能读取工具目录，请检查凭据、服务地址或本机程序。"
            ) from None
        return await asyncio.to_thread(
            save_candidate, self.connections, row, catalog, getattr(client, "instructions", "")
        )

    def approve(self, actor: Actor, id: str, data):
        require_permission(actor, "tools:update")
        from datetime import datetime

        with self.database.transaction() as db:
            reserve_writer(db, ToolConnection.__table__)
            row = own_connection(db, id, actor.user_id)
            candidate = row.discovery_candidate
            if (
                row.config_revision != data.expected_config_revision
                or row.catalog_revision != data.expected_catalog_revision
                or not candidate
                or candidate["hash"] != data.candidate_hash
                or candidate["credential_revision"] != row.credential_revision
                or datetime.fromisoformat(candidate["expires_at"]) <= utc_now()
            ):
                raise ConflictError(
                    "tool_candidate_expired", "候选目录已过期或连接已改变，请重新发现。"
                )
            from jsonschema import Draft202012Validator

            def check_refs(value):
                if isinstance(value, dict):
                    for key, item in value.items():
                        if key in {"$ref", "$dynamicRef"} and (
                            not isinstance(item, str) or not item.startswith("#")
                        ):
                            raise InvalidInputError(
                                "tool_schema_invalid",
                                "首版只接受 schema 内部引用，不读取外部引用地址。",
                            )
                        check_refs(item)
                elif isinstance(value, list):
                    for item in value:
                        check_refs(item)

            for tool in candidate["tools"]:
                check_refs(tool["input_schema"])
                try:
                    Draft202012Validator.check_schema(tool["input_schema"])
                except Exception:
                    raise InvalidInputError(
                        "tool_schema_invalid", "工具输入 schema 无效。"
                    ) from None
            if row.approved_catalog != candidate[
                "tools"
            ] or row.approved_instructions != candidate.get("instructions", ""):
                row.approved_catalog = candidate["tools"]
                row.approved_instructions = candidate.get("instructions", "")
                row.catalog_revision += 1
            row.discovery_candidate = None
            db.flush()
            return connection_read(row)

    def annotate(self, actor: Actor, id: str, data):
        require_permission(actor, "tools:update")
        with self.database.transaction() as db:
            reserve_writer(db, ToolConnection.__table__)
            row = own_connection(db, id, actor.user_id)
            if row.annotations_revision != data.expected_annotations_revision:
                raise ConflictError("tool_annotations_changed", "展示名称已修改，请刷新后重试。")
            names = {item["name"] for item in row.approved_catalog}
            names.update(row.tool_annotations)
            names.update(item["name"] for item in (row.discovery_candidate or {}).get("tools", []))
            if set(data.annotations) - names:
                raise InvalidInputError(
                    "tool_annotation_invalid", "只能为已读取的工具设置展示信息。"
                )
            row.tool_annotations = {
                key: value.model_dump() for key, value in data.annotations.items()
            }
            row.annotations_revision += 1
            db.flush()
            return connection_read(row)

    def discard(self, actor: Actor, id: str, data):
        require_permission(actor, "tools:update")
        with self.database.transaction() as db:
            reserve_writer(db, ToolConnection.__table__)
            row = own_connection(db, id, actor.user_id)
            if (
                not row.discovery_candidate
                or row.discovery_candidate["hash"] != data.candidate_hash
                or row.config_revision != data.expected_config_revision
                or row.catalog_revision != data.expected_catalog_revision
            ):
                raise ConflictError("tool_candidate_expired", "候选目录已变化，请刷新。")
            row.discovery_candidate = None
            db.flush()
            return connection_read(row)

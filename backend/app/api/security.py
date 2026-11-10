import re

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

from app.auth.config import AuthConfig, normalize_origin


class BrowserSecurityMiddleware:
    def __init__(self, app, config: AuthConfig):
        self.app, self.config = app, config

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            await self.app(scope, receive, send)
            return

        async def no_store(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = "no-store"
                headers["X-Content-Type-Options"] = "nosniff"
            await send(message)

        async def reject(status, code, message):
            await JSONResponse({"detail": {"code": code, "message": message}}, status_code=status)(
                scope, receive, no_store
            )

        if scope["method"] in {"POST", "PATCH", "PUT", "DELETE"}:
            headers = Headers(scope=scope)
            try:
                origin = normalize_origin(headers.get("origin", ""))
            except ValueError:
                origin = None
            if origin not in self.config.allowed_origins:
                await reject(403, "invalid_origin", "请求来源不受信任。")
                return
            if scope["method"] == "POST" and (
                scope["path"] == "/api/files"
                or re.fullmatch(r"/api/knowledge-bases/[^/]+/documents", scope["path"])
            ):
                # 上传入口自行流式限量，仍保留 Origin 和身份检查。
                await self.app(scope, receive, no_store)
                return
            if (
                headers.get("content-type", "").split(";", 1)[0].strip().lower()
                != "application/json"
            ):
                await reject(415, "unsupported_media_type", "请使用 JSON 提交请求。")
                return
            # 技能包 JSON 需容纳 base64 开销，但不提高普通配置与认证请求上限。
            limit = (
                8192
                if scope["path"].startswith("/api/auth/")
                else 32 * 1024 * 1024
                if scope["path"] == "/api/skills" or scope["path"].startswith("/api/skills/")
                else 1048576
            )
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > limit:
                    await reject(413, "request_too_large", "请求内容过大。")
                    return
                if not message.get("more_body", False):
                    break
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await self.app(scope, replay, no_store)
        else:
            await self.app(scope, receive, no_store)

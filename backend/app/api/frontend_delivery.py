"""Serve a built client application without masking API or asset failures."""

import mimetypes
import re
import stat
from pathlib import Path

import anyio
from fastapi import FastAPI
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

PAGE = re.compile(
    r"(?:|agents(?:/(?:new|[^/.]+)(?:/(?:connections|home|evaluations/[^/.]+/cases/[^/.]+/trace))?)?|skills(?:/(?:new|[^/.]+))?|brains|rules|"
    r"knowledge(?:/[^/.]+(?:/documents/[^/.]+)?)?|tools|"
    r"conversations(?:/(?:new|[^/.]+)(?:/trace)?)?|help(?:/[^/.]+)?|design-system|signin|"
    r"avatars/playground(?:/[^/.]+)?|avatars/svg|avatars/rive/programmer|login|preview)/?"
)


def document_navigation(path: str, scope: Scope) -> bool:
    """Recognize missing human pages without turning missing resources into HTML."""
    segments = path.strip("/").split("/")
    if (
        segments[0] in {"api", "assets", "brand", "avatars", "failures"}
        or any(segment.startswith(".") for segment in segments)
        or "." in segments[-1]
    ):
        return False
    headers = Headers(scope=scope)
    destination = headers.get("sec-fetch-dest")
    if destination is not None:
        return destination == "document"
    if headers.get("sec-fetch-mode") is not None:
        return False
    # Older clients omit Fetch Metadata. An extensionless path and an explicit
    # HTML accept value are both required for this compatibility fallback.
    for value in headers.get("accept", "").lower().split(","):
        media_type, *parameters = value.strip().split(";")
        if media_type != "text/html":
            continue
        try:
            quality = next(
                (float(item.strip()[2:]) for item in parameters if item.strip().startswith("q=")),
                1,
            )
        except ValueError:
            continue
        if quality > 0:
            return True
    return False


def encoding(header: str, available: set[str]) -> str | None:
    accepted = {}
    for part in header.lower().split(","):
        name, *params = part.strip().split(";")
        try:
            quality = next((float(p.strip()[2:]) for p in params if p.strip().startswith("q=")), 1)
            accepted[name] = max(0, min(1, quality))
        except ValueError:
            accepted[name] = 0
    candidates = []
    for name in ("br", "gzip", "identity"):
        if name not in available:
            continue
        quality = accepted.get(name, accepted.get("*", 0 if name != "identity" else 1))
        if quality > 0:
            candidates.append((quality, name))
    # Compression wins ties; an omitted identity is a fallback, as in the old entry.
    compressed = [p for p in candidates if p[1] != "identity"]
    if compressed and accepted.get("identity", 0) <= max(p[0] for p in compressed):
        return max(compressed, key=lambda p: (p[0], p[1] == "br"))[1]
    return max(candidates, key=lambda p: p[0])[1] if candidates else None


class FrontendFiles(StaticFiles):
    async def get_response(self, path, scope):
        if path == ".":
            path = ""
        if path.startswith(("api/", ".")) or path == "api":
            raise HTTPException(404)
        # StaticFiles normalizes dot components before calling this method.
        # Inspect the decoded original as well so a traversal cannot become a page.
        if any(segment.startswith(".") for segment in scope["path"].split("/")):
            raise HTTPException(404)
        if scope["method"] not in {"GET", "HEAD"}:
            if PAGE.fullmatch(path):
                raise HTTPException(405, headers={"Allow": "GET, HEAD"})
            raise HTTPException(404)
        if PAGE.fullmatch(path):
            path = "index.html"

        response = await self.static_response(path, scope)
        if response is not None:
            return response
        if document_navigation(path, scope):
            response = await self.static_response("failures/404.html", scope, status_code=404)
            if response is not None:
                return response
        return await super().get_response(path, scope)

    async def static_response(self, path: str, scope: Scope, *, status_code: int = 200):
        """Reuse static path boundaries and negotiation for normal and error documents."""

        # Resolve through StaticFiles so compression cannot bypass its path boundary.
        def variants():
            _, info = self.lookup_path(path)
            if info is None or not stat.S_ISREG(info.st_mode):
                return None
            available = {"identity"}
            for name, suffix in (("br", ".br"), ("gzip", ".gz")):
                _, compressed = self.lookup_path(path + suffix)
                if compressed is not None and stat.S_ISREG(compressed.st_mode):
                    available.add(name)
            return available

        available = await anyio.to_thread.run_sync(variants)
        if available is None:
            return None
        headers = dict(scope["headers"])
        selected = encoding(headers.get(b"accept-encoding", b"").decode(), available)
        if selected is None:
            return Response(status_code=406, headers={"Vary": "Accept-Encoding"})
        suffix = {"identity": "", "br": ".br", "gzip": ".gz"}[selected]
        if status_code == 200:
            response = await super().get_response(path + suffix, scope)
        else:
            full_path, info = await anyio.to_thread.run_sync(self.lookup_path, path + suffix)
            # StaticFiles' conditional response would turn a repeated unknown URL
            # into 304. Error documents must keep their original error status.
            response = FileResponse(
                full_path, status_code=status_code, stat_result=info, media_type="text/html"
            )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Vary"] = "Accept-Encoding"
        response.headers["Cache-Control"] = (
            "public,max-age=31536000,immutable" if path.startswith("assets/") else "no-cache"
        )
        if selected != "identity":
            response.headers["Content-Encoding"] = selected
            response.headers["Content-Type"] = (
                mimetypes.guess_type(path)[0] or "application/octet-stream"
            )
            if response.headers["Content-Type"].startswith("text/"):
                response.headers["Content-Type"] += "; charset=utf-8"
        return response


def mount_frontend(app: FastAPI, directory: Path) -> None:
    if (directory / "index.html").is_file():
        app.mount("/", FrontendFiles(directory=directory), name="frontend")

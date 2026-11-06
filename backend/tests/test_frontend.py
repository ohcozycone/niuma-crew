"""Shared React entry and static delivery, independently of application storage."""

import gzip

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.frontend_delivery import mount_frontend


@pytest.fixture
def web(tmp_path):
    html = b"<html>client-root</html>"
    (tmp_path / "index.html").write_bytes(html)
    (tmp_path / "index.html.gz").write_bytes(gzip.compress(html))
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/main-abc.js").write_text("console.log('client')")
    (tmp_path / "failures").mkdir()
    failure = b"<html>brand-not-found</html>"
    (tmp_path / "failures/404.html").write_bytes(failure)
    (tmp_path / "failures/404.html.gz").write_bytes(gzip.compress(failure))
    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"api": True}

    mount_frontend(app, tmp_path)
    return TestClient(app)


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/agents",
        "/agents/new",
        "/agents/abc?tab=instructions",
        "/agents/abc/connections",
        "/agents/abc/home?section=evaluations",
        "/skills/new",
        "/brains",
        "/tools",
        "/tools?agent=review-agent",
        "/rules",
        "/knowledge",
        "/knowledge/new",
        "/knowledge/library?view=search&strategy=vector",
        "/knowledge/library/documents/document?chunk=source",
        "/conversations/new?agent=abc",
        "/conversations/abc",
        "/help",
        "/help/agents",
        "/signin?next=/agents",
        "/login",
        "/preview",
    ],
)
def test_direct_business_routes_return_client_entry(web, path):
    result = web.get(path)
    assert result.status_code == 200
    assert "client-root" in result.text
    assert result.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize(
    "path",
    [
        "/api/missing",
        "/assets/missing.js",
        "/brand/missing.svg",
        "/unknown",
        "/%2e%2e/private.txt",
        "/.env",
    ],
)
def test_missing_api_assets_and_private_files_never_return_client_html(web, path):
    result = web.get(path)
    assert result.status_code == 404
    assert "client-root" not in result.text


def test_api_static_headers_and_write_boundary(web):
    assert web.get("/api/ping").json() == {"api": True}
    asset = web.get("/assets/main-abc.js")
    assert asset.status_code == 200
    assert "immutable" in asset.headers["cache-control"]
    assert web.post("/agents").status_code == 405
    assert web.post("/signin").status_code == 405
    assert web.post("/travel-expense/answers").status_code == 404
    assert web.post("/agents/abc/connections").headers["allow"] == "GET, HEAD"
    assert web.post("/knowledge/library/documents/document").status_code == 405


@pytest.mark.parametrize(
    "headers",
    [
        {"Sec-Fetch-Dest": "document"},
        {"Sec-Fetch-Dest": "document", "Accept": "*/*"},
        {"Accept": "text/html,application/xhtml+xml"},
    ],
)
def test_missing_document_navigation_uses_real_branded_404(web, headers):
    response = web.get("/old-bookmark", headers=headers)
    assert response.status_code == 404 and "brand-not-found" in response.text
    assert "client-root" not in response.text
    assert response.headers["cache-control"] == "no-cache"
    repeated = web.get(
        "/old-bookmark", headers={**headers, "If-None-Match": response.headers["etag"]}
    )
    assert repeated.status_code == 404


@pytest.mark.parametrize(
    "path,headers",
    [
        ("/api/missing", {"Sec-Fetch-Dest": "document"}),
        ("/assets/missing", {"Sec-Fetch-Dest": "document"}),
        ("/brand/missing", {"Sec-Fetch-Dest": "document"}),
        ("/avatars/missing", {"Sec-Fetch-Dest": "document"}),
        ("/failures/missing", {"Sec-Fetch-Dest": "document"}),
        ("/missing.js", {"Sec-Fetch-Dest": "document"}),
        ("/hidden/.env", {"Sec-Fetch-Dest": "document"}),
        ("/nested/%2e%2e/old-bookmark", {"Sec-Fetch-Dest": "document"}),
        ("/unknown", {"Sec-Fetch-Dest": "empty", "Accept": "text/html"}),
        ("/unknown", {"Sec-Fetch-Dest": "script", "Accept": "text/html"}),
        ("/unknown", {"Sec-Fetch-Mode": "cors", "Accept": "text/html"}),
        ("/unknown", {"Accept": "text/html;q=0"}),
        ("/unknown", {}),
    ],
)
def test_resource_or_non_document_failures_never_receive_brand_html(web, path, headers):
    response = web.get(path, headers=headers)
    assert response.status_code == 404
    assert "brand-not-found" not in response.text and "client-root" not in response.text


def test_error_document_preserves_compression_head_and_status(web):
    headers = {"Sec-Fetch-Dest": "document", "Accept-Encoding": "gzip"}
    response = web.get("/missing-page", headers=headers)
    assert response.status_code == 404 and "brand-not-found" in response.text
    assert response.headers["content-encoding"] == "gzip"
    assert response.headers["vary"] == "Accept-Encoding"
    assert "text/html" in response.headers["content-type"]
    head = web.head("/missing-page", headers=headers)
    assert head.status_code == 404 and head.content == b""
    assert head.headers["content-length"] == response.headers["content-length"]
    assert (
        web.get("/missing-page", headers={**headers, "Accept-Encoding": "*;q=0"}).status_code == 406
    )


def test_missing_generated_error_document_keeps_original_404(tmp_path):
    (tmp_path / "index.html").write_text("client-root")
    app = FastAPI()
    mount_frontend(app, tmp_path)
    response = TestClient(app).get("/unknown", headers={"Sec-Fetch-Dest": "document"})
    assert response.status_code == 404 and "client-root" not in response.text


@pytest.mark.parametrize("path", ["/signin?next=/agents", "/agents", "/help", "/index.html"])
def test_shared_entry_gzip_validation_and_head(web, path):
    result = web.get(path, headers={"Accept-Encoding": "gzip"})
    assert result.text == "<html>client-root</html>"
    assert result.headers["content-encoding"] == "gzip"
    assert result.headers["vary"] == "Accept-Encoding"
    assert result.headers["cache-control"] == "no-cache"
    cached = web.get(
        path, headers={"Accept-Encoding": "gzip", "If-None-Match": result.headers["etag"]}
    )
    assert cached.status_code == 304
    assert cached.content == b""
    head = web.head(path, headers={"Accept-Encoding": "identity"})
    assert head.content == b""
    assert int(head.headers["content-length"]) > 0
    assert web.get(path, headers={"Accept-Encoding": "*;q=0"}).status_code == 406


def test_api_only_without_built_frontend(tmp_path):
    app = FastAPI()
    mount_frontend(app, tmp_path)
    assert TestClient(app).get("/agents").status_code == 404


@pytest.mark.parametrize("override", [False, True])
def test_frontend_directory_defaults_to_sibling_project_and_allows_override(
    tmp_path, monkeypatch, override
):
    from app.config import load_config

    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    monkeypatch.delenv("FRONTEND_DIST", raising=False)
    directory = tmp_path / ("custom-dist" if override else "frontend/dist")
    directory.mkdir(parents=True)
    (directory / "index.html").write_text("<html>isolated frontend</html>")
    if override:
        monkeypatch.setenv("FRONTEND_DIST", str(directory))
    app = FastAPI()
    settings = load_config(backend_dir)
    assert settings.frontend_dist == directory
    mount_frontend(app, settings.frontend_dist)
    assert TestClient(app).get("/agents").text == "<html>isolated frontend</html>"


@pytest.mark.parametrize(
    "header, expected",
    [("gzip", "gzip"), ("gzip;q=0, identity", None), ("identity;q=0, gzip", "gzip")],
)
def test_hashed_asset_compression_retains_type_cache_and_head(tmp_path, header, expected):
    (tmp_path / "index.html").write_text("client")
    (tmp_path / "assets").mkdir()
    source = b"console.log('client')"
    (tmp_path / "assets/app.js").write_bytes(source)
    (tmp_path / "assets/app.js.gz").write_bytes(gzip.compress(source))
    app = FastAPI()
    mount_frontend(app, tmp_path)
    client = TestClient(app)
    response = client.get("/assets/app.js", headers={"Accept-Encoding": header})
    assert response.content == source
    assert response.headers.get("content-encoding") == expected
    assert "javascript" in response.headers["content-type"]
    assert "immutable" in response.headers["cache-control"]
    assert response.headers["x-content-type-options"] == "nosniff"
    head = client.head("/assets/app.js", headers={"Accept-Encoding": header})
    assert head.status_code == 200
    assert head.content == b""
    assert head.headers["content-length"] == response.headers["content-length"]
    assert client.get("/assets/missing.js", headers={"Accept-Encoding": "*;q=0"}).status_code == 404

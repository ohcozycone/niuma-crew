"""Built-in provider contracts, using only fake HTTP and DNS; no real credentials."""

import asyncio
import json
from dataclasses import replace

import httpx
import pytest

from app.runtime.tools.web import WebService, web_bindings
from app.runtime.tools.web_config import WebConfig, load_web_config
from app.runtime.tools.web_policy import WebFailure, checked_url, public_query, public_url


async def public_dns(host):
    return ["93.184.216.34"]


async def guard():
    pass


def service(handler, **options):
    return WebService(
        WebConfig(bocha_api_key="test-only-bocha", **options),
        transport=httpx.MockTransport(handler),
        resolve=public_dns,
    )


def run(service, name, arguments, check=guard):
    return asyncio.run(service.call(name, arguments, check))


def test_search_contract_separates_snippets_from_page_content():
    def handler(request):
        assert str(request.url) == "https://api.bocha.cn/v1/web-search"
        assert request.headers["authorization"] == "Bearer test-only-bocha"
        assert json.loads(request.content) == {
            "query": "公开气候报告",
            "count": 2,
            "freshness": "noLimit",
            "summary": False,
        }
        return httpx.Response(
            200,
            json={
                "code": 200,
                "data": {
                    "webPages": {
                        "value": [
                            {
                                "name": "Report",
                                "url": "https://example.com/report",
                                "snippet": "Summary",
                                "raw_content": "ignored",
                            },
                        ]
                    }
                },
            },
        )

    outcome = run(service(handler), "web_search", {"query": "公开气候报告", "count": 2})
    payload = json.loads(outcome.content)
    assert outcome.status == "succeeded"
    assert payload["kind"] == "search_snippets" and payload["untrusted"] is True
    assert payload["results"][0] == {
        "title": "Report",
        "url": "https://example.com/report",
        "snippet": "Summary",
    }
    assert "content" not in payload and "raw_content" not in outcome.content
    assert outcome.sources == ({"url": "https://example.com/report", "title": "Report"},)


def test_fetch_uses_fixed_provider_and_requires_target_http_200():
    def handler(request):
        assert str(request.url) == "https://r.jina.ai/"
        assert request.method == "POST"
        assert json.loads(request.content) == {"url": "https://example.com/report"}
        assert request.headers["accept"] == "application/json"
        assert request.headers["x-assert-status-code"] == "200"
        assert request.headers["x-no-cache"] == "true"
        assert request.headers["x-base"] == "final"
        assert request.headers["authorization"] == "Bearer test-only-jina"
        assert "cookie" not in request.headers
        return httpx.Response(
            200,
            json={
                "code": 200,
                "data": {"url": "https://example.org/final", "title": "Doc", "content": "x" * 1500},
            },
        )

    outcome = run(
        service(handler, jina_api_key="test-only-jina", max_content_chars=1000),
        "web_fetch",
        {"url": "https://example.com/report"},
    )
    result = json.loads(outcome.content)
    assert result["kind"] == "page_content" and result["untrusted"] is True
    assert result["url"] == "https://example.org/final"
    assert result["requested_url"] == "https://example.com/report"
    assert result["truncated"] is True and len(result["content"]) == 1000
    assert result["fetched_at"]


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://localhost/a",
        "http://127.0.0.1/a",
        "http://169.254.169.254/",
        "http://10.0.0.1/a",
        "http://192.168.1.2/a",
        "http://[::1]/",
        "http://service.internal/a",
        "http://service.local/a",
        "https://user:pass@example.com/a",
        "https://example.com/a?token=secret",
        "https://example.com/a?public=1",
        "https://example.com/a#private",
        "https://example.com:444/a",
        "https://example.com/\n",
        "https://example.com\\@internal/a",
        "https://example.com/token/private",
        "https://example.com/reset/private",
        "https://example.com/%74oken/private",
        "https://example.com/" + "a" * 50,
    ],
)
def test_sensitive_or_private_urls_never_reach_provider(url):
    requests = []
    result = run(service(lambda req: requests.append(req)), "web_fetch", {"url": url})
    assert result.status == "failed" and result.error_code == "web_url_denied"
    assert requests == []


def test_private_dns_and_mixed_dns_fail_closed():
    async def scenario():
        for addresses in [["10.0.0.1"], ["93.184.216.34", "127.0.0.1"], []]:

            async def resolve(_):
                return addresses

            with pytest.raises(WebFailure, match="web_url_denied"):
                await checked_url("https://public.example.com/", resolve)

    asyncio.run(scenario())


def test_private_final_destination_is_not_delivered():
    result = run(
        service(
            lambda request: httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": {
                        "url": "http://169.254.169.254/",
                        "content": "private data not exposed",
                    },
                },
            )
        ),
        "web_fetch",
        {"url": "https://example.com/"},
    )
    assert result.status == "failed" and "private data" not in result.content


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "web_provider_unauthorized"),
        (403, "web_provider_unauthorized"),
        (429, "web_rate_limited"),
        (422, "web_upstream_failed"),
        (500, "web_upstream_failed"),
        (302, "web_upstream_failed"),
    ],
)
def test_provider_failure_and_redirect_are_not_success_or_retried(status, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status, headers={"location": "http://127.0.0.1/"}, text="upstream secret body"
        )

    outcome = run(service(handler), "web_fetch", {"url": "https://example.com/"})
    assert outcome.status == "failed" and outcome.error_code == code
    assert "secret" not in outcome.content and len(calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"code": 500, "data": {}},
        {"code": 200, "data": {}},
        {"code": 200, "data": {"webPages": {"value": "invalid"}}},
    ],
)
def test_invalid_search_envelope_is_not_empty_success(payload):
    outcome = run(
        service(lambda request: httpx.Response(200, json=payload)),
        "web_search",
        {"query": "public"},
    )
    assert outcome.status == "failed" and outcome.error_code == "web_invalid_response"


def test_empty_search_is_success_not_failed_fetch():
    outcome = run(
        service(
            lambda request: httpx.Response(
                200, json={"code": 200, "data": {"webPages": {"value": []}}}
            )
        ),
        "web_search",
        {"query": "public"},
    )
    assert outcome.status == "succeeded" and json.loads(outcome.content)["results"] == []


@pytest.mark.parametrize(
    "payload,code",
    [
        (
            {"code": 200, "data": {"url": "https://example.com/", "content": ""}},
            "web_empty_content",
        ),
        ({"code": 200, "data": {"content": "missing url"}}, "web_url_denied"),
        (
            {"code": 400, "data": {"url": "https://example.com/", "content": "error page"}},
            "web_invalid_response",
        ),
    ],
)
def test_fetch_failure_never_delivers_error_page(payload, code):
    result = run(
        service(lambda request: httpx.Response(200, json=payload)),
        "web_fetch",
        {"url": "https://example.com/"},
    )
    assert result.status == "failed" and result.error_code == code


def test_response_limit_timeout_and_cancellation():
    result = run(
        service(lambda request: httpx.Response(200, content=b"x" * 5000), max_response_bytes=4096),
        "web_search",
        {"query": "public"},
    )
    assert result.error_code == "web_response_too_large"

    def timeout(request):
        raise httpx.ReadTimeout("no result")

    assert (
        run(service(timeout), "web_search", {"query": "public"}).error_code == "web_upstream_failed"
    )

    async def cancel(request):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        run(service(cancel), "web_search", {"query": "public"})


def test_guard_rechecked_before_dispatch_and_before_result():
    calls = []
    checks = 0

    async def revoked():
        nonlocal checks
        checks += 1
        if checks == 2:
            raise PermissionError("revoked")

    with pytest.raises(PermissionError):
        run(
            service(lambda req: calls.append(req)),
            "web_fetch",
            {"url": "https://example.com/"},
            revoked,
        )
    assert not calls
    checks = 0

    def response(request):
        calls.append(request)
        return httpx.Response(200, json={"code": 200, "data": {"webPages": {"value": []}}})

    async def revoke_after():
        if calls:
            raise PermissionError("revoked after request")

    with pytest.raises(PermissionError):
        run(service(response), "web_search", {"query": "public"}, revoke_after)
    assert len(calls) == 1


def test_missing_configuration_and_secrets_do_not_leak():
    config = load_web_config(
        {"WEB_BOCHA_API_KEY": "private-bocha", "WEB_JINA_API_KEY": "private-jina"}
    )
    assert "private" not in repr(config)
    with pytest.raises(ValueError):
        replace(config, bocha_endpoint="https://evil.example.com/")
    result = run(WebService(WebConfig()), "web_search", {"query": "public"})
    assert result.error_code == "web_not_configured"
    for query in [
        "api_key=private",
        "token:private",
        "Bearer private",
        "https://example.com/?token=private",
    ]:
        with pytest.raises(WebFailure):
            public_query(query)


def test_builtin_bindings_are_not_fake_mcp_connections():
    bindings = web_bindings()
    assert {b["tool_name"] for b in bindings} == {"web_search", "web_fetch"}
    assert all(b["kind"] == "web" and b["recovery"] == "readonly" for b in bindings)
    assert all("connection_id" not in b and "grant_id" not in b for b in bindings)
    assert public_url("https://Example.COM/report") == "https://example.com/report"


@pytest.mark.parametrize(
    "query",
    [
        "HTTPS://example.com/private?code=demo",
        "HtTpS://example.com/path#private",
        "HTTP://127.0.0.1/path",
        "HTTPS://user:pass@example.com/path",
        "FTP://user:pass@private.local/path",
        "file:///private/notes",
    ],
)
def test_mixed_case_url_in_search_never_bypasses_privacy_policy(query):
    calls = []
    result = run(service(lambda request: calls.append(request)), "web_search", {"query": query})
    assert result.status == "failed" and not calls


def test_search_marks_policy_filtered_results_distinct_from_no_matches():
    result = run(
        service(
            lambda request: httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": {
                        "webPages": {
                            "value": [
                                {
                                    "name": "private link",
                                    "url": "https://example.com/report?code=private",
                                    "snippet": "not delivered",
                                }
                            ]
                        }
                    },
                },
            )
        ),
        "web_search",
        {"query": "public"},
    )
    payload = json.loads(result.content)
    assert payload["results"] == [] and payload["filtered_count"] == 1
    assert "private" not in result.content

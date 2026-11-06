import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, request, retryDeadline } from "./http";

afterEach(() => vi.unstubAllGlobals());
describe("HTTP failure metadata", () => {
  it("accepts seconds or HTTP dates, ignoring malformed wait hints", () => {
    const now = Date.parse("2026-10-31T00:00:00Z");
    expect(retryDeadline("8", now)).toBe(now + 8000);
    expect(retryDeadline("Sat, 31 Oct 2026 00:00:09 GMT", now)).toBe(now + 9000);
    for (const value of [
      null,
      "",
      "-1",
      "1.5",
      "banana",
      "Infinity",
      "999999999999999999999",
      "Mon, 9999",
      "xxx, 31 Dec 2099 23:59:59 GMT",
      "Sun, 31 Feb 2099 23:59:59 GMT",
    ])
      expect(retryDeadline(value, now)).toBeUndefined();
  });
  it("keeps a safe ID, wait deadline and field locations from an error response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        Response.json(
          {
            detail: [
              {
                loc: ["body", "name"],
                msg: "名称不能为空",
                input: "secret",
                ctx: { raw: "secret" },
              },
            ],
          },
          { status: 422, headers: { "X-Request-ID": "request-1", "Retry-After": "8" } },
        ),
      ),
    );
    const error = (await request("agents").catch((failure: unknown) => failure)) as ApiError;
    expect(error).toMatchObject({
      status: 422,
      requestId: "request-1",
      issues: [{ path: ["name"], message: "名称不能为空" }],
    });
    expect(error.retryAt).toBeGreaterThan(Date.now());
    expect(JSON.stringify(error)).not.toContain("secret");
  });
  it("does not expose proxy HTML or malformed successful JSON", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(new Response("<html>secret upstream</html>", { status: 502 }))
      .mockResolvedValueOnce(new Response("private invalid JSON", { status: 200 }));
    vi.stubGlobal("fetch", fetcher);
    await expect(request("agents")).rejects.toMatchObject({
      status: 502,
      message: "操作失败，请稍后重试。",
    });
    await expect(request("agents")).rejects.toMatchObject({
      status: 200,
      source: "client",
      code: "client_invalid_response",
    });
  });
  it("distinguishes caller cancellation from a timeout signal", async () => {
    const controller = new AbortController();
    const abort = new DOMException("cancel", "AbortError");
    controller.abort(abort);
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(abort));
    await expect(request("agents", { signal: controller.signal })).rejects.toBe(abort);
    const custom = new AbortController();
    custom.abort(new Error("private cancellation reason"));
    await expect(request("agents", { signal: custom.signal })).rejects.toMatchObject({
      name: "AbortError",
    });
    const timeout = new AbortController();
    timeout.abort(new DOMException("expired", "TimeoutError"));
    await expect(request("agents", { signal: timeout.signal })).rejects.toMatchObject({
      status: 0,
      code: "client_timeout",
      source: "client",
    });
  });
  it("ends a session only for the website's explicit session error", async () => {
    vi.stubGlobal("window", new EventTarget());
    const listener = vi.fn();
    window.addEventListener("auth:session-ended", listener);
    try {
      const fetcher = vi
        .fn()
        .mockResolvedValueOnce(
          Response.json(
            { detail: { code: "upstream_auth_failed", message: "模型认证失败" } },
            { status: 401 },
          ),
        )
        .mockResolvedValueOnce(
          Response.json(
            { detail: { code: "authentication_required", message: "请登录" } },
            { status: 401 },
          ),
        );
      vi.stubGlobal("fetch", fetcher);
      await request("agents").catch(() => null);
      expect(listener).not.toHaveBeenCalled();
      await request("agents").catch(() => null);
      expect(listener).toHaveBeenCalledTimes(1);
    } finally {
      window.removeEventListener("auth:session-ended", listener);
    }
  });
});

// @vitest-environment jsdom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSigninForm } from "./useSigninForm";
import { notifyIdentityChange, type Identity } from "@/lib/identity";

vi.mock("@/lib/identity", async (original) => ({
  ...(await original<typeof import("@/lib/identity")>()),
  notifyIdentityChange: vi.fn(),
}));

const identity: Identity = {
  actor: { kind: "user", user: { id: "fixture-user", username: "fixture-admin" } },
  permissions: [],
  expires_at: "2030-01-01T00:00:00Z",
};
const navigation = {
  search: "?next=/agents",
  replace: vi.fn(),
  assign: vi.fn(),
  reload: vi.fn(),
};
let respond: (url: string, init: RequestInit) => Promise<Response>;
const fetcher = vi.fn((input: RequestInfo | URL, init: RequestInit = {}) =>
  respond(String(input), init),
);

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((finish) => {
    resolve = finish;
  });
  return { promise, resolve };
}
function calls(path: string) {
  return fetcher.mock.calls.filter(([url]) => String(url) === `/api/${path}`);
}
function credentials(
  hook: ReturnType<typeof renderHook<ReturnType<typeof useSigninForm>, unknown>>,
) {
  act(() => {
    hook.result.current.setUsername(" fixture-admin ");
    hook.result.current.setPassword("fixture-password");
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  navigation.search = "?next=/agents";
  vi.stubGlobal("location", navigation);
  if (typeof performance.mark !== "function")
    vi.stubGlobal("performance", {
      now: () => Date.now(),
      mark: vi.fn(),
      measure: vi.fn(),
      clearMarks: vi.fn(),
      clearMeasures: vi.fn(),
    });
  respond = async (url) =>
    url.endsWith("auth/providers")
      ? Response.json({ github: { enabled: true } })
      : url.endsWith("auth/me")
        ? Response.json({ detail: { code: "unauthenticated" } }, { status: 401 })
        : Response.json(identity);
  vi.stubGlobal("fetch", fetcher);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("React signin lifecycle", () => {
  it("validates required fields without sending a login request", async () => {
    const hook = renderHook(() => useSigninForm(vi.fn()));
    await act(async () => {
      await hook.result.current.enter("password");
    });
    expect(hook.result.current.feedback).toEqual({
      message: "请输入用户名和密码。",
      fields: ["username", "password"],
    });
    expect(calls("auth/login")).toHaveLength(0);
  });

  it("uses a synchronous gate for password and guest submissions, clears the password and redirects safely", async () => {
    const response = deferred<Response>();
    const original = respond;
    respond = (url, init) => (url.endsWith("auth/login") ? response.promise : original(url, init));
    const hook = renderHook(() => useSigninForm(vi.fn()));
    credentials(hook);
    let pending!: Promise<void>;
    act(() => {
      pending = hook.result.current.enter("password");
      void hook.result.current.enter("guest");
    });
    expect(calls("auth/login")).toHaveLength(1);
    expect(calls("auth/guest")).toHaveLength(0);
    expect(hook.result.current.pending).toBe("password");
    expect(JSON.parse(calls("auth/login")[0][1]!.body as string)).toEqual({
      username: "fixture-admin",
      password: "fixture-password",
    });
    await act(async () => {
      response.resolve(Response.json(identity));
      await pending;
    });
    expect(hook.result.current.password).toBe("");
    expect(notifyIdentityChange).toHaveBeenCalledOnce();
    expect(navigation.replace).toHaveBeenCalledWith("/agents");
  });

  it("recovers from invalid credentials and allows a subsequent guest entry", async () => {
    const original = respond;
    respond = (url, init) =>
      url.endsWith("auth/login")
        ? Promise.resolve(
            Response.json({ detail: { code: "invalid_credentials" } }, { status: 401 }),
          )
        : original(url, init);
    const hook = renderHook(() => useSigninForm(vi.fn()));
    credentials(hook);
    await act(async () => {
      await hook.result.current.enter("password");
    });
    expect(hook.result.current.pending).toBeNull();
    expect(hook.result.current.password).toBe("");
    expect(hook.result.current.feedback.fields).toEqual(["username", "password"]);
    expect(navigation.replace).not.toHaveBeenCalled();
    await act(async () => {
      await hook.result.current.enter("guest");
    });
    expect(JSON.parse(calls("auth/guest")[0][1]!.body as string)).toEqual({});
    expect(navigation.replace).toHaveBeenCalledWith("/");
  });

  it("keeps password and guest entry available when provider discovery fails", async () => {
    const original = respond;
    respond = (url, init) =>
      url.endsWith("auth/providers") ? Promise.reject(new Error("offline")) : original(url, init);
    const hook = renderHook(() => useSigninForm(vi.fn()));
    await act(async () => {
      await hook.result.current.enter("github");
    });
    expect(calls("auth/github")).toHaveLength(0);
    credentials(hook);
    await act(async () => {
      await hook.result.current.enter("password");
    });
    expect(navigation.replace).toHaveBeenCalledWith("/agents");
  });

  it("starts GitHub signin with a safe return path", async () => {
    navigation.search = "?next=//untrusted.example";
    const original = respond;
    respond = (url, init) =>
      url.endsWith("auth/github")
        ? Promise.resolve(
            Response.json({
              authorization_url: "https://github.com/login/oauth/authorize?client_id=fixture",
            }),
          )
        : original(url, init);
    const hook = renderHook(() => useSigninForm(vi.fn()));
    await waitFor(() => expect(hook.result.current.githubEnabled).toBe(true));
    await act(async () => {
      await hook.result.current.enter("github");
    });
    expect(JSON.parse(calls("auth/github")[0][1]!.body as string)).toEqual({ next: "/" });
    expect(navigation.assign).toHaveBeenCalledWith(
      "https://github.com/login/oauth/authorize?client_id=fixture",
    );
  });

  it("preserves entered credentials when GitHub initiation fails", async () => {
    const original = respond;
    respond = (url, init) =>
      url.endsWith("auth/github")
        ? Promise.resolve(
            Response.json({ detail: { code: "github_unavailable" } }, { status: 503 }),
          )
        : original(url, init);
    const hook = renderHook(() => useSigninForm(vi.fn()));
    await waitFor(() => expect(hook.result.current.githubEnabled).toBe(true));
    credentials(hook);
    await act(async () => {
      await hook.result.current.enter("github");
    });
    expect(hook.result.current.pending).toBeNull();
    expect(hook.result.current.password).toBe("fixture-password");
    expect(hook.result.current.feedback.message).toContain("GitHub 登录暂未启用");
  });

  it("does not let a late identity probe interrupt an interacting user", async () => {
    const probe = deferred<Response>();
    const original = respond;
    respond = (url, init) => (url.endsWith("auth/me") ? probe.promise : original(url, init));
    const finishMotion = vi.fn();
    const hook = renderHook(() => useSigninForm(finishMotion));
    act(() => hook.result.current.interact());
    expect(calls("auth/me")[0][1]!.signal!.aborted).toBe(true);
    await act(async () => {
      probe.resolve(Response.json(identity));
    });
    expect(finishMotion).toHaveBeenCalledOnce();
    expect(navigation.replace).not.toHaveBeenCalled();
  });

  it("shows OAuth failure instead of redirecting an existing user", async () => {
    navigation.search = "?auth_error=github_cancelled&next=/agents";
    const original = respond;
    respond = (url, init) =>
      url.endsWith("auth/me") ? Promise.resolve(Response.json(identity)) : original(url, init);
    const hook = renderHook(() => useSigninForm(vi.fn()));
    await waitFor(() => expect(hook.result.current.githubEnabled).toBe(true));
    expect(hook.result.current.feedback.message).toContain("已取消");
    expect(navigation.replace).not.toHaveBeenCalled();
  });

  it("does not navigate after unmount while a login response is pending", async () => {
    const response = deferred<Response>();
    const original = respond;
    respond = (url, init) => (url.endsWith("auth/login") ? response.promise : original(url, init));
    const hook = renderHook(() => useSigninForm(vi.fn()));
    credentials(hook);
    let pending!: Promise<void>;
    act(() => {
      pending = hook.result.current.enter("password");
    });
    hook.unmount();
    await act(async () => {
      response.resolve(Response.json(identity));
      await pending;
    });
    expect(navigation.replace).not.toHaveBeenCalled();
    expect(notifyIdentityChange).not.toHaveBeenCalled();
  });
});

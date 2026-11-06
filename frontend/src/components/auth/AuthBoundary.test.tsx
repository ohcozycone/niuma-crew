// @vitest-environment jsdom
import { useState } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, Link, Outlet } from "react-router";
import { RouterProvider } from "react-router/dom";
import { AuthBoundary } from "./AuthBoundary";
import { request } from "@/lib/api/http";
import type { Identity } from "@/lib/identity";
import { useIdentity } from "@/state/auth/useIdentity";

const identity: Identity = {
  actor: { kind: "user", user: { id: "fixture-user", username: "fixture-admin" } },
  permissions: ["agents:read", "skills:read"],
  expires_at: "2030-01-01T00:00:00Z",
};
let currentIdentity: Identity;
const channels: AuthChannel[] = [];
class AuthChannel {
  onmessage: (() => void) | null = null;
  close = vi.fn();
  constructor(public name: string) {
    channels.push(this);
  }
}
const fetcher = vi.fn(async (input: RequestInfo | URL) =>
  String(input) === "/api/auth/me" ? Response.json(currentIdentity) : Response.json({ ok: true }),
);
function identityCalls() {
  return fetcher.mock.calls.filter(([input]) => String(input) === "/api/auth/me");
}
function FixturePage({ title }: { title: string }) {
  const identity = useIdentity();
  const [count, setCount] = useState(0);
  return (
    <main>
      <h1>{title}</h1>
      <p>{identity.actor.user?.username ?? "游客"}</p>
      <input aria-label="搜索" />
      <button onClick={() => setCount(count + 1)}>操作 {count}</button>
    </main>
  );
}
function renderWorkspace() {
  const router = createMemoryRouter(
    [
      {
        element: (
          <AuthBoundary>
            <nav>
              <Link to="/agents">员工</Link>
              <Link to="/skills">技能</Link>
            </nav>
            <Outlet />
          </AuthBoundary>
        ),
        children: [
          { path: "/agents", element: <FixturePage title="员工页面" /> },
          { path: "/skills", element: <FixturePage title="技能页面" /> },
        ],
      },
    ],
    { initialEntries: ["/agents"] },
  );
  const view = render(<RouterProvider router={router} />);
  return {
    ...view,
    unmount() {
      view.unmount();
      router.dispose();
    },
  };
}

beforeEach(() => {
  currentIdentity = identity;
  channels.length = 0;
  fetcher.mockClear();
  vi.stubGlobal("fetch", fetcher);
  vi.stubGlobal("BroadcastChannel", AuthChannel);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("workspace identity lifecycle", () => {
  it("loads identity on entry and reuses it for local actions, focus, requests, and navigation", async () => {
    const view = renderWorkspace();
    await screen.findByRole("heading", { name: "员工页面" });
    expect(screen.getByText("fixture-admin")).toBeTruthy();
    expect(identityCalls()).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "操作 0" }));
    const search = screen.getByRole("textbox", { name: "搜索" });
    search.focus();
    fireEvent.change(search, { target: { value: "示例" } });
    await act(async () => {
      for (let index = 0; index < 3; index++) window.dispatchEvent(new Event("focus"));
      await request("agents");
    });
    expect(screen.getByRole("button", { name: "操作 1" })).toBeTruthy();

    fireEvent.click(screen.getByRole("link", { name: "技能" }));
    await screen.findByRole("heading", { name: "技能页面" });
    fireEvent.click(screen.getByRole("link", { name: "员工" }));
    await screen.findByRole("heading", { name: "员工页面" });
    expect(screen.getByText("fixture-admin")).toBeTruthy();
    expect(identityCalls()).toHaveLength(1);
    view.unmount();
  });

  it("loads identity again when entering a new workspace boundary", async () => {
    const first = renderWorkspace();
    await screen.findByText("fixture-admin");
    first.unmount();
    expect(channels[0].close).toHaveBeenCalledOnce();

    currentIdentity = { ...identity, actor: { kind: "guest", user: null }, permissions: [] };
    const second = renderWorkspace();
    await screen.findByText("游客");
    expect(identityCalls()).toHaveLength(2);
    second.unmount();
  });

  it("refreshes identity and clears the old workspace after a cross-tab session change", async () => {
    const view = renderWorkspace();
    await screen.findByText("fixture-admin");
    fireEvent.click(screen.getByRole("button", { name: "操作 0" }));
    currentIdentity = { ...identity, actor: { kind: "guest", user: null }, permissions: [] };

    await act(async () => channels[0].onmessage?.());

    await screen.findByText("游客");
    expect(screen.queryByText("fixture-admin")).toBeNull();
    expect(screen.getByRole("button", { name: "操作 0" })).toBeTruthy();
    expect(identityCalls()).toHaveLength(2);
    view.unmount();
  });

  it("refreshes permissions after a business API returns permission_denied", async () => {
    const view = renderWorkspace();
    await screen.findByText("fixture-admin");
    fetcher.mockResolvedValueOnce(
      Response.json(
        { detail: { code: "permission_denied", message: "无权操作" } },
        { status: 403 },
      ),
    );

    await act(async () => {
      await expect(request("agents")).rejects.toMatchObject({ status: 403 });
    });

    await screen.findByText("fixture-admin");
    expect(identityCalls()).toHaveLength(2);
    view.unmount();
  });

  it("allows manual retry when the initial identity request fails", async () => {
    fetcher.mockRejectedValueOnce(new TypeError("offline"));
    const view = renderWorkspace();
    const retry = await screen.findByRole("button", { name: "重新连接" });
    expect(screen.queryByText("fixture-admin")).toBeNull();

    fireEvent.click(retry);

    await screen.findByText("fixture-admin");
    expect(identityCalls()).toHaveLength(2);
    view.unmount();
  });
});

it("keeps an identity service failure separate from a guest identity and can recover", async () => {
  fetcher.mockResolvedValueOnce(
    Response.json(
      { detail: { code: "database_busy", message: "身份服务暂不可用" } },
      { status: 503 },
    ),
  );
  const view = renderWorkspace();
  await screen.findByRole("heading", { name: "暂时无法确认登录状态" });
  expect(screen.queryByText("游客")).toBeNull();
  expect(screen.queryByText("fixture-admin")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "重新连接" }));
  await screen.findByText("fixture-admin");
  expect(identityCalls()).toHaveLength(2);
  view.unmount();
});
it("reconfirms an unqualified streaming revocation while keeping a valid session", async () => {
  const view = renderWorkspace();
  await screen.findByText("fixture-admin");
  await act(async () => window.dispatchEvent(new Event("auth:permissions-changed")));
  await screen.findByText("fixture-admin");
  expect(identityCalls()).toHaveLength(2);
  expect(window.location.pathname).not.toBe("/signin");
  view.unmount();
});

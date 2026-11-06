// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiError, request } from "@/lib/api/http";
import { AccountMenu } from "./AccountMenu";

vi.mock("@/lib/api/http", async (original) => ({
  ...(await original<typeof import("@/lib/api/http")>()),
  request: vi.fn(),
}));
vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({
    actor: { kind: "user", user: { id: "owner", username: "测试账号" } },
    permissions: [],
  }),
}));
beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);

it("keeps a rejected logout local and preserves public diagnostic metadata", async () => {
  vi.mocked(request).mockRejectedValue(
    new ApiError("本次退出请求被拒绝", 403, "invalid_origin", { requestId: "logout-rejected" }),
  );
  const ended = vi.fn();
  window.addEventListener("auth:session-ended", ended);
  try {
    render(<AccountMenu />);
    fireEvent.click(screen.getByRole("button", { name: "测试账号，账户菜单" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "退出登录" }));
    await screen.findByText("本次退出请求被拒绝");
    expect(screen.getByText("问题编号：logout-rejected")).toBeTruthy();
    expect(ended).not.toHaveBeenCalled();
    expect(request).toHaveBeenCalledTimes(1);
  } finally {
    window.removeEventListener("auth:session-ended", ended);
  }
});

it("hides unexpected logout exception text and keeps the menu usable", async () => {
  vi.mocked(request).mockRejectedValue(new Error("private session value"));
  render(<AccountMenu />);
  fireEvent.click(screen.getByRole("button", { name: "测试账号，账户菜单" }));
  fireEvent.click(await screen.findByRole("menuitem", { name: "退出登录" }));
  await screen.findByText("还无法确认是否提交成功");
  expect(screen.queryByText(/private session/)).toBeNull();
  expect(screen.getByRole("menuitem", { name: "退出登录" }).hasAttribute("disabled")).toBe(false);
});

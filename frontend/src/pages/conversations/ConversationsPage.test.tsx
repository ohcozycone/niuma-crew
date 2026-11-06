// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { ConversationPage } from "./ConversationsPage";
import { getConversations, type ConversationPage as HistoryPage } from "@/lib/api/conversations";
vi.mock("@/state/auth/useIdentity", () => ({
  useIdentity: () => ({
    permissions: ["agents:read", "runs:create"],
    actor: { kind: "user", user: { id: "u", username: "test" } },
    expires_at: "2099",
  }),
}));
vi.mock("@/lib/api/conversations", () => ({ getConversations: vi.fn() }));
vi.mock("./ConversationPanel", () => ({
  ConversationPanel: ({ id, agentId }: { id?: string; agentId?: string }) => (
    <p>{agentId ? "空白对话" : `继续 ${id}`}</p>
  ),
}));
function Location() {
  return <p>{useLocation().search}</p>;
}
function open(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Location />
      <Routes>
        <Route path="/conversations/new" element={<ConversationPage />} />
        <Route path="/conversations/:id" element={<ConversationPage />} />
      </Routes>
    </MemoryRouter>,
  );
}
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  sessionStorage.clear();
});
it("opens the latest conversation for the employee and preserves return context", async () => {
  vi.mocked(getConversations).mockResolvedValue({ items: [{ id: "latest" }] } as HistoryPage);
  open("/conversations/new?agent=employee&resume=1&from=%2Fagents");
  await screen.findByText("继续 latest");
  expect(getConversations).toHaveBeenCalledWith(
    { agentId: "employee", limit: 1 },
    expect.any(AbortSignal),
  );
  expect(screen.getByText("?agent=employee&from=%2Fagents")).toBeTruthy();
});
it("opens a blank conversation when there is no history", async () => {
  vi.mocked(getConversations).mockResolvedValue({ items: [] } as unknown as HistoryPage);
  open("/conversations/new?agent=employee&resume=1");
  await screen.findByText("空白对话");
});
it("always keeps an explicit new conversation blank", async () => {
  open("/conversations/new?agent=employee");
  expect(await screen.findByText("空白对话")).toBeTruthy();
  expect(getConversations).not.toHaveBeenCalled();
});
it("does not mistake a read failure for empty history and allows retry", async () => {
  vi.mocked(getConversations).mockRejectedValueOnce(new Error("网络错误"));
  open("/conversations/new?agent=employee&resume=1");
  await screen.findByRole("alert");
  expect(screen.queryByText("空白对话")).toBeNull();
  vi.mocked(getConversations).mockResolvedValueOnce({ items: [{ id: "latest" }] } as HistoryPage);
  fireEvent.click(screen.getByRole("button", { name: "重新加载最近对话" }));
  await waitFor(() => expect(screen.getByText("继续 latest")).toBeTruthy());
});

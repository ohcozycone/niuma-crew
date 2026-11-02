import { ApiError } from "@/lib/api/http";
// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { ConversationHistory } from "./ConversationHistory";
import { getConversations, type Conversation } from "@/lib/api/conversations";
vi.mock("@/lib/api/conversations", () => ({ getConversations: vi.fn() }));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
function Location() {
  return <p data-testid="location">{useLocation().search}</p>;
}
const item = (id: string) =>
  ({
    id,
    title: `话题 ${id}`,
    agent_name: "老赵",
    updated_at: "2026-10-24T08:00:00Z",
    active_response_id: null,
  }) as Conversation;
it("keeps employee-history paging local and preserves the return context when switching", async () => {
  vi.mocked(getConversations).mockImplementation(async ({ offset = 0 } = {}) => ({
    items: [item(offset === 0 ? "current" : "older")],
    total: 26,
    offset,
    limit: 20,
  }));
  render(
    <MemoryRouter initialEntries={["/conversations/current?from=%2Fagents"]}>
      <Location />
      <ConversationHistory agentId="agent" activeId="current" returnTo="/agents" />
    </MemoryRouter>,
  );
  const current = await screen.findByRole("link", { name: /话题 current/ });
  expect(current.getAttribute("aria-current")).toBe("page");
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  const older = await screen.findByRole("link", { name: /话题 older/ });
  expect(older.getAttribute("href")).toBe("/conversations/older?from=%2Fagents");
  expect(screen.getByTestId("location").textContent).toBe("?from=%2Fagents");
  expect(screen.getByText("2 / 2")).toBeTruthy();
  expect((screen.getByRole("button", { name: "下一页" }) as HTMLButtonElement).disabled).toBe(true);
  expect(getConversations).toHaveBeenLastCalledWith(
    { agentId: "agent", offset: 20 },
    expect.any(AbortSignal),
  );
});
it("keeps full-history paging in the URL for browser navigation", async () => {
  vi.mocked(getConversations).mockImplementation(async ({ offset = 0 } = {}) => ({
    items: [item(String(offset))],
    total: 26,
    offset,
    limit: 20,
  }));
  render(
    <MemoryRouter initialEntries={["/conversations"]}>
      <Location />
      <ConversationHistory />
    </MemoryRouter>,
  );
  await screen.findByRole("link", { name: /话题 0/ });
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  await screen.findByRole("link", { name: /话题 20/ });
  expect(screen.getByTestId("location").textContent).toBe("?offset=20");
});

it("keeps the last loaded history page visible when another page fails", async () => {
  vi.mocked(getConversations)
    .mockResolvedValueOnce({ items: [item("loaded")], total: 26, offset: 0, limit: 20 })
    .mockRejectedValueOnce(new ApiError("历史暂不可读", 503, "database_busy"));
  render(
    <MemoryRouter>
      <ConversationHistory />
    </MemoryRouter>,
  );
  await screen.findByRole("link", { name: /话题 loaded/ });
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  expect((await screen.findByRole("alert")).textContent).toContain("历史暂不可读");
  expect(screen.getByRole("link", { name: /话题 loaded/ })).toBeTruthy();
});

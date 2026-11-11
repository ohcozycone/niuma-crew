// @vitest-environment jsdom
import type { ComponentProps } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ConversationMessage } from "./ConversationMessage";
import type { ConversationMessage as MessageView } from "./conversationState";
import { runFixture } from "./conversationTestHelpers";

const state = vi.hoisted(() => ({ message: null as MessageView | null }));
vi.mock("./useMessage", () => ({
  useMessage: () => ({ message: state.message, actions: {} }),
}));
vi.mock("@/components/avatars/index", () => ({ AgentAvatar: () => null }));
vi.mock("@/components/common/Markdown", () => ({
  Markdown: ({ text }: { text: string }) => <p>{text}</p>,
}));
vi.mock("@/components/ui/MessageScroller", () => ({
  MessageScrollerItem: ({ children, ref, ...props }: ComponentProps<"div">) => (
    <div ref={ref} className={props.className} tabIndex={props.tabIndex}>
      {children}
    </div>
  ),
}));
afterEach(cleanup);

const view = () => (
  <ConversationMessage messageId="a1" agentName="全栈工程师老赵" registerMessage={() => () => {}} />
);
it("shows identity in the header and a single completed execution summary", () => {
  const run = runFixture({ status: "succeeded", content: "完成的回答" });
  state.message = { id: run.id, role: "assistant", content: run.content, published: true, run };
  const { container } = render(view());
  expect(container.querySelector('[data-slot="message-header"]')?.textContent).toBe(
    "全栈工程师老赵",
  );
  expect(screen.getAllByText("已完成")).toHaveLength(1);
});
it("uses one progress row from queuing to execution without duplicate waiting text", async () => {
  const run = runFixture({ status: "queued", steps: [], content: "", started_at: null });
  state.message = { id: run.id, role: "assistant", content: "", published: false, run };
  const { rerender, container } = render(view());
  expect(screen.getByText("排队中")).toBeTruthy();
  expect(screen.queryByText("等待模型响应…")).toBeNull();
  expect(screen.queryByRole("button", { name: "执行过程" })).toBeNull();
  state.message = { ...state.message, run: runFixture({ content: "", steps: [] }) };
  rerender(view());
  expect(await screen.findByText("执行中")).toBeTruthy();
  expect(container.querySelectorAll('[data-slot="run-activity"]')).toHaveLength(1);
});

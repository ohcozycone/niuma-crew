// @vitest-environment jsdom
import { StrictMode, type ComponentProps } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ConversationTranscript } from "./ConversationTranscript";
import type { ConversationOutline } from "./ConversationOutline";
import type { ConversationMessage } from "./conversationState";
import type { ConversationView } from "./conversationStore";
import { runFixture } from "./conversationTestHelpers";

const state = vi.hoisted(() => ({
  chat: null as unknown as ConversationView,
  messages: new Map<string, ConversationMessage>(),
  outline: null as unknown as ComponentProps<typeof ConversationOutline>,
  scrollToMessage: vi.fn<(id: string, options: unknown) => boolean>(() => true),
  scrollToEnd: vi.fn(() => true),
}));
vi.mock("./useConversation", () => ({ useConversation: () => state.chat }));
vi.mock("./useMessage", () => ({
  useMessage: (id: string) => ({
    message: state.messages.get(id) ?? null,
    actions: {},
  }),
}));
vi.mock("./ConversationOutline", () => ({
  ConversationOutline: (props: ComponentProps<typeof ConversationOutline>) => {
    state.outline = props;
    return <output data-testid="visible">{props.visibleQuestionIds.join(",")}</output>;
  },
}));
vi.mock("@/components/avatars/index", () => ({ AgentAvatar: () => null }));
vi.mock("@/components/common/Markdown", () => ({
  Markdown: ({ text }: { text: string }) => <p>{text}</p>,
}));
vi.mock("./RunActions", () => ({ RunActions: () => null }));
vi.mock("@/components/ui/MessageScroller", () => ({
  MessageScroller: ({ children }: ComponentProps<"div">) => <div>{children}</div>,
  MessageScrollerViewport: (props: ComponentProps<"div">) => <div role="region" {...props} />,
  MessageScrollerContent: (props: ComponentProps<"div">) => <div {...props} />,
  MessageScrollerItem: ({
    messageId,
    scrollAnchor,
    ...props
  }: ComponentProps<"div"> & {
    messageId: string;
    scrollAnchor?: boolean;
  }) => <div data-message-id={messageId} data-scroll-anchor={!!scrollAnchor} {...props} />,
  MessageScrollerButton: ({ onClick }: { onClick: () => void }) => (
    <button onClick={onClick}>回到最新</button>
  ),
  useMessageScroller: () => ({
    scrollToMessage: state.scrollToMessage,
    scrollToEnd: state.scrollToEnd,
  }),
}));

const bounds = (top: number, bottom: number, left = 0, right = 600) =>
  ({ top, bottom, left, right, height: bottom - top, width: right - left }) as DOMRect;
const geometry = new Map<string, DOMRect>();
const observers: Array<{
  callback: () => void;
  observe: ReturnType<typeof vi.fn>;
  unobserve: ReturnType<typeof vi.fn>;
  disconnect: ReturnType<typeof vi.fn>;
}> = [];
beforeEach(() => {
  geometry.clear();
  observers.length = 0;
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    const element = this as HTMLElement;
    return element.getAttribute("aria-label") === "对话消息"
      ? bounds(100, 400)
      : (geometry.get(element.dataset.messageId ?? "") ?? bounds(0, 0));
  });
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe = vi.fn();
      unobserve = vi.fn();
      disconnect = vi.fn();
      constructor(readonly callback: () => void) {
        observers.push(this);
      }
    },
  );
  state.messages.clear();
  state.chat = {
    id: "chat",
    phase: "ready",
    conversation: { id: "chat" },
    latestQuestionId: "q3",
    messageIds: [],
    history: {
      position: null,
      isHistorical: false,
      hasMore: false,
      hasNewer: false,
      isLoading: false,
      loading: null,
      error: null,
      errorOrigin: null,
      jump: vi.fn(async () => true),
      showLatest: vi.fn(async () => {}),
      loadMore: vi.fn(async () => {}),
      loadNewer: vi.fn(async () => {}),
    },
  } as unknown as ConversationView;
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});
function message(id: string, questionId: string, top: number, bottom: number) {
  const user = id === questionId;
  state.messages.set(id, {
    id,
    role: user ? "user" : "assistant",
    content: `正文 ${id}`,
    published: true,
    run: user
      ? null
      : runFixture({ id, reply_to_message_id: questionId, status: "succeeded", steps: [] }),
  });
  geometry.set(id, bounds(top, bottom));
  state.chat = { ...state.chat, messageIds: [...state.chat.messageIds, id] };
}
const view = () => <ConversationTranscript agentName="资料整理员" avatarId="admin" />;
const flush = () =>
  act(async () => {
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
  });
const visible = () => screen.getByTestId("visible").textContent;

it("registers explicit ownership and highlights every partly visible group", () => {
  message("q1", "q1", -100, -50);
  message("a1", "q1", -20, 101);
  message("q2", "q2", 130, 170);
  message("a2", "q2", 190, 300);
  message("q3", "q3", 399, 450);
  message("a3", "q3", 470, 600);
  render(view());
  expect(visible()).toBe("q1,q2,q3");
  expect(document.querySelector("[data-question-id]")).toBeNull();
  expect(Object.keys(state.outline).sort()).toEqual([
    "conversationId",
    "latestQuestionId",
    "navigation",
    "visibleQuestionIds",
  ]);
});
it("groups long answers and retries without requiring their question in the window", () => {
  message("a1", "unloaded-question", -1000, 200);
  message("retry", "unloaded-question", 230, 1200);
  render(view());
  expect(visible()).toBe("unloaded-question");
});
it("excludes boundary contact, zero-size nodes and content outside the viewport", () => {
  message("q1", "q1", 0, 100);
  message("q2", "q2", 400, 450);
  message("q3", "q3", 200, 200);
  message("q4", "q4", 200, 230);
  geometry.set("q4", bounds(200, 230, 600, 700));
  render(view());
  expect(visible()).toBe("");
});
it("keeps DOM reading order after history is prepended and unregisters removed rows", async () => {
  message("q2", "q2", 200, 250);
  const { rerender } = render(view());
  expect(visible()).toBe("q2");
  const old = document.querySelector('[data-message-id="q2"]');
  message("a1", "q1", 110, 150);
  state.chat = { ...state.chat, messageIds: ["a1", "q2"] };
  rerender(view());
  await flush();
  expect(visible()).toBe("q1,q2");
  state.chat = { ...state.chat, messageIds: ["a1"] };
  rerender(view());
  await flush();
  expect(visible()).toBe("q1");
  expect(observers[0].unobserve).toHaveBeenCalledWith(old);
});
it("replaces a message node without keeping the old registration", async () => {
  message("q2", "q2", 150, 200);
  const saved = state.messages.get("q2")!;
  const { rerender } = render(view());
  const old = document.querySelector('[data-message-id="q2"]');
  state.messages.delete("q2");
  rerender(<ConversationTranscript agentName="更新的员工" avatarId="admin" />);
  await flush();
  expect(visible()).toBe("");
  expect(observers[0].unobserve).toHaveBeenCalledWith(old);
  state.messages.set("q2", saved);
  rerender(view());
  await flush();
  const replacement = document.querySelector('[data-message-id="q2"]');
  expect(replacement).not.toBe(old);
  expect(visible()).toBe("q2");
  expect(observers[0].observe).toHaveBeenCalledWith(replacement);
});
it("updates on scroll and row resizing while keeping unchanged visibility stable", async () => {
  message("a1", "q1", -500, 350);
  message("q2", "q2", 380, 430);
  render(view());
  const previous = state.outline.visibleQuestionIds;
  fireEvent.scroll(screen.getByRole("region"));
  await flush();
  expect(state.outline.visibleQuestionIds).toBe(previous);
  geometry.set("a1", bounds(-1000, 100));
  geometry.set("q2", bounds(120, 170));
  fireEvent.scroll(screen.getByRole("region"));
  await flush();
  expect(visible()).toBe("q2");
  geometry.set("a1", bounds(-1000, 110));
  observers[0].callback();
  await flush();
  expect(visible()).toBe("q1,q2");
});
it("focuses the registered question after committing a jump and replays feedback without remounting", async () => {
  message("q2", "q2", 150, 200);
  const { rerender } = render(view());
  const node = document.querySelector('[data-message-id="q2"]')!;
  const bubble = node.querySelector("[data-slot=bubble]");
  act(() => state.outline.navigation.navigate("q2"));
  expect(state.chat.history.jump).toHaveBeenCalledWith("q2");
  expect(state.scrollToMessage).not.toHaveBeenCalled();
  state.chat = {
    ...state.chat,
    history: { ...state.chat.history, position: { key: 1, target: "q2" } },
  };
  rerender(view());
  await flush();
  expect(state.scrollToMessage).toHaveBeenCalledWith("q2", {
    align: "start",
    scrollMargin: 16,
    behavior: "auto",
  });
  expect(document.activeElement).toBe(node);
  expect(document.querySelector('[data-message-id="q2"]')).toBe(node);
  expect(node.querySelector("[data-slot=bubble]")).not.toBe(bubble);
  expect(visible()).toBe("q2");
  const firstFeedback = node.querySelector("[data-slot=bubble]");
  state.chat = {
    ...state.chat,
    history: { ...state.chat.history, position: { key: 2, target: "q2" } },
  };
  rerender(view());
  await flush();
  expect(document.querySelector('[data-message-id="q2"]')).toBe(node);
  expect(node.querySelector("[data-slot=bubble]")).not.toBe(firstFeedback);
});
it("cancels an older placement and exposes only jump loading and errors to navigation", async () => {
  message("q1", "q1", 110, 160);
  message("q2", "q2", 190, 240);
  const { rerender } = render(view());
  state.chat = {
    ...state.chat,
    history: { ...state.chat.history, position: { key: 1, target: "q1" } },
  };
  rerender(view());
  state.chat = {
    ...state.chat,
    history: {
      ...state.chat.history,
      position: { key: 2, target: "q2" },
      loading: "older",
      error: "读取更早消息失败",
      errorOrigin: "older",
    },
  };
  rerender(view());
  await flush();
  expect(state.scrollToMessage).toHaveBeenCalledTimes(1);
  expect(state.scrollToMessage.mock.calls[0][0]).toBe("q2");
  expect(state.outline.navigation.pending).toBe(false);
  expect(state.outline.navigation.error).toBeNull();
  state.chat = {
    ...state.chat,
    history: { ...state.chat.history, loading: "jump", error: null, errorOrigin: null },
  };
  rerender(view());
  expect(state.outline.navigation.pending).toBe(true);
  state.chat = {
    ...state.chat,
    history: { ...state.chat.history, loading: null, error: "目标读取失败", errorOrigin: "jump" },
  };
  rerender(view());
  expect(state.outline.navigation.error).toBe("目标读取失败");
});
it("cleans observers and pending frames and makes captured navigation inert after unmount", async () => {
  message("q1", "q1", 120, 170);
  const { unmount } = render(<StrictMode>{view()}</StrictMode>);
  expect(visible()).toBe("q1");
  const navigate = state.outline.navigation.navigate;
  fireEvent.scroll(screen.getByRole("region"));
  unmount();
  await flush();
  for (const observer of observers) expect(observer.disconnect).toHaveBeenCalledOnce();
  navigate("q1");
  expect(state.chat.history.jump).not.toHaveBeenCalled();
});

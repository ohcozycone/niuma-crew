// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  getMessages,
  getQuestions,
  getQuestionPreview,
  type ConversationQuestion,
} from "@/lib/api/conversations";
import { ConversationOutline } from "./ConversationOutline";
const visibility = vi.hoisted(() => ({ questionIds: ["q9988"] }));
vi.mock("@/lib/api/conversations", async (original) => ({
  ...(await original<typeof import("@/lib/api/conversations")>()),
  getQuestions: vi.fn(),
  getMessages: vi.fn(),
  getQuestionPreview: vi.fn(),
}));
const question = (number: number): ConversationQuestion => ({
  id: `q${number}`,
  number,
  sequence: number * 2 - 1,
  preview: `问题 ${number}`,
  created_at: "2026-10-24T00:00:00Z",
});
beforeEach(() => {
  vi.mocked(getQuestions).mockImplementation(async (_id, _q, after, _signal, options) => ({
    items: Array.from({ length: Math.min(100, 10001 - (options?.startNumber ?? 1)) }, (_, i) =>
      question(
        (options?.startNumber ? options.startNumber - 1 : after ? (after + 1) / 2 : 0) + i + 1,
      ),
    ),
    total: 10000,
    next_after_sequence: after ? null : 199,
    anchor: options?.anchor ? question(Number(options.anchor.slice(1))) : null,
  }));
  vi.mocked(getMessages).mockResolvedValue({
    items: [],
    has_more: false,
    next_before_sequence: null,
  });
  vi.mocked(getQuestionPreview).mockImplementation(async (_id, questionId) => ({
    question_id: questionId,
    question: `问题 ${questionId.slice(1)}`,
    answer: "已保存的回答",
    response_id: "run",
    id: "answer",
    version: 1,
    status: "succeeded",
  }));
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  visibility.questionIds = ["q9988"];
});
const outline = (onJump = vi.fn(async () => true)) => (
  <ConversationOutline
    conversationId="chat"
    latestQuestionId={null}
    visibleQuestionIds={visibility.questionIds}
    navigation={{ pending: false, error: null, navigate: onJump }}
  />
);
it("does not read a draft conversation and releases directory requests when disconnected", async () => {
  const { rerender } = render(
    <ConversationOutline
      conversationId={null}
      latestQuestionId={null}
      visibleQuestionIds={[]}
      navigation={{ pending: false, error: null, navigate: () => {} }}
    />,
  );
  expect(getQuestions).not.toHaveBeenCalled();
  rerender(outline());
  await screen.findByRole("button", { name: "跳转到第 9988 个问题：问题 9988" });
  const signals = vi.mocked(getQuestions).mock.calls.map((call) => call[3]);
  rerender(
    <ConversationOutline
      conversationId={null}
      latestQuestionId={null}
      visibleQuestionIds={[]}
      navigation={{ pending: false, error: null, navigate: () => {} }}
    />,
  );
  expect(screen.queryByRole("navigation")).toBeNull();
  expect(signals.every((signal) => signal?.aborted)).toBe(true);
});
it("resolves a distant reading position and makes neighboring ticks directly clickable", async () => {
  const onJump = vi.fn(async () => true);
  const { container } = render(outline(onJump));
  const current = await screen.findByRole("button", { name: "跳转到第 9988 个问题：问题 9988" });
  expect(current.getAttribute("aria-description")).toBe("此轮对话当前可见");
  expect(getQuestions).toHaveBeenCalledWith("chat", "", undefined, expect.any(AbortSignal), {
    anchor: "q9988",
    limit: 1,
  });
  const neighbor = await screen.findByRole("button", { name: "跳转到第 9987 个问题：问题 9987" });
  expect(getQuestions).toHaveBeenCalledWith("chat", "", undefined, expect.any(AbortSignal), {
    startNumber: 9941,
  });
  expect(container.querySelectorAll("[data-question-number]").length).toBeLessThanOrEqual(21);
  fireEvent.click(neighbor);
  await waitFor(() => expect(onJump).toHaveBeenCalledWith("q9987"));
  expect(getMessages).not.toHaveBeenCalled();
  expect(screen.queryByRole("textbox")).toBeNull();
});
it("highlights all visible groups and keeps clicks anchored to their questions", async () => {
  visibility.questionIds = ["q2", "q3", "q4"];
  const onJump = vi.fn(async () => true);
  const { container, rerender } = render(outline(onJump));
  await screen.findByRole("button", { name: "跳转到第 2 个问题：问题 2" });
  expect(
    [...container.querySelectorAll("[data-visible]")].map((tick) =>
      tick.getAttribute("data-question-number"),
    ),
  ).toEqual(["2", "3", "4"]);
  for (const number of [2, 3, 4]) {
    expect(
      screen
        .getByRole("button", { name: `跳转到第 ${number} 个问题：问题 ${number}` })
        .getAttribute("aria-description"),
    ).toBe("此轮对话当前可见");
  }
  fireEvent.click(screen.getByRole("button", { name: "跳转到第 3 个问题：问题 3" }));
  expect(onJump).toHaveBeenCalledWith("q3");
  // 点击不会用目标覆盖可见集合；位置变化后才根据实际内容更新。
  expect(container.querySelectorAll("[data-visible]")).toHaveLength(3);
  visibility.questionIds = ["q3", "q4"];
  rerender(outline(onJump));
  expect(container.querySelectorAll("[data-visible]")).toHaveLength(2);
  expect(container.querySelector('[data-question-number="2"][data-visible]')).toBeNull();
});
it("previews on keyboard focus without jumping, and Escape dismisses it", async () => {
  visibility.questionIds = ["q3"];
  const onJump = vi.fn(async () => true);
  render(outline(onJump));
  const trigger = await screen.findByRole("button", { name: "跳转到第 3 个问题：问题 3" });
  act(() => trigger.focus());
  expect(await screen.findByRole("tooltip")).toBeTruthy();
  expect(screen.getByText("问题 3")).toBeTruthy();
  await waitFor(() =>
    expect(getQuestionPreview).toHaveBeenCalledWith("chat", "q3", expect.any(AbortSignal)),
  );
  expect(onJump).not.toHaveBeenCalled();
  fireEvent.keyDown(trigger, { key: "Escape", code: "Escape" });
  await waitFor(() => expect(screen.queryByRole("tooltip")).toBeNull());
  expect(onJump).not.toHaveBeenCalled();
});
it("opens a preview on hover while keeping the reading position unchanged", async () => {
  visibility.questionIds = ["q3"];
  const onJump = vi.fn(async () => true);
  render(outline(onJump));
  const trigger = await screen.findByRole("button", { name: "跳转到第 2 个问题：问题 2" });
  fireEvent.mouseEnter(trigger);
  fireEvent.mouseMove(trigger);
  expect(await screen.findByRole("tooltip")).toBeTruthy();
  expect(screen.getByText("问题 2")).toBeTruthy();
  expect(onJump).not.toHaveBeenCalled();
  expect(
    screen
      .getByRole("button", { name: "跳转到第 3 个问题：问题 3" })
      .getAttribute("aria-description"),
  ).toBe("此轮对话当前可见");
});
it("keeps previews closed while ticks move under a stationary pointer after a jump", async () => {
  visibility.questionIds = ["q19"];
  vi.mocked(getQuestions).mockResolvedValue({
    items: Array.from({ length: 19 }, (_, i) => question(i + 1)),
    total: 19,
    next_after_sequence: null,
  });
  const onJump = vi.fn(async () => true);
  const { rerender } = render(outline(onJump));
  const target = await screen.findByRole("button", { name: "跳转到第 8 个问题：问题 8" });
  fireEvent.mouseEnter(target);
  fireEvent.mouseMove(target);
  await screen.findByRole("tooltip");
  fireEvent.click(target, { clientX: 20, clientY: 30 });
  visibility.questionIds = ["q8"];
  rerender(outline(onJump));
  await waitFor(() => expect(screen.queryByRole("tooltip")).toBeNull());
  const shifted = screen.getByRole("button", { name: "跳转到第 3 个问题：问题 3" });
  fireEvent.mouseEnter(shifted);
  fireEvent.mouseMove(shifted, { clientX: 20, clientY: 30 });
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 120));
  });
  expect(screen.queryByRole("tooltip")).toBeNull();
  // 键盘焦点是明确的新预览意图，不受鼠标静止保护影响。
  act(() => shifted.focus());
  expect(await screen.findByRole("tooltip")).toBeTruthy();
  expect(screen.getByText("问题 3")).toBeTruthy();
});
it("aborts old conversation requests and clears its ticks when switching conversations", async () => {
  const { rerender } = render(outline());
  await screen.findByRole("button", { name: "跳转到第 9988 个问题：问题 9988" });
  const oldSignal = vi.mocked(getQuestions).mock.calls[0][3];
  vi.mocked(getQuestions).mockReturnValue(new Promise(() => {}));
  visibility.questionIds = ["new-question"];
  rerender(
    <ConversationOutline
      conversationId="other"
      latestQuestionId={null}
      visibleQuestionIds={visibility.questionIds}
      navigation={{ pending: false, error: null, navigate: () => {} }}
    />,
  );
  expect(oldSignal?.aborted).toBe(true);
  expect(screen.queryByRole("navigation", { name: "问题导航" })).toBeNull();
});
it("scrolls the ruler independently across metadata pages, then jumps using the loaded question ID", async () => {
  const onJump = vi.fn(async () => true);
  const outerWheel = vi.fn();
  const { container } = render(<div onWheel={outerWheel}>{outline(onJump)}</div>);
  await screen.findByRole("button", { name: "跳转到第 9987 个问题：问题 9987" });
  const ruler = container.querySelector("[data-slot=conversation-ruler]")!;
  const wheel = new WheelEvent("wheel", { deltaY: -600, bubbles: true, cancelable: true });
  fireEvent(ruler, wheel);
  expect(wheel.defaultPrevented).toBe(true);
  expect(outerWheel).not.toHaveBeenCalled();
  expect(ruler.getAttribute("data-window-start")).toBe("9921");
  const target = await screen.findByRole("button", { name: "跳转到第 9922 个问题：问题 9922" });
  expect(getQuestions).toHaveBeenCalledWith("chat", "", undefined, expect.any(AbortSignal), {
    startNumber: 9881,
  });
  expect(onJump).not.toHaveBeenCalled();
  expect(getMessages).not.toHaveBeenCalled();
  expect(visibility.questionIds[0]).toBe("q9988");
  expect(container.querySelectorAll("[data-question-number]").length).toBeLessThanOrEqual(21);
  fireEvent.click(target);
  await waitFor(() => expect(onJump).toHaveBeenCalledWith("q9922"));
});
it("reaches both ends immediately and resumes following when the main reading position changes", async () => {
  const { container, rerender } = render(outline());
  await screen.findByRole("button", { name: "跳转到第 9987 个问题：问题 9987" });
  const ruler = container.querySelector("[data-slot=conversation-ruler]")!;
  fireEvent.keyDown(ruler, { key: "End" });
  expect(ruler.getAttribute("data-window-start")).toBe("9987");
  fireEvent.keyDown(ruler, { key: "ArrowUp" });
  expect(ruler.getAttribute("data-window-start")).toBe("9986");
  fireEvent.keyDown(ruler, { key: "Home" });
  expect(ruler.getAttribute("data-window-start")).toBe("0");
  expect(await screen.findByRole("button", { name: "跳转到第 1 个问题：问题 1" })).toBeTruthy();
  visibility.questionIds = ["q5000"];
  rerender(outline());
  const current = await screen.findByRole("button", { name: "跳转到第 5000 个问题：问题 5000" });
  expect(current.getAttribute("aria-description")).toBe("此轮对话当前可见");
  expect(ruler.getAttribute("data-window-start")).toBe("4993");
  visibility.questionIds = ["q9988"];
  rerender(outline());
  expect(ruler.getAttribute("data-window-start")).toBe("9981");
});
it("aborts superseded metadata reads and ignores late results while browsing", async () => {
  const { container } = render(outline());
  await screen.findByRole("button", { name: "跳转到第 9987 个问题：问题 9987" });
  const normal = vi.mocked(getQuestions).getMockImplementation()!;
  let completeOld!: (page: Awaited<ReturnType<typeof getQuestions>>) => void;
  vi.mocked(getQuestions).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        completeOld = resolve;
      }),
  );
  const ruler = container.querySelector("[data-slot=conversation-ruler]")!;
  fireEvent.wheel(ruler, { deltaY: -600 });
  await waitFor(() => expect(completeOld).toBeDefined());
  const old = vi.mocked(getQuestions).mock.calls.at(-1)!;
  fireEvent.wheel(ruler, { deltaY: -600 });
  await screen.findByRole("button", { name: "跳转到第 9862 个问题：问题 9862" });
  expect(old[3]?.aborted).toBe(true);
  await act(async () => {
    completeOld(await normal(...old));
  });
  expect(ruler.getAttribute("data-window-start")).toBe("9861");
  expect(screen.queryByRole("button", { name: "跳转到第 9922 个问题：问题 9922" })).toBeNull();
});
it("retries a failed metadata page without moving the main conversation", async () => {
  const onJump = vi.fn(async () => true);
  const { container } = render(outline(onJump));
  await screen.findByRole("button", { name: "跳转到第 9987 个问题：问题 9987" });
  vi.mocked(getQuestions).mockRejectedValueOnce(new Error("读取暂时失败"));
  const ruler = container.querySelector("[data-slot=conversation-ruler]")!;
  fireEvent.wheel(ruler, { deltaY: -600 });
  fireEvent.click(await screen.findByRole("button", { name: "重试问题导航" }));
  expect(
    await screen.findByRole("button", { name: "跳转到第 9922 个问题：问题 9922" }),
  ).toBeTruthy();
  expect(ruler.getAttribute("data-window-start")).toBe("9921");
  expect(onJump).not.toHaveBeenCalled();
});
it.each([0, 1, 2])("hides navigation for %i questions using the server total", async (total) => {
  visibility.questionIds = ["q1"];
  vi.mocked(getQuestions).mockResolvedValue({
    items: Array.from({ length: total }, (_, i) => question(i + 1)),
    total,
    next_after_sequence: null,
  });
  render(outline());
  await act(async () => {});
  expect(screen.queryByRole("navigation", { name: "问题导航" })).toBeNull();
  expect(getQuestions).toHaveBeenCalledTimes(1);
  expect(getQuestionPreview).not.toHaveBeenCalled();
});
it("shows navigation when the third accepted question refreshes the directory", async () => {
  visibility.questionIds = ["q2"];
  vi.mocked(getQuestions).mockResolvedValue({
    items: [question(1), question(2)],
    total: 2,
    next_after_sequence: null,
  });
  const { rerender } = render(
    <ConversationOutline
      conversationId="chat"
      latestQuestionId="q2"
      visibleQuestionIds={visibility.questionIds}
      navigation={{ pending: false, error: null, navigate: () => {} }}
    />,
  );
  await act(async () => {});
  expect(screen.queryByRole("navigation", { name: "问题导航" })).toBeNull();
  vi.mocked(getQuestions).mockResolvedValue({
    items: [question(1), question(2), question(3)],
    total: 3,
    next_after_sequence: null,
  });
  visibility.questionIds = ["q3"];
  rerender(
    <ConversationOutline
      conversationId="chat"
      latestQuestionId="q3"
      visibleQuestionIds={visibility.questionIds}
      navigation={{ pending: false, error: null, navigate: () => {} }}
    />,
  );
  expect(await screen.findByRole("button", { name: "跳转到第 3 个问题：问题 3" })).toBeTruthy();
  expect(screen.getByRole("navigation", { name: "问题导航" })).toBeTruthy();
});
it("accepts an injected data source without accessing the default HTTP adapter", async () => {
  visibility.questionIds = ["q2"];
  const source = {
    questions: vi.fn().mockResolvedValue({
      items: [question(1), question(2), question(3)],
      total: 3,
      next_after_sequence: null,
    }),
    preview: vi.fn().mockResolvedValue({
      question_id: "q2",
      question: "问题 2",
      answer: "来自注入数据源",
      response_id: "run",
      id: "answer",
      version: 1,
      status: "succeeded" as const,
    }),
  };
  render(
    <ConversationOutline
      conversationId="chat"
      latestQuestionId={null}
      source={source}
      visibleQuestionIds={visibility.questionIds}
      navigation={{ pending: false, error: null, navigate: () => {} }}
    />,
  );
  const trigger = await screen.findByRole("button", { name: "跳转到第 2 个问题：问题 2" });
  act(() => trigger.focus());
  expect(await screen.findByText("来自注入数据源")).toBeTruthy();
  expect(getQuestions).not.toHaveBeenCalled();
  expect(getQuestionPreview).not.toHaveBeenCalled();
});

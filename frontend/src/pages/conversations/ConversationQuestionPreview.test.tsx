// @vitest-environment jsdom
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { QuestionPreview } from "@/lib/api/conversations";
import { ConversationQuestionPreview } from "./ConversationQuestionPreview";
import { useQuestionPreview } from "./useQuestionPreview";
import type { QuestionNavigationSource } from "./questionNavigation";
afterEach(cleanup);
const preview = (questionId: string, answer = "最新回答"): QuestionPreview => ({
  question_id: questionId,
  question: `问题 ${questionId}`,
  answer,
  response_id: "run",
  version: 1,
  status: "succeeded",
});
function Reader({
  id = "chat",
  questionId,
  read,
}: {
  id?: string;
  questionId: string;
  read: QuestionNavigationSource["preview"];
}) {
  const model = useQuestionPreview(id, questionId, read);
  return (
    <ConversationQuestionPreview
      question={model.data?.question ?? `问题 ${questionId}`}
      answer={model.data?.answer}
      loading={model.loading}
      error={model.error}
    />
  );
}
it("renders preview content without a Provider or network dependency", () => {
  render(
    <ConversationQuestionPreview
      question="用户问题"
      answer="公开回答"
      loading={false}
      error={null}
    />,
  );
  expect(screen.getByText("用户问题")).toBeTruthy();
  expect(screen.getByText("公开回答")).toBeTruthy();
});
it("reads the requested question directly and revalidates on every reopen", async () => {
  const read = vi
    .fn()
    .mockResolvedValueOnce(preview("q1", "失败时的旧回答"))
    .mockResolvedValueOnce({
      ...preview("q1", "重试后的新回答"),
      response_id: "retry",
      version: 2,
    });
  const first = render(<Reader questionId="q1" read={read} />);
  await screen.findByText("失败时的旧回答");
  first.unmount();
  render(<Reader questionId="q1" read={read} />);
  expect(await screen.findByText("重试后的新回答")).toBeTruthy();
  expect(read).toHaveBeenCalledTimes(2);
  expect(read).toHaveBeenLastCalledWith("chat", "q1", expect.any(AbortSignal));
});
it("aborts superseded reads and ignores late answers", async () => {
  let complete!: (data: QuestionPreview) => void;
  const read = vi
    .fn()
    .mockReturnValueOnce(
      new Promise((resolve) => {
        complete = resolve;
      }),
    )
    .mockResolvedValueOnce(preview("q2", "第二个问题的回答"));
  const { rerender } = render(<Reader questionId="q1" read={read} />);
  const signal = read.mock.calls[0][2] as AbortSignal;
  rerender(<Reader questionId="q2" read={read} />);
  expect(signal.aborted).toBe(true);
  await screen.findByText("第二个问题的回答");
  await act(async () => {
    complete(preview("q1", "迟到的旧回答"));
  });
  expect(screen.queryByText("迟到的旧回答")).toBeNull();
});
it("isolates conversations even when a caller reuses the same question key", async () => {
  const read = vi
    .fn()
    .mockResolvedValueOnce(preview("q", "第一段会话"))
    .mockResolvedValueOnce(preview("q", "另一段会话"));
  const { rerender } = render(<Reader id="first" questionId="q" read={read} />);
  await screen.findByText("第一段会话");
  rerender(<Reader id="second" questionId="q" read={read} />);
  expect(screen.queryByText("第一段会话")).toBeNull();
  expect(await screen.findByText("另一段会话")).toBeTruthy();
});
it("shows a fallback for empty answers and failures", async () => {
  const read = vi
    .fn()
    .mockResolvedValueOnce(preview("q1", ""))
    .mockRejectedValueOnce(new Error("offline"));
  const { rerender } = render(<Reader questionId="q1" read={read} />);
  await screen.findByText("点击刻度查看完整对话。");
  rerender(<Reader questionId="q2" read={read} />);
  expect(await screen.findByText("预览暂时无法读取，点击刻度可查看完整对话。")).toBeTruthy();
});
it("does not retain another data source's preview while a replacement source is loading", async () => {
  const first = vi.fn().mockResolvedValue(preview("q", "原数据源"));
  const second = vi.fn().mockResolvedValue(preview("q", "新数据源"));
  const { rerender } = render(<Reader questionId="q" read={first} />);
  await screen.findByText("原数据源");
  rerender(<Reader questionId="q" read={second} />);
  expect(screen.queryByText("原数据源")).toBeNull();
  expect(await screen.findByText("新数据源")).toBeTruthy();
});

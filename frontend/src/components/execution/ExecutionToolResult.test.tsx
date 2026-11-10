// @vitest-environment jsdom
import { cleanup, render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ExecutionToolResult } from "./ExecutionToolResult";
vi.mock("@/components/common/Markdown", () => ({
  Markdown: ({ text }: { text: string }) => <div>{text}</div>,
}));
afterEach(cleanup);
it("unwraps nested knowledge JSON into ordered hits while preserving the original envelope", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  const previous = Object.getOwnPropertyDescriptor(navigator, "clipboard");
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  const payload = {
    status: "succeeded",
    content: JSON.stringify({
      status: "ok",
      hits: [
        {
          title: "费用报销制度",
          locator: "6. 发票和附件",
          document_id: "doc1",
          evidence_id: "K-1",
          content: "发票不得重复提交。",
          offset: 0,
          next_offset: null,
          total_chars: 10,
        },
        {
          title: "访客接待",
          locator: "3. 来访登记",
          document_id: "doc2",
          content: "到访需要登记。",
        },
      ],
    }),
  };
  try {
    render(<ExecutionToolResult payload={payload} />);
    expect(screen.getByRole("heading", { name: "检索命中 · 2 条" })).toBeTruthy();
    expect(screen.getByText("发票不得重复提交。")).toBeTruthy();
    expect(screen.getByText("6. 发票和附件", { selector: "summary span" })).toBeTruthy();
    expect(screen.getByText(/2\. 访客接待/).closest("details")?.open).toBe(false);
    const raw = screen.getByText("原始返回 JSON").closest("details")!;
    fireEvent.click(screen.getByText("原始返回 JSON"));
    fireEvent.click(within(raw).getByRole("button", { name: "复制 JSON" }));
    await waitFor(() => expect(writeText).toHaveBeenCalled());
    expect(JSON.parse(writeText.mock.calls[0][0])).toEqual(payload);
  } finally {
    if (previous) Object.defineProperty(navigator, "clipboard", previous);
    else Reflect.deleteProperty(navigator, "clipboard");
  }
});
it("uses a JSON tree for other tool objects and keeps malformed JSON as text", () => {
  const view = render(<ExecutionToolResult payload={{ content: '{"count":3,"ready":true}' }} />);
  expect(screen.getByRole("region", { name: "结构化工具结果" })).toBeTruthy();
  expect(screen.getByText("count")).toBeTruthy();
  view.rerender(<ExecutionToolResult payload={{ content: '{"truncated":' }} />);
  expect(
    within(screen.getByRole("region", { name: "结构化工具结果" })).getByText('{"truncated":'),
  ).toBeTruthy();
  expect(screen.queryByRole("region", { name: "知识检索命中" })).toBeNull();
});

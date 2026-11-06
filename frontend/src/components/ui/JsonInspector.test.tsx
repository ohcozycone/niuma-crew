// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { JsonInspector } from "./JsonInspector";

const previousClipboard = Object.getOwnPropertyDescriptor(navigator, "clipboard");
afterEach(() => {
  cleanup();
  if (previousClipboard) Object.defineProperty(navigator, "clipboard", previousClipboard);
  else Reflect.deleteProperty(navigator, "clipboard");
});
it("folds reasoning fields without removing them from copied response evidence", async () => {
  const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  const evidence = {
    content: "ANSWER",
    reasoning_content: "THINKING_FIELD",
    usage: { total_tokens: 28 },
  };
  render(<JsonInspector value={evidence} foldReasoning />);
  expect(screen.getByText("ANSWER")).toBeTruthy();
  expect(screen.queryByText("THINKING_FIELD")).toBeNull();
  const toggle = screen.getByRole("button", { name: /展开思考字段/ });
  expect(toggle.getAttribute("aria-expanded")).toBe("false");
  fireEvent.click(screen.getByRole("button", { name: "复制 JSON" }));
  await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
  expect(JSON.parse(writeText.mock.calls[0][0])).toEqual(evidence);
  fireEvent.click(toggle);
  expect(screen.getByText("THINKING_FIELD")).toBeTruthy();
});

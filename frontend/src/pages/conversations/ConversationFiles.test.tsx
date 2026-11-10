// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ConversationFiles } from "./ConversationFiles";
import { ApiError } from "@/lib/api/http";
import { uploadFile, listConversationFiles } from "@/lib/api/files";

vi.mock("@/lib/api/files", () => ({ uploadFile: vi.fn(), listConversationFiles: vi.fn() }));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it("selects only the saved file identity after upload completes", async () => {
  const ref = {
    id: "input-id",
    name: "input.csv",
    size: 4,
    media_type: "text/csv",
    content_hash: "hash",
    purpose: "input",
  };
  vi.mocked(uploadFile).mockResolvedValue(ref);
  const onChange = vi.fn();
  const onBusy = vi.fn();
  render(<ConversationFiles selected={[]} onChange={onChange} disabled={false} onBusy={onBusy} />);
  fireEvent.change(screen.getByLabelText("上传输入文件"), {
    target: { files: [new File(["a,b"], "input.csv", { type: "text/csv" })] },
  });
  await waitFor(() => expect(onChange).toHaveBeenCalledWith([ref]));
  expect(onBusy.mock.calls.map(([value]) => value)).toEqual([true, false]);
});

it("rejects an oversized file before starting a request", () => {
  render(<ConversationFiles selected={[]} onChange={vi.fn()} disabled={false} onBusy={vi.fn()} />);
  const file = new File(["x"], "too-large.csv");
  Object.defineProperty(file, "size", { value: 10 * 1024 * 1024 + 1 });
  fireEvent.change(screen.getByLabelText("上传输入文件"), { target: { files: [file] } });
  expect(screen.getByRole("alert").textContent).toContain("10 MiB");
  expect(uploadFile).not.toHaveBeenCalled();
});

it("shows a missing saved conversation instead of treating its file list as empty", async () => {
  vi.mocked(listConversationFiles).mockRejectedValue(
    new ApiError("对话不存在", 404, "conversation_not_found"),
  );
  render(
    <ConversationFiles
      conversationId="100000000000"
      selected={[]}
      onChange={vi.fn()}
      disabled={false}
      onBusy={vi.fn()}
    />,
  );
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(uploadFile).not.toHaveBeenCalled();
});

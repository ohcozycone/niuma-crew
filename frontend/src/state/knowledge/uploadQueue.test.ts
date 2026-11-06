// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import * as api from "@/lib/api/knowledge";
import { KnowledgeUploadQueue } from "./uploadQueue";

vi.mock("@/lib/api/knowledge", () => ({ uploadKnowledgeDocument: vi.fn() }));
afterEach(() => vi.resetAllMocks());
const document = { id: "doc", keyword_ready: false } as api.KnowledgeDocument;
const file = () => new File(["# 内容"], "资料.md");
const tick = async () => {
  await Promise.resolve();
  await Promise.resolve();
};

it("keeps its target and request alive when observers unsubscribe", async () => {
  let finish!: (value: api.KnowledgeDocument) => void;
  vi.mocked(api.uploadKnowledgeDocument).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const changed = vi.fn();
  const queue = new KnowledgeUploadQueue(changed);
  queue.add("first", "第一个库", [file()]);
  const unsubscribe = queue.state.subscribe(vi.fn());
  queue.start();
  const args = vi.mocked(api.uploadKnowledgeDocument).mock.calls[0];
  unsubscribe();
  queue.setOpen(false);
  queue.add("second", "第二个库", [file()]);
  expect(args[0]).toBe("first");
  expect(args[3]?.aborted).toBe(false);
  expect(api.uploadKnowledgeDocument).toHaveBeenCalledTimes(1);
  finish(document);
  await tick();
  expect(queue.state.getSnapshot().entries[0].status).toBe("done");
  expect(queue.state.getSnapshot().entries[1].status).toBe("ready");
  expect(changed).toHaveBeenCalledTimes(1);
  queue.dispose();
});

it("retries with the same identifier after an uncertain transport failure", async () => {
  vi.mocked(api.uploadKnowledgeDocument)
    .mockRejectedValueOnce(new Error("disconnected"))
    .mockResolvedValueOnce(document);
  const queue = new KnowledgeUploadQueue(vi.fn());
  queue.add("kb", "库", [file()]);
  queue.start();
  await tick();
  const entry = queue.state.getSnapshot().entries[0];
  expect(entry.status).toBe("failed");
  queue.retry(entry.id);
  await tick();
  expect(vi.mocked(api.uploadKnowledgeDocument).mock.calls[0][2]).toBe(
    vi.mocked(api.uploadKnowledgeDocument).mock.calls[1][2],
  );
  expect(queue.state.getSnapshot().entries[0].status).toBe("done");
  queue.dispose();
});

it("identity disposal aborts in-flight work and discards late responses", async () => {
  let finish!: (value: api.KnowledgeDocument) => void;
  vi.mocked(api.uploadKnowledgeDocument).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const changed = vi.fn();
  const queue = new KnowledgeUploadQueue(changed);
  queue.add("kb", "库", [file()]);
  queue.start();
  const signal = vi.mocked(api.uploadKnowledgeDocument).mock.calls[0][3];
  queue.dispose();
  finish(document);
  await tick();
  expect(signal?.aborted).toBe(true);
  expect(queue.state.getSnapshot().entries).toEqual([]);
  expect(changed).not.toHaveBeenCalled();
});

it("serializes uploads and cancels a queued file without sending it", async () => {
  let finish!: (value: api.KnowledgeDocument) => void;
  vi.mocked(api.uploadKnowledgeDocument).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const queue = new KnowledgeUploadQueue(vi.fn());
  queue.add("kb", "库", [file(), file()]);
  queue.start();
  queue.start();
  const second = queue.state.getSnapshot().entries[1];
  queue.cancel(second.id);
  finish(document);
  await tick();
  expect(api.uploadKnowledgeDocument).toHaveBeenCalledTimes(1);
  expect(queue.hasPending()).toBe(false);
  queue.clearFinished();
  expect(queue.state.getSnapshot().entries).toEqual([]);
  queue.dispose();
});

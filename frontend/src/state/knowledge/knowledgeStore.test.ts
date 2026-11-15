import { afterEach, beforeEach, expect, it, vi } from "vitest";
import * as api from "@/lib/api/knowledge";
import { ApiError } from "@/lib/api/http";
import { KnowledgeStore } from "./knowledgeStore";

vi.mock("@/lib/api/knowledge", () => ({
  buildKnowledgeVectors: vi.fn(),
  listKnowledgeVectorJobs: vi.fn(),
  cancelKnowledgeVectorJob: vi.fn(),
  clearKnowledgeVectors: vi.fn(),
}));
const job: api.VectorJob = {
  id: "job",
  status: "queued",
  connection_id: "model",
  chunk_count: 5,
  completed_count: 0,
  reused_count: 0,
  error: null,
  created_at: "2026-11-15T00:00:00Z",
  updated_at: "2026-11-15T00:00:00Z",
};
let store: KnowledgeStore;
beforeEach(() => {
  vi.resetAllMocks();
  store = new KnowledgeStore();
  vi.mocked(api.listKnowledgeVectorJobs).mockResolvedValue([]);
});
afterEach(() => store.dispose());

it("keeps submission busy without observers and rejects simultaneous duplicate submissions", async () => {
  let finish!: (value: api.VectorJob) => void;
  vi.mocked(api.buildKnowledgeVectors).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const unsubscribe = store.vectorOperations.subscribe(vi.fn());
  const pending = store.buildVectors("kb", "model");
  unsubscribe();
  expect(store.vectorOperations.getSnapshot().kb.busy).toBe(true);
  await expect(store.buildVectors("kb", "model")).rejects.toMatchObject({
    code: "operation_in_progress",
  });
  expect(api.buildKnowledgeVectors).toHaveBeenCalledTimes(1);
  finish(job);
  await pending;
  expect(store.vectorOperations.getSnapshot().kb).toMatchObject({ busy: false, request: null });
});

it("retains the key and model after an uncertain result and uses a new key after confirmed acceptance", async () => {
  vi.mocked(api.buildKnowledgeVectors)
    .mockRejectedValueOnce(new ApiError("offline", 0, "client_connection_failed"))
    .mockResolvedValueOnce({ ...job, status: "failed" })
    .mockResolvedValueOnce(job);
  await expect(store.buildVectors("kb", "model")).rejects.toThrow("offline");
  expect(store.vectorOperations.getSnapshot().kb.request?.connectionId).toBe("model");
  await store.buildVectors("kb", "changed-model");
  const calls = vi.mocked(api.buildKnowledgeVectors).mock.calls;
  expect(calls[0]).toEqual(calls[1]);
  await store.buildVectors("kb", "changed-model");
  expect(calls[2][1]).toBe("changed-model");
  expect(calls[2][2]).not.toBe(calls[1][2]);
});

it("releases a definitively rejected key so corrected input can create a new job", async () => {
  vi.mocked(api.buildKnowledgeVectors)
    .mockRejectedValueOnce(new ApiError("unavailable", 400, "embedding_connection_unavailable"))
    .mockResolvedValueOnce(job);
  await expect(store.buildVectors("kb", "model")).rejects.toThrow();
  expect(store.vectorOperations.getSnapshot().kb.request).toBeNull();
  await store.buildVectors("kb", "other-model");
  const calls = vi.mocked(api.buildKnowledgeVectors).mock.calls;
  expect(calls[1][1]).toBe("other-model");
  expect(calls[1][2]).not.toBe(calls[0][2]);
});

it("uses server records to block an active job and keeps confirmed cancellation if refresh fails", async () => {
  vi.mocked(api.listKnowledgeVectorJobs).mockResolvedValue([job]);
  const resource = store.vectorJobs("kb");
  const unsubscribe = resource.subscribe(vi.fn());
  await resource.ensure();
  await expect(store.buildVectors("kb", "model")).rejects.toMatchObject({
    code: "operation_in_progress",
  });
  expect(api.buildKnowledgeVectors).not.toHaveBeenCalled();
  vi.mocked(api.listKnowledgeVectorJobs).mockRejectedValue(
    new ApiError("offline", 0, "client_connection_failed"),
  );
  vi.mocked(api.cancelKnowledgeVectorJob).mockResolvedValue({ ...job, status: "cancelled" });
  await store.cancelVectors("kb", job.id);
  await resource.ensure();
  expect(resource.getSnapshot().data?.[0].status).toBe("cancelled");
  unsubscribe();
});

it("clears an uncertain request after confirmed index removal", async () => {
  vi.mocked(api.buildKnowledgeVectors).mockRejectedValue(
    new ApiError("offline", 0, "client_connection_failed"),
  );
  await expect(store.buildVectors("kb", "model")).rejects.toThrow();
  vi.mocked(api.clearKnowledgeVectors).mockResolvedValue(undefined);
  await store.clearVectors("kb");
  expect(store.vectorOperations.getSnapshot().kb.request).toBeNull();
});

it("drops identity-scoped operation state and ignores a late submission result after disposal", async () => {
  let finish!: (value: api.VectorJob) => void;
  vi.mocked(api.buildKnowledgeVectors).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const pending = store.buildVectors("kb", "model");
  store.dispose();
  finish(job);
  await pending;
  expect(store.vectorOperations.getSnapshot()).toEqual({});
  await expect(store.buildVectors("kb", "model")).rejects.toMatchObject({
    code: "workspace_closed",
  });
});

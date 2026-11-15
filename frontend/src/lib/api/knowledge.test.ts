import { afterEach, expect, it, vi } from "vitest";
import {
  buildKnowledgeVectors,
  cancelKnowledgeVectorJob,
  getKnowledgeVectorJob,
  listKnowledgeVectorJobs,
} from "./knowledge";

afterEach(() => vi.unstubAllGlobals());

it("submits an idempotent asynchronous vector job and reads/cancels its persisted record", async () => {
  const job = { id: "job", status: "queued" };
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(job), { status: 202 }))
    .mockResolvedValueOnce(new Response(JSON.stringify([job])))
    .mockResolvedValueOnce(new Response(JSON.stringify(job)))
    .mockResolvedValueOnce(new Response(JSON.stringify({ ...job, status: "cancelled" })));
  vi.stubGlobal("fetch", fetcher);
  expect(await buildKnowledgeVectors("kb", "model", "request")).toEqual(job);
  expect(fetcher.mock.calls[0][0]).toBe("/api/knowledge-bases/kb/vector-index");
  expect(fetcher.mock.calls[0][1]).toMatchObject({
    method: "POST",
    body: JSON.stringify({ model_connection_id: "model", client_request_id: "request" }),
  });
  const signal = new AbortController().signal;
  expect(await listKnowledgeVectorJobs("kb", signal)).toEqual([job]);
  expect(fetcher.mock.calls[1][0]).toBe("/api/knowledge-bases/kb/vector-jobs");
  expect(fetcher.mock.calls[1][1].signal).toBe(signal);
  expect(await getKnowledgeVectorJob("kb", "job", signal)).toEqual(job);
  expect(fetcher.mock.calls[2][0]).toBe("/api/knowledge-bases/kb/vector-jobs/job");
  expect(await cancelKnowledgeVectorJob("kb", "job")).toEqual({ ...job, status: "cancelled" });
  expect(fetcher.mock.calls[3][0]).toBe("/api/knowledge-bases/kb/vector-jobs/job/cancel");
  expect(fetcher.mock.calls[3][1]).toMatchObject({ method: "POST", body: "{}" });
});

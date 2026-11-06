import { ApiError } from "@/lib/api/http";
import { expect, it, vi } from "vitest";
import { Resource, ResourceCache, queryKey } from "./resource";
import { Atom, batchChanges } from "./atom";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

it("does not read during construction and deduplicates simultaneous subscriptions", async () => {
  const load = vi.fn(async () => 7);
  const resource = new Resource(load);
  expect(load).not.toHaveBeenCalled();
  const first = resource.subscribe(vi.fn());
  const second = resource.subscribe(vi.fn());
  await resource.ensure();
  expect(load).toHaveBeenCalledTimes(1);
  expect(resource.getSnapshot()).toEqual({ data: 7, loading: false, error: "", failure: null });
  first();
  second();
  resource.dispose();
});

it("preserves confirmed data on refresh failure and retries after an explicit refresh", async () => {
  const load = vi
    .fn()
    .mockResolvedValueOnce(7)
    .mockRejectedValueOnce(new ApiError("offline", 0, "connection_failed"))
    .mockResolvedValueOnce(8);
  const resource = new Resource<number>(load);
  const unsubscribe = resource.subscribe(vi.fn());
  await resource.ensure();
  resource.refresh();
  expect(resource.getSnapshot()).toEqual({ data: 7, loading: true, error: "", failure: null });
  await resource.ensure();
  expect(resource.getSnapshot()).toMatchObject({
    data: 7,
    loading: false,
    error: "offline",
    failure: { source: "network", status: null, code: "connection_failed", message: "offline" },
  });
  resource.refresh();
  await resource.ensure();
  expect(resource.getSnapshot().data).toBe(8);
  unsubscribe();
  resource.dispose();
});

it("cancels old reads before acceptance so late data cannot leak through domain callbacks", async () => {
  const old = deferred<number>();
  const load = vi.fn().mockReturnValueOnce(old.promise).mockResolvedValueOnce(8);
  const accept = vi.fn((value: number) => value);
  const resource = new Resource<number>(load, { accept });
  const unsubscribe = resource.subscribe(vi.fn());
  await Promise.resolve();
  const oldSignal = load.mock.calls[0][0] as AbortSignal;
  resource.refresh();
  await resource.ensure();
  old.resolve(1);
  await old.promise;
  await Promise.resolve();
  expect(oldSignal.aborted).toBe(true);
  expect(accept).toHaveBeenCalledTimes(1);
  expect(resource.getSnapshot().data).toBe(8);
  unsubscribe();
  resource.dispose();
});

it("keeps an in-flight read during immediate subscription handoff, then cancels the final unmount", async () => {
  const read = deferred<number>();
  const load = vi.fn<(signal: AbortSignal) => Promise<number>>(() => read.promise);
  const resource = new Resource(load);
  const first = resource.subscribe(vi.fn());
  await Promise.resolve();
  const signal = load.mock.calls[0][0] as AbortSignal;
  first();
  const second = resource.subscribe(vi.fn());
  await Promise.resolve();
  expect(signal.aborted).toBe(false);
  expect(load).toHaveBeenCalledTimes(1);
  second();
  await Promise.resolve();
  expect(signal.aborted).toBe(true);
  read.resolve(9);
  await read.promise;
  await Promise.resolve();
  expect(resource.getSnapshot().data).toBeUndefined();
  resource.dispose();
});

it("defers blocked reads without polling and resumes only once", async () => {
  let blocked = true;
  const load = vi.fn(async () => 7);
  const resource = new Resource(load, { blocked: () => blocked });
  const unsubscribe = resource.subscribe(vi.fn());
  await resource.ensure();
  expect(load).not.toHaveBeenCalled();
  expect(resource.getSnapshot().loading).toBe(true);
  blocked = false;
  await resource.ensure();
  expect(load).toHaveBeenCalledTimes(1);
  unsubscribe();
  resource.dispose();
});

it("bounds inactive query results while retaining active entries and canonicalizes query order", () => {
  const cache = new ResourceCache(2);
  const load = vi.fn(async () => 7);
  const active = cache.get("active", load);
  const unsubscribe = active.subscribe(vi.fn());
  const old = cache.get("old", load);
  cache.get("new", load);
  expect(old.isDisposed).toBe(true);
  expect(active.isDisposed).toBe(false);
  expect(cache.get("active", load)).toBe(active);
  expect(queryKey(new URLSearchParams("q=x&offset=0"))).toBe(
    queryKey(new URLSearchParams("offset=0&q=x")),
  );
  unsubscribe();
  cache.dispose();
});

it("notifies after all values in a batch have been committed", () => {
  const first = new Atom(0);
  const second = new Atom(0);
  const seen: number[][] = [];
  const listener = () => seen.push([first.getSnapshot(), second.getSnapshot()]);
  first.subscribe(listener);
  second.subscribe(listener);
  batchChanges(() => {
    first.set(1);
    second.set(2);
  });
  expect(seen).toEqual([[1, 2]]);
});

it.each([401, 403])(
  "drops protected data when a refresh is explicitly denied with %s",
  async (status) => {
    const load = vi
      .fn()
      .mockResolvedValueOnce(7)
      .mockRejectedValueOnce(new ApiError("访问已失效", status, "permission_denied"));
    const resource = new Resource<number>(load);
    const unsubscribe = resource.subscribe(vi.fn());
    await resource.ensure();
    resource.refresh();
    await resource.ensure();
    expect(resource.getSnapshot().data).toBeUndefined();
    expect(resource.getSnapshot().failure?.status).toBe(status);
    unsubscribe();
    resource.dispose();
  },
);
it.each([false, true])(
  "only treats 404 as removed data for an opted-in detail (%s)",
  async (discardOnMissing) => {
    const load = vi
      .fn()
      .mockResolvedValueOnce(7)
      .mockRejectedValueOnce(new ApiError("不存在", 404, "item_not_found"));
    const resource = new Resource<number>(load, { discardOnMissing });
    const unsubscribe = resource.subscribe(vi.fn());
    await resource.ensure();
    resource.refresh();
    await resource.ensure();
    expect(resource.getSnapshot().data).toBe(discardOnMissing ? undefined : 7);
    unsubscribe();
    resource.dispose();
  },
);

// @vitest-environment jsdom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/http";
import { Resource } from "./resource";
import { useRetainedResource } from "./useResource";

afterEach(cleanup);
it("does not restore a denied query's old data when another query starts", async () => {
  const owner = {};
  const load = vi
    .fn()
    .mockResolvedValueOnce("private")
    .mockRejectedValueOnce(new ApiError("无权访问", 403, "permission_denied"));
  const resource = new Resource<string>(load);
  const next = new Resource<string>(() => new Promise(() => {}));
  const view = renderHook(({ current }) => useRetainedResource(current, owner), {
    initialProps: { current: resource },
  });
  await waitFor(() => expect(view.result.current.data).toBe("private"));
  act(() => resource.refresh());
  await waitFor(() => expect(view.result.current.failure?.status).toBe(403));
  expect(view.result.current.data).toBeUndefined();
  view.rerender({ current: next });
  expect(view.result.current.data).toBeUndefined();
  view.unmount();
  resource.dispose();
  next.dispose();
});

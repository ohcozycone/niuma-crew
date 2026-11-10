// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { createConversationTransport } from "./conversationTransport";

class FakeSource extends EventTarget {
  static instances: FakeSource[] = [];
  close = vi.fn();
  onerror: (() => void) | null = null;
  constructor(public url: string) {
    super();
    FakeSource.instances.push(this);
  }
}
afterEach(() => {
  vi.unstubAllGlobals();
  FakeSource.instances = [];
});
it("reconfirms an unqualified SSE revocation without assuming the session expired", () => {
  vi.stubGlobal("EventSource", FakeSource);
  const changed = vi.fn();
  const ended = vi.fn();
  window.addEventListener("auth:permissions-changed", changed);
  window.addEventListener("auth:session-ended", ended);
  const revoked = vi.fn();
  const close = createConversationTransport().subscribe("chat", "reply", {
    snapshot: vi.fn(),
    disconnected: vi.fn(),
    invalid: vi.fn(),
    revoked,
  });
  FakeSource.instances[0].dispatchEvent(new Event("access.revoked"));
  expect(FakeSource.instances[0].close).toHaveBeenCalledOnce();
  expect(changed).toHaveBeenCalledOnce();
  expect(ended).not.toHaveBeenCalled();
  expect(revoked).toHaveBeenCalledOnce();
  close();
  window.removeEventListener("auth:permissions-changed", changed);
  window.removeEventListener("auth:session-ended", ended);
});

it.each([null, "100000000000"])("only treats 200/null as an absent request for %s", async (id) => {
  const fetch = vi.fn<typeof globalThis.fetch>(async () => Response.json(null));
  vi.stubGlobal("fetch", fetch);
  const key = "00000000-0000-4000-8000-000000000001";
  expect(await createConversationTransport().findRequest(id, key)).toBeNull();
  expect(fetch.mock.calls[0][0]).toBe(
    id === null ? `/api/conversations/requests/${key}` : `/api/conversations/${id}/requests/${key}`,
  );
});

it.each([null, "100000000000"])(
  "preserves a lookup 404 as a resource failure for %s",
  async (id) => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof globalThis.fetch>(async () =>
        Response.json(
          { detail: { code: "conversation_not_found", message: "对话不存在。" } },
          { status: 404 },
        ),
      ),
    );
    await expect(
      createConversationTransport().findRequest(id, "00000000-0000-4000-8000-000000000001"),
    ).rejects.toMatchObject({ status: 404, code: "conversation_not_found" });
  },
);

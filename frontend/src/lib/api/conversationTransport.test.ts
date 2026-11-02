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

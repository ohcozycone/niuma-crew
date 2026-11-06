import { describe, expect, it } from "vitest";
import { identityKey, type Identity } from "@/lib/identity";
import { safeReturnPath } from "@/lib/navigation";

describe("session navigation", () => {
  it.each([
    "//evil.test",
    "https://evil.test",
    "/\\evil.test",
    "/login",
    "/signin",
    "/api/auth/logout",
    "/%2f%2fevil.test",
    "/agents\r\nLocation: https://evil.test",
    "/agents\t",
    null,
  ])("rejects an unsafe return path %s", (path) => {
    expect(safeReturnPath(path)).toBe("/");
  });
  it("preserves legitimate agent deep links", () => {
    expect(safeReturnPath("/?agent=abc&tab=instructions")).toBe("/?agent=abc&tab=instructions");
  });
  it.each([
    "/agents?filter=favorites",
    "/agents/new",
    "/agents/abc?tab=instructions",
    "/skills/new",
    "/skills/abc",
    "/knowledge?document=demo",
    "/knowledge?tab=rules",
    "/knowledge/new",
    "/knowledge/abc?view=search&question=test",
    "/knowledge/abc/documents/def?chunk=xyz",
    "/avatars/svg",
    "/conversations/new?agent=abc",
  ])("retains client business route %s", (path) => {
    expect(safeReturnPath(path)).toBe(path);
  });
  it("resets state on a new session, account, or permission change, but not a reordered capability list", () => {
    const identity: Identity = {
      actor: { kind: "user", user: { id: "a", username: "admin" } },
      permissions: ["agents:read", "skills:read"],
      expires_at: "one",
    };
    expect(identityKey({ ...identity, permissions: [...identity.permissions].reverse() })).toBe(
      identityKey(identity),
    );
    expect(identityKey({ ...identity, expires_at: "two" })).not.toBe(identityKey(identity));
    expect(identityKey({ ...identity, permissions: [] })).not.toBe(identityKey(identity));
    expect(identityKey({ ...identity, actor: { kind: "guest", user: null } })).not.toBe(
      identityKey(identity),
    );
  });
});

it("allows a rules deep link after login", () => {
  expect(safeReturnPath("/rules")).toBe("/rules");
});

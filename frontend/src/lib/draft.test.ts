import { afterEach, expect, it, vi } from "vitest";
import { clearDraft, draftKey, readDraft, readStaleDraft } from "./draft";
afterEach(() => vi.unstubAllGlobals());
it("restores only the same account, resource and unchanged server baseline", () => {
  const values = new Map<string, string>();
  vi.stubGlobal("sessionStorage", {
    getItem: (key: string) => values.get(key),
    removeItem: (key: string) => values.delete(key),
  });
  const key = draftKey("account-a", "agent:one");
  const baseline = { name: "原名", skills: ["one"] };
  const draft = { name: "草稿", skills: ["one", "two"] };
  values.set(key, JSON.stringify({ baseline: JSON.stringify(baseline), value: draft }));
  expect(readDraft(key, baseline)).toEqual(draft);
  expect(readDraft(draftKey("account-b", "agent:one"), baseline)).toEqual(baseline);
  expect(readDraft(key, { ...baseline, name: "服务端已更新" })).toEqual({
    ...baseline,
    name: "服务端已更新",
  });
  values.set(
    key,
    JSON.stringify({ baseline: JSON.stringify(baseline), value: { name: 9, skills: [] } }),
  );
  expect(readDraft(key, baseline)).toEqual(baseline);
  clearDraft(key);
  expect(values.has(key)).toBe(false);
});
it("storage denial and invalid JSON do not prevent editing", () => {
  vi.stubGlobal("sessionStorage", {
    getItem: () => {
      throw new Error("denied");
    },
    removeItem: () => {
      throw new Error("denied");
    },
  });
  expect(readDraft("key", { name: "default" })).toEqual({ name: "default" });
  expect(() => clearDraft("key")).not.toThrow();
});

it("keeps an old revision for explicit recovery without automatically applying it", () => {
  const old = { name: "原名", revision: 1, settings: {} };
  const current = { ...old, name: "服务器最新", revision: 2 };
  const draft = { ...old, name: "需要保留的草稿" };
  const record = JSON.stringify({ baseline: JSON.stringify(old), value: draft });
  vi.stubGlobal("sessionStorage", { getItem: () => record });
  expect(readDraft("key", current)).toEqual(current);
  expect(readStaleDraft("key", current)).toEqual(draft);
  expect(readStaleDraft("key", old)).toBeNull();
});
it("does not restore malformed nested configuration", () => {
  const baseline = { name: "原名", settings: {} };
  vi.stubGlobal("sessionStorage", {
    getItem: () => JSON.stringify({ baseline: "old", value: { name: "草稿", settings: null } }),
  });
  expect(readStaleDraft("key", baseline)).toBeNull();
});

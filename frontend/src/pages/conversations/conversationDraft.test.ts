// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import { retireLegacyConversationDraft } from "./conversationDraft";

afterEach(() => sessionStorage.clear());
it("clears retired mode drafts and URL inputs before ordinary message recovery", () => {
  sessionStorage.setItem(
    "draft",
    JSON.stringify({ baseline: '{"content":""}', value: { content: "旧排查重点" } }),
  );
  sessionStorage.setItem(
    "draft:ci",
    JSON.stringify({ value: { url: "https://example.test/run" } }),
  );
  expect(retireLegacyConversationDraft("draft", false)).toBe(true);
  expect(sessionStorage.getItem("draft")).toBeNull();
  expect(sessionStorage.getItem("draft:ci")).toBeNull();
});
it("leaves an ordinary message draft unchanged when no retired input is present", () => {
  sessionStorage.setItem("draft", "ordinary-draft");
  expect(retireLegacyConversationDraft("draft", false)).toBe(false);
  expect(sessionStorage.getItem("draft")).toBe("ordinary-draft");
});

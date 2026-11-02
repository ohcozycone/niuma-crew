import { expect, it } from "vitest";
import { isKnowledgeSourceLink } from "./knowledgeSourceLink";

const source = `/knowledge/12345678-1234-1234-1234-123456789abc/documents/22345678-1234-1234-1234-123456789abc?chunk=${"a".repeat(64)}`;
it("allows only the exact platform evidence path", () => {
  expect(isKnowledgeSourceLink(source)).toBe(true);
  for (const value of [
    null,
    "/knowledge",
    `${source}&next=https://evil.test`,
    `${source}#extra`,
    `https://evil.test${source}`,
    `/${source}`,
    source.replace("/documents/", "/../documents/"),
    source.replace("?chunk=", "?file="),
    source.replace("a".repeat(64), "short"),
    `javascript:alert(1)`,
    source.replace("/knowledge/", "/%6bnowledge/"),
  ]) {
    expect(isKnowledgeSourceLink(value)).toBe(false);
  }
});

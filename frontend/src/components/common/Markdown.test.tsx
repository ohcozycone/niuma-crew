// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { Markdown } from "./Markdown";

afterEach(cleanup);
it("renders exact knowledge evidence links while rejecting other relative answer links", () => {
  const source = `/knowledge/12345678-1234-1234-1234-123456789abc/documents/22345678-1234-1234-1234-123456789abc?chunk=${"a".repeat(64)}`;
  const { container } = render(
    <Markdown
      text={`[制度依据](${source})\n\n[不允许的入口](/brains)\n\n[外部资料](https://example.com)`}
      sourceTitles={new Map([[source, "报销制度"]])}
    />,
  );
  const citation = screen.getByRole("button", { name: "预览来源 1：报销制度" });
  expect(citation.textContent).toBe("报销制度");
  expect(citation.parentElement?.tagName).not.toBe("SUP");
  fireEvent.click(screen.getByRole("button", { name: "引用了 1 个来源" }));
  expect(screen.getByRole("link", { name: /报销制度/ }).getAttribute("href")).toBe(source);
  expect(screen.getByRole("link", { name: "外部资料" }).getAttribute("href")).toBe(
    "https://example.com/",
  );
  expect(container.querySelector('a[href="/brains"]')).toBeNull();
});

const source = (character: string) =>
  `/knowledge/12345678-1234-1234-1234-123456789abc/documents/22345678-1234-1234-1234-123456789abc?chunk=${character.repeat(64)}`;

it("numbers knowledge sources across paragraphs and reuses the same source number", () => {
  render(
    <Markdown
      text={`住宿上限400元。[K-1111111111111111](${source("a")})\n\n需准备发票。[K-2222222222222222](${source("b")})\n\n再次参考住宿标准。[K-1111111111111111](${source("a")})`}
    />,
  );
  expect(
    screen.getAllByRole("button", { name: /^预览来源/ }).map((link) => link.textContent),
  ).toEqual(["知识来源 1", "知识来源 2", "知识来源 1"]);
  fireEvent.click(screen.getByRole("button", { name: "引用了 2 个来源" }));
  expect(screen.getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual([
    source("a"),
    source("b"),
  ]);
  expect(screen.queryByText(/K-1111111111111111/)).toBeNull();
});

it("ignores code and escaped links while supporting Markdown reference links", () => {
  render(
    <Markdown
      text={`示例：\n\n\`\`\`md\n[示例](${source("a")})\n\`\`\`\n\n\`[内联示例](${source("b")})\`\n\n\\[转义示例](${source("b")})\n\n实际依据：[制度][rule]\n\n[rule]: ${source("c")}`}
    />,
  );
  expect(screen.getByRole("button", { name: "预览来源 1：知识来源 1" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "引用了 1 个来源" }));
  const citation = screen.getByRole("link", { name: /知识来源 1/ });
  expect(citation.getAttribute("href")).toBe(source("c"));
  expect(screen.getAllByRole("link")).toHaveLength(1);
});

it("keeps numbering when streaming appends another source and when generation finishes", () => {
  const first = `住宿要求。[K-1111111111111111](${source("a")})`;
  const { rerender } = render(<Markdown text={first} streaming />);
  expect(screen.getByRole("button", { name: "预览来源 1：知识来源 1" }).textContent).toBe(
    "知识来源 1",
  );
  expect(screen.queryByRole("button", { name: /^引用了/ })).toBeNull();
  const full = `${first}\n\n材料要求。[K-2222222222222222](${source("b")})`;
  rerender(<Markdown text={full} streaming />);
  expect(
    screen.getAllByRole("button", { name: /^预览来源/ }).map((link) => link.textContent),
  ).toEqual(["知识来源 1", "知识来源 2"]);
  rerender(<Markdown text={full} />);
  expect(
    screen.getAllByRole("button", { name: /^预览来源/ }).map((link) => link.textContent),
  ).toEqual(["知识来源 1", "知识来源 2"]);
  expect(screen.getByRole("button", { name: "引用了 2 个来源" })).toBeTruthy();
});

it("does not count retrieved candidates absent from the parsed answer", () => {
  render(
    <Markdown
      text={`只引用一条。[证据](${source("a")})`}
      sourceTitles={
        new Map([
          [source("a"), "引用文档"],
          [source("b"), "仅检索候选"],
        ])
      }
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "引用了 1 个来源" }));
  expect(screen.queryByText("仅检索候选")).toBeNull();
  expect(screen.getAllByRole("link")).toHaveLength(1);
});

it("does not create a sources list for answers without knowledge citations", () => {
  render(<Markdown text="普通答复。[公开网页](https://example.com)" />);
  expect(screen.queryByRole("button", { name: /^引用了/ })).toBeNull();
});

// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { CapabilityCard } from "./CapabilityCard";

afterEach(cleanup);

it("links an MCP service to its configuration", () => {
  render(
    <MemoryRouter>
      <CapabilityCard
        item={{
          id: "search",
          name: "网页检索",
          description: "查询网页",
          kind: "mcp_http",
          enabled: true,
        }}
      />
    </MemoryRouter>,
  );
  expect(screen.getByText("· 已启用")).toBeTruthy();
  expect(screen.getByRole("button", { name: "查看配置" }).getAttribute("href")).toBe(
    "/tools?service=search",
  );
  expect(screen.queryByRole("button", { name: /删除|编辑/ })).toBeNull();
});

import { describe, expect, it } from "vitest";
import {
  catalogDifferences,
  evaluateDemoCall,
  toolDisplayName,
  validGrantedTools,
} from "./demoCatalog";
import { createDemoConnections, createDemoEmployees } from "./fixtures/capabilities";

describe("MCP 目录演示的授权边界", () => {
  it("远端新增无关工具不会改变已确认目录或中断已有操作", () => {
    const connection = createDemoConnections()[0];
    const assignment = createDemoEmployees()[0].assignments[1];
    connection.remoteCatalog.push({
      name: "new_tool",
      description: "New operation",
      descriptor_hash: "new-v1",
    });
    expect(connection.approved_catalog).toHaveLength(2);
    expect(evaluateDemoCall(assignment, connection, "tavily_search").ok).toBe(true);
    expect(evaluateDemoCall(assignment, connection, "new_tool").ok).toBe(false);
  });
  it("确认新增目录也不会自动增加员工许可；显示别名不影响身份", () => {
    const connection = createDemoConnections()[0];
    const assignment = createDemoEmployees()[0].assignments[1];
    connection.approved_catalog.push({
      name: "new_tool",
      description: "New operation",
      descriptor_hash: "new-v1",
    });
    connection.aliases.tavily_search.name = "检索资料";
    expect(toolDisplayName(connection, "tavily_search")).toBe("检索资料（tavily_search）");
    expect(toolDisplayName(connection, "new_tool")).toBe("new_tool");
    expect(validGrantedTools(assignment, connection)).toEqual(["tavily_search"]);
    expect(evaluateDemoCall(assignment, connection, "tavily_search").ok).toBe(true);
  });
  it("定义改变时先阻断远端调用，确认新目录后仍需显式重新授权", () => {
    const connection = createDemoConnections()[0];
    const assignment = createDemoEmployees()[0].assignments[1];
    connection.remoteCatalog[0].descriptor_hash = "search-v2";
    expect(evaluateDemoCall(assignment, connection, "tavily_search").message).toContain(
      "远端目标工具",
    );
    connection.approved_catalog = structuredClone(connection.remoteCatalog);
    expect(validGrantedTools(assignment, connection)).toEqual([]);
    expect(evaluateDemoCall(assignment, connection, "tavily_search").message).toContain(
      "旧许可已失效",
    );
    assignment.toolHashes.tavily_search = "search-v2";
    expect(evaluateDemoCall(assignment, connection, "tavily_search").ok).toBe(true);
  });
  it("原始工具改名被识别为删除与新增，不用中文别名迁移许可", () => {
    const connection = createDemoConnections()[0];
    const assignment = createDemoEmployees()[0].assignments[1];
    const next = connection.remoteCatalog.map((tool) =>
      tool.name === "tavily_search"
        ? { ...tool, name: "web_search", descriptor_hash: "renamed-v1" }
        : tool,
    );
    const diff = catalogDifferences(connection.approved_catalog, next);
    expect(diff.find((item) => item.tool.name === "tavily_search")?.status).toBe("removed");
    expect(diff.find((item) => item.tool.name === "web_search")?.status).toBe("added");
    connection.remoteCatalog = next;
    expect(evaluateDemoCall(assignment, connection, "tavily_search").ok).toBe(false);
  });
});

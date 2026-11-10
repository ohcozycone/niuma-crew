import { afterEach, expect, it, vi } from "vitest";
import { designDocumentationUrl } from "./documentation";

afterEach(() => vi.unstubAllEnvs());

it("旧分类链接指向统一文档中的对应规范，不携带演示数据", () => {
  vi.stubEnv("VITE_DOCS_URL", "http://127.0.0.1:3001/");
  expect(designDocumentationUrl("#buttons")).toBe(
    "http://127.0.0.1:3001/docs/development/design-components/",
  );
  expect(designDocumentationUrl("#resource-language")).toBe(
    "http://127.0.0.1:3001/docs/development/design-patterns/",
  );
  expect(designDocumentationUrl("#unknown")).toBe(
    "http://127.0.0.1:3001/docs/development/design-system/",
  );
});

it("同域子路径与独立文档域名均保留配置的根地址", () => {
  vi.stubEnv("DEV", false);
  vi.stubEnv("VITE_DOCS_URL", "");
  expect(designDocumentationUrl()).toBe("/docs/docs/development/design-system/");
  vi.stubEnv("VITE_DOCS_URL", "https://manual.example.com/");
  expect(designDocumentationUrl("#colors")).toBe(
    "https://manual.example.com/docs/development/design-colors/",
  );
});

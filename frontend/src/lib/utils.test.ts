import { describe, expect, it } from "vitest";
import { cn } from "./utils";

describe("semantic utility merging", () => {
  it("keeps semantic foregrounds when a component overrides its font size", () => {
    expect(cn("bg-action text-action-text text-sm", "text-body")).toBe(
      "bg-action text-action-text text-body",
    );
    expect(cn("text-text text-section", "text-body")).toBe("text-text text-body");
  });

  it("replaces colours and font sizes independently", () => {
    expect(cn("text-text-muted text-body", "text-danger text-lg")).toBe("text-danger text-lg");
  });
});

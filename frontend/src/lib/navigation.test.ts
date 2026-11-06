import { expect, it } from "vitest";
import { isRulesLocation, leavesEditingArea, ORGANIZATION_RULES_URL } from "@/lib/navigation";

function location(path: string) {
  const url = new URL(path, "http://localhost");
  return { pathname: url.pathname, search: url.search };
}

it("recognizes both the canonical rules page and legacy tab for draft cleanup", () => {
  expect(isRulesLocation(location(ORGANIZATION_RULES_URL))).toBe(true);
  expect(isRulesLocation(location("/knowledge?tab=rules"))).toBe(true);
  expect(isRulesLocation(location("/knowledge?q=规则"))).toBe(false);
});

it.each(["/knowledge", "/knowledge?tab=documents", "/knowledge?q=报销"])(
  "protects rule drafts when a tab or history navigation goes to %s",
  (next) => {
    expect(leavesEditingArea(location(ORGANIZATION_RULES_URL), location(next))).toBe(true);
  },
);

it("keeps same-tab query changes and agent configuration tab changes unblocked", () => {
  expect(leavesEditingArea(location(ORGANIZATION_RULES_URL), location("/rules?q=报销"))).toBe(
    false,
  );
  expect(
    leavesEditingArea(
      location("/agents/abc?tab=instructions"),
      location("/agents/abc?tab=capabilities"),
    ),
  ).toBe(false);
  expect(
    leavesEditingArea(location("/knowledge?q=报销"), location("/knowledge?document=demo")),
  ).toBe(false);
});

it("still protects pathname navigation away from any editor", () => {
  expect(leavesEditingArea(location(ORGANIZATION_RULES_URL), location("/agents"))).toBe(true);
  expect(leavesEditingArea(location("/agents/abc"), location("/skills"))).toBe(true);
});

it("protects rules reached through a trailing-slash URL", () => {
  expect(isRulesLocation(location("/knowledge/?tab=rules"))).toBe(true);
  expect(leavesEditingArea(location("/knowledge/?tab=rules"), location("/knowledge/"))).toBe(true);
});

it("protects selected uploads on a library tab change but keeps document filtering local", () => {
  expect(
    leavesEditingArea(location("/knowledge/abc"), location("/knowledge/abc?view=search")),
  ).toBe(true);
  expect(leavesEditingArea(location("/knowledge/abc"), location("/knowledge/abc?q=指南"))).toBe(
    false,
  );
});

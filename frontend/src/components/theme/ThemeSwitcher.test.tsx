// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ThemeSwitcher } from "./ThemeSwitcher";
const { setPreference } = vi.hoisted(() => ({ setPreference: vi.fn() }));
vi.mock("@/state/theme/useTheme", () => ({
  useTheme: () => ({ preference: "system", resolved: "dark", setPreference }),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
describe("theme menu selection", () => {
  it.each([
    ["日间", "light"],
    ["夜间", "dark"],
    ["跟随系统", "system"],
  ])("closes and returns focus after choosing %s", async (label, value) => {
    render(<ThemeSwitcher />);
    const trigger = screen.getByRole("button", { name: /选择外观模式/ });
    fireEvent.click(trigger);
    const option = await screen.findByRole("menuitemradio", {
      name: value === "system" ? /^跟随系统/ : label,
    });
    fireEvent.click(option);
    await waitFor(() => expect(trigger.getAttribute("aria-expanded")).toBe("false"));
    await waitFor(() => expect(document.activeElement).toBe(trigger));
    if (value !== "system") expect(setPreference).toHaveBeenCalledWith(value);
  });
});

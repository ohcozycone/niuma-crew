import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { installThemeController, type ThemeController } from "./themeController";

function environment(saved?: string, dark = false) {
  const values = new Map<string, string>(saved === undefined ? [] : [["niuma:theme", saved]]);
  const media = Object.assign(new EventTarget(), { matches: dark });
  const storage = {
    getItem: vi.fn((key: string) => values.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {
      values.set(key, value);
    }),
  };
  const root = {
    dataset: {} as Record<string, string>,
    classList: { toggle: vi.fn() },
    style: { colorScheme: "" },
  };
  const win = Object.assign(new EventTarget(), {
    localStorage: storage,
    matchMedia: () => media,
    NiumaTheme: undefined as ThemeController | undefined,
  });
  vi.stubGlobal("window", win);
  vi.stubGlobal("document", { documentElement: root });
  return { media, storage, root, win };
}
function system(media: { matches: boolean; dispatchEvent(event: Event): boolean }, dark: boolean) {
  media.matches = dark;
  media.dispatchEvent(new Event("change"));
}
function stored(win: EventTarget, key: string | null, newValue: string | null) {
  win.dispatchEvent(Object.assign(new Event("storage"), { key, newValue }));
}

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());
describe("theme preference across bootstrap and React runtime", () => {
  it("resolves an unset preference before the UI starts without writing storage", () => {
    const env = environment(undefined, true);
    const theme = installThemeController();
    expect(theme.getSnapshot()).toEqual({ preference: "system", resolved: "dark" });
    expect(env.root.dataset.theme).toBe("dark");
    expect(env.root.style.colorScheme).toBe("dark");
    expect(env.storage.setItem).not.toHaveBeenCalled();
  });
  it("keeps explicit light even when the system changes", () => {
    const env = environment("light", true),
      theme = installThemeController();
    system(env.media, false);
    system(env.media, true);
    expect(theme.getSnapshot()).toEqual({ preference: "light", resolved: "light" });
  });
  it("remembers a manual choice and resumes live system following", () => {
    const env = environment(),
      theme = installThemeController();
    theme.setPreference("dark");
    expect(env.storage.setItem).toHaveBeenLastCalledWith("niuma:theme", "dark");
    theme.setPreference("system");
    system(env.media, true);
    expect(theme.getSnapshot()).toEqual({ preference: "system", resolved: "dark" });
  });
  it("synchronizes another tab and returns to system when preferences are cleared", () => {
    const env = environment("light", true),
      theme = installThemeController();
    stored(env.win, "niuma:theme", "dark");
    expect(theme.getSnapshot().preference).toBe("dark");
    stored(env.win, null, null);
    expect(theme.getSnapshot()).toEqual({ preference: "system", resolved: "dark" });
    expect(env.storage.setItem).not.toHaveBeenCalled();
  });
  it("ignores unrelated storage and rejects invalid saved preferences", () => {
    const env = environment("invalid", true),
      theme = installThemeController();
    stored(env.win, "unrelated", "light");
    expect(theme.getSnapshot()).toEqual({ preference: "system", resolved: "dark" });
  });
  it("allows in-memory switching if storage is blocked", () => {
    const env = environment();
    env.storage.getItem.mockImplementation(() => {
      throw new Error("blocked");
    });
    env.storage.setItem.mockImplementation(() => {
      throw new Error("blocked");
    });
    const theme = installThemeController();
    theme.setPreference("dark");
    expect(theme.getSnapshot()).toEqual({ preference: "dark", resolved: "dark" });
  });
  it("reuses the early controller and only notifies subscribed changes", () => {
    const env = environment(),
      theme = installThemeController(),
      listener = vi.fn();
    const stop = theme.subscribe(listener);
    expect(installThemeController()).toBe(theme);
    theme.setPreference("dark");
    theme.setPreference("dark");
    expect(listener).toHaveBeenCalledTimes(1);
    stop();
    system(env.media, true);
    theme.setPreference("light");
    expect(listener).toHaveBeenCalledTimes(1);
  });
  it("refreshes a cached page from the latest stored choice on history restore", () => {
    const env = environment("light"),
      theme = installThemeController();
    env.storage.setItem("niuma:theme", "dark");
    env.win.dispatchEvent(Object.assign(new Event("pageshow"), { persisted: true }));
    expect(theme.getSnapshot()).toEqual({ preference: "dark", resolved: "dark" });
    env.storage.setItem("niuma:theme", "system");
    env.media.matches = true;
    env.win.dispatchEvent(Object.assign(new Event("pageshow"), { persisted: true }));
    expect(theme.getSnapshot()).toEqual({ preference: "system", resolved: "dark" });
  });
  it("falls back to light when the platform has no media query support", () => {
    const env = environment();
    env.win.matchMedia = () => {
      throw new Error("unavailable");
    };
    expect(installThemeController().getSnapshot()).toEqual({
      preference: "system",
      resolved: "light",
    });
  });
});

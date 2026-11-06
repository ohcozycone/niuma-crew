export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";
export type ThemeSnapshot = { preference: ThemePreference; resolved: ResolvedTheme };
export type ThemeController = {
  getSnapshot(): ThemeSnapshot;
  subscribe(listener: () => void): () => void;
  setPreference(preference: ThemePreference): void;
};

declare global {
  interface Window {
    NiumaTheme?: ThemeController;
  }
}

/** Self-contained so the exact same function can run inline before first paint. */
export function installThemeController(): ThemeController {
  if (window.NiumaTheme) return window.NiumaTheme;
  const key = "niuma:theme";
  const root = document.documentElement;
  let media: MediaQueryList | undefined;
  try {
    media = window.matchMedia("(prefers-color-scheme: dark)");
  } catch {
    /* Light is the platform fallback. */
  }
  function valid(value: unknown): ThemePreference {
    return value === "light" || value === "dark" ? value : "system";
  }
  let preference: ThemePreference = "system";
  try {
    preference = valid(window.localStorage.getItem(key));
  } catch {
    /* Storage is optional. */
  }
  let snapshot: ThemeSnapshot = {
    preference,
    resolved: preference === "system" ? (media?.matches ? "dark" : "light") : preference,
  };
  const listeners = new Set<() => void>();
  function apply() {
    const resolved = preference === "system" ? (media?.matches ? "dark" : "light") : preference;
    const changed = snapshot.preference !== preference || snapshot.resolved !== resolved;
    snapshot = changed ? { preference, resolved } : snapshot;
    root.dataset.theme = resolved;
    root.dataset.themePreference = preference;
    root.classList.toggle("dark", resolved === "dark");
    root.style.colorScheme = resolved;
    if (changed) for (const listener of listeners) listener();
  }
  const controller: ThemeController = {
    getSnapshot: () => snapshot,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    setPreference(value) {
      preference = valid(value);
      try {
        window.localStorage.setItem(key, preference);
      } catch {
        /* Keep this page usable. */
      }
      apply();
    },
  };
  media?.addEventListener("change", () => {
    if (preference === "system") apply();
  });
  window.addEventListener("storage", (event) => {
    if (event.key === key || event.key === null) {
      preference = valid(event.newValue);
      apply();
    }
  });
  window.addEventListener("pageshow", (event) => {
    if (!event.persisted) return;
    try {
      preference = valid(window.localStorage.getItem(key));
    } catch {
      /* Keep the in-memory choice. */
    }
    apply();
  });
  window.NiumaTheme = controller;
  apply();
  return controller;
}

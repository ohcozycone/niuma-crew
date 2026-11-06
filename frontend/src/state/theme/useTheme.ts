import { useSyncExternalStore } from "react";
import { installThemeController } from "./themeController";

export function useTheme() {
  const controller = installThemeController();
  const snapshot = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getSnapshot,
  );
  return { ...snapshot, setPreference: controller.setPreference };
}

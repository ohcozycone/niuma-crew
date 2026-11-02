import { useLayoutEffect, useState } from "react";
import { useTheme } from "@/state/theme/useTheme";
import source from "@/design-system/theme.css?raw";
import { themeDeclarations, type ThemeMode } from "@/design-system/themeValues";

function read(mode: ThemeMode) {
  const declarations = themeDeclarations(source, mode);
  const computed = getComputedStyle(document.documentElement);
  return {
    declarations,
    values: Object.fromEntries(
      Object.keys(declarations).map((name) => [name, computed.getPropertyValue(name).trim()]),
    ),
  };
}
export function useThemeValues() {
  const { resolved } = useTheme();
  const [snapshot, setSnapshot] = useState(() => read(resolved));
  useLayoutEffect(() => {
    setSnapshot(read(resolved));
  }, [resolved]);
  return { ...snapshot, number: (name: string) => parseFloat(snapshot.values[name]) };
}

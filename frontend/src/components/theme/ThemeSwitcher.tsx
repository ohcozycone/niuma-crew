import { useEffect, useState } from "react";
import { Check, ChevronDown, Monitor } from "lucide-react";
import { useTheme } from "@/state/theme/useTheme";
import type { ThemePreference } from "@/state/theme/themeController";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuRadioItemIndicator,
} from "@/components/ui/DropdownMenu";
import { ThemeArtwork } from "./ThemeArtwork";
import { cn } from "@/lib/utils";
const labels = { light: "日间", dark: "夜间", system: "跟随系统" };
const triggerClasses =
  "relative grid h-8 place-items-center rounded-small border-0 bg-transparent p-0 text-inherit shadow-none hover:text-text focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-focus [@media(pointer:coarse)]:size-11";
export function ThemeSwitcher({ className }: { className?: string }) {
  const { preference, resolved, setPreference } = useTheme();
  const [open, setOpen] = useState(false);
  const [ready, setReady] = useState(false);
  const [status, setStatus] = useState("");
  useEffect(() => {
    let frame = requestAnimationFrame(() => {
      frame = requestAnimationFrame(() => setReady(true));
    });
    return () => cancelAnimationFrame(frame);
  }, []);
  const next = resolved === "dark" ? "light" : "dark";
  const context = preference === "system" ? `跟随系统 · 当前${labels[resolved]}` : labels[resolved];
  const action = `切换至${labels[next]}${preference === "system" ? "并转为手动模式" : ""}`;
  function choose(value: ThemePreference) {
    setPreference(value);
    setStatus(value === "system" ? "已跟随系统" : `已切换为${labels[value]}模式`);
  }
  return (
    <div
      className={cn(
        "os-theme-switcher group/theme relative isolate inline-flex h-(--os-control-small) w-11 shrink-0 items-center text-text-muted [@media(pointer:coarse)]:h-11 [@media(pointer:coarse)]:w-22",
        className,
      )}
      data-ready={ready || undefined}
      data-theme-switcher
      aria-label="外观"
    >
      <button
        type="button"
        className={cn(triggerClasses, "w-8")}
        aria-label={`${context}；${action}`}
        title={`${context}；点击${action}`}
        onClick={() => {
          setOpen(false);
          choose(next);
        }}
      >
        <span className="relative block size-[26px] overflow-hidden" aria-hidden="true">
          <span className="absolute top-px left-px size-6 opacity-100 [transform:translate(0,0)_rotate(0deg)] dark:opacity-0 dark:[transform:translate(-9px,29px)_rotate(-45deg)] group-data-ready/theme:[transition:transform_calc(var(--os-theme-duration)*0.74)_cubic-bezier(0.2,0.9,0.22,1.22)_calc(var(--os-theme-duration)*0.16),opacity_calc(var(--os-theme-duration)*0.34)_linear_calc(var(--os-theme-duration)*0.16)] dark:group-data-ready/theme:[transition:transform_calc(var(--os-theme-duration)*0.43)_cubic-bezier(0.6,0,1,0.6),opacity_calc(var(--os-theme-duration)*0.29)_linear] motion-reduce:transition-none!">
            <ThemeArtwork kind="light" />
          </span>
          <span className="absolute top-px left-px size-6 opacity-0 [transform:translate(9px,29px)_rotate(35deg)] dark:opacity-100 dark:[transform:translate(0,0)_rotate(0deg)] group-data-ready/theme:[transition:transform_calc(var(--os-theme-duration)*0.43)_cubic-bezier(0.6,0,1,0.6),opacity_calc(var(--os-theme-duration)*0.29)_linear] dark:group-data-ready/theme:[transition:transform_calc(var(--os-theme-duration)*0.74)_cubic-bezier(0.2,0.9,0.22,1.22)_calc(var(--os-theme-duration)*0.16),opacity_calc(var(--os-theme-duration)*0.34)_linear_calc(var(--os-theme-duration)*0.16)] motion-reduce:transition-none!">
            <ThemeArtwork kind="dark" />
          </span>
        </span>
        {preference === "system" && (
          <span
            aria-hidden="true"
            className="pointer-events-none absolute right-[calc(50%-16px)] bottom-[calc(50%-15px)] size-3 text-center text-[10px] leading-3 tracking-[normal]"
          >
            A
          </span>
        )}
      </button>
      <DropdownMenu open={open} onOpenChange={setOpen} modal={false}>
        <DropdownMenuTrigger
          className={cn(triggerClasses, "w-3 [&>svg]:size-2.5")}
          aria-label={`选择外观模式，当前${labels[preference]}`}
          title={`外观：${labels[preference]}`}
        >
          <ChevronDown strokeWidth={1.25} />
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align="end"
          className="z-100 w-[206px] max-w-[calc(100vw-16px)] rounded-panel bg-raised p-1.5 text-[13px] leading-normal"
          aria-label="外观模式"
        >
          <div className="px-2 pt-[5px] pb-[7px] text-xs text-text-muted">外观</div>
          <DropdownMenuRadioGroup
            value={preference}
            onValueChange={(value: ThemePreference) => choose(value)}
          >
            {(["light", "dark", "system"] as const).map((value) => (
              <DropdownMenuRadioItem
                key={value}
                value={value}
                closeOnClick
                className="focus-inset grid min-h-[38px] w-full cursor-pointer grid-cols-[20px_minmax(0,1fr)_15px] items-center gap-2.5 rounded-control border-0 bg-transparent px-2 py-[7px] text-left outline-none hover:bg-muted data-highlighted:bg-muted data-checked:bg-selected [@media(pointer:coarse)]:min-h-11"
              >
                {value === "system" ? (
                  <Monitor className="size-[18px] text-text-muted" />
                ) : (
                  <span className="relative block h-6 w-5" aria-hidden="true">
                    <ThemeArtwork
                      kind={value}
                      className={value === "light" ? "-left-0.5 scale-80" : "left-[3px]"}
                    />
                  </span>
                )}
                <span>
                  {labels[value]}
                  {value === "system" && (
                    <small className="block text-[11px] leading-normal text-text-muted">
                      {preference === "system"
                        ? `当前为${labels[resolved]}`
                        : "与设备深浅色保持一致"}
                    </small>
                  )}
                </span>
                <DropdownMenuRadioItemIndicator
                  keepMounted
                  className="invisible size-[15px] data-checked:visible"
                >
                  <Check className="size-full" strokeWidth={1.75} />
                </DropdownMenuRadioItemIndicator>
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>
      <span className="sr-only" aria-live="polite" aria-atomic="true">
        {status}
      </span>
    </div>
  );
}

import { cn } from "@/lib/utils";
export function ThemeArtwork({ kind, className }: { kind: "light" | "dark"; className?: string }) {
  return kind === "light" ? (
    <span
      className={cn(
        "absolute top-0 left-0 size-6 before:absolute before:inset-0 before:bg-[repeating-conic-gradient(from_-3deg,var(--os-sun-ray)_0deg_7deg,transparent_7deg_45deg)] before:[mask:radial-gradient(circle,transparent_0_8.4px,#000_8.5px_10.5px,transparent_10.6px)] after:absolute after:inset-[6px] after:rounded-full after:bg-[radial-gradient(circle_at_32%_25%,var(--os-sun-highlight),var(--os-sun)_72%,var(--os-sun-shade))]",
        className,
      )}
    />
  ) : (
    <span
      className={cn(
        "absolute top-[4.5px] left-[4.5px] size-[15px] rounded-full [background:radial-gradient(circle_at_35%_68%,var(--os-moon-crater)_0_1.4px,transparent_1.6px),radial-gradient(circle_at_23%_33%,var(--os-moon-crater)_0_0.8px,transparent_1px),linear-gradient(130deg,var(--os-moon-highlight),var(--os-moon)_72%)] [mask:radial-gradient(circle_at_84%_17%,transparent_0_6px,#000_6.4px)]",
        className,
      )}
    />
  );
}

import { lazy, Suspense } from "react";
import { cn } from "@/lib/utils";
import type { CharacterSvgProps, SvgCharacterId } from "./svgAvatar";

const characters = {
  "intern-bull": lazy(() =>
    import("./svg/intern-bull").then((m) => ({ default: m.InternBullAvatar })),
  ),
  "finance-bull": lazy(() =>
    import("./svg/finance-bull").then((m) => ({ default: m.FinanceBullAvatar })),
  ),
  "admin-bull": lazy(() =>
    import("./svg/admin-bull").then((m) => ({ default: m.AdminBullAvatar })),
  ),
  "designer-bull": lazy(() =>
    import("./svg/designer-bull").then((m) => ({ default: m.DesignerBullAvatar })),
  ),
  "programmer-horse": lazy(() =>
    import("./svg/programmer-horse").then((m) => ({ default: m.ProgrammerHorseAvatar })),
  ),
  "backend-horse": lazy(() =>
    import("./svg/backend-horse").then((m) => ({ default: m.BackendHorseAvatar })),
  ),
  "frontend-bull": lazy(() =>
    import("./svg/frontend-bull").then((m) => ({ default: m.FrontendBullAvatar })),
  ),
  "product-horse": lazy(() =>
    import("./svg/product-horse").then((m) => ({ default: m.ProductHorseAvatar })),
  ),
  "sysadmin-horse": lazy(() =>
    import("./svg/sysadmin-horse").then((m) => ({ default: m.SysadminHorseAvatar })),
  ),
  "knowledge-bull": lazy(() =>
    import("./svg/knowledge-bull").then((m) => ({ default: m.KnowledgeBullAvatar })),
  ),
  "research-horse": lazy(() =>
    import("./svg/research-horse").then((m) => ({ default: m.ResearchHorseAvatar })),
  ),
  "operations-bull": lazy(() =>
    import("./svg/operations-bull").then((m) => ({ default: m.OperationsBullAvatar })),
  ),
  "support-horse": lazy(() =>
    import("./svg/support-horse").then((m) => ({ default: m.SupportHorseAvatar })),
  ),
} satisfies Record<SvgCharacterId, unknown>;

export function LazySvgAvatar({
  character,
  size = 96,
  alt = "",
  className,
  ...props
}: CharacterSvgProps & { character: SvgCharacterId }) {
  const Character = characters[character];
  return (
    <Suspense
      fallback={
        <svg
          {...props}
          width={size}
          height={size}
          viewBox="0 0 1254 1254"
          role={alt ? "img" : undefined}
          aria-label={alt || undefined}
          aria-hidden={!alt || undefined}
          data-avatar-character={character}
          data-avatar-loading
          className={cn("inline-block aspect-square shrink-0 align-middle", className)}
          style={{ width: size, height: size }}
        />
      }
    >
      <Character {...props} size={size} alt={alt} className={className} />
    </Suspense>
  );
}

import { InternBullAvatar } from "./intern-bull";
import { FinanceBullAvatar } from "./finance-bull";
import { AdminBullAvatar } from "./admin-bull";
import { DesignerBullAvatar } from "./designer-bull";
import { ProgrammerHorseAvatar } from "./programmer-horse";
import { BackendHorseAvatar } from "./backend-horse";
import { FrontendBullAvatar } from "./frontend-bull";
import { ProductHorseAvatar } from "./product-horse";
import { SysadminHorseAvatar } from "./sysadmin-horse";
import { KnowledgeBullAvatar } from "./knowledge-bull";
import { ResearchHorseAvatar } from "./research-horse";
import { OperationsBullAvatar } from "./operations-bull";
import { SupportHorseAvatar } from "./support-horse";
import type { CharacterSvgProps } from "./frame";
export { InternBullAvatar } from "./intern-bull";
export { FinanceBullAvatar } from "./finance-bull";
export { AdminBullAvatar } from "./admin-bull";
export { DesignerBullAvatar } from "./designer-bull";
export { ProgrammerHorseAvatar } from "./programmer-horse";
export { BackendHorseAvatar } from "./backend-horse";
export { FrontendBullAvatar } from "./frontend-bull";
export { ProductHorseAvatar } from "./product-horse";
export { SysadminHorseAvatar } from "./sysadmin-horse";
export { KnowledgeBullAvatar } from "./knowledge-bull";
export { ResearchHorseAvatar } from "./research-horse";
export { OperationsBullAvatar } from "./operations-bull";
export { SupportHorseAvatar } from "./support-horse";
export type { CharacterSvgProps } from "./frame";
export const svgCharacters = [
  { id: "intern-bull", label: "实习生牛", focus: [620, 420] },
  { id: "finance-bull", label: "财务牛", focus: [560, 400] },
  { id: "admin-bull", label: "行政牛", focus: [800, 470] },
  { id: "designer-bull", label: "设计师牛", focus: [550, 340] },
  { id: "programmer-horse", label: "程序员马", focus: [680, 435] },
  { id: "backend-horse", label: "后端马", focus: [805, 525] },
  { id: "frontend-bull", label: "前端牛", focus: [665, 445] },
  { id: "product-horse", label: "产品经理马", focus: [585, 350] },
  { id: "sysadmin-horse", label: "运维马", focus: [560, 360] },
  { id: "knowledge-bull", label: "知识牛", focus: [550, 340] },
  { id: "research-horse", label: "研究马", focus: [560, 380] },
  { id: "operations-bull", label: "运营牛", focus: [600, 410] },
  { id: "support-horse", label: "客服马", focus: [660, 340] },
] as const;
export type SvgCharacterId = (typeof svgCharacters)[number]["id"];
export type SvgAvatarProps = CharacterSvgProps & { character: SvgCharacterId };
const renderers = {
  "intern-bull": InternBullAvatar,
  "finance-bull": FinanceBullAvatar,
  "admin-bull": AdminBullAvatar,
  "designer-bull": DesignerBullAvatar,
  "programmer-horse": ProgrammerHorseAvatar,
  "backend-horse": BackendHorseAvatar,
  "frontend-bull": FrontendBullAvatar,
  "product-horse": ProductHorseAvatar,
  "sysadmin-horse": SysadminHorseAvatar,
  "knowledge-bull": KnowledgeBullAvatar,
  "research-horse": ResearchHorseAvatar,
  "operations-bull": OperationsBullAvatar,
  "support-horse": SupportHorseAvatar,
};
export function SvgAvatar({ character, ...props }: SvgAvatarProps) {
  const Character = renderers[character];
  if (!Character) throw new Error(`Unknown SVG avatar: ${String(character)}`);
  return <Character {...props} />;
}

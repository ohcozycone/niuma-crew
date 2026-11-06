/** Catalogue metadata only. All visual values and mappings live in theme.css. */
export const designSystem = { version: "2.7", updated: "2026-11-06" } as const;
export const colorLayers = [
  {
    id: "semantic",
    name: "语义用途",
    purpose: "开发时选色",
    description: "按背景、文字、操作等使用场景分类，页面开发优先选用。",
  },
  {
    id: "palette",
    name: "基础色板",
    purpose: "维护颜色来源",
    description: "按色系和明度登记具体色值，供日夜主题引用。",
  },
  {
    id: "component",
    name: "组件映射",
    purpose: "保留局部差异",
    description: "按组件保留必要差异，例如卡片边框的日夜对应关系。",
  },
] as const;
export const colorGroups = [
  {
    id: "surface",
    name: "背景与边界",
    usage: "先区分工作底、内容表面与抬起表面，再选择强调层级。",
  },
  { id: "text", name: "文字", usage: "正文与辅助信息共用文字语义，导航无需再复制一组颜色。" },
  { id: "control", name: "交互与遮罩", usage: "输入边界、键盘焦点和遮罩各有明确职责。" },
  { id: "action", name: "操作", usage: "背景、悬停、前景成组使用，主操作统一引用 action。" },
  { id: "brand", name: "品牌", usage: "品牌小点、强调文字与辅助衬色按用途区分。" },
  { id: "feedback", name: "反馈", usage: "前景与背景配对，并同时提供状态文字。" },
  { id: "component", name: "组件映射", usage: "只有需要独立控制的组件差异才增加映射。" },
] as const;
type ColorGroup = (typeof colorGroups)[number]["id"];
export const colorRoles = {
  canvas: { group: "surface", label: "工作底与外壳" },
  surface: { group: "surface", label: "工作区、输入与浮层" },
  raised: { group: "surface", label: "资源卡片、表格与编辑区" },
  muted: { group: "surface", label: "次级背景与悬停" },
  selected: { group: "surface", label: "普通控件选中" },
  border: { group: "surface", label: "分隔与边界" },
  text: { group: "text", label: "正文与导航文字" },
  "text-muted": { group: "text", label: "辅助文字与导航图标" },
  input: { group: "control", label: "输入边界" },
  focus: { group: "control", label: "键盘焦点兜底" },
  "field-focus": { group: "control", label: "表单焦点" },
  "disabled-bg": { group: "control", label: "禁用操作背景" },
  "disabled-text": { group: "control", label: "禁用操作文字" },
  hover: { group: "control", label: "中性悬停背景" },
  "hover-text": { group: "control", label: "中性悬停前景" },
  pressed: { group: "control", label: "中性按下背景" },
  overlay: { group: "control", label: "移动抽屉遮罩" },
  "modal-overlay": { group: "control", label: "对话框遮罩" },
  action: { group: "action", label: "主操作背景" },
  "action-hover": { group: "action", label: "主操作悬停" },
  "action-pressed": { group: "action", label: "主操作按下" },
  "action-text": { group: "action", label: "主操作文字" },
  "action-soft": { group: "action", label: "次级强调背景" },
  "action-soft-hover": { group: "action", label: "次级强调悬停" },
  "action-soft-pressed": { group: "action", label: "次级强调按下" },
  "action-soft-text": { group: "action", label: "次级强调文字" },
  "danger-action": { group: "action", label: "危险操作背景" },
  "danger-action-hover": { group: "action", label: "危险操作悬停" },
  "danger-action-pressed": { group: "action", label: "危险操作按下" },
  "danger-action-text": { group: "action", label: "危险操作文字" },
  brand: { group: "brand", label: "品牌小点与收藏" },
  "brand-text": { group: "brand", label: "品牌强调文案" },
  "title-accent": { group: "brand", label: "品牌辅助衬色" },
  success: { group: "feedback", label: "成功前景" },
  "success-bg": { group: "feedback", label: "成功背景" },
  warning: { group: "feedback", label: "警告前景" },
  "warning-bg": { group: "feedback", label: "警告背景" },
  danger: { group: "feedback", label: "危险前景" },
  "danger-bg": { group: "feedback", label: "危险背景" },
  "danger-text": { group: "feedback", label: "危险反馈实底文字" },
  info: { group: "feedback", label: "信息前景" },
  "info-bg": { group: "feedback", label: "信息背景" },
  "card-border": { group: "component", label: "卡片边界" },
  "workspace-border": { group: "component", label: "工作区外框与顶栏分隔" },
  "nav-active": { group: "component", label: "导航选中背景" },
  "nav-active-text": { group: "component", label: "导航选中文字" },
  "nav-count-bg": { group: "component", label: "导航数量背景" },
} as const satisfies Record<string, { group: ColorGroup; label: string }>;
export type ColorToken = keyof typeof colorRoles;
export const componentColors = {
  "--os-card-border": "卡片边界",
  "--os-workspace-border": "工作区外框与顶栏分隔",
  "--os-nav-active": "导航选中背景",
  "--os-nav-active-text": "导航选中文字",
  "--os-nav-count-bg": "导航数量背景",
  "--os-avatar-bg": "员工头像背板",
  "--os-code-comment": "代码注释",
  "--os-code-keyword": "代码关键字",
  "--os-code-string": "代码字符串",
  "--os-code-constant": "代码常量与类型",
  "--os-code-function": "代码函数",
  "--login-bg": "登录页面外底",
  "--login-scene": "登录品牌场景",
  "--login-border": "登录容器边界",
  "--login-title": "登录表单标题",
  "--login-input": "登录输入边界",
  "--login-ring": "登录焦点轮廓",
  "--login-selection": "登录输入选区",
  "--login-shadow": "登录场景阴影",
} as const;
export const contrastExceptions: {
  mode: "light" | "dark";
  foreground: ColorToken;
  background: ColorToken;
  target: number;
  reason: string;
}[] = [];
export const paletteFamilies = [
  { id: "gray", label: "暖白与燕麦灰", kind: "界面", usage: "日间表面、文字与表单的暖灰尺度" },
  { id: "night", label: "暖炭灰与米白", kind: "界面", usage: "夜间表面、文字与表单的暖灰尺度" },
  { id: "orange", label: "陶橙", kind: "品牌", usage: "品牌、收藏与局部强调" },
  { id: "green", label: "灰绿", kind: "反馈", usage: "成功与可用状态" },
  { id: "amber", label: "琥珀色", kind: "反馈", usage: "注意与等待确认" },
  { id: "red", label: "红色", kind: "反馈", usage: "失败与危险操作" },
  { id: "blue", label: "蓝色", kind: "反馈", usage: "信息反馈" },
  { id: "overlay", label: "透明遮罩", kind: "合成", usage: "抽屉与对话框遮罩" },
  { id: "scene", label: "场景", kind: "插画", usage: "角色接地阴影" },
  { id: "art", label: "日月插画", kind: "插画", usage: "仅用于主题入口的图形固有色" },
] as const;
export const typographyRoles = {
  page: { label: "页面标题", usage: "功能页主标题", sample: "数字员工" },
  section: { label: "区块标题", usage: "内容分组与窄屏标题", sample: "能力配置" },
  title: { label: "卡片标题", usage: "卡片与内容单元", sample: "行政管家" },
  label: { label: "辅助标识", usage: "品牌或资料分类", sample: "功能指南" },
  description: {
    label: "用途说明",
    usage: "标题后的说明",
    sample: "为合适的员工配齐能力，交办工作。",
  },
  body: { label: "正文", usage: "常规内容", sample: "把工作交给合适的员工" },
  caption: { label: "附注", usage: "数量与辅助信息", sample: "共 12 位员工" },
} as const;
export type TypographyToken = keyof typeof typographyRoles;
export const agentNavigationRoles = {
  "avatar-size": "头像尺寸",
  "favorite-gap": "头像与名称",
  "favorite-px": "横向留白",
  "favorite-py": "纵向留白",
  "favorite-stack": "行间距",
} as const;

/** Deliberate custom silhouettes; ordinary surfaces use semantic radius utilities. */
export const cornerShapeExceptions = [
  { file: "design-system/theme.css", reason: "表单 rounded-field 沿用 shadcn 普通圆角。" },
  { file: "components/ui/InputGroup.tsx", reason: "组合输入外层沿用普通圆角，半径按容器保留。" },
  { file: "pages/agents/agentCardStyles.ts", reason: "员工圆拱背板使用独立几何，保留人物构图。" },
  { file: "pages/agents/AgentConfiguration.tsx", reason: "配置页角色圆拱与员工卡片保持同一构图。" },
  { file: "pages/agents/EmployeeHomePage.tsx", reason: "员工个人页沿用角色圆拱背板。" },
  { file: "Layout.tsx", reason: "帮助气泡采用不对称四角造型。" },
] as const;

/** Geometry is read from theme.css; metadata never maintains a second numeric table. */
export const layoutRoles = {
  "--os-card-padding": { label: "资源卡片内边距", usage: "员工和知识资源卡片的共享留白" },
  "--os-workspace-max": {
    label: "工作台外框上限",
    usage: "资源与配置页面的外框，包含两侧留白",
  },
  "--os-conversation-standard": {
    label: "常规对话外框",
    usage: "居中阅读，包含正文行长与两侧留白",
  },
  "--os-conversation-wide": {
    label: "宽屏对话外框",
    usage: "1920px 起给表格、代码和输入适度增加空间",
  },
  "--os-conversation-ultrawide": {
    label: "超宽屏对话外框",
    usage: "2560px 起扩展结构化内容，文字行长独立保持",
  },
  "--os-conversation-sidebar-width": {
    label: "对话辅助栏",
    usage: "工作区可并排时展示员工历史对话与能力，正文单独限宽",
  },
  "--os-navigation-width": { label: "桌面侧栏", usage: "外壳占位与内容偏移共用" },
  "--os-employee-min": { label: "员工卡片并列预算", usage: "空间不足时单列紧凑构图" },
  "--os-capability-min": { label: "简单能力并列预算", usage: "内容目录与嵌入集合共用" },
  "--os-connection-min": { label: "复杂连接并列预算", usage: "为状态、标识和操作保留空间" },
  "--os-preview-width": { label: "配置预览", usage: "主区预算充足时才并列" },
  "--os-agent-editor-max": { label: "员工编辑外框", usage: "居中限制字段与指令编辑宽度" },
  "--os-agent-context-width": { label: "指令辅助栏", usage: "集中继承规则与知识入口" },
  "--os-field-max": { label: "普通字段组上限", usage: "长标识、编辑器与数据区使用主区全宽" },
  "--os-prose-chat": { label: "对话正文行长", usage: "只作用于段落、列表、引用" },
  "--os-prose-article": { label: "独立文章行长", usage: "中文说明文；不限制工具与数据" },
  "--os-question-reserve": { label: "对话导航避让", usage: "普通屏消息右侧留出快捷目录空间" },
} as const;

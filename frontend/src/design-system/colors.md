# 颜色令牌与用法

数值与日夜映射只在 [theme.css](theme.css) 维护；[spec.ts](spec.ts) 登记用途，`/design-system#colors` 展示实际计算值及引用来源。本页说明如何选色，不维护第二份色值表。

## 三层职责

| 层级         | 示例                                | 用途                                           |
| ------------ | ----------------------------------- | ---------------------------------------------- |
| 基础色       | `--gray-25`、`--night-850`          | 集中登记具体颜色，仅主题定义和色板展示直接使用 |
| 语义用途     | `--os-surface`、`--os-text`         | 页面按用途选择，两种主题沿用相同名称           |
| 必要组件映射 | `--os-card-border`、`--login-scene` | 保留组件实际差异，通过引用复用基础或语义层     |

基础色按日间灰阶、夜间灰阶、品牌、反馈、遮罩和插画分类。字面色值只登记一次；组件和业务页面不直接选择灰阶或硬编码色值。

## 当前配色

日间以暖白资源卡片、浅暖灰工作区和深灰文字组织阅读层次；raised 比 surface 更明亮，使用轻边界区分资源。夜间以暖炭灰和米白文字区分工作底、内容表面、抬起表面与次级背景。陶橙用于品牌强调和 3px Tab 活动线，灰绿用于成功和可用状态，警告、危险和信息保持各自含义及低饱和度。主按钮日间使用暖墨底浅字、夜间使用柔和米色深字。

所有普通表面上的正文与辅助文字均按至少 4.5:1 检查，含资源卡片、工作底、选中及次级背景；键盘焦点和表单聚焦边界至少 3:1。静态错误页、帮助、Markdown 和文档站继续复用同一来源；头像与品牌插画的固有颜色保持原画。初轮验证见暖色主题验收，日间表面见暖白卡片验收。

展示页的三个分类按职责划分：语义用途按背景、文字、操作等使用场景分组，作为页面开发的首选；基础色板按色系和明度呈现具体数值，供主题维护；组件映射保留必要的组件差异。分类依据直接展示在目录上方，每个分类附实际用法示例。语义用途的分组卡片采用响应式瀑布流，桌面两列、窄屏单列；组内顺序与键盘阅读顺序保留。

## 通用语义

| 分组       | 令牌                                                                    | 选择原则                                                                                                   |
| ---------- | ----------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| 背景与边界 | `canvas`、`surface`、`raised`、`muted`、`selected`、`border`            | 工作底与外壳共用 canvas，右侧工作区、输入和普通浮层使用 surface，资源卡片使用 raised；选中和悬停按状态选择 |
| 文字       | `text`、`text-muted`                                                    | 正文与导航文字共用 text，辅助内容和常态导航图标使用 text-muted                                             |
| 交互与遮罩 | `input`、`focus`、`field-focus`、`overlay`、`modal-overlay`             | 输入边界、键盘焦点、抽屉遮罩与对话框遮罩分别使用                                                           |
| 操作       | `action`、`action-hover`、`action-text`                                 | 主按钮的背景、悬停与前景                                                                                   |
| 品牌       | `brand`、`brand-text`、`title-accent`                                   | 小点与收藏、强调文案、品牌辅助衬色，不借用状态色                                                           |
| 反馈       | `success`、`warning`、`danger`、`info` 及各自 `-bg`，另有 `danger-text` | 前景与背景配对；危险按钮使用独立前景，状态同时有文字或图标                                                 |

上述名称统一加 `--os-`。完整接口及用途分组以 spec.ts 实际登记为准，导航等必要组件映射仍属于全站接口。用途完全重复的变量已经合并，不维护另一套旧名兼容色板。

## 组件映射

| 变量                                                                   | 保留原因                                                     |
| ---------------------------------------------------------------------- | ------------------------------------------------------------ |
| `--os-card-border`                                                     | 两主题均引用 border，采用轻实色边界                          |
| `--os-workspace-border`                                                | 右侧工作区外框与header底线，日夜分别使用比普通边界更弱的灰阶 |
| `--os-nav-active`、`--os-nav-active-text`                              | 暖灰当前态，深于临时 hover，前景引用 text，配合 500 字重     |
| `--os-nav-count-bg`                                                    | 日间引用 muted，夜间引用 selected                            |
| `--os-avatar-bg`                                                       | 所有员工共用中性背板；日间浅暖灰，夜间引用 selected          |
| `--login-bg`、`--login-scene`、`--login-border`、`--login-title`       | 登录外底、场景、容器与表单标题的实际差异                     |
| `--login-input`、`--login-ring`、`--login-selection`、`--login-shadow` | 登录输入线、焦点、选区与角色接地阴影                         |

登录按钮、正文、辅助文字、品牌与错误直接复用通用语义，不再复制整套登录颜色。日月插画用 `--art-*` 基础色，经 `--os-sun-*`／`--os-moon-*` 引用；其固有色不用于状态或界面表面。

两个角色在某一主题同色，不代表应合并。例如导航选中前景当前引用 text，但背景配对属于导航状态，仍保留独立组件映射。合理抽象以用途和完整日夜映射为依据。

## 命名

文字用途使用 `text`、`text-muted`，操作前景使用 `action-text`，导航当前前景使用 `nav-active-text`。文字角色按 `--os-type-<角色>-<属性>` 组织，属性使用 `size`、`weight`、`leading`、`tracking`、`color`；背景后缀使用 `bg`，组件组合不重复上下文，例如 `--os-card-gap`。完整接口以 CSS 声明与展示目录为准。

## 组件使用

```tsx
<section className="rounded-card border border-border bg-surface p-4 text-text">
  <p className="text-text-muted">员工详情</p>
</section>
```

```css
/* 现有 CSS 消费同一语义；新静态页面样式按工程手册使用工具类。 */
.agent-panel {
  background: var(--os-surface);
  color: var(--os-text);
  border: 1px solid var(--os-border);
}
```

Tailwind 与 CSS 消费同一语义源；应用颜色工具类与语义名称一致，例如 `bg-action`、`text-action-text`、`border-input`、`ring-focus`。应用不使用第三方颜色别名或 body 主题外壳。文字和 SVG 图标优先继承前景，装饰图标使用 `currentColor`。

默认输入边界 `input` 沿用同源暖灰，表单焦点 `field-focus` 使用日间较深暖灰、夜间较浅暖灰，边框至少 3:1，外圈为 3px、50% 透明度。其他交互的键盘轮廓使用 `focus`；`login-ring` 引用此兜底，登录字段容器使用 `field-focus`。输入、选择与搜索共用同一规则，具体映射只在 theme.css 维护。

新增颜色先明确用途：通用语义能覆盖时直接复用；确需新用途时在 `theme.css` 定义基础引用与完整日夜映射，在 `spec.ts` 登记，并验证消费者、对比度、首屏及浮层继承。禁止未定义引用与循环；导航已改用中性背景和正文前景，原日间橙白配对限制已移除，日夜均执行普通小字的对比度检查。

## Markdown 渲染器主题

Streamdown 使用官方支持的 CSS 主题变量，接入已完成，实际验证状态见[当前适配说明](../../../docs/reference/design-system.md#markdown-官方主题接入)。Tailwind v4 在 `theme.css` 的 `@theme inline` 中直接将库需要的颜色名称映射到项目语义，不重复定义色值：

| 库的 Tailwind 颜色              | 项目来源                          | 用途                                         |
| ------------------------------- | --------------------------------- | -------------------------------------------- |
| `background`                    | `--os-surface`                    | 代码正文、菜单、图片与表格全屏、链接确认浮层 |
| `foreground`                    | `--os-text`                       | 正文与交互前景                               |
| `primary`／`primary-foreground` | `--os-action`／`--os-action-text` | 链接与确认操作                               |
| `muted-foreground`              | `--os-text-muted`                 | 工具栏、辅助文字与行号                       |
| `sidebar`                       | `transparent`                     | 保持代码块／表格外框与工具栏的原有透明背景   |

`muted`、`border`、`input` 已与项目语义同名，复用既有映射。工具栏背景与边框在库中共用 `sidebar`；边框通过 `globals.css` 的 `[data-streamdown="code-block-actions"]` 与 `[data-streamdown="mermaid-block-actions"]` 单独引用 `--os-border`。样式只使用官方属性标记，不依赖内部 DOM 层级或打包后的类名。应用代码继续使用项目语义类，以上名称仅用于第三方接入，不恢复旧的应用令牌。

根元素的 `data-theme` 切换现有 `--os-*` 值，`.dark` 与 Tailwind 夜间变体保持同步；无需额外的 Streamdown 主题状态。`@streamdown/code` 通过官方 createCodePlugin 注册 `niuma-light`／`niuma-dark`，共用 codeTheme.json 的语法角色；颜色引用现有 code 语义，并通过根变量与官方夜间变体切换。映射位于全局入口，挂到 body 的浮层同样生效。

升级时保留原版依赖与锁文件，检查库是否新增颜色角色及公开标记；执行契约测试、构建和两主题下代码块／工具栏、表格／全屏、链接确认及图片／下载控件的浏览器验证。不再维护依赖补丁。官方接口见[样式说明](https://streamdown.ai/docs/styling)与[代码块](https://streamdown.ai/docs/code-blocks)。

按钮次级强调使用 `action-soft`、`action-soft-hover`、`action-soft-pressed`、`action-soft-text` 成组接口，日间为浅陶色与深陶色文字，夜间为深陶色与浅陶色文字。卡片操作复用 outline，不再维护单独的按钮颜色映射。

危险实心按钮使用 `danger-action*` 独立于反馈前景 `danger`，夜间深砖红底配浅字；主操作使用柔和米色。按钮的悬停／按下使用明确状态色，不用整体透明度混色；禁用使用中性主题层级，加载保留动作层级。

中性 hover／hover-text／pressed 为未选导航、按钮、账户与操作菜单共享；导航选中是更深一级的暖灰且持续显示。日间主操作用暖墨色，小幅改变状态明度；浅陶色的悬停和按下同样采用较小的明度变化。

禁用操作使用 disabled-bg／disabled-text 独立映射；实底和描边按钮禁用时均移除描边，底色贴近内容表面，文字与图标采用弱化前景和 400 字重，区别可用次操作。项目将真正禁用标签的对比度控制在 2.5—3.5:1，兼顾轮廓可辨与不可用的视觉信号；透明轻操作同时检查工作区背景。“已保存”等原因说明与正常文字继续按至少 4.5:1 检查。此范围是项目设计选择；[WCAG 对非交互控件的说明](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html#inactive-user-interface-components)明确将禁用控件与正常文本的对比度要求区分，不能把该弱化规则用于可用控件或正文。

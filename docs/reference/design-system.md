# 设计系统展示与第三方主题接入

本文描述当前展示目录和第三方适配边界。视觉数值、令牌、组件外观与状态以[源码旁设计系统](../../frontend/src/design-system/README.md)、[颜色用法](../../frontend/src/design-system/colors.md)、[组件规范](../../frontend/src/design-system/components.md)为权威来源。历史改造与验证见记录。

完整组件类型和现行空间设计见[组件分类](../../frontend/src/design-system/component-catalog.md)、[布局与响应式](../../frontend/src/design-system/layout.md)及[源码清单](../../frontend/src/design-system/component-inventory.md)。规则已接入正式页面，`/design-system#layout` 提供实时令牌与容器样例。迁移职责见实施方案。

## 展示目录

跨页业务对象、动作、生效时机与危险操作确认由[对象、动作与确认](../../frontend/src/design-system/resource-language.md)统一维护。`/design-system#resource-language` 直接展示正式 ResourceIcon 与 ConfirmActionDialog，不维护另一套图形。

/design-system 使用真实组件与独立演示数据，展示布局、颜色、文字、组件和组合模式。页面分类与名称来自 spec.ts；展示页读取浏览器实际计算值，业务模块不导入展示页或 fixtures。语义色卡按用途分组，桌面瀑布流、窄屏单列；搜索、深链、复制和键盘行为由展示页维护。

实现入口为[展示页面](../../frontend/src/pages/design-system/DesignSystemPage.tsx)、[目录元数据](../../frontend/src/design-system/spec.ts)与[主题读取器](../../frontend/src/pages/design-system/useThemeValues.ts)。目录不维护第二份色值，视觉规则调整同步真实组件与示例。

## Markdown 官方主题接入

Streamdown 保留原版依赖和锁文件，通过官方公开主题角色与 data-streamdown 标记适配。theme.css 将库角色映射到项目语义变量，工具栏边界差异由 globals.css 的公开属性选择器处理。详细映射与升级核对见[颜色规范](../../frontend/src/design-system/colors.md#markdown-渲染器主题)。

当前已移除发布 JS 颜色补丁及补丁登记；历史评审中的补丁成本属于旧快照。升级验证日夜、Portal、代码与表格全屏、链接确认和图片查看器；库默认能力不替代项目的链接与数据边界。

## 验证入口

[令牌契约测试](../../frontend/src/design-system/tokenContract.test.ts)、[主题值测试](../../frontend/src/design-system/themeValues.test.ts)、[主题资产测试](../../frontend/src/state/theme/themeAssets.test.ts)核对当前实现。浏览器检查范围与实际结果单独记录，旧截图不能代替升级回归。

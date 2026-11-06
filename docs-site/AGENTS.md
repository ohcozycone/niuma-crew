# 文档站维护入口

- 先读[站点说明](README.md)、[项目文档规范](../docs/documentation.md)和[共享工程约定](../docs/engineering/shared.md)。
- 正文修改回到原始 Markdown；发布清单在 scripts/content.mjs，生成目录不能人工维护。
- 修改界面时读取[平台设计系统](../frontend/src/design-system/README.md)，验证中文搜索、主题和窄屏导航；使用 make check-docs-site 检查站点，make check-docs 检查原文。
- Next.js 与 Fumadocs 接口先核对当前安装版本的类型和官方文档；Next.js 本地参考位于 node_modules/next/dist/docs。

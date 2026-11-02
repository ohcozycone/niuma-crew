# 前端构建脚本

本目录维护正式前端开发、构建与检查所需的脚本，直接使用 [package.json](../package.json) 声明的依赖，由前端统一执行 lint 和格式检查。脚本使用相对于自身文件的路径，不依赖调用者的当前目录。

| 脚本                                                             | 职责与调用入口                                                                                                                                                        |
| ---------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [build-brand.mjs](build-brand.mjs)                               | 从登录品牌图形和主题令牌生成日夜字标，复制独立图标；开发和构建自动执行，根目录 `make build-brand` 可单独执行                                                          |
| [build-theme.mjs](build-theme.mjs)                               | 从同源主题令牌和 [themeController](../src/state/theme/themeController.ts) 生成首屏 CSS 与初始化脚本，由 Vite 的 HTML 插件调用                                         |
| [build-avatar-manifest.mjs](build-avatar-manifest.mjs)           | 从 `public/avatars/catalog.json` 生成浏览器使用的 TypeScript 快照；开发、构建、测试与类型检查自动执行，根目录 `make build-avatar-manifest` 可单独执行                 |
| [build-frontend-compression.mjs](build-frontend-compression.mjs) | 在 Vite 生产构建后为 HTML、CSS、JS、SVG、JSON 生成 gzip 和 Brotli 副本                                                                                                |
| [build-failure-pages.mjs](build-failure-pages.mjs)               | 从共享错误文案 JSON 与主题生成 `dist/failures/{404,500,502,503,504}.html`，在 Vite 构建后、压缩前执行；同时向 HTML 插件提供无 JS/入口失败兜底，开发服务器按需提供文档 |

移动源码时同步更新脚本读取路径；[首屏构建回归](../src/state/theme/themeAssets.test.ts)通过 Node 实际生成并执行主题初始化脚本。根目录 `make lint-frontend-scripts` 单独检查本目录，也包含在 `make lint-frontend` 中。品牌源稿约束见[品牌设计](../../docs/reference/brand.md)。

头像制作工具、Rive、母版与历史产物位于同级独立归档，正式静态 SVG 保留在应用内。边界与迁移依据见[素材隔离设计](../../docs/guides/assets.md)。

静态错误文档直接消费 `src/lib/failures/copy.json`，不执行 React 或业务模块；配图位于 `public/failures/`。入口观察器只把明确脚本失败称为资源失败，等待超时只显示加载较慢；收到 React 首次真实提交的 `app:mounted` 事件后移除兜底与监听。生成器与启动观察的回归在 [build-failure-pages.test.mjs](build-failure-pages.test.mjs)。可选代理交付和未覆盖的真实停机验收见 [Nginx 说明](../../deploy/nginx/README.md)。

# 客户端路由迁移与专项复查

记录日期：2026-10-21。原验证环境与限制保留如下，本次仅整理文档。

## 迁移时验证

前端 15 个测试文件、89 项测试通过；后端 195 项通过；保留的头像制作工具 53 项通过。lint、TypeScript、Prettier、Vite 生产构建及离线 frozen-lockfile 安装通过。浏览器在 Vite 开发代理和 FastAPI 生产交付下验证登录、共享外壳、URL/草稿/滚动恢复、保存、会话单次提交与重连、SSE 首包、游客边界和移动导航，无页面异常，未调用真实模型。

[验证记录](../../../niuma-crew-archive/output/reviews/client-routing/validation.json)、[生产浏览器记录](../../../niuma-crew-archive/output/reviews/client-routing/browser-production.json)、[开发浏览器记录](../../../niuma-crew-archive/output/reviews/client-routing/browser-development.json)。Markdown/语法高亮仍有大分包提示，构建成功，本次未缩减支持的语法范围。

## 路由专项复查（2026-10-21）

修复六处遗漏：大脑搜索未进入 URL、大脑员工链接整页加载、会话新对话链接整页加载、会话详情返回丢失列表页码、提交成功响应晚于离页时已发送草稿残留，以及滚动恢复期间的临时偏移覆盖与刷新前漏存窗口。业务链接、来源返回、草稿清理与滚动行为遵循上方统一规则。

最终 Vite 开发环境 30 组、FastAPI 生产交付 31 组浏览器回归全部通过，无未捕获异常。覆盖员工/技能新建与编辑、筛选与配置标签、知识资料弹窗、大脑搜索、对话分页/草稿/单次提交/重连、保存中离页和保存失败、过期草稿、滚动与加载中再次刷新、游客和登录失效、兼容链接、帮助与预览、移动导航和生产深链/404。测试使用独立 SQLite，关闭 Runner 模型执行，未操作日常数据或调用真实模型。

前端 16 个测试文件、118 项单元测试通过；后端静态交付 21 项测试通过；lint、TypeScript、本次修改文件格式及生产构建通过。全量 `format:check` 未通过：8 个 SVG 组件与 `CHARACTERS.md`、`colors.md` 共 10 个非本次修改文件存在格式告警，未混入本次路由修复。语法高亮大分包提示仍保留。

[专项汇总与复现入口](../../../niuma-crew-archive/output/reviews/client-routing-recheck/validation.json)、[开发环境记录](../../../niuma-crew-archive/output/reviews/client-routing-recheck/development.json)、[生产环境记录](../../../niuma-crew-archive/output/reviews/client-routing-recheck/production.json)。本轮检查没有覆盖真实模型输出效果。

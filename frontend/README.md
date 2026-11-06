# NiumaCrew Web

React + Vite + React Router 客户端，FastAPI 提供 API 与生产静态交付。首次安装、数据库迁移和管理员初始化见[根目录启动流程](../README.md#本地运行)。以下命令均在仓库根目录执行。

## 从用户操作理解前端

工作台让用户先配置或选择员工，再提交需求、读进展和成果。前端负责让表单、导航、草稿和读取状态清楚一致，后端决定权限、业务状态及实际执行；页面隐藏按钮不能代替服务端授权。

初次阅读从[平台说明](../docs/product/README.md)和[使用流程](../docs/product/workflows.md)开始；[前端架构](../docs/architecture/frontend.md)解释页面、共享组件、状态和接口客户端怎样分工。

| 用户工作                               | 模块说明                                           |
| -------------------------------------- | -------------------------------------------------- |
| 搜索、配置岗位及选择能力               | [员工](src/pages/agents/README.md)                 |
| 检索能力、创建/导入/同步技能           | [能力库与技能](src/pages/skills/README.md)         |
| 维护所有员工自动继承的工作规范         | [全员规范](src/pages/organization-rules/README.md) |
| 维护员工使用的模型连接                 | [大脑配置](src/pages/brains/README.md)             |
| 接入工具、确认清单、绑定本人账号       | [工具与账号](src/pages/tools/README.md)            |
| 浏览教学资料及维护全员规范             | [知识与规则](src/pages/knowledge/README.md)        |
| 发送消息、读历史、停止、重试与文件交付 | [对话](src/pages/conversations/README.md)          |
| 让目录、侧栏和编辑结果保持一致         | [共享状态与数据](src/state/README.md)              |

## 开发

```bash
make dev
```

前端固定 `http://127.0.0.1:3000`，后端端口占用时自动避让，`/api` 代理同步使用实际地址，Ctrl+C 结束两端进程。

分端排查可用 `make dev-backend BACKEND_PORT=8001` 和 `make dev-frontend BACKEND_URL=http://127.0.0.1:8001`；分端启动不自动避让。参数和退出规则见[本地开发设计](../docs/guides/local-development.md)。

## 构建与预览

```bash
make build   # 生成 frontend/dist/ 及文本资源的 gzip、Brotli 副本
make start   # 使用 FastAPI 在 3000 端口提供页面与 API
```

先升级后端数据库；切换前停止使用同一数据目录的开发服务。`make start` 使用后端 uv 环境，端口由 `START_PORT` 指定，默认 3000，不自动避让。

`make preview` 仅查看 Vite 静态产物，不提供生产 API 代理。`dist/` 也可单独部署，由网关转发 API；路径、来源和缓存规则见[后端静态交付](../docs/guides/backend-operations.md#运行)。

## 验证与资源边界

```bash
make lint-frontend   # ESLint、类型和格式检查
make test-frontend   # 前端离线测试
make build           # 生产构建
```

头像与构建脚本可分别运行 `make test-avatars`、`make lint-frontend-scripts`。底层包脚本继续在 `package.json` 维护。检查范围与生成资源边界见[工程手册](../docs/engineering/frontend.md)，资源生成入口见[构建脚本](scripts/README.md)。正式头像使用静态 SVG，制作母版与历史产物归属见[素材隔离设计](../docs/guides/assets.md)。

ESLint 规则集中维护在 `eslint.config.mjs`，项目配置回归测试位于 `eslint.config.test.ts`。

## 维护入口

| 文档                                                                                | 负责内容                                       |
| ----------------------------------------------------------------------------------- | ---------------------------------------------- |
| [工程手册](../docs/engineering/frontend.md)、[维护约定](AGENTS.md)                  | 工程标准、目录与依赖规则、开发者和 AI 工作入口 |
| [共享数据标准](src/state/README.md)                                                 | Provider、业务数据模块、订阅和同步的接入规则   |
| [前端架构](../docs/architecture/frontend.md)                                        | 路由、共享外壳、身份与状态恢复、读取和交付契约 |
| [设计系统](src/design-system/README.md)                                             | 主题令牌、组件视觉与交互规范                   |
| [员工模块](src/pages/agents/README.md)、[知识库模块](src/pages/knowledge/README.md) | 页面职责、配置与保存边界                       |
| [构建脚本](scripts/README.md)、[第三方许可](THIRD_PARTY_NOTICES.md)                 | 资源生成与许可                                 |
| [文档索引](../docs/README.md)                                                       | 业务设计、接口与其他专项说明                   |

从页面、Network、后台动作到 SQLite 的完整学习路径见运行观测指南。跨页面数据读写统一经过[工作台共享数据](src/state/README.md)，页面 Hook 组合 URL、表单与交互；身份、主题、编辑保护各自独立。

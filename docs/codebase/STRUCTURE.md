# 代码结构与入口

适用范围：本文保留 2026-10-31 的调查快照，未随之后的知识处理、向量及员工装配增量逐项更新，不作为当前能力清单或当前测试通过证明。当前行为从[系统架构](../architecture/overview.md)、[知识契约](../reference/knowledge.md)与[工程文档索引](../README.md)进入。
调查日期：2026-10-31。本页定位真实工作区和入口；运行协作见 [ARCHITECTURE](ARCHITECTURE.md)。目录名本身不证明服务或分层，以下职责依据导入、调用和启动配置核对。

## 1. 顶层地图

```text
niuma-crew/
├── Makefile                 # 编排安装、启动、迁移、检查与实验命令
├── backend/                 # 独立 Python/uv 工程，提供 API 与后台执行
│   ├── app/                 # 正式应用源码，按业务和执行职责组织
│   ├── migrations/          # Alembic 正式迁移，含知识 FTS5 建表
│   ├── experiments/         # checkpoint 与知识 POC 的独立入口
│   ├── tests/               # 后端 API、事务、恢复、工具与配置测试
│   ├── datasets/            # 教学及实验材料，非自动初始化业务数据
│   ├── pyproject.toml       # Python 依赖及检查范围
│   └── uv.lock              # Python 解析依赖
├── frontend/                # 独立 pnpm/Vite 工程，输出静态应用
│   ├── src/                 # 页面、状态、UI、API 与设计系统
│   ├── scripts/             # 品牌、头像、主题和压缩资源生成
│   ├── public/              # 直接发布的静态资源
│   ├── package.json         # 前端依赖及包脚本
│   └── pnpm-lock.yaml       # 前端解析依赖
├── scripts/                 # 跨端开发监督器与文档检查器
├── deploy/                  # 当前只有 OpenSandbox 的镜像与宿主配置示例
└── docs/                    # 现行产品/契约、方案、记录及源码调查导航
```

事实来源：[Makefile](../../Makefile)、[后端清单](../../backend/pyproject.toml)、[前端清单](../../frontend/package.json)、[迁移](../../backend/migrations/versions/)、[部署](../../deploy/opensandbox/)。`.requirements/` 与 `.impeccable/` 是本地需求/评审材料；当前入口未调用它们。`.venv/`、node_modules、缓存、dist、tsbuildinfo 不作为正式架构源码证据。

## 2. 入口清单

| 入口                | 选择方式、实际工作                                                             | 证据                                                                                                                                             |
| ------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| 前端 main.tsx       | index.html 的 module 脚本；安装主题、挂载 React Router                         | [index.html](../../frontend/index.html)、[main.tsx](../../frontend/src/main.tsx):L8                                                              |
| router.tsx / Layout | lazy 页面；AuthBoundary 包住工作台，再建立共享数据与编辑作用域                 | [router.tsx](../../frontend/src/router.tsx) `router`；[Layout.tsx](../../frontend/src/Layout.tsx) `Layout`:L39                                   |
| app.main:app        | Uvicorn 导入时调用 create_app；服务在 lifespan 中实例化                        | [main.py](../../backend/app/main.py):L3；[bootstrap.py](../../backend/app/bootstrap.py) `create_app`:L48                                         |
| scripts/dev.py      | 根 make dev 调用，先监督后端就绪，再把实际端口注入 Vite                        | [dev.py](../../scripts/dev.py) `DevLauncher`:L59、`run`；[Makefile](../../Makefile):L32                                                          |
| app.auth.cli        | 管理员初始化、维护和会话撤销；不是成员业务 CLI                                 | [cli.py](../../backend/app/auth/cli.py)、[Makefile](../../Makefile) `admin-*`                                                                    |
| Alembic env         | 命令加载模型注册表与数据库配置，执行正式迁移                                   | [env.py](../../backend/migrations/env.py)、[models.py](../../backend/app/infrastructure/database/models.py)                                      |
| experiments         | checkpoint 演示服务、知识烟测和实验，均有独立 **main** 入口                    | [sqlite_checkpoint_chat.py](../../backend/experiments/sqlite_checkpoint_chat.py)、[knowledge_poc.py](../../backend/experiments/knowledge_poc.py) |
| 沙箱宿主            | systemd 启动 opensandbox-server；工作负载容器默认 sleep infinity，等待远端执行 | [service](../../deploy/opensandbox/niuma-opensandbox.service):L13、[Dockerfile](../../deploy/opensandbox/Dockerfile)                             |

没有找到独立正式 worker/队列服务入口。Runner、文件清理、沙箱清理都是 `bootstrap.lifespan` 创建的同进程任务；消费端说明见 [ARCHITECTURE](ARCHITECTURE.md)。

## 3. 模块边界

| 模块                                    | 实际持有/处理                                    | 与相邻模块的分工及证据                                                                                                                                                 |
| --------------------------------------- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| backend/app/api                         | HTTP DTO、依赖提取、安全、错误、SSE、静态交付    | 从 app.state 获取服务，业务服务拥有事务；[dependencies.py](../../backend/app/api/dependencies.py)、[router.py](../../backend/app/api/router.py)                        |
| auth                                    | 用户、会话、登录与权限                           | 输出 Actor，业务层继续检查资源归属；[service.py](../../backend/app/auth/service.py) `AuthService`:L44                                                                  |
| agents                                  | 员工、技能关系、工具许可和个人账号选择           | 引用资源表，不保存模型 Key；[service.py](../../backend/app/agents/service.py)、[tool_grants.py](../../backend/app/agents/tool_grants.py)                               |
| skills                                  | 标准包、编辑目录、不可变 blob、资源版本          | Agent 关系在 agents，调用工具仍需许可；[service.py](../../backend/app/skills/service.py):L49、[packages.py](../../backend/app/skills/packages.py)                      |
| tools                                   | MCP 定义、账号密文、发现/审核、网络和进程客户端  | 员工授权位于 agents；反向引用检查由 bootstrap 注入；[invocation.py](../../backend/app/tools/invocation.py)、[bootstrap.py](../../backend/app/bootstrap.py):L75         |
| model_connections / llm                 | 前者管理配置密文与修订；后者构造模型客户端       | [service.py](../../backend/app/model_connections/service.py)、[factory.py](../../backend/app/llm/factory.py):L13                                                       |
| organization_rules                      | 全员单份规则及修订                               | 对话准备时复制正文；[service.py](../../backend/app/organization_rules/service.py)、[preparation.py](../../backend/app/conversations/preparation.py):L71                |
| conversations                           | 对话消息、接受输入、上下文、组合授权、成果发布   | 调用 execution，执行反向协作使用注入回调；[service.py](../../backend/app/conversations/service.py)、[publication.py](../../backend/app/conversations/publication.py)   |
| execution                               | Run、RunAction、预算、调度、取消和恢复           | 不导入对话 ORM；[scheduler.py](../../backend/app/execution/scheduler.py)、[store.py](../../backend/app/execution/store.py)                                             |
| agent_runtime                           | SDK 循环、技能加载、工作区、模型/工具事件转换    | 通过 RuntimeControl 回报动作，返回候选回答；不直接发布 Message；[langchain.py](../../backend/app/agent_runtime/langchain.py):L109                                      |
| files / sandboxes                       | 不可变文件及回收；沙箱申请、远端归属与回收       | 对话和知识分别提供文件保留引用，沙箱不是 stdio MCP；[bootstrap.py](../../backend/app/bootstrap.py):L98、[sandboxes/service.py](../../backend/app/sandboxes/service.py) |
| knowledge                               | 个人库、固定原文、片段与 FTS 检索；另有 POC 算法 | 正式 service 不调用 answering/indexing 的向量问答；[service.py](../../backend/app/knowledge/service.py):L251、L371                                                     |
| capability_catalog                      | 跨 Skill/MCP 的统一目录查询                      | 不接管修改与执行；[queries.py](../../backend/app/capability_catalog/queries.py)                                                                                        |
| infrastructure/database                 | 引擎、事务、字段、错误、迁移模型注册             | 注册表集中导入 ORM 是迁移依赖，不能由此推断基础数据库工具调用所有业务；[models.py](../../backend/app/infrastructure/database/models.py):L3                             |
| frontend/src/pages                      | 各业务页面及局部 Hook/Controller                 | router 通过 Page 入口加载；[router.tsx](../../frontend/src/router.tsx)                                                                                                 |
| frontend/src/state                      | 身份、主题、编辑、共享 Resource 和领域 Store     | 不承担服务器权限或持久化事实；[workspaceData.ts](../../frontend/src/state/workspace/workspaceData.ts):L18                                                              |
| frontend/src/lib                        | HTTP、DTO、浏览器存储及普通工具                  | 无 React Provider；[http.ts](../../frontend/src/lib/api/http.ts):L48、[draft.ts](../../frontend/src/lib/draft.ts)                                                      |
| frontend/src/components / design-system | 基础和共享 UI、语义令牌、正式头像资源            | 不是独立部署包；[eslint.config.mjs](../../frontend/eslint.config.mjs):L124                                                                                             |

## 4. 命名、工作区及产物

Python 文件/函数通常 snake_case，类 PascalCase；TS 普通文件 camelCase、组件 PascalCase、目录短横线，具体强制范围见 [CONVENTIONS](CONVENTIONS.md)。前端 `@/` 在 Vite、tsconfig、Vitest 都指向 src；后端 `app.*` 由 backend 作为工作目录/安装包解析。

前端嵌套 [svg/package.json](../../frontend/src/components/avatars/svg/package.json)只有 private 与 sideEffects，不含构建脚本/依赖，不是另一个运行服务或声明的 pnpm 包。头像及 manifest 应从生成器和源资源理解；不能把大型生成 TSX 当业务层复杂度。[package.json](../../frontend/package.json):L7–17 和 [构建说明](../../frontend/scripts/README.md)给出实际调用。

## 5. 扫描覆盖与证据

- [x] Phase 1：运行扫描，先读取并总结产品意图。
- [x] Phase 2：按七份模板调查源码，继续检查两端工作区、脚本和部署入口。
- [x] Phase 3：填充七份文档，附关键符号、文件和行号。
- [x] Phase 4：复核模板问题、证据、链接和格式；无待解的意图问题，未知验证项标为 `[TODO]`。

1. 已运行技能 scan.py：根目录、backend、frontend 各一次，输出分别位于 `/tmp/niuma-crew-codebase-scan.txt`、`/tmp/niuma-crew-backend-scan.txt`、`/tmp/niuma-crew-frontend-scan.txt`，均是可丢弃临时材料。
2. 根扫描错误地报告未识别 monorepo、入口、环境模板与容器，且目录树被缓存淹没；人工补查上表中的清单、隐藏配置、脚本、迁移、实验与 deploy。根扫描“152644 行”混有非正式材料，不作为产品规模依据。
3. 已对 backend/app 的 Python AST 导入进行汇总，并继续读取关键调用、回调装配和 SQL；导入计数不等于运行调用次数。对前端同时核对 route lazy imports、别名和 Provider/Store/API 调用。
4. Git 当前 main 尚无提交，源文件整体未跟踪；无法得出 90 天高变更文件或提交演化结论，详见 [CONCERNS](CONCERNS.md)。

证据：[根 Makefile](../../Makefile)、[应用装配](../../backend/app/bootstrap.py)、[路由](../../frontend/src/router.tsx)、[沙箱配置](../../deploy/opensandbox/)、[模型注册](../../backend/app/infrastructure/database/models.py)。

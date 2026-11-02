# 技术栈与运行条件

调查日期：2026-10-31。本文按本地源码、清单和锁文件描述实际组成；版本范围来自清单，不表示当前部署版本。阅读主线见 [ARCHITECTURE](ARCHITECTURE.md)，本组是源码调查导航，业务契约仍以[文档索引](../README.md)中的权威正文为准。

## 1. 运行概要

| 范围     | 已确认事实                                                                     | 证据                                                                                                                                                                                       |
| -------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 后端     | Python >=3.12，开发版本文件指定 3.12；独立 uv 工程                             | [pyproject.toml](../../backend/pyproject.toml):L6；[.python-version](../../backend/.python-version)                                                                                        |
| 前端     | TypeScript、React，ES module，Vite 编译；pnpm 11.11.0                          | [package.json](../../frontend/package.json):L5–24                                                                                                                                          |
| Node     | 根 README 要求 22.12+；前端清单未设置 engines，不能把类型包版本当运行版本      | [README](../../README.md)“本地运行”；[package.json](../../frontend/package.json)                                                                                                           |
| 仓库组织 | backend 与 frontend 独立安装、锁定和构建，根 Makefile 编排；不是根 pnpm 工作区 | [Makefile](../../Makefile):L13–53；[pnpm-workspace.yaml](../../frontend/pnpm-workspace.yaml)只有安装策略，没有 packages 列表                                                               |
| 平台约束 | 文件型 SQLite；Runner 使用 fcntl 文件锁；开发器使用 POSIX 进程组               | [config.py](../../backend/app/config.py) `_load_database_url`:L66；[scheduler.py](../../backend/app/execution/scheduler.py) `Runner.start`:L30；[dev.py](../../scripts/dev.py) `spawn`:L96 |

## 2. 正式依赖

下表列出对架构有直接影响的运行依赖；完整集合与精确解析版本分别由两端清单及锁文件维护。

| 依赖                                        | 清单约束                           | 实际用途及调用证据                                                                                                                                                                                                                             |
| ------------------------------------------- | ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FastAPI / Uvicorn                           | >=0.115,<1 / >=0.30,<1             | `create_app` 装配 ASGI；Makefile 的 start/dev 启动服务器                                                                                                                                                                                       |
| SQLAlchemy / Alembic                        | >=2,<3 / >=1.16,<2                 | 同步 Session 和独立迁移；[session.py](../../backend/app/infrastructure/database/session.py) `Database`:L25；[env.py](../../backend/migrations/env.py)                                                                                          |
| LangChain / DeepAgents                      | 1.4.7 / 0.7.30                     | 正式主循环调用 `langchain.agents.create_agent`，DeepAgents 提供文件系统/技能中间件，并非启动第二个服务；[langchain.py](../../backend/app/agent_runtime/langchain.py):L12、L158；[middleware.py](../../backend/app/agent_runtime/middleware.py) |
| langchain-core / langchain-openai           | >=1.6.10 / >=1.7.2                 | SDK 消息、模型接口和 ChatOpenAI；[factory.py](../../backend/app/llm/factory.py) `create_chat_model`:L13                                                                                                                                        |
| langgraph-checkpoint-sqlite                 | 3.1.2                              | 按 Run 保存 SDK 状态；[checkpoints.py](../../backend/app/agent_runtime/checkpoints.py) `CheckpointStore`:L45                                                                                                                                   |
| langchain[mcp] / httpx                      | 1.4.7 / >=0.28,<1                  | MCPAdapter、HTTP 客户端及网络边界；[mcp.py](../../backend/app/tools/adapters/mcp.py) `MCPClient.session`:L60                                                                                                                                   |
| opensandbox / langchain-sandbox-opensandbox | 1.1.1 / 0.1.2                      | 远端沙箱与运行时文件适配；[sandboxes](../../backend/app/sandboxes/)、[sandbox_backend.py](../../backend/app/agent_runtime/sandbox_backend.py)                                                                                                  |
| cryptography / pwdlib[argon2]               | >=45,<48 / >=0.3,<1                | Fernet 凭证密文与密码哈希；[credentials.py](../../backend/app/infrastructure/credentials.py):L14；[auth/service.py](../../backend/app/auth/service.py) `hash_password`:L34                                                                     |
| jieba / langchain-text-splitters            | >=0.42,<1 / >=1,<2                 | 正式知识关键词分词及切片；[lexical.py](../../backend/app/knowledge/lexical.py)、[chunking.py](../../backend/app/knowledge/chunking.py)                                                                                                         |
| jsonschema / pyyaml / python-dotenv         | >=4.26,<5 / >=6.0.3,<7 / >=1.2.4   | 参数规范、Skill 元信息、部署配置；[parameters.py](../../backend/app/skills/parameters.py)、[packages.py](../../backend/app/skills/packages.py)、[config.py](../../backend/app/config.py):L49                                                   |
| React / React DOM / React Router            | ^19.3.0 / ^19.3.0 / ^8.5.0         | 客户端页面、Provider 和 lazy 路由；[main.tsx](../../frontend/src/main.tsx)、[router.tsx](../../frontend/src/router.tsx)                                                                                                                        |
| Base UI / @shadcn/react                     | ^1.9.0 / ^0.3.1                    | 本地 UI 适配及消息滚动；[components/ui](../../frontend/src/components/ui/)                                                                                                                                                                     |
| Streamdown、CJK、Code                       | ^2.7.0 / ^1.0.4 / ^2.0.0           | 回复富文本；[Markdown.tsx](../../frontend/src/components/common/Markdown.tsx)                                                                                                                                                                  |
| lucide-react、CVA、clsx、tailwind-merge     | ^1.56.0 / ^0.7.1 / ^2.1.1 / ^3.7.0 | 图标、有限变体与样式合并；[package.json](../../frontend/package.json)、[utils.ts](../../frontend/src/lib/utils.ts)                                                                                                                             |

SQLite FTS5 属于数据库能力，不是额外搜索服务：[0013 迁移](../../backend/migrations/versions/0013_knowledge_libraries.py) `upgrade`:L70。Pydantic 被正式源码广泛导入，但没有作为直接依赖单列，随 FastAPI/SDK 依赖解析；事实入口是 [uv.lock](../../backend/uv.lock)。

本次读取 uv.lock 核对的解析版本包括 FastAPI 0.143.1、Uvicorn 0.54.0、SQLAlchemy 2.1.4、Alembic 1.20.0、Pydantic 2.14.1、langchain-core 1.6.13、jieba 0.42.1。它们是该锁文件的版本，不是所有可接受安装版本，也不代表线上已运行这些版本。

## 3. 开发工具

| 工具                                             | 范围及证据                                                                                                                                                                                  |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Ruff、mypy、pytest                               | backend 的 dev 依赖组；Ruff 选择 E4/E7/E9/F/I；mypy 只覆盖显式 files 范围，[pyproject.toml](../../backend/pyproject.toml):L30–68                                                            |
| Vite、TypeScript、Tailwind Vite 插件             | dev/build 编译工具，不是生产 Node 服务；[vite.config.ts](../../frontend/vite.config.ts)、[package.json](../../frontend/package.json)                                                        |
| ESLint、Prettier、Vitest、Testing Library、jsdom | 规则与测试见 [CONVENTIONS](CONVENTIONS.md)、[TESTING](TESTING.md)                                                                                                                           |
| knowledge-poc 可选依赖组                         | Chroma、PDF、DOCX 等服务实验；正式知识 HTTP 上传只接 .md/.txt；[pyproject.toml](../../backend/pyproject.toml):L37；[service.py](../../backend/app/knowledge/service.py) `text_document`:L54 |

## 4. 公共命令

```bash
make setup           # uv / pnpm 按锁安装；仅缺失时复制 .env.example
make db-upgrade      # 独立执行迁移，启动不自动迁移
make admin-create    # 后端管理 CLI，交互输入密码
make dev             # 开发监督进程、Uvicorn reload、Vite
make build           # 资源生成、Vite build、静态压缩
make start           # 单后端进程同源交付 dist 与 API
make check-docs
make lint
make test
```

定义：[Makefile](../../Makefile)。`make preview` 只预览静态资源；`make verify-knowledge`、`make verify-checkpoint` 是独立验证入口，不是业务 worker。

## 5. 环境与部署

配置来源为 `backend/.env` 与进程环境，环境优先；不读取本地秘密文件内容作为调查材料。`load_config` 解析路径但不建立数据库连接：[config.py](../../backend/app/config.py):L49、L85。模板将 APP_DATA_DIR 设为用户目录；无配置时源码回退到 backend/.data，两者需区分。

基础配置有 APP_DATA_DIR、DATABASE_URL、RUNNER_LOCK_FILE、AUTH_ALLOWED_ORIGINS；默认值可用于本地启动，模型凭据不是启动必填项。真实生成依赖数据库中的模型连接；GitHub 登录需三项 OAuth 配置；沙箱另需 endpoint、API key、镜像和验证 profile。完整参数只维护在 [.env.example](../../backend/.env.example)和[操作指南](../guides/backend-operations.md)。

人工发现 [deploy/opensandbox/Dockerfile](../../deploy/opensandbox/Dockerfile)只构建沙箱工作负载；基镜像来自必传的 PYTHON_IMAGE，不是平台应用镜像。[systemd 文件](../../deploy/opensandbox/niuma-opensandbox.service)启动外部沙箱服务器。未在纳入调查的项目配置中发现平台应用 Dockerfile、CI pipeline 或集群编排；[TODO] 实际部署、网络和上游可用性未验证。

## 6. 证据

- [后端清单](../../backend/pyproject.toml)、[uv 锁](../../backend/uv.lock)、[前端清单](../../frontend/package.json)、[pnpm 锁](../../frontend/pnpm-lock.yaml)。
- [根命令](../../Makefile)、[应用装配](../../backend/app/bootstrap.py)、[配置入口](../../backend/app/config.py)。
- [沙箱部署](../../deploy/opensandbox/)、[构建脚本](../../frontend/scripts/README.md)。

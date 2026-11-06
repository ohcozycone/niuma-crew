# NiumaCrew 后端

基于 FastAPI、SQLAlchemy 和 Alembic 的模块化单体，应用包为 app。业务模块维护同一套员工、技能、账号和权限规则；HTTP 处理用户接入，execution 组织可靠执行，其 runtime 子包集中后台运行与 SDK 模型循环。

## 从业务理解后端

先读[平台说明](../docs/product/README.md)，再读[使用流程](../docs/product/workflows.md)，最后进入[后端业务与工程架构](../docs/architecture/backend.md)。这里的「模块化单体」指职责按目录分开，运行仍在同一进程和同一业务库中；目录不是一组已独立部署的服务。

配置类功能由员工、技能、大脑、工具和规则模块各自维护。处理一条消息时，对话模块选择输入并捕获固定依据，执行宿主排队和看护，Agent 运行模块驱动模型与工具，最后由执行侧保存成果，再由对话模块接纳正文与文件。下面的 README 会先解释本模块的业务作用和正常流程，再说明设计、文件和依赖。

配置与首次启动见[项目说明](../README.md)、[本地开发](../docs/guides/local-development.md)和[后端操作](../docs/guides/backend-operations.md)。完成配置、数据库迁移和账号初始化后，在仓库根执行 `make dev-backend`；Web 服务器入口为 `app.main:app`，应用启动不自动迁移数据库。

## 模块架构与阅读入口

[main.py](app/main.py) 导出应用，[bootstrap.py](app/bootstrap.py) 创建服务、连接业务与运行流程，并统一启动和关闭资源。工程要求见[后端手册](../docs/engineering/backend.md)，模块说明维护职责与协作，字段和外部行为由[现行契约](../docs/README.md#现行契约)维护。

| 模块                                                    | 负责什么                                             |
| ------------------------------------------------------- | ---------------------------------------------------- |
| [HTTP 接口](app/api/README.md)                          | HTTP 参数、会话、传输安全、响应和只读 SSE 订阅       |
| [身份与访问控制](app/auth/README.md)                    | 用户、会话、角色操作权限和资源访问范围               |
| [员工配置与装配](app/employees/README.md)               | 岗位指令、技能与模型选择、工具许可和本人账号绑定     |
| [共享工作方法](app/skills/README.md)                    | Skill 正文、标准包、参数规范、来源同步和固定版本定义 |
| [工具服务与账号](app/mcp/README.md)                     | 服务登记、连接凭据、工具清单确认和获准调用           |
| [模型连接](app/model_connections/README.md)             | 模型配置、密钥保管、修订、引用保护和运行解析         |
| [全员工作规范](app/employees/README.md)                 | 全员继承的正文及带修订的并发保存                     |
| [方法与工具服务检索](app/capability_catalog/README.md)  | 按查看范围搜索两类条目，整体计数、排序和分页         |
| [员工考核](app/evaluations/README.md)                   | 固定BFCL题库、独立考试运行、评分与报告               |
| [对话与消息](app/conversations/README.md)               | 输入、历史、发送、重试、停止以及正文和文件的原子交付 |
| [可靠执行](app/execution/README.md)                     | 准入、排队、动作、预算、取消、期限和恢复             |
| [Agent 运行](app/execution/runtime/README.md)           | 模型与工具循环、技能加载、SDK 输出解释与执行存档     |
| [持久文件](app/files/README.md)                         | 可靠字节保存、归属、完整性、限额和清理               |
| [临时环境](app/environments/README.md)                  | 沙箱申请、部署配额、环境身份和回收责任               |
| [模型客户端](app/llm/README.md)                         | 用明确配置创建客户端，识别供应商失败和 Token 用量    |
| [数据库基础设施](app/infrastructure/database/README.md) | 连接、短事务、字段、数据库技术错误与模型注册         |
| [公共基础设施](app/infrastructure/README.md)            | 数据库与凭据机制的共同边界，业务含义仍由所属模块决定 |
| [共用凭据加密](app/infrastructure/credentials.py)       | 加解密和主密钥文件机制；业务模块分别解释失败         |

追踪一次工作可从[对话操作](app/conversations/service.py)进入[员工配置捕获](app/execution/snapshot.py)、[单次执行](app/execution/runtime/task.py)、[执行协调](app/execution/runtime/worker.py)和[模型循环](app/execution/runtime/agent.py)，最后查看[成果保存](app/execution/service.py)和[应用接纳](app/conversations/acceptance.py)。按文件学习见代码阅读指南。

[知识模块](app/knowledge/README.md)当前代码已装配本人库、原件/片段、手动后台处理、BM25/向量/混合检索，以及员工个人多库装配和带引用回答；独立 POC 保留另一套检索实验入口，`make verify-knowledge` 是实验验证入口。

## 验证

公共命令在仓库根执行，依赖由 uv.lock 锁定；新增依赖同步更新清单与锁文件。

```bash
make lint-backend  # 静态、格式和 Python 类型检查
make test-backend  # 隔离数据库与假上游的业务测试
make test-dev      # 启动、端口、代理和进程清理
make check-docs    # 文档路径、章节与索引检查
make check         # 完整离线检查与构建
```

离线替身用于验证业务边界，不证明真实模型、MCP 或沙箱部署可用；外部接入与备份恢复按[后端操作指南](../docs/guides/backend-operations.md)验证。

## SQLite checkpoint 验证

`make verify-checkpoint` 使用临时 SQLite、假模型和真实 HTTP 子进程，验证多轮对话、消息历史、稳定线程及按 Run 定位的 SDK 存档、关闭与重启恢复、权限和预算。正式恢复规则见[运行契约](../docs/reference/runtime.md#checkpoint历史与恢复)。

`make dev-checkpoint` 启动独立实验后端，默认地址 `127.0.0.1:8001`，存档为 `/tmp/niuma-crew-checkpoint-demo.sqlite`；CHECKPOINT_DB 和 CHECKPOINT_PORT 可覆盖。手动请求与观测步骤见实验说明。该入口使用假模型，与正式业务存储分开。

```
backend/app/
├── api/                  # HTTP 接入
├── employees/            # 员工配置与装配
├── skills/               # 技能管理
├── model_connections/    # 模型连接管理
├── knowledge/            # 知识能力，内部再分入库、检索、证据等职责
├── mcp/                  # MCP 接入能力
├── conversations/        # 对话与消息
├── execution/            # Agent 执行子系统
│   ├── models.py         # 定义 Run 与动作的持久结构
│   ├── store.py          # 原子保存状态、预算、动作与恢复事实
│   ├── snapshot.py       # 捕获本轮冻结配置与输入依据
│   ├── prompts.py        # 固定模型指令及纯文本渲染
│   ├── runtime/          # 后台 Worker、单次 Task、运行期工具及 SDK 循环
│   └── service.py        # 应用事务内受理、取消与可靠成果保存
├── llm/                  # 模型客户端适配
└── infrastructure/       # 数据库、加密、观测等公共技术机制
```

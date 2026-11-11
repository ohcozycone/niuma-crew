# 后端设计

后端是按功能所有权组织的模块化单体，同一进程内使用 SQLite 短事务和官方 SDK 执行存档。对话与考核拥有业务受理、发布与评分；执行宿主管理 Run、动作、预算和生命周期；Agent 适配模型工具循环；资源模块维护可复用的组织配置和外部资源。

## 目录与职责

以下展开主要目录和体现职责分工的关键文件，其余实现、测试和说明随所属模块维护。完整文件归属、迁移映射与具名例外见[架构契约](../../backend/tests/architecture_contract.json)。

```text
backend/
├── app/                               # 后端应用代码
│   ├── main.py                        # 服务导出入口
│   ├── config.py                      # 汇总并校验应用配置
│   ├── bootstrap/                     # 组合具体服务，管理应用启停
│   │   ├── app.py                     # 创建应用，接入路由与中间件
│   │   ├── services.py                # 创建服务并注入模块间依赖
│   │   ├── lifecycle.py               # 协调后台任务启动与资源关闭
│   │   └── model_registry.py          # 统一注册业务模型与历史映射
│   ├── api/                           # HTTP 协议、入口权限与响应转换
│   │   ├── routes/                    # 按业务组织接口，调用所属模块公开操作
│   │   ├── dependencies.py            # 取得启动时已装配的服务
│   │   ├── router.py                  # 汇总业务路由
│   │   └── streaming.py               # 订阅并推送已提交的回复状态
│   ├── cli/                           # 账号维护、环境检查等命令行入口
│   ├── applications/                  # 业务受理、推进与成果接纳
│   │   ├── configuration_summary.py   # 汇总工作台所需的只读配置摘要
│   │   ├── conversations/             # 对话、消息与正式回复
│   │   │   ├── commands.py            # 协调发送、停止与重试事务
│   │   │   ├── writes.py              # 写入消息、执行绑定与接纳结果
│   │   │   ├── acceptance.py          # 复核成果并组织正式回复发布
│   │   │   └── queries.py             # 核对访问范围并读取对话状态
│   │   └── evaluations/               # 考核批次、题目、答卷与评分
│   │       ├── commands.py            # 创建与取消考核
│   │       ├── progression.py         # 推进题目并提交执行
│   │       ├── acceptance.py          # 接纳答卷、评分与版本复核
│   │       ├── worker.py              # 扫描待推进的考核并触发处理
│   │       └── data/                  # 固定题库、答案与来源说明
│   ├── runtime/                       # 共用执行能力与 SDK 适配
│   │   ├── assembly.py                # 绑定执行宿主、Agent 与工具实现
│   │   ├── contracts/                 # 普通运行类型与受限能力协议
│   │   ├── execution/                 # 执行状态、调度、授权、预算与证据
│   │   │   ├── service.py             # 受理执行、组合授权并提交成果终态
│   │   │   ├── scheduler.py           # 管理排队、在途任务与恢复扫描
│   │   │   ├── runner.py              # 协调单次执行、看护与资源收尾
│   │   │   ├── preparation.py         # 准备模型、工具与执行环境
│   │   │   ├── context.py             # 向 Agent 提供受控动作与进度能力
│   │   │   └── store.py               # 保存执行、动作及成果记录
│   │   ├── agent/                     # 适配模型工具循环、技能与检查点
│   │   └── tools/                     # 文件、知识、结果补读与工具发现适配
│   ├── resources/                     # 可复用组织配置与资源的状态所有者
│   │   ├── employees/                 # 员工岗位、资源关系与装配事实
│   │   ├── organization_rules/        # 全员规范的配置与修订
│   │   ├── skills/                    # 技能定义、参数、包与内容发布
│   │   ├── model_connections/         # 模型连接配置、凭据与使用关系
│   │   ├── capability_catalog/        # 技能与 MCP 工具的只读联合目录
│   │   ├── knowledge/                 # 资料入库、处理、索引、检索与来源
│   │   ├── mcp/                       # 工具服务、工作连接、目录与调用
│   │   │   └── adapters/              # HTTP、标准输入输出及 OAuth 存储适配
│   │   ├── files/                     # 文件字节、业务引用、保留与清理
│   │   └── environments/              # 隔离代码环境的申请、使用与回收
│   ├── auth/                          # 身份、会话、操作权限与工作授权
│   ├── infrastructure/                # 数据库、模型 API、凭据加密、线程与日志
│   │   ├── database/                  # 会话、事务、字段与数据库错误识别
│   │   ├── llm/                       # 调用聊天与向量模型，转换协议和用量
│   │   ├── credentials.py             # 加密保存和读取连接凭据
│   │   ├── concurrency.py             # 在线程中执行同步任务，取消时等待其退出
│   │   └── observability.py           # 关联请求与执行日志，记录故障位置
│   └── common/                        # 普通值、错误、用量结构与校验基类
├── migrations/                        # 正式数据库升级历史
├── tests/                             # 业务、边界、故障与恢复的隔离测试
│   ├── architecture_contract.json     # 文件归属、允许依赖与具名例外
│   └── test_architecture_contract.py  # 检查目录、依赖方向及普通契约隔离
├── datasets/                          # 样本、来源与许可说明
├── experiments/                       # 独立实验及验证入口
├── pyproject.toml                     # 依赖声明与工程检查配置
└── uv.lock                            # 锁定后端依赖版本
```

例如模型连接的配置、修订和使用关系归 `resources/model_connections/`；把配置转换为聊天或向量客户端归 `infrastructure/llm/`；模型何时调用、预算是否允许归 `runtime/execution/`；模型调用怎样进入 SDK 循环归 `runtime/agent/`。

## 依赖与公开能力

正常模块依赖必须无环；`bootstrap` 与 `runtime/assembly.py` 只在启动时绑定实现，运行中的业务代码通过预先注入的能力协作，不返回装配入口寻找服务。`runtime/contracts/` 定义普通类型和能力协议，不加载 ORM、模型 SDK 或具体服务。

| 调用方                       | 可以使用                                            | 边界                                        |
| ---------------------------- | --------------------------------------------------- | ------------------------------------------- |
| API、CLI                     | 应用与资源的公开操作、auth、公开状态值              | 不直接操作业务 ORM、Store 或模型 SDK        |
| applications                 | 执行公共事务操作、资源公开能力、auth、基础机制      | 不调用 Agent 引擎，不持有外部模块的可变 ORM |
| runtime/execution            | 普通运行契约、资源公开能力、auth、基础机制          | 不依赖业务应用、Agent 或工具具体实现        |
| runtime/agent                | 普通契约、工具适配、模型客户端、SDK 存档            | 不访问业务数据库、HTTP、正式回复发布或评分  |
| runtime/tools                | 受限宿主能力、普通资源契约和 SDK                    | 不调度 Run，不独立维护授权或资源所有权      |
| resources/employees          | 技能、模型连接、MCP、知识、环境和组织规则的配置事实 | 来源资源不反过来调用员工流程                |
| resources/knowledge          | 文件与模型连接公开能力                              | 不认识 Run、员工实现或模型工具反馈          |
| capability_catalog           | 技能与 MCP 只读概要                                 | 不管理资源或推进执行                        |
| auth、infrastructure、common | 必要的基础机制和普通值                              | 不反向获取业务服务；common 不保存服务实例   |

跨表只读投影与环境历史多态映射按文件声明，不能豁免整个目录。投影禁止写入、提交或回滚。数据库元数据聚合只在 `bootstrap/model_registry.py`，数据库机制不导入业务模型。应用启动与 Alembic 均经该入口完成注册，包括历史 `native` 多态记录；不能依赖迁移进程替运行进程完成映射初始化。绝对、相对、包聚合、类型分支、局部和字面量动态导入均受[架构测试](../../backend/tests/test_architecture_contract.py)检查；普通运行契约另做独立进程导入验证。

## 状态所有权与事务

| 状态或流程                       | 协调者与写入所有者                                     |
| -------------------------------- | ------------------------------------------------------ |
| 对话受理、消息与绑定             | conversations/commands、writes                         |
| 正式回复、附件与接纳重试         | conversations/acceptance                               |
| 考核创建、取消                   | evaluations/commands                                   |
| 逐题推进、答卷接纳与评分         | evaluations/progression、acceptance；worker 仅触发推进 |
| 排队、在途任务、进程锁与恢复扫描 | RunWorker                                              |
| 单次准备、看护、使用者退出与收尾 | RunTask，准备算法在 preparation                        |
| Run、动作、预算、执行证据        | 执行公共事务操作及 Store                               |
| 模型与工具循环、SDK checkpoint   | 官方 SDK 与 Agent 适配                                 |
| 资料、索引、连接、文件、沙箱     | 各自资源模块                                           |

API 只调用应用或资源的公开查询；对话与考核查询负责核对业务归属后读取执行诊断，Run 知识来源读取也经应用入口进入执行公共能力。HTTP 路由不直接拼接业务与执行流程。

跨模块读取返回独立状态值或具名只读投影。需要原子协作时传递同一 Session，参与者不隐式提交；模型、远端工具、文件解析和向量生成置于写事务之外，返回后在短事务中复核资格与版本。

员工关系查询由员工提供；对话与考核提供各自历史保护；知识与执行提供各自模型、文件引用。技能兼容性检查读取装配参数，计数查询只读聚合列。查询与文件补偿仍使用原操作事务和锁，不能因目录拆分产生先保存一半的状态。

## 一次对话的执行顺序

1. API 完成输入与入口权限检查，commands 在同一事务保存输入、空回复、冻结配置、queued Run 和绑定。
2. Worker 领取已提交工作，Task 通过 preparation 准备模型配置、工具范围、沙箱和受限 Context；每项资源创建后立即登记关闭责任。
3. Agent 通过普通协议申请动作。宿主在同一事务核验授权、可见工具、预算并登记开始，随后在事务外调用上游。
4. 保存动作结果与执行证据后才向模型反馈。取消、撤权、存储失败和迟到结果按执行规则收束。
5. 等待模型、工具及同步工作退出，再关闭它们使用的资源。成果与 Run 终态先提交，完成通知随后仅唤醒接纳扫描。
6. 对话在独立接纳事务复核资格并写正式回复；考核接纳答卷并评分。接纳失败只重试发布阶段，不再次调用模型。

知识检索通过明确的只读 guard 在每次读取和发布前复核 Run 范围；资源内部加载自己的库记录，不从回调接收其他模块的 ORM。`execution/knowledge` 拥有运行授权与跨库协调，`knowledge_evidence` 拥有 Run 证据和历史关联，资源 `sources` 仅核对文档与片段当前有效性，工具适配负责反馈格式。

模型用量的数据定义在 `common/usage`，供应商字段解释在 `infrastructure/llm/usage`，纯累计在 `runtime/usage`，诊断投影在 `runtime/execution/metrics`。普通调用与摘要共用一份累计状态，不能把已累计用量再次相加。

模型适配、检索实现和业务发布的隔离由[替换测试](../../backend/tests/test_architecture_substitution.py)验证。[旧版本中断恢复测试](../../backend/tests/test_architecture_recovery.py)使用源码快照生成的合成持久样本，核对已保存工具、未知尝试、预算与未知用量。外部协议、表结构和旧 SDK 存档恢复仍须与迁移前样本比较；架构检查或单元测试通过不能替代这些验收。

本次迁移的六项门槛、跨版本样本和快照恢复结果见[迁移验收](../records/后端模块边界迁移验收.md)。

当前宿主采用单进程锁，不支持多 worker 或跨主机领取。完整机制见[执行说明](../../backend/app/runtime/execution/README.md)，工程要求见[后端手册](../engineering/backend.md)，部署与恢复见[运维指南](../guides/backend-operations.md)。

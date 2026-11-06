# 后端架构

当前后端是 Python 模块化单体：HTTP、业务模块、后台执行与 Agent 循环在一个应用进程协作，使用 SQLite 和同步 SQLAlchemy。前端交互、接口接入、业务应用、运行管理、Agent 循环、基础设施与外部资源是六种职责视角，不是六个部署服务，也不要求建六个同名目录。

## 模块怎样对应职责

| 职责           | 目录                                                                                                                    | 处理什么                                                                       |
| -------------- | ----------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| 接口接入       | api                                                                                                                     | 解析 HTTP、身份与输入，调用业务入口，返回响应和已保存的进展                    |
| 业务应用       | employees、skills、model_connections、knowledge、mcp、conversations、evaluations、auth、employees/organization_rules.py | 分别维护员工装配、技能、“大脑”连接、资料检索、外部服务接入、正式交流和身份规则 |
| 运行管理       | execution/service.py、runtime/worker.py、runtime/task.py、store.py                                                      | 接受工作，排队、领取、取消、预算、动作、恢复和可靠成果保存                     |
| 执行资源组合   | execution/snapshot.py、prompts.py、runtime/task.py                                                                      | 捕获冻结依据、生成固定指令并绑定单次资源；当前授权由 RunService 组合           |
| Agent 循环     | execution/runtime                                                                                                       | 组装 SDK 程序，执行模型/工具往返、摘要、流解析、工作区映射及存档               |
| 基础设施与资源 | infrastructure、files、environments、llm 及外部服务                                                                     | 数据库、加密、文件、沙箱及明确参数下的模型客户端                               |

业务模块按能力平铺，执行相关机制聚合在 execution 内部。这是所有权的组织方式，不需要把执行记录或 runtime 拆成顶层业务模块。MCP 对外统一描述“接入能力与适配”，内部协议细节在[模块说明](../../backend/app/mcp/README.md)展开。

## 工程入口

```text
backend/
├── app/
│   ├── main.py                 # 导出 ASGI 应用
│   ├── bootstrap.py            # 装配业务服务、资源回调、执行器和生命周期
│   ├── config.py               # 汇总和校验配置
│   ├── api/                    # HTTP 路由、安全、错误和只读 SSE
│   ├── employees/              # 员工资料、技能/工具关系及自身装配事实
│   ├── skills/                 # 可复用技能内容和资源包
│   ├── model_connections/      # “大脑”连接配置、凭据和修订
│   ├── knowledge/              # 个人资料入库、处理、检索、引用证据和装配
│   ├── mcp/                    # 服务、账号、清单、OAuth、受控调用与协议适配
│   ├── evaluations/            # 独立员工考核、题目推进与评分报告
│   ├── conversations/          # 业务历史、消息、对话占用和独立成果接纳
│   ├── capability_catalog/     # 统一能力目录的只读查询
│   ├── execution/              # 公共工作操作和协作契约
│   │   ├── models.py           # 定义 Run、动作及持久约束
│   │   ├── store.py            # 原子保存状态、预算、动作与恢复事实
│   │   ├── snapshot.py         # 本轮冻结配置与输入捕获
│   │   ├── prompts.py          # 共享固定指令与纯文本渲染
│   │   └── runtime/            # 后台控制、单次资源与 Agent SDK 实现
│   ├── files/                  # 持久文件字节、配额和清理
│   ├── environments/           # 工作区配置、沙箱分配和回收
│   ├── llm/                    # 模型客户端与用量字段适配，不查询业务库
│   ├── auth/                   # 登录、会话、角色和工作身份授权
│   └── infrastructure/         # 数据库、字段、事务、加密及观测
├── migrations/                 # 显式数据库升级，应用启动不隐式迁移
├── tests/                      # 隔离数据库、假上游及真实进程生命周期验证
```

execution 的[完整文件职责](../../backend/app/execution/README.md)是执行目录唯一详细说明。其他模块分别沿源码 README 阅读，避免在总览只展开某个模块的技术细节。

## 从提问到正式回复

1. API 将输入交给 ConversationService；它使用 RunService 的同事务操作冻结本轮配置、输入和预算，保存 Run、用户消息、回复占位及关联。
2. 同一对话使用稳定 Thread，每次输入新建 Run。正常追问从最近成功接纳的 Run 的明确 checkpoint 接续，只新增当前问题，不再每轮拼装完整页面历史。
3. RunWorker 扫描 queued 并调度 RunTask.execute；Task 加载 Run、复核授权并领取，完成请求、恢复与资源准备，再用 AgentRequest 和 AgentContext 调用 SDK，同时看护取消、总时限与权限变化。
4. 每次模型或工具操作先原子登记与申请预算，再调用上游；SDK 进展转成普通更新并保存。摘要复用官方中间件，其模型请求也记账。
5. RunService 保存完整成果及终态；ConversationAcceptance 再把成果接成正式回复。后者失败可独立重试，不改变成功 Run 或重跑模型。

## 存储与恢复

业务数据库保存 Conversation、Message、Run、动作和正式成果。旁边的 checkpoint SQLite 文件保存 SDK 消息及图状态；平台配置官方存储器，框架在步骤边界落盘，平台保存定位引用。历史展示不打开 SDK 库。

重启恢复同一 Run 时使用其线程和归属明确的存档继续，保留原预算与总时限。新一轮使用成功接纳的基点，失败或取消分支不污染后续。数字 ID 切换采用空库重建；无基点时从当前输入开始，选定基点不可续接时明确失败，不导入 Message。

当前是单宿主、本机文件存储；无分布式队列或多主机租约。全平台 Run 并发数字限制已移除，账号、队列和线程占用限制仍存在。详细恢复资格和失败语义见[运行契约](../reference/runtime.md)。

## 依赖和维护

API 不反向导入 bootstrap；业务服务不接收 HTTP Request。models/store 不解释 SDK 消息，snapshot 不创建 SDK 工具，runtime 的 SDK 文件不导入业务 ORM 或具体 RunTask；Worker/Task 按职责使用执行模型和平台服务。跨边界使用 contracts 的普通对象、受限控制和资源回调；bootstrap 调用 execution/assembly.py 构建子系统，只连接跨模块共享服务、完成通知与生命周期。

工程标准见[后端手册](../engineering/backend.md)，实施与验证见执行架构重构验收。

# API 请求服务与共享业务流程

API 归属已由 [2026-10-30 整理方案](../api-responsibilities.md) 接替；当前结构以 [API 模块](../../../backend/app/api/README.md)为准，本文保留上一轮设计依据。

本文保留[总方案](README.md)的服务归属判断，2026-10-27 已实施当前范围；实际代码、事务和检查见[当前后端架构](../../architecture/backend.md)与[实施记录](../../records/platform-refactor-implementation.md)。下文“当前”源码研究描述实施前的问题，生效规则以现行契约为准。

## 1. 本轮结论与撤回项

**按业务归属保存规则，按实际调用拆分请求编排与共享流程；只在对话 API 增加有内容的请求服务，不给每个 router 配一个 Service。**

具体选择：

1. 当前 ConversationCommands 迁到 `api/routes/conversations/service.py`，定名 ConversationRequestService，组织当前 Web API 的发送、停止、重试和专业反馈事务。
2. 运行准备、组合授权、最终发布分别归 `conversations/preparation.py`、`authorization.py`、`publication.py`。它们是对话回复处理的共享业务流程，由 API 与后台在不同阶段使用。
3. auth、agents、skills、model_connections、organization_rules、ci_diagnosis 的 service 留在所属模块。它们维护已有业务规则和操作，不在 API 目录复制一套同名方法。
4. 对话路由拆出 `router.py` 与 `streaming.py`。前者负责 HTTP 参数/响应，后者负责实际 SSE 连接管理；其他简单路由继续用单文件。
5. 撤销全局 `use_cases/` 目标目录，不新增集中式 `application/`。跨模块调用本身不决定文件归属，也不形成新的业务层。

这不是“所有 service 放业务模块”或“所有 service 放 API”之间选一边。API 请求编排与资源规则确有不同维护原因，但都可以完成业务操作，不能继续用 Service/UseCase 两种名称暗示两套层级。

## 2. 为什么只给对话 API 增加请求服务

当前[对话命令](../../../backend/app/conversations/service.py)只被[对话 HTTP 入口](../../../backend/app/api/routes/conversations.py)使用；bootstrap 负责构造，测试负责验证，并不是额外的产品入口。它处理请求键、首条提交、重试目标和停止目标，同时组织对话内容与运行登记。这些内容足以独立于 HTTP 代码存在。

其中用于执行的配置固定、权限复核和结果提交，已有后台调用需求；先迁出这些共享部分，再将剩余请求编排放到接口旁边。这样没有把后台职责也搬进 API。

相较之下，员工、方法和规则接口已有对应业务服务。再新增 AgentApiService.update → AgentService.update，只增加跳转。少量参数转换、字段级请求权限和响应白名单可留路由，业务有效性仍由所属模块保证。当前配置服务的入口授权责任不在本轮偷偷改变；未来新增调用入口时必须显式承担同样的身份与操作授权。

“当前只有 HTTP 调用”也不是搬进 API 的充分条件。员工配置的操作、修订和装配规则具有完整业务归属，即使修改入口只有一个，也可以留在 agents/service。

## 3. 服务与流程的具体归属

| 目标位置                            | 实际维护内容                                                                        | 调用方与不迁入 API 的原因                                    |
| ----------------------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| api/routes/conversations/service.py | 请求授权、请求键、发送/重试目标、回复 ID 解析、接受/停止/反馈事务、返回当前业务视图 | 当前对话 HTTP 命令；不被执行器或后台导入                     |
| auth/service.py                     | 登录、会话、撤销、有效性解析与后台只读复核                                          | HTTP、已有 CLI 和后台授权均使用                              |
| agents/service.py                   | 配置 CRUD、装配、修订、就绪判断、员工执行事实与一致性检查                           | 管理/公开读取，以及运行准备和授权共同使用                    |
| skills/service.py                   | 方法资产、修订、明确的管理/公开读取和删除规则                                       | 管理与公开 API；参数规则还被装配和运行准备使用               |
| model_connections/service.py        | 连接配置、密文协作、连接检查、当次模型解析与修订复核                                | 配置 API、启动准备、运行授权使用；解密和网络不进入共同写事务 |
| organization_rules/service.py       | 全员正文及版本更新、当前规则读取                                                    | 配置 API与提示词准备共用                                     |
| ci_diagnosis/service.py             | 专业配置/安装、目标与仓库范围、授权、专业过程、报告读取和反馈条件                   | API、运行准备、CI 执行与最终发布共同使用                     |
| conversations/preparation.py        | 接受时捕获依据；启动/恢复时从原冻结依据准备执行函数                                 | API 捕获；协调器启动/恢复；不属于员工配置或 HTTP             |
| conversations/authorization.py      | 组合身份、员工装配、连接与专业范围复核                                              | 接受、启动、动作前、等待和发布五种时点共用                   |
| conversations/publication.py        | 回复正文、专业报告、Run 终态和活动占用原子提交                                      | 后台完成、恢复补发布、排队停止共同使用                       |

共享流程不另建一个 ConversationService 再转调这三个文件。现有 PublishRun 继续作为 publication 中的实际发布协作者，不新增 Manager、Facade 或通用工作流注册表。

preparation/authorization/publication 归 conversations，是因为当前正式运行来源只有对话，完成条件是交付或结束一份对话回复。执行模块不得因此反向导入对话。未来出现真正独立的任务来源时，为新业务定义自己的接受和发布规则，再比较是否有值得共享的部分；不能为了假想 Task 现在建全局协调目录。

## 4. 哪些 API 不新增 service

| API 文件或分组                  | 目标处理方式                                                     | 保留在 API 的逻辑                             |
| ------------------------------- | ---------------------------------------------------------------- | --------------------------------------------- |
| routes/agents.py                | 直接调用 AgentService                                            | 参数、请求权限、公开响应；不再增加转发类      |
| routes/skills.py                | 直接调用 SkillService                                            | 参数、权限和响应                              |
| routes/model_connections.py     | 直接调用 ModelConnectionService                                  | 请求限流、参数和秘密字段响应限制              |
| routes/organization_rules.py    | 直接调用 OrganizationRulesService                                | 参数、权限、修订冲突响应                      |
| routes/auth.py                  | 直接调用 AuthService/GitHubOAuth                                 | Cookie、来源、限流、OAuth 跳转与身份响应      |
| routes/ci_diagnosis.py          | 配置和安装调用 CiDiagnosisService                                | HTTP 权限和专业配置响应；安装默认规则不留路由 |
| routes/public.py                | 调用明确的公开读取入口                                           | 公开端点与白名单响应；不先加载完整秘密配置    |
| routes/configuration_summary.py | 保留有界只读汇总查询                                             | 导航计数，不新建 SummaryService               |
| routes/health.py                | 保留直接响应                                                     | 存活与就绪                                    |
| routes/conversations/router.py  | 命令调请求服务，普通读取调 ConversationQueries，观察调 streaming | 路径、参数、200/202、响应模型与 SSE 响应头    |

路由有逻辑是正常现象。HTTP 状态码、连接释放和 Cookie 不需要被藏进业务模块；配置安装、修订保护与运行资格也不能因为曾写在路由里就变成 HTTP 机制。

## 5. 目标局部目录

以下仅展开本次变动；全部文件含中文注释的目标树见[完整目标树](target-tree.md)。

```text
app/                             # 正式应用；业务、入口与运行按实际职责协作
├── api/                         # HTTP 接入；不被后台或 Agent 反向依赖
│   ├── router.py                # 注册路由；对话分组显式导入其 router
│   └── routes/                  # 简单接口保留单文件；复杂分组按需要展开
│       ├── agents.py            # 员工 HTTP 入口；复用员工模块服务
│       ├── auth.py              # Cookie 与 OAuth；复用认证能力
│       ├── ci_diagnosis.py      # 专业配置与安装入口；不定义取证循环
│       └── conversations/       # 当前对话请求与观察；不成为通用业务容器
│           ├── __init__.py      # 包声明；不自动导入 SDK 或启动业务
│           ├── router.py        # 参数与 HTTP 响应；命令和观察交给对应实现
│           ├── service.py       # 请求事务和目标解析；不再包一层同名业务服务
│           └── streaming.py     # SSE 连接、心跳、重验身份与释放；断线只停止观察
├── conversations/               # 内容、查询与共享回复流程；不导入 API
│   ├── models.py                # 对话、消息和关联约束；数据身份保持单一
│   ├── schemas.py               # 对话公开输入输出；不暴露 SDK 消息
│   ├── queries.py               # 历史、目录、预览和回复读取；不搬入 HTTP
│   ├── writes.py                # 调用方事务内内容写入；不擅自提交
│   ├── preparation.py           # 捕获与从冻结依据准备；恢复不覆盖原输入
│   ├── authorization.py         # 组合运行授权；各时点复用规则
│   └── publication.py           # 内容、专业报告和终态共同提交；多入口共用
├── execution/                   # 队列、控制、预算、停止和恢复；使用注入回调
└── agent_runtime/               # 模型工具循环与 SDK；只取得受限运行能力
```

其他模块的 service 保留在各自模块，详见上一节。不会把其余 router 批量改成目录，也不为同样的读写操作创建两份 API/业务 Service。

## 6. 五条调用路径

### 6.1 员工等配置操作

前端页面 → API 路由 → 所属模块 service → 本模块数据与必要检查 → 提交。

身份与操作权限按现行入口规则检查，资源条件和修订在模块内保证。配置服务可以直接使用 SQLAlchemy，不新建 repository。员工配置对技能/模型的读取不会自动把它升级为“全局用例”。

### 6.2 发送、重试与停止

前端对话控制器 → conversations/router → ConversationRequestService。

发送/重试由请求服务持有一个短事务：

1. 检查 Actor、归属、请求键及准确输入/回复目标。
2. 先按原顺序处理幂等重放；已接受命令返回当前视图，不重复抓取配置和创建记录。
3. 调用 preparation 的捕获函数，使用当前 Session 固定员工、方法、规则、模型修订及专业输入。
4. 调用 conversations/writes 与 execution/admission，建立消息、关联和 Run；一起提交。
5. 提交成功后才允许调度器发现并启动；进程重启仍可扫描已提交 queued，不依赖一次内存通知。

请求服务不执行模型、不等待整个运行结束。router 根据 created/replayed 决定 202/200。

停止解析 response_id 后调用 store 的当前事务入口。排队停止在同一事务调用 publication.finish；运行中停止只登记取消，再由看护收束。二者共用状态与发布规则，API 不复制一次“简化发布”。

### 6.3 后台启动、动作和恢复

bootstrap 注入共享流程 → scheduler/coordinator → preparation 的执行准备函数 → 普通 Agent 或 CI 执行器。

准备函数只使用原冻结依据；当前数据用于版本与权限复核，不重写原提示词。模型解密和网络在事务外。authorization 为控制对象提供检查回调；Agent 只使用 RuntimeControl，不取得认证服务、数据库或 API 服务。

恢复调用同一准备入口。可信已完成存档只返回候选交给 publication；不重新发一次用户请求，不调用 ConversationRequestService，不再次调用模型。

### 6.4 完成与专业过程

执行器 → coordinator → 注入的 PublishRun（conversations/publication）。

publication 在一个写事务中核对状态和本地授权，调用 CI 专业写入、对话写入与 RunStore 状态操作，一起保存正文/报告/终态/占用。执行模块调用能力，不知道消息或专业表。

CI 的过程保存回调在 preparation 绑定：同一短事务调用 CI service 保存有界过程，再调用 store 推进公开版本。它不写正式 report/delivered/feedback，终态后拒绝迟到更新。不为这个回调新增文件。

### 6.5 专业反馈与只读观察

反馈由对话请求服务解析准确回复和专业记录，在一个事务调用 CI 的反馈操作并推进 Run 公开版本，返回当前专业视图与助手视图。反馈条件在 CI service，API 不复制。CI service 提供接受 Session 的写入入口，不嵌套调用会自行提交的公开方法。

历史、快照和报告 GET 通过已有查询和专业读取协作。streaming 只观察已提交视图，处理连接限额、重验查看权限、版本、心跳与释放，不调用模型或改变 Run。前端关闭连接不会触发 stop。

## 7. 事务、授权和依赖约束

| 场景                    | 谁持有事务                                           | 内部协作者                                                                |
| ----------------------- | ---------------------------------------------------- | ------------------------------------------------------------------------- |
| 配置 CRUD               | 所属模块公开 service 操作                            | 模块内部校验、查询、写入                                                  |
| 发送、停止、重试        | ConversationRequestService                           | preparation.capture、admission、writes；排队停止还调用 publication.finish |
| 运行中授权              | authorization 开短只读事务，或使用明确传入的 Session | auth、agents、连接与 CI 的本模块检查                                      |
| 专业过程                | preparation 绑定的保存回调                           | CI service + RunStore，短事务共同提交                                     |
| 后台最终发布/恢复补发布 | PublishRun 的外部调用入口                            | 同 Session 授权、专业与消息写入、状态操作                                 |
| 专业反馈                | ConversationRequestService                           | CI 反馈与公开版本一起提交                                                 |
| 快照/历史/SSE 读取      | 对应查询的一致读取事务                               | 组合摘要、消息、关联与安全运行事实                                        |

需要原子协作时只使用当前 Session 辅助；不能通过连续调用两个自行提交的 service 方法假装完成一个事务。publication.finish 使用已存在事务，publication 的后台入口才创建新事务。SDK 调用、远端证据复查和模型解密不占用这个共同写事务。

依赖方向：

- API 可以调用所属业务能力；共享业务、execution、agent_runtime 不导入 api。
- execution 接受准备、授权、发布回调，不导入 conversations、CI 具体流程或 API 服务。
- agent_runtime 只依赖自己的协议和模型技术能力；不取得 Store/Session，也不导入业务 ORM。
- 对话共享流程可以组合其他模块；被调用模块不反向调用对话请求服务，避免服务循环。
- 模块间明确的数据引用允许存在，不为“零引用”制造代理层；bootstrap 是具体装配例外。
- API 请求服务不使用 Request/Response/FastAPI 类型。路径所在位置表达当前归属，普通参数便于独立测试，但不会因此把它作为后台公共入口。

## 8. 开源调研：采用什么，拒绝什么

调研使用固定快照，不把热门项目目录当成架构标准：

| 来源与已核实事实                                                   | 本方案采用                           | 不采用                                                |
| ------------------------------------------------------------------ | ------------------------------------ | ----------------------------------------------------- |
| LobeHub 路由按功能分组，部分调模型、部分调共享服务                 | 简单接口可直读，复杂对话请求就近组织 | 每个路由必须配 Service、所有接口必须经过同样层数      |
| LobeHub HTTP/RPC 共用 AiAgentService，运行通过宿主接口获得具体能力 | 共享执行独立于入口，运行能力显式注入 | 复制多包工程和宽泛的全部 transport 接口               |
| StaffDeck HTTP 与 IM 都调用 AgentLoop，底层引擎由桥接启动          | 共享流程不要成为路由私有实现         | 为 demo 建 Node 子进程、进程池或模块插槽体系          |
| StaffDeck 平台协调仍持有 ORM，存在兼容层与大型路由                 | 参考真实调用，逐项核对边界           | 照搬 core 目录、历史 wrapper、TaskFrame/Turn/Run 名称 |

源码依据：[LobeHub 路由](https://github.com/lobehub/lobehub/blob/ab57dc331efa16903acc1e97d60319d2643a8e8f/apps/server/src/routers/lambda/agent/lifecycle.ts)、[共享运行服务](https://github.com/lobehub/lobehub/blob/ab57dc331efa16903acc1e97d60319d2643a8e8f/apps/server/src/services/aiAgent/index.ts)、[宿主装配](https://github.com/lobehub/lobehub/blob/ab57dc331efa16903acc1e97d60319d2643a8e8f/apps/server/src/modules/AgentRuntime/buildHost.ts)；[StaffDeck 对话入口](https://github.com/OpenBMB/StaffDeck/blob/fcc28c003ef188e6d0a11596d44fdfb3723b275b/backend/app/api/chat.py#L889)、[渠道入口](https://github.com/OpenBMB/StaffDeck/blob/fcc28c003ef188e6d0a11596d44fdfb3723b275b/backend/app/channels/service_intake.py#L1619)、[运行桥接](https://github.com/OpenBMB/StaffDeck/blob/fcc28c003ef188e6d0a11596d44fdfb3723b275b/backend/src/staffdeck_harness/bridge/engine_host.py)。

本项目继续保留 Conversation/Message/Run、单宿主 SQLite、当前受控 CI，以及原子交付约束。没有因为调研而增加正式任务、计划、目标、事件总线或通用引擎框架。

## 9. 实施与验收

P1 先迁出共享准备/授权/发布，再移动请求服务和 SSE；使用现有记录及响应，API URL、当前消息存储和停止行为保持。P2 增加 CiDiagnosis 专业版本时启用专业/公开 revision 的共同推进，P3 再切换回复路径与新视图。服务位置变化不作为提前修改外部契约的理由。

实施时至少核对：

1. 原命令及发布测试的导入切换，API 与后台实际指向同一共享授权/发布实现。
2. 不通过 HTTP 或 API 服务也能验证启动、撤权、停止、恢复和发布。
3. 请求服务接受普通 Actor/输入，幂等和接受失败完整回滚。
4. 队列停止与后台完成竞争只有一次终态；配置读取未就绪员工仍能编辑。
5. CI 反馈/过程版本共同提交，终态报告不得被迟到过程或反馈覆盖。
6. SSE 在开始前断开、运行中断开、鉴权失败、异常退出均释放名额；不自动停止后台。
7. AST/导入边界检查确认共享流程和执行器没有反向依赖 API，公开字段不泄漏 SDK。
8. 模块与前端无关的路径、生成资源、凭证和数据库数据保持；纯移动不增加镜像测试。

实际本轮只做文档与生成工具检查，见[本轮记录](../../records/api-service-boundaries.md)。

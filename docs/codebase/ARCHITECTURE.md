# 实际架构与核心链路

适用范围：本文保留 2026-10-31 的调查快照，未随之后的知识处理、向量及员工装配增量逐项更新，不作为当前能力清单或当前测试通过证明。当前行为从[系统架构](../architecture/overview.md)、[知识契约](../reference/knowledge.md)与[工程文档索引](../README.md)进入。
调查日期：2026-10-31。结论依据本地源码和本次隔离验证，未验证已部署实例。本文中“已确认”指可定位的实现事实；“推断”只表示从该实现导出的工程判断；无法确认的项目使用 `[TODO]`。环境、目录、规则、集成、测试和风险分别见 [STACK](STACK.md)、[STRUCTURE](STRUCTURE.md)、[CONVENTIONS](CONVENTIONS.md)、[INTEGRATIONS](INTEGRATIONS.md)、[TESTING](TESTING.md)、[CONCERNS](CONCERNS.md)。

## 1. 架构风格、问题与约束

**已确认：这是客户端 React SPA 加 FastAPI 模块化单体。** 它把“岗位指令、可复用方法、模型连接、工具许可”组成可反复使用的数字员工；成员提交输入，平台接受处理责任，保存消息、动作及成果文件。员工配置与登录用户不是同一对象，模型生成的候选文本也不直接等于已发布成果。[Agent](../../backend/app/agents/models.py)、[AuthService](../../backend/app/auth/service.py):L44、[ConversationService.submit](../../backend/app/conversations/service.py):L61、[PublishRun.finish](../../backend/app/conversations/publication.py):L33 支撑这一判断。

后端按业务模块持有对象，短事务组织跨模块写入；耗时执行通过数据库队列与同进程异步任务推进。它同时有分层适配（HTTP、业务、执行、SDK、外部资源），但不是目录整齐排列的单向 controller-service-repository 架构，也没有为每个服务建立独立 Repository。真实依赖包括直接查询其他模块 ORM、启动注入回调，以及同库外键，具体见下文。

主要实现约束是单机文件型 SQLite、一个正式 Runner，以及受限且可重新检查的资源授权。证据：[config._load_database_url](../../backend/app/config.py):L66、[Runner.start](../../backend/app/execution/scheduler.py):L30、[ConversationAuthorization.check](../../backend/app/conversations/authorization.py):L17。**推断：** 当前的业务原子提交和简化部署适合单宿主；拆 worker 或多实例必须重新设计领取、租约与发布，不能仅增加 Uvicorn workers。

## 2. 运行进程与启动初始化

| 场景          | 实际进程/任务                                                                                              | 证据                                                                                                                                                                                                                             |
| ------------- | ---------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 本地 make dev | Python DevLauncher，Uvicorn 热重载监督/应用进程，Vite Node 进程，浏览器                                    | [Makefile](../../Makefile):L32；[dev.py](../../scripts/dev.py) `backend_command`:L67、`frontend_command`:L85、`spawn`:L96                                                                                                        |
| make start    | 单 Uvicorn 应用进程交付 API 与 frontend/dist；无正式 Node SSR 服务                                         | [Makefile](../../Makefile):L41；[frontend_delivery.py](../../backend/app/api/frontend_delivery.py) `mount_frontend`:L93                                                                                                          |
| 应用内部      | Runner 扫描任务、每 Run 的执行/观察任务、文件/沙箱清理任务；同步 I/O 多处交给 asyncio.to_thread            | [bootstrap.py](../../backend/app/bootstrap.py) `lifespan`:L58；[coordinator.py](../../backend/app/execution/coordinator.py):L90–95                                                                                               |
| 外部能力      | 模型 API、HTTP MCP；启用可信 stdio 时派生 MCP 子进程；启用沙箱时访问外部 OpenSandbox server 与工作负载容器 | [invocation.py](../../backend/app/tools/invocation.py) `client_for_connection`:L27；[stdio.py](../../backend/app/tools/adapters/stdio.py) `_own_session`:L33；[部署 service](../../deploy/opensandbox/niuma-opensandbox.service) |

### 后端启动

1. Uvicorn 导入 [main.py](../../backend/app/main.py):L3 的 `create_app`，调用 [config.load_config](../../backend/app/config.py):L85；环境覆盖 .env，解析 SQLite、Key、锁、文件与工具配置。此时不执行迁移、不要求模型 Key。
2. [bootstrap.create_app](../../backend/app/bootstrap.py):L48 定义 lifespan，注册 router、安全中间件、错误处理器及静态交付。静态资源只在构造时存在 index.html 才挂载；未知 API 不回退到 SPA。[frontend_delivery.py](../../backend/app/api/frontend_delivery.py):L48、L93。
3. lifespan 创建 `Database`，配置 foreign_keys、WAL、FULL；构建 Auth/模型连接/员工/工具/技能/文件/知识等服务，保存到 app.state。[session.py](../../backend/app/infrastructure/database/session.py) `Database`:L25；[bootstrap.py](../../backend/app/bootstrap.py):L59–96。
4. 构造 `ConversationAuthorization.check`、`PublishRun`、`CheckpointStore`、`ConversationPreparation`、`RunAdmission`、`RunStore`、`ExecutionCoordinator` 与 `Runner`。prepare/authorize/publish 是注入给执行宿主的回调，宿主不直接查询对话 ORM。[bootstrap.py](../../backend/app/bootstrap.py):L113–147。
5. runtime.enabled 时 `Runner.start` 先获取非阻塞 fcntl 独占锁，再 `store.recover(True)`，发布不可恢复终态，启动数据库扫描循环并置 ready；随后启动沙箱/文件清理。[scheduler.py](../../backend/app/execution/scheduler.py):L30–51；[store.py](../../backend/app/execution/store.py) `recover`:L20。
6. shutdown 先停止 Runner，再停止沙箱/文件维护，关闭 MCP 调用服务和数据库。可恢复 Run 在协调器收到 CancelledError 时保留恢复机会；这与用户显式停止不同。[bootstrap.py](../../backend/app/bootstrap.py):L148–160；[coordinator.py](../../backend/app/execution/coordinator.py):L113–117。

迁移是 [Makefile](../../Makefile) `db-upgrade` 的独立前置操作，启动不会补表。[test_bootstrap.py](../../backend/tests/test_bootstrap.py) `test_app_owns_database_lifecycle_without_running_migrations`:L100 直接检查空库行为。

### 前端与开发监督器

[DevLauncher](../../scripts/dev.py):L59 预占端口、拉起后端并检查 `/health`，将实际 `BACKEND_URL` 交给 Vite，统一清理本次子进程。Vite 代理 `/api`、保持同源，代理失败返回明确的 502。[vite.config.ts](../../frontend/vite.config.ts) `defineConfig`:L22。

浏览器从 index.html 进入 [main.tsx](../../frontend/src/main.tsx):L8，安装 theme controller 并挂载 RouterProvider；路由 lazy 加载 Page，工作台 [Layout](../../frontend/src/Layout.tsx):L39 依次建立 AuthBoundary、WorkspaceDataProvider、工具栏和 EditingProvider。[WorkspaceDataProvider](../../frontend/src/state/workspace/WorkspaceDataProvider.tsx):L13 以 identityKey 重建数据实例，卸载时释放缓存与请求；[workspaceData.retain](../../frontend/src/state/workspace/workspaceData.ts):L58 用微任务兼容 StrictMode 重挂载。

## 3. 核心链路一：提交对话到交付与观察

### 正常路径及异步消费端

1. **页面发出可确认的命令。** [useConversationController.submit](../../frontend/src/pages/conversations/useConversationController.ts):L230 先将提交标识和输入写入待确认存储，再经 [conversationTransport](../../frontend/src/lib/api/conversationTransport.ts) 调用 [sendMessage](../../frontend/src/lib/api/conversations.ts):L211。HTTP `POST /api/conversations/{id}/messages` 调用 `commands.submit`，新接受返回 202，幂等重放返回 200。[routes/conversations.py](../../backend/app/api/routes/conversations.py):L107–132。
2. **接受事务。** [ConversationService.submit](../../backend/app/conversations/service.py):L92–212 在取得 SQLite 写者位置后，核对对话所有者和员工，检查幂等摘要、容量、对话空闲，准备配置/文件/上下文，再创建用户 Message、queued Run、空回复 Message 与 ConversationRun 关联。`RunAdmission.accept` 不自行提交；任何失败回滚整个接受。[admission.py](../../backend/app/execution/admission.py):L29、L43、L62；[writes.py](../../backend/app/conversations/writes.py) `prepare_input`:L33、`bind_run`:L56。
3. **固定输入和资源依据。** [ConversationPreparation.prepare](../../backend/app/conversations/preparation.py):L56–131 复制全员规则、岗位指令、技能正文/manifest、参数、连接配置/凭据修订、工具绑定和运行预算；不把明文模型 Key 写进 Run。上下文由 [select_context](../../backend/app/conversations/queries.py)从已发布消息选择，不从 SDK checkpoint 拼装。执行前才解析凭据和资源。
4. **数据库队列消费。** [Runner._loop](../../backend/app/execution/scheduler.py):L80–123 周期读取 `RunStore.queued_metadata`；过队列期限即发布 queue_timeout，否则按并发数 create_task。没有 broker 推送。`ExecutionCoordinator.run` 读取快照、检查 schema/剩余时限、重新授权、claim queued→running，然后调用注入的 preparation.execution。[store.py](../../backend/app/execution/store.py):L44–61；[coordinator.py](../../backend/app/execution/coordinator.py):L60–95。
5. **SDK 执行和动作消费。** [ConversationPreparation.execution](../../backend/app/conversations/preparation.py):L133–212 解析本 Run 的 checkpoint、精确修订模型连接、文件与 MCP/沙箱资源，调用 [execute_agent](../../backend/app/agent_runtime/langchain.py):L109。后者用 `create_agent`、技能/文件中间件、获准工具及 sync durability 驱动 `agent.astream`。模型 messages/updates 被 `_consume_agent_stream` 消费，交给 `hooks.report_content`；工具调用经 [tool_calls.py](../../backend/app/agent_runtime/tool_calls.py) 和 [middleware.py](../../backend/app/agent_runtime/middleware.py)申请 RunControl 授权/预算，调用 MCP 或工作区，写入 RunAction。SDK 内部事件不会直接推送浏览器。[control.py](../../backend/app/execution/control.py)、[store.py](../../backend/app/execution/store.py) `start_model`:L203、`begin_tool`:L306。
6. **发布事务与前端消费。** SDK 确认最终 AIMessage 无工具请求且正文非空，收集输出，返回 AgentOutput。协调器再次 guard，调用 [PublishRun](../../backend/app/conversations/publication.py):L33–89；同一事务写 Run 终态、动作收尾、Message 正文、解除 active 关联，并校验/绑定本 Run 的输出文件。SSE [subscribe.snapshots](../../backend/app/api/conversation_streaming.py):L30 轮询已保存的 response.version，产生 `response.snapshot` / `response.finished`；浏览器 [useResponseSubscription.receive](../../frontend/src/pages/conversations/useResponseSubscription.ts):L31 按版本合并并结束终态观察。

### 取消、重试、恢复与失败返回

以下运行失败通常已经发生在 202 接受之后，结果通过保存的回复状态与 SSE/GET 读取，不能期待它们回到原始 POST 的 HTTP 状态。SSE 在响应开始后的读取异常可能直接断流，HTTP 错误处理器不能把已发出的 200 改成另一个响应；前端由断连恢复路径重新 GET 核对。[subscribe](../../backend/app/api/conversation_streaming.py):L30–79、[useResponseSubscription.recover](../../frontend/src/pages/conversations/useResponseSubscription.ts):L54。

| 情况                                  | 已确认路径与用户可见结果                                                                                                                                                                                                                                                                                                         |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 接受前失败                            | ServiceError 在 HTTP 层转 401/403/404/409/422/429/503；数据库 busy 为 503，含 Retry-After；不创建半份消息/Run。[api/errors.py](../../backend/app/api/errors.py):L53、L94                                                                                                                                                         |
| POST 网络结果不确定                   | Controller 保留相同 request key，重新打开先 findRequest；不是直接用新 key 重发。[useConversationController.ts](../../frontend/src/pages/conversations/useConversationController.ts):L140–150、L281；[admission.replay](../../backend/app/execution/admission.py):L29                                                             |
| 关闭页面 / SSE 断开                   | 只释放订阅。浏览器先 GET 快照，再按 1/2/5 秒最多三次重连；401/403/404 停止自动恢复；不启动新 Run。[conversation_streaming.py](../../backend/app/api/conversation_streaming.py):L35–66；[useResponseSubscription.ts](../../frontend/src/pages/conversations/useResponseSubscription.ts):L44–100                                   |
| 用户显式停止                          | queued 直接发布 cancelled；running→cancelling，协调器 watcher 检出并中止。发布也检查 cancelling，避免迟到成功覆盖。[service.cancel](../../backend/app/conversations/service.py):L225；[coordinator._watch](../../backend/app/execution/coordinator.py):L41；[publication.py](../../backend/app/conversations/publication.py):L36 |
| 手动重试                              | 只允许当前对话最后一次 failed/cancelled/interrupted；复用原输入 Message，创建新 Run 和回复，重新准备当前配置。不是回退原 Run 的状态。[service.py](../../backend/app/conversations/service.py):L110–146、L198；[writes.prepare_input](../../backend/app/conversations/writes.py):L33                                              |
| 模型/工具错误、空回复、预算或期限耗尽 | 协调器映射稳定错误码并发布终态；失败的部分正文是否保留由快照策略控制。正式 SDK 模型自动重试默认 0。[coordinator.py](../../backend/app/execution/coordinator.py):L101–136；[llm/config.py](../../backend/app/llm/config.py) `LLMConfig`                                                                                           |
| 存储或发布失败                        | coordinator 将 Run 放入内存 pending_failures、状态 degraded；Runner 后续补发 persistence_unavailable 失败终态，不能报告交付成功。[coordinator.py](../../backend/app/execution/coordinator.py):L118、L165；[scheduler.py](../../backend/app/execution/scheduler.py):L83                                                           |
| 进程重启                              | recover 将兼容且 resumable 的活动 Run 重新排队，其余中断，cancelling 收为取消。SDK checkpoint 以 run.id 为 thread_id，查最新 metadata 弥补 checkpoint 提交与业务引用不在同一事务的问题。[store.py](../../backend/app/execution/store.py):L20；[checkpoints.py](../../backend/app/agent_runtime/checkpoints.py):L23、L36、L77     |
| 工具结果不确定                        | 已成功 readonly 调用可复用保存结果；非 readonly 的已存在调用拒绝重放，报 tool_result_unknown；不承诺外部副作用 exactly-once。[store.begin_tool](../../backend/app/execution/store.py):L306–331                                                                                                                                   |

## 4. 核心链路二：知识文本入库、检索与来源核对

1. **浏览器逐文件提交。** [KnowledgeLibrary.LibraryDocuments.upload](../../frontend/src/pages/knowledge/KnowledgeLibrary.tsx):L101 为每个 File 保存稳定 UUID；同页失败后再点击仍使用同一个条目标识。[KnowledgeStore.upload](../../frontend/src/state/knowledge/knowledgeStore.ts):L52 调 API，写成功统一失效 knowledge 查询。浏览器上传队列只存在页面局部状态，不是后台队列。
2. **HTTP 限界。** [routes/knowledge.upload_document](../../backend/app/api/routes/knowledge.py):L46–66 先验证本人库，再限频和流式收集最多 128 KiB，使用 to_thread 调同步 `KnowledgeService.upload`。HTTP 请求直到业务入库完成才返回；没有后续 worker。
3. **解析与原件落盘。** [text_document](../../backend/app/knowledge/service.py):L54 校验 .md/.txt、UTF-8、非空和文本，固定规范化正文与 SourceBlock 位置，计算原始字节 hash。`upload` 第一次查重后，在事务外切片与 jieba 分词，再调用 FileService.save，原件独立提交；切片预算这里用字符长度 len，不是模型 token 计数。[service.py](../../backend/app/knowledge/service.py):L251–268。
4. **事务发布索引。** 再取得库写锁，复核所有者、请求/content hash 去重、200 文档/5000 片段额度；同一 SQLite 事务写 LibraryDocument、LibraryChunk、knowledge_fts 与库 updated_at。失败回滚文档/片段/FTS；已经保存但无引用的原件由保留清理回收。[service.py](../../backend/app/knowledge/service.py):L269–313；[0013.upgrade](../../backend/migrations/versions/0013_knowledge_libraries.py):L20–71。
5. **关键词检索。** [KnowledgeStore.search](../../frontend/src/state/knowledge/knowledgeStore.ts):L31 按库和问题缓存请求；后端 `KnowledgeService.search` 分词、最多 64 去重词、构造转义的 FTS OR 表达式，核对 lexical_version，并在库归属过滤下执行 FTS5 MATCH / bm25，返回实际 Chunk 与排名，无模型生成/embedding 请求。[service.py](../../backend/app/knowledge/service.py):L371–408。
6. **来源与删除。** `detail` 从保存的 document/chunk snapshot 返回固定文字与位置，`download` 经 FileService 读取原件；`remove` 同事务删除 FTS、片段与文档，原件失去知识引用后遵循 FileService 的保留策略。[service.py](../../backend/app/knowledge/service.py):L324–360；[retained_file_ids](../../backend/app/knowledge/service.py):L43。

失败分支：格式/编码/大小/额度拒绝是 422，非本人库统一 404，同 request id 不同内容及索引版本过期为 409。相同内容去重不会重建过期索引：**本次隔离实验已确认**，标记旧版本后以新 request id 重传同文件仍返回原文档，检索继续 409；需先移除旧文档再上传，或后续实现显式重建。证据与复现见 [CONCERNS](CONCERNS.md)。`import_demo` 是逐文档 upload，不保证整批原子成功：[service.py](../../backend/app/knowledge/service.py):L362–369。

## 5. 状态所有者与持久化

| 状态                        | 持有者与修改入口                                                                                    | 保存/恢复边界                                                                                                                                                                                                                                                                                             |
| --------------------------- | --------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 用户、会话和权限            | AuthService login/guest/resolve/maintain_user；业务检查 Actor 和资源归属                            | SQLite User/AuthSession/ExternalIdentity；浏览器 Cookie 是凭据，前端 Identity 只是投影。[auth/service.py](../../backend/app/auth/service.py):L44–267                                                                                                                                                      |
| 员工、装配、模型/工具与规则 | AgentService、SkillService、ModelConnectionService、ToolConnectionService、OrganizationRulesService | 同业务库；配置修订、凭据修订用于防止运行中静默切换。Skill 编辑目录与 blob 独立于 DB。[skills/service.py](../../backend/app/skills/service.py):L49、L131、L425；[preparation.py](../../backend/app/conversations/preparation.py):L79                                                                       |
| 对话、输入与稳定回复        | ConversationService / writes / PublishRun                                                           | Message.body 保存输入与最终/部分正文；ConversationRun 绑定 Run 与消息，active 约束串行；执行中片段由 RunAction 投影。[writes.py](../../backend/app/conversations/writes.py):L33、L90                                                                                                                      |
| Run / RunAction / 预算      | RunAdmission 创建，RunStore claim/start/finish，Coordinator 决策、PublishRun 事务发布               | SQLite；状态、revision、预算和结果引用持久化。Runner.tasks、pending_failures 是进程内控制状态，不是持久事实。[models.py](../../backend/app/execution/models.py):L22–88；[store.py](../../backend/app/execution/store.py):L103                                                                             |
| SDK 执行状态                | LangGraph / TrackingSqliteSaver                                                                     | 独立 `.checkpoints.sqlite`，按 Run 隔离；不作为产品历史库；metadata 与完成标记校验恢复。[checkpoints.py](../../backend/app/agent_runtime/checkpoints.py):L45；[langchain.py](../../backend/app/agent_runtime/langchain.py):L167–211                                                                       |
| 文件与沙箱                  | FileService.save/sweep；SandboxService.acquire/release/sweep                                        | 文件字节在目录、metadata 在 SQLite；沙箱 metadata 在库，远端字节由容器持有。正式输出还需 MessageFile 发布关联。[files/service.py](../../backend/app/files/service.py):L47、L155；[sandboxes/service.py](../../backend/app/sandboxes/service.py):L128                                                      |
| 知识数据                    | KnowledgeService                                                                                    | LibraryDocument snapshot、LibraryChunk、FTS 在业务库；原件在 FileService；无正式向量服务。[knowledge/service.py](../../backend/app/knowledge/service.py):L251、L371                                                                                                                                       |
| 前端共享副本                | identityKey 作用域 WorkspaceData、AgentStore/SkillStore/KnowledgeStore、Resource                    | 内存缓存按记录订阅，写成功同步/失效；身份切换 dispose，不承担服务器最终事实。[workspaceData.ts](../../frontend/src/state/workspace/workspaceData.ts):L18、L58                                                                                                                                             |
| 本地 UI、草稿与待确认请求   | 页面 state/reducer、draft/pendingSubmissionStorage；主题 controller                                 | 草稿/提交确认使用标签页存储，主题使用 localStorage；不能据此推断服务器是否已执行。[pendingSubmissionStorage.ts](../../frontend/src/pages/conversations/pendingSubmissionStorage.ts)、[draft.ts](../../frontend/src/lib/draft.ts)、[themeController.ts](../../frontend/src/state/theme/themeController.ts) |

## 6. 实际依赖与复用模式

| 关系/模式        | 调用依据                                                                            | 架构含义                                                                      |
| ---------------- | ----------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| 装配根与手动注入 | bootstrap 把 preparation.execution、authorization.check、publisher 注入 Coordinator | 运行时存在 execution→对话回调协作，不能因无直接 import 就遗漏；无独立 DI 容器 |
| 同库业务组合     | conversations.service 导入 Run/Message/员工快照；agents.service 导入 Skill 等资源   | 模块所有权不同，但不是独立数据库边界；共享 Session 保证接受/配置原子性        |
| 反向使用检查     | bootstrap 将 tool_grants.assert_connections_unused 注入 MCP 定义/账号服务           | 工具资源删除可检查员工引用；tools 不必直接导入 agents 服务                    |
| 限制型端口       | RuntimeControl、RuntimeResources、AgentRequest                                      | SDK 只获得运行授权、动作记录与受限文件/工具资源；正式发布留在宿主/产品        |
| 模型注册聚合     | infrastructure.database.models 导入所有 ORM                                         | 供迁移/metadata 使用，不能把这条导入误读成数据库工具承担业务编排              |
| 前端资源订阅     | Provider→WorkspaceData→领域 Store→API→Resource/useSyncExternalStore                 | 固定实例按身份释放；查询与局部对话状态并存，没有 Redux/Zustand 运行依赖       |

证据：[bootstrap.py](../../backend/app/bootstrap.py)、[contracts.py](../../backend/app/agent_runtime/contracts.py)、[resources.py](../../backend/app/agent_runtime/resources.py)、[models.py](../../backend/app/infrastructure/database/models.py)、[useResource.ts](../../frontend/src/state/shared/useResource.ts)。

## 7. 架构风险与未知项

- 已确认单机锁和 SQLite 单写者边界；跨主机扩容不在当前实现内。
- 已确认业务库、checkpoint、blob、原件和密钥属于不同保存介质/事务；**推断：** 只备份 app.db 不足以恢复完整执行与附件，实际恢复演练为 `[TODO]`。
- 已确认过期知识索引重传同内容无法修复；详见 [CONCERNS](CONCERNS.md)。
- `[TODO]` 未连接真实模型/MCP/GitHub/沙箱，未做浏览器端到端、负载或生产恢复演练；当前代码及离线测试不证明部署就绪。

## 8. 证据入口

- 装配和生命周期：[bootstrap.py](../../backend/app/bootstrap.py) `create_app/lifespan`；[scheduler.py](../../backend/app/execution/scheduler.py) `Runner`。
- 对话接受与发布：[service.py](../../backend/app/conversations/service.py) `submit/cancel/retry`；[publication.py](../../backend/app/conversations/publication.py) `PublishRun`。
- 执行及 SDK：[coordinator.py](../../backend/app/execution/coordinator.py) `run/_watch`；[langchain.py](../../backend/app/agent_runtime/langchain.py) `execute_agent`。
- 知识与状态：[knowledge/service.py](../../backend/app/knowledge/service.py) `upload/search`；[workspaceData.ts](../../frontend/src/state/workspace/workspaceData.ts) `WorkspaceData`。

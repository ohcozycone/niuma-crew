# 外部集成、保存介质与故障边界

调查日期：2026-10-31。已确认的是接线和代码约束，`[TODO]` 是未接触真实服务的运行状态。部署参数仍以[后端指南](../guides/backend-operations.md)、[工具指南](../guides/agent-tools.md)和 [.env.example](../../backend/.env.example)为准。

## 1. 集成清单

| 系统                    | 类型与目的                              | 身份及关键性                                                     | 实现证据                                                                                                                                                          |
| ----------------------- | --------------------------------------- | ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 文件型 SQLite           | 业务对象、Run/动作、凭据密文与知识 FTS5 | 后端本地文件访问；核心依赖                                       | [session.py](../../backend/app/infrastructure/database/session.py) `Database`:L25；[0013 迁移](../../backend/migrations/versions/0013_knowledge_libraries.py):L70 |
| 独立 checkpoint SQLite  | LangGraph 按 Run 恢复状态               | SDK 内部序列化；恢复依赖                                         | [checkpoints.py](../../backend/app/agent_runtime/checkpoints.py) `CheckpointStore`:L45                                                                            |
| Kimi Code               | Chat Completions 生成                   | 管理员保存的连接密钥；真实对话依赖                               | [presets.py](../../backend/app/model_connections/presets.py) `KIMI_CODE`:L17；[factory.py](../../backend/app/llm/factory.py):L24                                  |
| MCP HTTP                | 外部工具发现、审核和获准调用            | 服务定义/共享或个人连接，Bearer/指定 header 等；按员工许可使用   | [connections.py](../../backend/app/tools/connections.py)、[mcp.py](../../backend/app/tools/adapters/mcp.py) `invoke`:L136                                         |
| MCP stdio               | 可信宿主程序提供工具                    | 部署默认关闭，管理员登记，环境凭据解密注入；程序拥有后端宿主权限 | [config.py](../../backend/app/config.py):L108；[stdio.py](../../backend/app/tools/adapters/stdio.py) `_own_session`:L33                                           |
| GitHub OAuth            | 登录普通成员                            | server-side client secret、state/PKCE；可选                      | [github.py](../../backend/app/auth/github.py) `start`:L56、`context`:L84、`identity`:L123                                                                         |
| OpenSandbox             | 隔离命令与运行文件                      | server API key、已验证 profile、镜像、部署归属；execute 工具需要 | [provider.py](../../backend/app/sandboxes/provider.py)、[service.py](../../backend/app/sandboxes/service.py) `acquire`:L128                                       |
| 知识 POC 的 Chroma/向量 | 独立实验及评估                          | knowledge-poc 可选组；未进入正式知识 HTTP 问答                   | [pyproject.toml](../../backend/pyproject.toml):L37；[experiments/knowledge_poc.py](../../backend/experiments/knowledge_poc.py)                                    |

没有在正式应用装配和执行路径发现 Redis、Kafka、RabbitMQ 等 broker；待处理 Run 在 SQLite，Runner 轮询消费。MCP 的 Streamable HTTP/SSE 与对浏览器的 response SSE 是两个不同传输边界。[scheduler.py](../../backend/app/execution/scheduler.py):L94；[mcp.py](../../backend/app/tools/adapters/mcp.py):L90；[conversation_streaming.py](../../backend/app/api/conversation_streaming.py):L13。

## 2. 数据保存介质

| 介质                   | 所有者、访问层                              | 保存与一致性边界                                                                         |
| ---------------------- | ------------------------------------------- | ---------------------------------------------------------------------------------------- |
| app.db                 | Database + 各业务服务/ORM                   | WAL、foreign_keys、synchronous=FULL；短 Session 事务，同步 I/O；迁移独立执行             |
| app.checkpoints.sqlite | CheckpointStore / TrackingSqliteSaver       | 与业务 checkpoint_id 引用非原子提交；恢复查最新 metadata；产品历史不依赖它               |
| files 目录             | FileService                                 | 原子替换/fsync 字节后提交 metadata；知识/对话引用由 bootstrap 合并保留；无引用旧字节回收 |
| skill-assets           | SkillBlobStore                              | 内容 hash 寻址的运行资源；数据库 manifest 引用固定字节                                   |
| 可编辑技能目录         | SkillLibrary，默认后端宿主 ~/.agents/skills | 文件锁、指纹检查与目录替换辅助数据库更新；不同于不可变 blob；显式 sync 才入库            |
| 主密钥文件/环境        | CredentialVault                             | Fernet 密钥在数据库外；模型与工具可用独立文件，显式环境 Key 优先                         |
| 远端沙箱               | SandboxService + provider                   | SQLite metadata 记录申请/归属/销毁；远端文件不等于平台交付文件                           |

证据：[FileService.save/sweep](../../backend/app/files/service.py):L47、L155；[SkillService](../../backend/app/skills/service.py):L49–60；[packages.py](../../backend/app/skills/packages.py) `SkillBlobStore`；[library.py](../../backend/app/skills/library.py) `SkillLibrary`；[credentials.py](../../backend/app/infrastructure/credentials.py):L14；[SandboxService](../../backend/app/sandboxes/service.py):L128–220。

**推断：** 恢复整套可用系统需要协调业务库、checkpoint、文件、Skill blob 和密钥，不能仅复制 app.db。`[TODO]` 本次未做备份恢复演练，不能确认现网备份完整性。

## 3. 凭据与信任边界

- 部署配置合并 .env 与环境；密钥不以浏览器参数决定模型 base_url，正式预设目前只有 Kimi Code。[config.py](../../backend/app/config.py):L49；[presets.py](../../backend/app/model_connections/presets.py):L27。
- 模型/工具凭据存 Fernet 密文，运行时在服务端解密；主密钥注入优先于文件。生成文件使用临时文件、fsync 和 link 防竞争，无法解密返回明确不可用，不能直接更换主密钥后仍假定旧密文可用。[CredentialVault._cipher](../../backend/app/infrastructure/credentials.py):L18–51。
- 员工许可、使用者账号和工具描述分别核对；个人绑定不能扩大许可。调用前核对配置/凭据修订以及 descriptor/instructions hash，目录变化需重新审核。[ConversationAuthorization.check](../../backend/app/conversations/authorization.py):L17；[MCPClient.invoke](../../backend/app/tools/adapters/mcp.py):L136。
- MCP HTTP 使用主机策略、DNS/IP 校验和 PinnedTransport，关闭环境代理、跳转及 transport 重试；源码检查不等于完整渗透测试。[network.py](../../backend/app/tools/network.py) `validate_endpoint`:L14、`PinnedTransport`:L54。
- 浏览器写请求验证 Origin，JSON 有大小边界，文件上传单独流式限界；身份和对象所有权继续在服务内检查。[security.py](../../backend/app/api/security.py):L11；[knowledge.py](../../backend/app/api/routes/knowledge.py):L46。

未读取真实 .env、数据库内密文或宿主 Key 内容，也未做全仓历史秘密扫描；不能给出“没有硬编码秘密”的全局结论。所读样例为占位配置，所读正式模型端点为预设元数据。

## 4. 超时、重试与故障处理

| 集成     | 实际处理                                                                                                                                                                                                                                                               |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 模型     | model_session 的 httpx 超时 60 秒、连接 10 秒；trust_env=false、无重定向。LLMConfig.max_retries 默认 0；协调器另施加整 Run 剩余期限与预算。[factory.py](../../backend/app/llm/factory.py):L36–46；[llm/config.py](../../backend/app/llm/config.py)                     |
| MCP      | 每次调用取工具配置与绑定超时的较小值；401/403 变公开工具错误，目录变化保存 candidate 并拒绝；未知失败 tool_upstream_failed，不自动重放外部写操作。[invocation.py](../../backend/app/tools/invocation.py):L46–111；[network.py](../../backend/app/tools/network.py):L59 |
| Run 恢复 | readonly 且保存成功结果可重用；不确定副作用拒绝重放，避免重复外部操作。[store.begin_tool](../../backend/app/execution/store.py):L306–331                                                                                                                               |
| 沙箱     | 申请先记录 requested；未知创建结果仍占容量，按精确 metadata 核对。回收失败留 cleanup/unknown，维护任务再尝试；退出清理有 20 秒外层期限。[service.py](../../backend/app/sandboxes/service.py):L128–241                                                                  |
| 文件维护 | 启动和定时 sweep 删除无引用过期内容；对话/知识提供 retained 集合，维护异常记录并继续。[service.py](../../backend/app/files/service.py):L155–214；[bootstrap.py](../../backend/app/bootstrap.py):L98                                                                    |
| GitHub   | httpx 10 秒、无环境代理和重定向，网络/格式错误统一拒绝；本地管理员/游客是不同登录入口，并非自动切换账号。[github.py](../../backend/app/auth/github.py):L123–165                                                                                                        |
| 数据库   | busy_timeout 等待，HTTP busy→503；后台 degraded 后重试读取/失败发布；没有发现单独通用熔断器。[session.py](../../backend/app/infrastructure/database/session.py):L31；[scheduler.py](../../backend/app/execution/scheduler.py):L80                                      |

SDK 自身可能有版本内协议处理；这里仅陈述项目配置，不能将客户端自动行为扩大成平台的通用重试保证。

## 5. 可观测性

已确认 Python logging 记录接受、启动、发布、扫描器/维护错误及资源 ID；RunAction 保存模型/工具步骤与安全详情，API/SSE 提供用户观察。[bootstrap.py](../../backend/app/bootstrap.py):L50；[coordinator.py](../../backend/app/execution/coordinator.py):L82；[store.py](../../backend/app/execution/store.py):L178；[health.py](../../backend/app/api/routes/health.py)。

未在已调查的应用装配、依赖清单与 deploy 配置发现主动配置的指标 exporter、分布式 tracing、集中日志管道或服务网格。锁文件出现 telemetry 相关传递依赖不代表项目启用了它。`[TODO]` 外部网关、日志采集、监控告警和真实运行指标。

## 6. 证据

- [网络适配](../../backend/app/tools/adapters/mcp.py)、[stdio 生命周期](../../backend/app/tools/adapters/stdio.py)、[沙箱 provider](../../backend/app/sandboxes/provider.py)。
- [模型工厂](../../backend/app/llm/factory.py)、[GitHub OAuth](../../backend/app/auth/github.py)、[凭据仓](../../backend/app/infrastructure/credentials.py)。
- [数据库](../../backend/app/infrastructure/database/session.py)、[文件](../../backend/app/files/service.py)、[部署示例](../../deploy/opensandbox/)。

# 后端设计

后端是按功能所有权组织的模块化单体，同一进程内使用 SQLite 短事务和官方 SDK 执行存档。对话与考核拥有业务受理、发布与评分；执行宿主管理 Run、动作、预算和生命周期；Agent 适配模型工具循环；资源模块维护可复用的组织配置和外部资源。

## 当前目录与文件归属

以下列出全部业务 Python 文件，省略不含业务逻辑的 `__init__.py`。模块说明、图和数据留在所属目录；考核固定题库位于 `applications/evaluations/data/`。旧文件与最终文件的完整对应、保留数据摘要、具名例外和回调时机见[架构契约](../../backend/tests/architecture_contract.json)。

```text
backend/
├── app/
│   ├── config.py, main.py
│   ├── bootstrap/
│   │   └── app.py, lifecycle.py, model_registry.py, services.py
│   ├── api/
│   │   ├── config.py, dependencies.py, errors.py, failure_boundary.py, frontend_delivery.py
│   │   ├── oauth_logging.py, rate_limit.py, router.py, security.py, streaming.py
│   │   └── routes/
│   │       ├── auth.py, capabilities.py, configuration_summary.py, conversations.py, employees.py
│   │       ├── evaluations.py, files.py, health.py, knowledge.py, mcp.py, mcp_oauth.py
│   │       └── model_connections.py, organization_rules.py, public.py, skills.py
│   ├── cli/
│   │   └── auth.py, environments.py, verify_environment.py
│   ├── applications/
│   │   ├── configuration_summary.py
│   │   ├── conversations/
│   │   │   ├── acceptance.py, access.py, commands.py, context.py, files.py, models.py
│   │   │   └── projections.py, queries.py, references.py, schemas.py, writes.py
│   │   └── evaluations/
│   │       ├── acceptance.py, benchmark.py, bfcl_checker.py, commands.py, models.py
│   │       └── progression.py, queries.py, references.py, schemas.py, worker.py
│   ├── runtime/
│   │   ├── assembly.py, usage.py
│   │   ├── agent/
│   │   │   ├── checkpoints.py, config.py, engine.py, errors.py, mcp_tools.py, model_calls.py
│   │   │   └── prompts.py, skills.py, streaming.py, tool_calls.py, tool_discovery.py
│   │   ├── contracts/
│   │   │   └── agent.py, content.py, runs.py, tools.py
│   │   ├── execution/
│   │   │   ├── authorization.py, config.py, context.py, errors.py, evidence.py
│   │   │   ├── evidence_models.py, knowledge.py, knowledge_evidence.py, metrics.py, models.py
│   │   │   ├── preparation.py, queries.py, references.py, runner.py, scheduler.py, service.py
│   │   │   └── snapshot.py, snapshot_rules.py, store.py, tool_results.py
│   │   └── tools/
│   │       ├── bindings.py, knowledge.py, result_files.py, results.py, sandbox_backend.py
│   │       └── tool_search.py, workspace.py
│   ├── resources/
│   │   ├── capability_catalog/
│   │   │   └── queries.py, schemas.py
│   │   ├── employees/
│   │   │   ├── access.py, assembly.py, knowledge.py, models.py, references.py, schemas.py
│   │   │   └── service.py, tool_grants.py
│   │   ├── environments/
│   │   │   ├── config.py, contracts.py, legacy_models.py, models.py, open_sandbox.py, policy.py
│   │   │   └── service.py
│   │   ├── files/
│   │   │   └── cleanup.py, config.py, contracts.py, models.py, schemas.py, service.py, storage.py
│   │   ├── knowledge/
│   │   │   ├── access.py, chunking.py, contracts.py, documents.py, lexical.py, libraries.py
│   │   │   ├── loading.py, models.py, processing.py, references.py, retrieval.py, samples.py
│   │   │   └── schemas.py, search.py, sources.py, vector_store.py, vectors.py, worker.py
│   │   ├── mcp/
│   │   │   ├── access.py, catalogs.py, config.py, connections.py, contracts.py, definitions.py
│   │   │   ├── invocation.py, models.py, network.py, oauth.py, policy.py, schemas.py, tokens.py
│   │   │   └── adapters/
│   │   │       └── http.py, oauth_storage.py, stdio.py, stdio_runner.py, transport.py
│   │   ├── model_connections/
│   │   │   └── models.py, presets.py, references.py, resolution.py, schemas.py, service.py
│   │   ├── organization_rules/
│   │   │   └── models.py, schemas.py, service.py
│   │   └── skills/
│   │       ├── config.py, contracts.py, definitions.py, library.py, models.py, packages.py
│   │       └── parameters.py, schemas.py, service.py, storage.py
│   ├── auth/
│   │   ├── actor.py, config.py, github.py, models.py, permissions.py, service.py
│   │   └── work_authorizations.py
│   ├── infrastructure/
│   │   ├── concurrency.py, credentials.py, observability.py, settings.py
│   │   ├── database/
│   │   │   └── base.py, errors.py, fields.py, identifiers.py, session.py, transactions.py
│   │   └── llm/
│   │       └── config.py, embeddings.py, errors.py, factory.py, probe.py, reasoning.py, usage.py
│   └── common/
│       └── errors.py, public_errors.py, schemas.py, usage.py, values.py
├── migrations/                  # 保留全部迁移历史，注册入口指向 bootstrap/model_registry
├── tests/
│   ├── architecture_contract.json
│   ├── test_architecture_contract.py
│   ├── test_architecture_substitution.py
│   ├── test_architecture_recovery.py
│   ├── fixtures/backend_boundary_v8.tar.gz
│   └── 其他业务、事务、故障与恢复测试
├── datasets/                    # 保留全部样本与来源说明
├── experiments/                 # 保留实验并更新引用
├── pyproject.toml
└── uv.lock
```

## 依赖与公开能力

目录表达所有权，不要求一次请求经过每一层。正常模块依赖必须无环；`bootstrap` 与 `runtime/assembly.py` 只在启动时绑定实现，运行中的业务代码不能返回装配入口寻找服务。

| 调用方 | 可以使用 | 边界 |
| --- | --- | --- |
| API、CLI | 应用与资源的公开操作、auth、公开状态值 | 不直接操作业务 ORM、Store 或模型 SDK |
| applications | 执行公共事务操作、资源公开能力、auth、基础机制 | 不调用 Agent 引擎，不持有外部模块的可变 ORM |
| runtime/execution | 普通运行契约、资源公开能力、auth、基础机制 | 不依赖业务应用、Agent 或工具具体实现 |
| runtime/agent | 普通契约、工具适配、模型客户端、SDK 存档 | 不访问业务数据库、HTTP、正式回复发布或评分 |
| runtime/tools | 受限宿主能力、普通资源契约和 SDK | 不调度 Run，不独立维护授权或资源所有权 |
| resources/employees | 技能、模型连接、MCP、知识、环境和组织规则的配置事实 | 来源资源不反过来调用员工流程 |
| resources/knowledge | 文件与模型连接公开能力 | 不认识 Run、员工实现或模型工具反馈 |
| capability_catalog | 技能与 MCP 只读概要 | 不管理资源或推进执行 |
| auth、infrastructure、common | 必要的基础机制和普通值 | 不反向获取业务服务；common 不保存服务实例 |

跨表只读投影与环境历史多态映射按文件声明，不能豁免整个目录。投影禁止写入、提交或回滚。数据库元数据聚合只在 `bootstrap/model_registry.py`，数据库机制不导入业务模型。绝对、相对、包聚合、类型分支、局部和字面量动态导入均受[架构测试](../../backend/tests/test_architecture_contract.py)检查；普通运行契约另做独立进程导入验证。

## 状态所有权与事务

| 状态或流程 | 协调者与写入所有者 |
| --- | --- |
| 对话受理、消息与绑定 | conversations/commands、writes |
| 正式回复、附件与接纳重试 | conversations/acceptance |
| 考核创建、取消 | evaluations/commands |
| 逐题推进、答卷接纳与评分 | evaluations/progression、acceptance；worker 仅触发推进 |
| 排队、在途任务、进程锁与恢复扫描 | RunWorker |
| 单次准备、看护、使用者退出与收尾 | RunTask，准备算法在 preparation |
| Run、动作、预算、执行证据 | 执行公共事务操作及 Store |
| 模型与工具循环、SDK checkpoint | 官方 SDK 与 Agent 适配 |
| 资料、索引、连接、文件、沙箱 | 各自资源模块 |

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

当前宿主采用单进程锁，不支持多 worker 或跨主机领取。完整机制见[执行说明](../../backend/app/runtime/execution/README.md)，工程要求见[后端手册](../engineering/backend.md)，部署与恢复见[运维指南](../guides/backend-operations.md)。

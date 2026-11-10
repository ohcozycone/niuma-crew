# 执行子系统

执行子系统把一次输入变成可跟踪、可取消、能恢复且有可靠成果的工作。例如员工读取资料生成报告，页面断开后工作仍由后台负责；完整成果先保存为 Run 的结果，再由对话模块保存为正式回复。

## 先分清四个对象

| 对象                   | 负责保存什么                           | 生命周期                                       |
| ---------------------- | -------------------------------------- | ---------------------------------------------- |
| Conversation / Message | 用户能重新打开查看的对话和正式消息     | 业务历史，不依赖模型启动或 checkpoint          |
| Thread                 | SDK 连续交流的状态范围                 | 同一对话多次提问共用稳定线程；独立任务独享线程 |
| Run                    | 一次被接受输入的处理、动作、预算和成果 | 每次提问独立创建，失败重试也是新 Run           |
| Checkpoint             | SDK 在某一步的消息、图状态和待执行位置 | 同一线程有多个存档，通过 Run 归属定位恢复点    |

Run 新建不等于线程新建。一份 Run 内可以多次调用模型和工具。两套数据库通过线程、Run 和存档引用关联，不能拿页面历史代替未完成工作的恢复状态。

同步工作持有会话资源或执行事务时，经 run_sync 等待其真正结束后才处理取消和释放。测试中的假执行器不会自动生成 SDK 存档；验证续聊必须实际执行 SDK，缺少成功基点时明确拒绝。最终正文规范化后再次检查非空及字节预算，校验失败保存为执行失败，真实存储错误仍按持久化故障处理。

## 执行职责与装配

Run 和 RunAction 是数据库记录：Run 保存整次工作的输入、预算、状态与成果；RunAction 保存该 Run 内模型、工具、技能及来源检查的关键动作。它们通过 run_id 一对多关联，记录本身不驱动执行。

RunWorker 是随服务存在的协调组件，负责进程锁、恢复扫描、队列轮询、在途任务、停止等待和持久化故障重试。每条待执行记录对应一份 RunTask；Task.execute 负责加载、领取、准备、运行 SDK、看护、资源释放和成果提交。Task通过 preparation 创建RunContext，由后者实现SDK所见的AgentContext能力协议；平台资源和事务留在execution，SDK组合位于平级agent模块。

runtime/assembly.py 构建 RunService、RunTask 工厂与 RunWorker；bootstrap 只传共享服务、连接完成通知并管理 Worker 的启动和关闭。RunService 接收模型连接与运行知识授权能力，装配不再创建单独的 ExecutionAuthorization 或注入 authorize 回调。Worker 创建 Task 时提供统一完成回调，Task 决定何时、以什么结果完成；回调通过 RunService.complete 保存终态并通知独立接纳，失败进入协调层的持久化重试。该回调不运行模型、准备资源或看护单次执行。

## 代码入口与职责

| 入口                                                                                               | 所有权                                                      |
| -------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| [assembly.py](../assembly.py)                                                                         | 组合服务、Worker、Task工厂与Agent引擎                       |
| [service.py](service.py)、[authorization.py](authorization.py)                                     | 受理、当前授权、取消与可靠提交成果                          |
| [snapshot.py](snapshot.py)、[contracts.py](../contracts/runs.py)                                           | 捕获配置与普通执行输入/终态契约                             |
| [scheduler.py](scheduler.py)                                                                       | RunWorker持有进程锁、恢复扫描、调度和完成故障重试           |
| [runner.py](runner.py)                                                                             | RunTask拥有一次执行、看护、资源和最终完成                   |
| [context.py](context.py)                                                                           | RunContext实现受限能力、动作与进度报告，不把数据库暴露给SDK |
| [store.py](store.py)、[tool_results.py](tool_results.py)                                           | 持久动作、预算、恢复与本Run工具结果保存/分页读取            |
| [agent/engine.py](../agent/engine.py)                                                              | 官方模型/工具循环及中间件装配                               |
| [agent/contracts.py](../contracts/agent.py)                                                        | 引擎普通输入、输出和AgentContext协议                        |
| [agent/model_calls.py](../agent/model_calls.py)、[tool_calls.py](../agent/tool_calls.py)           | SDK模型与工具适配，通过受限接口申请动作                     |
| [agent/skills.py](../agent/skills.py)、[builtin_tools/workspace.py](../tools/workspace.py) | 技能发现/激活与受控虚拟/沙箱文件后端                        |
| [agent/checkpoints.py](../agent/checkpoints.py)、[streaming.py](../agent/streaming.py)             | SDK存档、归属核对及流式内容解释                             |
| [agent/config.py](../agent/config.py)、[prompts.py](../agent/prompts.py)                           | Agent摘要配置和固定指令                                     |

本说明统一解释两侧协作。execution 拥有 Run 的事实、事务和资源责任；agent 通过 [contracts.py](../contracts/agent.py) 的普通接口请求能力，不导入 execution 或业务 ORM。Context 不是新的流程调度层，也不另存一套授权或预算；snapshot 保存提交时的依据，authorization 组合当前规则，RunStore 在同一事务复核授权、预占预算并登记动作。

执行侧其余文件：[config.py](config.py) 定义容量、持久预算和看护参数；[models.py](models.py) 定义 Run/动作；[queries.py](queries.py) 提供受限诊断查询；[evidence.py](evidence.py) 构造脱敏诊断文档；[errors.py](errors.py) 定义技术错误分类及终态处理。Agent 引擎异常归 [agent/errors.py](../agent/errors.py)，模型协议与用量解释归 [llm/usage.py](../../infrastructure/llm/usage.py)，HTTP 订阅设置归 [api/config.py](../../api/config.py)。共用取消等待由 [infrastructure/concurrency.py](../../infrastructure/concurrency.py) 维护。

`tool_results.py` 处理本 Run 结果归属、原样存档及旧字符游标兼容，不再生成固定首预览，也不识别供应商私有字段。`builtin_tools/result_files.py` 将官方长结果路径关联到已有冻结文本，别名随原动作保存；工具门在 SDK 处理之后保存最终反馈。每次真实工具调用只提交一份请求证据，实际参数由工具适配器提供；拒绝路径独立记录，证据故障不覆盖原始动作结果。

## 固定指令与按条件注入

agent/prompts.py 保存身份、公司/员工关系、通用工具范围、服务说明与技能指令。知识、结果读取和发现工具的描述归各 builtin_tools 文件；这些文件只适配模型入口，资料、文件和环境仍由原领域维护。员工指令、技能正文、公司规则及服务方文案仍从原配置读取；SDK 默认摘要模板仍引用 SDK 定义。

snapshot 在受理事务中生成基础指令并捕获组织资源；引擎准备时从冻结目录建立内存索引，每次模型请求只追加实际可见工具的名称映射和服务说明。skills 判断是否创建技能中间件、准备技能文件和固定加载清单，并交给 SDK 填充技能目录占位符；engine 选择新轮或恢复输入，model_calls 按既有条件追加资料说明；builtin_tools/results.py 装配本轮结果读取。固定文案的归属不决定是否启用，运行模块继续决定启用条件和注入位置。

## 内部工具与按需发现

[builtin_tools](../tools) 提供官方文件/执行、知识、结果读取和 search_tools 的模型入口；[agent/mcp_tools.py](../agent/mcp_tools.py) 适配外部 MCP 的调用与反馈。构造时绑定各自的结果转换函数：MCP 保存通用原始结果并保留多模态，工作区解释命令退出码，内部工具还原普通 ToolOutcome。tool_calls.py 只组织 begin/guard/complete 和框架反馈，不解析供应商或能力业务字段。

[tool_discovery.py](../agent/tool_discovery.py) 只索引本轮已确认且获准的冻结工具；SQLite 内存 FTS5、中文分词和英文词项处理不查询账号或知识范围，不维护另一份业务目录。工具名多词匹配优先，其余按 BM25 排序。索引在本次引擎调用的准备阶段创建，所有退出路径关闭；Runner 仍等待引擎退出再结束资源责任。

初始暴露基础文件、条件 execute、条件知识、结果读取与 search_tools，MCP 延迟展开。搜索 Outcome 先持久化，再由官方 Command 合并 discovered_tool_ids；缓存重建同一状态增量。并行发现取并集，新 Run 使用 Overwrite 清空，同 Run 恢复只接受同版本可信存档。

发现集合不是调用许可。每次模型请求通过完整上下文检查后，在原子 start_model 事务保存 catalog_hash/exposed_tool_ids。返回的调用关联父模型动作；begin_tool 与逐次 guard 检查其真实可见性、当前授权、参数及预算。同一响应里的搜索不能放行猜名调用。动作仍使用 tool_call，通过 category=tool_discovery 展示发现用途，原始 query 仅进入受限结果/证据，不进入普通摘要。

## 一次工作怎么走

1. ConversationService 在同一事务查幂等请求、创建或检查对话、准备用户输入，并调用 RunService.submit；后者生成 Run ID，业务助手消息复用它，消息、Run、关联一起提交，Run 初始为 queued。
2. Worker 按默认 0.5 秒间隔查询待执行记录，通过在途任务表去重，并直接调度 RunTask.execute。Task 加载 Run，检查剩余总时限和授权，通过 Store.claim 的短事务写入 running 与开始时间。
3. Task 准备连接、可信恢复点、工具、沙箱和 AgentRequest，并行运行 SDK 与看护。模型通过 start_model，工具通过 begin_tool，在短事务内核对许可、预占预算和记录动作；工具结果保存成功后才返回模型。
4. Context 缓冲普通 ContentUpdate，Task 看护定期调用其保存入口。SDK 读回完整存档，核对本 Run 完成标记及输出，返回 AgentOutput。SSE 只观察已提交状态，断线不取消运行。
5. Task 等待执行、看护及资源释放后提交 Completion；RunService.complete 复核成果，通过 Store.finish 原子写入正文、结构化成果、最终状态和结束时间。成功为 succeeded，失败为 failed，错误原因另存 error_code。
6. 完成事务后唤醒 ConversationAcceptance，它独立保存正式回复。通知只是提示，持久扫描和退避仍负责补漏；接纳失败不会重新执行模型。

取消会等待已经启动的准备、数据库及清理工作结束；清理失败不覆盖原停机取消，符合恢复资格的 Run 保留待恢复状态。Worker 停止时等待所有在途 Task 结束后才释放进程锁。整个 Run 不使用跨模型调用的长事务，执行失败通过新的短事务保存，不回滚已提交的动作。

Conversation、用户 Message 和 Run 从同一持久序列分配固定 12 位数字，数据库用整数，API 用字符串。助手 Message 不另发号：`Run.id == Message.id == response_id`。失败重试沿用原用户输入，另建 Run 与同 ID 的助手消息。线程使用稳定的 `conversation:v8:<id>`，幂等键仍是客户端生成的 UUID。

文件工具的定义与装配归 [builtin_tools/workspace.py](../tools/workspace.py)，来自官方 FilesystemMiddleware；[snapshot.py](snapshot.py) 固定后端、路径范围与工具定义，基础操作不查询员工插件许可。[workspace.py](../tools/workspace.py) 将官方工具路由到虚拟状态或本轮唯一沙箱；[environments](../../resources/environments/README.md) 持有远端生命周期，平台文件服务保存正式产物。

## 连续对话与重启恢复

正常下一轮只提交本次输入，通过 `base_run_id/base_checkpoint_id` 指向同一线程中最近已成功接纳的 Run。运行时从这个明确起点由官方 reducer 延续消息、配对工具记录、技能 pin 和 SDK 摘要，清空本轮动作用量、文件和技能临时状态，重新绑定当前资源。失败分支不作为新一轮起点；历史工具消息或技能正文不授予本轮权限。

知识资料内容、已有技能/工具或关键配置变化时，旧上下文可能携带已失效资料，当前实现保守重置执行记忆并提示重新检索；单纯新增技能或 MCP 保留普通记忆，下一轮重新捕获并发现新能力。业务消息仍完整保留。工具许可和模型参数每轮重新捕获，不因旧消息出现某项能力就授予调用权。

后端重启后，以同一 Run 的线程及 metadata 查到最新可信存档；创建同样的 SDK 程序，再以空输入继续待执行节点。SDK 存储先于业务引用提交时，也能按本 Run 归属找到已落盘的新点。正在生成的网络请求不能从最后一个字续传，可能重新发起；在途动作先标未知，已用预算和总时限不重置。完整存档已完成时只补结果提交。

恢复资格读取持久快照：普通聊天和虚拟文件只读可以按可信存档恢复；虚拟文件首次修改开始前，动作事务标记本轮不可自动恢复，沙箱和 MCP 工作同样不重放。缺失或不匹配的存档明确中断，不能从失败线程最新点续跑，也不能默默从页面历史重做外部动作。

## 框架负责什么，平台保留什么

| 能力                                 | 实现                                                                                 |
| ------------------------------------ | ------------------------------------------------------------------------------------ |
| 模型与工具循环                       | 官方 create_agent                                                                    |
| 工具调用上下文传递                   | 官方 ToolRuntime / ToolCallRequest.runtime；host 与 run_id 由调用方通过 context 传入 |
| 消息状态与 checkpoint                | 官方 SQLite Saver；平台只接数据库路径、归属和通知                                    |
| 摘要与近期消息保留                   | 官方 SummarizationMiddleware；阈值在 AgentConfig，摘要经现有受管模型门执行           |
| Token 采集与已知值合并               | usage_metadata、runtime/usage 的纯累计；未报告或中断用量保持未知                             |
| 跨重启硬预算、权限、取消、成果和接纳 | 平台持久动作账本；模型限次统一覆盖普通回答、摘要与未知尝试，不重复装配 SDK 模型限次  |

摘要会消耗一次模型预算并计入本 Run 用量；摘要不是对话正式回复。未开启通用模型/工具自动重试。当前预算包含次数、输出上限和时限，不是按用户金额扣费系统。历史 checkpoint 仍由官方存储器保留；摘要缩短模型上下文，不等于压缩磁盘文件。

剩余模型次数由持久账本只读查询；最后一次请求通过官方 ModelRequest.override 移除工具并要求基于已有证据收尾，摘要适配只在额度足够时调用官方 abefore_model，沿用原节点名保持检查点兼容。不增加模型额度，不维护第二份次数计数。可修正参数错误保存为失败反馈；授权、存储和未知执行错误继续停止后续动作。

## 并发和维护

无全平台 Run 并发数字上限；队列容量、单用户未结束容量、同一对话/线程单活动 Run、动作预算和时限仍生效。宿主是单进程，使用 SQLite 和文件锁，不支持多 worker 或跨主机租约。

[运行契约](../../../../docs/reference/runtime.md)维护外部语义；[迁移和操作](../../../../docs/guides/backend-operations.md)说明部署。核心回归见 [线程测试](../../../tests/test_execution_threads.py)、[进程恢复测试](../../../tests/test_checkpoint_runtime.py)、[边界测试](../../../tests/test_runtime_boundaries.py)。

## 执行证据与关联查询

`evidence.py` 维护脱敏文档；`queries.py` 只读既有执行、动作与私有文件证据。RunAction 的 request_file_id / response_file_id 指向 StoredFile，不新增 tracing 表。模型请求在 HTTP JSON 边界采集，SDK 响应与工具反馈通过RunContext 保存；拒绝申请标为未执行，恢复载荷格式不变。采集失败不改变原执行结果。业务适配先核对对话/考题关联，完整输入另查配置权限。完整[契约](../../../../docs/reference/runtime.md)。

查询为当前动作页、失败动作及所选动作提取 metrics 数值摘要，用于预算对照与阶段消耗；同次请求复用证据读取。输入受限或文件超过内联预览上限时不从正文推断上限或用量，已有安全动作用量仍可使用。摘要触发依据不从当前设置反推历史，也不为展示重新运行模型。

## 失败事实与公开文案

Agent 的 RuntimeFailure 与执行侧 ExecutionFailure 分别表达本层失败，公共 CodedFailure 只携带 code、kind 和可选部分输出。RunTask 按受控错误及执行规则选择终态，不读取文案表；存储故障仍由调度器协调，不能转成业务拒绝。

Run 保存原错误码；动作继续保存自身类型、动作键、状态及错误码。工具参数错误、未连接账号、命令非零退出、上游失败和未知结果分别记录。查询按稳定码定义提供 error_kind，历史未登记码保留原值、类型返回 null；不凭最近失败动作猜测 Run 的失败位置。无需改表或重建历史。

应用层 [public_errors.py](../../common/public_errors.py) 提供默认公开说明；API 在输出业务拒绝时映射，对话读取另行组合部分输出提示，考核由自己的应用界面展示。更改文案不改变失败事实或重试资格。完整外部契约见[失败说明](../../../../docs/reference/failures.md#执行失败事实与应用文案)。


## 知识范围与运行证据

`knowledge.KnowledgeAccess` 检查真实发起会话、当前员工修订、范围、时限和已登记来源；`guard_library` 是同事务只读复核，不伪造库所有者 Actor，也不返回资源 ORM。`RunKnowledgeSearch` 组合库概要、单库检索与证据登记，按排名融合候选，受全局 Top-K 和约18KiB结果预算约束；待处理原件不送模，上游故障明确失败。

`knowledge_evidence` 持有 Run 证据表及历史关联；资源 `sources` 按普通来源值核验当前文档版本和完整片段。命中先在执行事务登记，再交给工具适配生成反馈。补读仅允许本轮已登记来源；即使文档版本不变，重切后的完整片段不同仍使旧证据失效。

成果事务调用 `finalize_answer`，只对已登记编号和规范路径逐字匹配的链接恢复遗漏根斜杠，并拒绝未经取得或路径不符的来源。原始动作保留，正式回复保存规范化正文；这不证明结论在语义上得到原文支持。

`capture_history` 只接受宿主选定的成功对话回复，核对同员工、同拥有者、同线程、原冻结库范围、当前范围和完整片段。旧个人快照继续核对原用户等于拥有者及发起者。受理事务重新登记本轮证据，送模副本移除失效引用，已交付历史保持原样；重复追问保留已核验的根来源地址。

历史阅读按 Run 读取资格核验，允许员工卸载后继续读仍有效的已交付来源；在途查询必须继续满足当前装配。相关负例见[来源访问测试](../../../tests/test_knowledge_evidence_access.py)和[历史上下文测试](../../../tests/test_employee_knowledge_context.py)。

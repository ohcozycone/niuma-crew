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

RunWorker 是随服务存在的协调组件，负责进程锁、恢复扫描、队列轮询、在途任务、停止等待和持久化故障重试。每条待执行记录对应一份 RunTask；Task.execute 负责加载、领取、准备、运行 SDK、看护、资源释放和成果提交。Task 同时实现 SDK 所见的 AgentContext 能力协议，不再保留独立 RunContext 对象。

execution/assembly.py 构建 RunService、RunTask 工厂与 RunWorker；bootstrap 只传共享服务、连接完成通知并管理 Worker 的启动和关闭。RunService 直接接收模型连接与知识服务，装配不再创建单独的 ExecutionAuthorization 或注入 authorize 回调。Worker 创建 Task 时提供统一完成回调，Task 决定何时、以什么结果完成；回调通过 RunService.complete 保存终态并通知独立接纳，失败进入协调层的持久化重试。该回调不运行模型、准备资源或看护单次执行。

## 完整目录与文件职责

```text
execution/
├── __init__.py                 # 保留包标记，不建立转发入口
├── README.md                   # 说明执行流程、文件归属与运行边界
├── assembly.py                 # 构建 Service、Worker 与 Task 工厂
├── config.py                   # 定义和校验预算、容量、时限及观察参数
├── prompts.py                  # 集中固定模型指令、模板和纯文本渲染
├── snapshot.py                 # 捕获员工、工具、技能、知识与文件的本轮快照
├── contracts.py                # 定义普通请求、输出、快照与受限能力协议
├── evidence.py                # 保存和读取私有模型调用证据
├── queries.py                 # 检查执行详情与证据的读取权限
├── errors.py                   # 定义执行异常、公开消息与终态分类
├── models.py                   # 定义 Run、RunAction 的持久字段与约束
├── service.py                  # 受理、组合当前授权、取消并原子提交成果和终态
├── store.py                    # 查询队列，原子保存领取、动作、预算和恢复事实
└── runtime/
    ├── __init__.py             # 保留包标记
    ├── README.md               # 说明运行代码的协作与 SDK 边界
    ├── worker.py               # 轮询、调度、在途管理、故障重试与服务启停
    ├── task.py                 # 完成一次 Run 的执行及资源生命周期
    ├── agent.py                # 组装并执行 SDK 模型与工具循环
    ├── model_calls.py          # 处理模型和摘要调用的预算、计账与输出限制
    ├── tool_calls.py           # 适配 SDK 工具并完成许可、缓存、校验和结果提交
    ├── tool_results.py         # 保存、分页读取结果并核验来源和实际读取范围
    ├── skills.py               # 准备技能文件，核验发现、读取和激活
    ├── streaming.py            # 合并 SDK 消息片段，生成普通进度更新
    ├── workspace.py            # 统一受控路径、虚拟/沙箱后端、命令及成果收集
    ├── checkpoints.py          # 保存 SDK 状态，核验续接、恢复与完整成果
    ├── concurrency.py          # 取消时等待已启动线程结束，维持资源与事务顺序
```

snapshot.py 负责配置捕获，prompts.py 统一固定模板和纯文本渲染；RunService.authorize 组合当前身份、模型、技能、工具及知识授权，复用调用方事务或建立独立短事务。runtime 统一运行期控制、结果处理与 SDK 实现；bindings 包已删除，不增加新的分类目录。模型和工具各有独立 SDK 协议与足够复杂的适配逻辑，分别维护；工具的薄执行包装已并回 tool_calls.py。ToolResults 在同一文件处理保存、预览、分页和网页读取核验，解析与 URL 辅助函数私有化；工作区的沙箱后端作为内部类与路径路由同文件维护，仍按需申请沙箱。Task 的进度缓冲是私有辅助类，留在 task.py；concurrency 被多个运行与结果处理入口共用，继续独立维护。

MCP 连接归 [MCP 模块](../mcp/README.md)，环境申请与回收归 environments，持久字节归 files。runtime 中 SDK 文件只通过 AgentContext 使用获准能力，不持有 ORM、Store 或具体 Task；Worker 和 Task 按各自职责访问平台服务。models/store 不反向依赖 snapshot、prompts 或 runtime。snapshot 不导入 runtime 或 SDK；prompts 仅处理普通数据与文本，不导入业务模型、数据库或 SDK。

## 固定指令与按条件注入

prompts.py 集中项目自有固定指令：身份与公司/员工关系、工具范围、知识与服务说明、技能目录模板、技能正文固定说明、本轮资料/附件的说明和结果读取工具描述。员工指令、技能正文、公司规则及服务方文案仍从原配置读取；SDK 默认摘要模板仍引用 SDK 定义。

snapshot 在捕获时生成基础指令，Task 在执行准备时追加工具与服务说明。skills 判断是否创建技能中间件、准备技能文件和固定加载清单，并交给 SDK 填充技能目录占位符；checkpoints 选择本轮输入及资料，按既有条件追加共享说明；tool_calls 注册结果读取工具时引用共享描述。固定文案的归属不决定是否启用，运行模块继续决定启用条件和注入位置。

## 一次工作怎么走

1. ConversationService 在同一事务查幂等请求、创建或检查对话、准备用户输入，并调用 RunService.submit；后者生成 Run ID，业务助手消息复用它，消息、Run、关联一起提交，Run 初始为 queued。
2. Worker 按默认 0.5 秒间隔查询待执行记录，通过在途任务表去重，并直接调度 RunTask.execute。Task 加载 Run，检查剩余总时限和授权，通过 Store.claim 的短事务写入 running 与开始时间。
3. Task 准备连接、可信恢复点、工具、沙箱和 AgentRequest，并行运行 SDK 与看护。模型通过 start_model，工具通过 begin_tool，在短事务内核对许可、预占预算和记录动作；工具结果保存成功后才返回模型。
4. Task 缓冲普通 ContentUpdate，看护定期保存。SDK 读回完整存档，核对本 Run 完成标记及输出，返回 AgentOutput。SSE 只观察已提交状态，断线不取消运行。
5. Task 等待执行、看护及资源释放后提交 Completion；RunService.complete 复核成果，通过 Store.finish 原子写入正文、结构化成果、最终状态和结束时间。成功为 succeeded，失败为 failed，错误原因另存 error_code。
6. 完成事务后唤醒 ConversationAcceptance，它独立保存正式回复。通知只是提示，持久扫描和退避仍负责补漏；接纳失败不会重新执行模型。

取消会等待已经启动的准备、数据库及清理工作结束；清理失败不覆盖原停机取消，符合恢复资格的 Run 保留待恢复状态。Worker 停止时等待所有在途 Task 结束后才释放进程锁。整个 Run 不使用跨模型调用的长事务，执行失败通过新的短事务保存，不回滚已提交的动作。

Conversation、用户 Message 和 Run 从同一持久序列分配固定 12 位数字，数据库用整数，API 用字符串。助手 Message 不另发号：`Run.id == Message.id == response_id`。失败重试沿用原用户输入，另建 Run 与同 ID 的助手消息。线程使用稳定的 `conversation:<id>`，幂等键仍是客户端生成的 UUID。

## 连续对话与重启恢复

正常下一轮只提交本次输入，通过 `base_run_id/base_checkpoint_id` 指向同一线程中最近已成功接纳的 Run。运行时从这个明确起点由官方 reducer 延续消息、配对工具记录、技能 pin 和 SDK 摘要，清空本轮动作用量、文件和技能临时状态，重新绑定当前资源。失败分支不作为新一轮起点；历史工具消息或技能正文不授予本轮权限。

知识资料内容、已有技能/工具或关键配置变化时，旧上下文可能携带已失效资料，当前实现保守重置执行记忆并提示重新检索；单纯新增技能或 MCP 保留普通记忆，下一轮重新捕获并发现新能力。业务消息仍完整保留。工具许可和模型参数每轮重新捕获，不因旧消息出现某项能力就授予调用权。

后端重启后，以同一 Run 的线程及 metadata 查到最新可信存档；创建同样的 SDK 程序，再以空输入继续待执行节点。SDK 存储先于业务引用提交时，也能按本 Run 归属找到已落盘的新点。正在生成的网络请求不能从最后一个字续传，可能重新发起；在途动作先标未知，已用预算和总时限不重置。完整存档已完成时只补结果提交。

恢复资格仍受原快照约束：原生写入、沙箱和不支持安全恢复的 MCP 工作中断后不自动重放。缺失或不匹配的存档明确中断，不能从失败线程最新点续跑，也不能默默从页面历史重做外部动作。

## 框架负责什么，平台保留什么

| 能力                                 | 实现                                                                                 |
| ------------------------------------ | ------------------------------------------------------------------------------------ |
| 模型与工具循环                       | 官方 create_agent                                                                    |
| 工具调用上下文传递                   | 官方 ToolRuntime / ToolCallRequest.runtime；host 与 run_id 由调用方通过 context 传入 |
| 消息状态与 checkpoint                | 官方 SQLite Saver；平台只接数据库路径、归属和通知                                    |
| 摘要与近期消息保留                   | 官方 SummarizationMiddleware；阈值在 RuntimeConfig，摘要经现有受管模型门执行         |
| Token 采集与已知值合并               | usage_metadata、官方 add_usage；未报告或中断用量保持未知                             |
| 单次图调用的模型次数防线             | 官方 ModelCallLimitMiddleware                                                        |
| 跨重启硬预算、权限、取消、成果和接纳 | 平台现有持久事实；不以 SDK 内存计数取代原子动作账本                                  |

摘要会消耗一次模型预算并计入本 Run 用量；摘要不是对话正式回复。未开启通用模型/工具自动重试。当前预算包含次数、输出上限和时限，不是按用户金额扣费系统。历史 checkpoint 仍由官方存储器保留；摘要缩短模型上下文，不等于压缩磁盘文件。

## 并发和维护

无全平台 Run 并发数字上限；队列容量、单用户未结束容量、同一对话/线程单活动 Run、动作预算和时限仍生效。宿主是单进程，使用 SQLite 和文件锁，不支持多 worker 或跨主机租约。

[运行契约](../../../docs/reference/runtime.md)维护外部语义；[迁移和操作](../../../docs/guides/backend-operations.md)说明部署。核心回归见 [线程测试](../../tests/test_execution_threads.py)、[进程恢复测试](../../tests/test_checkpoint_runtime.py)、[边界测试](../../tests/test_runtime_boundaries.py)。

## 执行证据与关联查询

`evidence.py` 维护脱敏文档；`queries.py` 只读既有执行、动作与私有文件证据。RunAction 的 request_file_id / response_file_id 指向 StoredFile，不新增 tracing 表。模型请求在 HTTP JSON 边界采集，SDK 响应与工具反馈通过原 AgentContext 保存；拒绝申请标为未执行，恢复载荷格式不变。采集失败不改变原执行结果。业务适配先核对对话/考题关联，完整输入另查配置权限。完整[契约](../../../docs/reference/execution-evidence.md)。

查询为当前动作页、失败动作及所选动作提取 metrics 数值摘要，用于预算对照与阶段消耗；同次请求复用证据读取。输入受限或文件超过内联预览上限时不从正文推断上限或用量，已有安全动作用量仍可使用。摘要触发依据不从当前设置反推历史，也不为展示重新运行模型。

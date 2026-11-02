# Agent 与执行宿主

一次请求被接受后，应用先登记运行，再由执行宿主调用 Agent。Agent 决定如何使用当前获准的方法和模型；宿主负责这次处理是否仍允许运行以及过程能否可靠保存。

## 先区分对话、运行与动作

用户与一位员工持续交流形成一段对话；每次提问和回复是消息。系统处理一个输入时建立一条运行（Run），其中可以发生多次模型请求、技能读取或工具调用，每次实际开始的操作记为动作（RunAction）。一次失败重试保留输入和旧回复，新增运行及回复，因此不能把运行直接当作一条消息。

接受时保存空回复记录，是为了从排队开始就有稳定的观察及停止目标。执行中的内容和动作单独保存；成功发布后，最终正文写入这条回复。页面读取的是业务消息和状态，不从 SDK 内部存档拼出用户历史。

## 为什么分成三个模块

| 模块          | 负责的问题                                           | 协作产物                                                     |
| ------------- | ---------------------------------------------------- | ------------------------------------------------------------ |
| conversations | 这是谁向哪位员工提出的工作，怎样准备输入并交付到对话 | 固定输入，组合授权检查，最终消息及文件关联。                 |
| execution     | 工作能否开始和继续，怎样记账、停止、超时及收束       | 运行状态、实际动作和预算；通过回调请求业务准备与发布。       |
| agent_runtime | 已获准工作怎样进入模型与工具循环                     | SDK 存档、内容更新和候选结果，通过受限控制接口申请实际动作。 |

这个边界使 HTTP 断线不影响处理责任，也使模型 SDK 的消息变化不必进入业务查询。它带来的要求是三方必须共享清楚的输入、动作和完成约定；不能用 SDK 正常返回来替代业务发布成功。

## 固定配置与当前授权

快照保存接受时的指令、方法定义、资源选择及版本依据，使一次工作不会在排队后悄悄换成另一套内容。快照不包含秘密，也不赋予永久权限：宿主仍检查当前会话、员工状态、装配及连接修订；实际凭据由所属服务解析。

恢复存档（checkpoint）保存 SDK 的内部状态和继续位置。只有运行允许恢复、存档可信且授权仍有效时才可使用；不支持安全重放的外部操作不能被当作普通模型聊天自动恢复。一次未确认的外部操作也不能假定没有发生。完整时序见[对话流程](../product/workflows.md#发起对话并取得结果)。

当前恢复资格在接受时根据可用工具与工作区确定：捕获外部 MCP、不可重放的原生操作或沙箱配置，会将本轮标记为不自动恢复。这里采用保守判断，不能因为实际动作列表尚无工具调用就推断可恢复。代码依据是 [capture_tools](../../backend/app/agents/tool_grants.py) 与 [RunStore.recover](../../backend/app/execution/store.py)。

## 输入、控制和输出

[AgentRequest](../../backend/app/agent_runtime/contracts.py) 包含冻结输入、模型配置、预算与恢复引用，不包含 HTTP 请求、Actor 或业务 ORM。RuntimeControl 提供 guard、start_model、start、finish、report_content、checkpoint_saved，以及 begin_tool、guard_tool、complete_tool；它没有公开 store、database 或 auth。

start_model 在写事务内复核授权、扣减预算并建立动作。方法读取也在获准、记账和记录成功后执行。普通内容使用 ContentUpdate，SDK 的 AIMessage/Chunk 留在适配器。

[LangChain 实现](../../backend/app/agent_runtime/langchain.py) 负责模型与工具循环，[streaming](../../backend/app/agent_runtime/streaming.py) 解析片段与模型轮，[middleware](../../backend/app/agent_runtime/middleware.py) 约束上下文、开始和结束模型动作，[skill_loading](../../backend/app/agent_runtime/skill_loading.py) 校验本轮技能激活，普通工具由 [tool_calls](../../backend/app/agent_runtime/tool_calls.py) 统一申请授权/预算并持久保存结果。文件路由保留完整路径，资源操作通过注入接口协作，详见[基础工具契约](../reference/agent-tools.md)。

有装配工具时，模型收到由本轮快照生成的操作名/调用名清单及使用指引；实际函数定义来自同一快照。历史答复中的“没有联网工具”等判断不代表本轮能力状态，读取网页或其他外部任务应使用当前匹配工具取得结果。该指引不授予权限，也不强制每个问题调用工具；账号、范围和预算仍由宿主逐动作检查。历史消息保留原文，不为修正模型判断而删除或改写对话。

MCP 服务说明随已确认账号目录冻结，以来源标明的指导注入模型。可信 stdio 客户端由 Run 持有，结束、取消或停服关闭，不占用 OpenSandbox 的脚本容器。Skill 支持文件按摘要读取，实际执行前投递已激活包。长结果与网页读取证据见[运行契约](../reference/runtime.md#外部读取证据与长结果)。

AgentOutput 是候选正文、用量及可选的已保存输出文件引用。协调器调用注入的[发布流程](../../backend/app/conversations/publication.py)；运行器不自行创建对话消息或宣告报告已交付。

## 过程和恢复

宿主 RunControl 只缓冲普通内容并按频率保存，恢复数据由 Store 返回后自行装入控制对象。SDK 的消息聚合、工具请求识别和完成判断不进入执行核心或前端。

专用 CheckpointStore 在装配时注入 Agent 实现。SDK 保存状态后通知引用；正式历史直接读取 Message。可信完成标记只在原 Run 仍活动时用于补发布，已终止记录不会被改写。没有可信存档或协议不兼容时明确 interrupted。普通可重试回复由 can_retry 表达；已退役的旧工作仅供历史读取。

[独立边界测试](../../backend/tests/test_runtime_boundaries.py) 用内存控制运行真实 SDK，并验证业务库不产生动作；另用存储故障测试证明开始记录失败不会调用模型。这里是受信 Python 代码间的职责边界，不是进程沙箱。

## 知识工具与个人授权

knowledge模块拥有个人员工装配、多库召回及Run证据，conversations在接受事务捕获目录并组合Prompt，在每次宿主授权时复核个人设置、拥有者及已登记Chunk。RuntimeResources仅注入knowledge_call/knowledge_finalize，agent_runtime/knowledge.py负责普通工具schema和always预检索，不持有Actor或业务数据库。

同一对话连续追问时，conversations只交付实际选入上下文的成功回复来源；knowledge.context重新核验并按剩余上下文预算登记本Run证据。来源片段及原编号冻结在knowledge.history_evidence，runtime在当前问题中加入这些不可信参考数据，按需模式可复用或补读，always仍执行搜索。接受事务已记录核验动作，SDK恢复不重复登记或增加核验动作；每次模型/工具及发布继续检查当前来源。

知识工具与MCP工具共用ToolExecutionMiddleware动作门，但采用专用binding和knowledge授权回调。always在进图前通过固定action_key申请预算并记录结果，checkpoint恢复可复用已重新授权的只读结果；按需模式真实注册search/read工具，模型自行选择。证据只进入knowledge表，不提供普通source文件旁路。

SDK结束时及最终发布的同一事务内完成知识引用规范化与校验：仅当本轮编号与完整路径配对时补回遗漏的根斜杠，正式消息使用返回正文，模型动作保留原文。知识快照关闭失败部分正文交付；已流出的草稿不等于验证后的正式消息。引用检查确保本轮来源和精确路径，无法代替语义评测。协议与模式边界见[知识契约](../reference/knowledge.md#员工个人装配与正式问答)。

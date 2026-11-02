# Agent运行层SDK接入评估

源码链接已按当前位置修复；本文保留记录时的名称和结论，当前行为以现行契约为准。

历史记录：适用范围与日期以原文为准；2026-10-23 仅整理归属。旧结构、建议与通过结果不代表当前实现，现行入口见[主索引](../README.md)。

| 项目     | 内容                                                                                                                                                                                                                                               |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 设计状态 | P1 组合已采用；外部工具、CI 通用化及更多 SDK 能力仍待分阶段验证                                                                                                                                                                                    |
| 实现状态 | P1 普通聊天已接入并完成回归及真实模型验收；CI 通用化与外部工具后置                                                                                                                                                                                 |
| 更新日期 | 2026-10-23                                                                                                                                                                                                                                         |
| 涉及模块 | runtime、llm、技能库与装配、CI诊断、运行记录及对话展示                                                                                                                                                                                             |
| 相关入口 | [技能库设计](../proposals/skills-and-mcp/README.md)、[CI诊断](../reference/ci-diagnosis/README.md)、[运行器](../../backend/app/execution/README.md)、[验证证据](../../../niuma-crew-archive/output/reviews/agent-runtime-sdk-assessment/README.md) |

## 结论与范围

推荐当前采用LangChain `create_agent` 加Deep Agents官方 `SkillsMiddleware`、受限 `FilesystemMiddleware` 及调用限额中间件，放在现有Runner内部作为执行入口；不继续自研标准技能扫描、渐进加载和通用工具循环。不把完整Deep Agents默认栈作为本阶段所有员工的统一运行模式。

完整Deep Agents也可以作为Runner内部执行器，不要求替换FastAPI、数据库、页面或迁往LangSmith云。本次选择基于当前任务边界与默认行为，不基于依赖更少、性能更快或模型效果更好；后几项不能由本次验证推出。

初始工作为隔离架构评估；后续 P1 已获实施授权并完成普通聊天接入。原评估证据保留其当时范围，不能代替后续验收。SDK能力、实际验证、建议接法和待验证事项分开记录。P1 生产改动和验收另见[迁移清单](agent-model-rebuild.md)。资源、历史与实际字段以[目标模型](../proposals/agent-capabilities/README.md)及[数据字典](../proposals/agent-capabilities/data.md)为依据；[运行契约](../proposals/agent-capabilities/runtime.md)规定按需加载与授权，SDK 默认结构不决定业务表。当前关系和运行快照可以接入，不以技能发布、多实例为前置。

## 评估时的代码基线

| 入口                                                                      | 当前职责                                                                                 | 对接入的影响                                             |
| ------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| [依赖清单](../../backend/pyproject.toml)、[锁文件](../../backend/uv.lock) | 使用langchain-core及langchain-openai，尚未引入langchain Agent工厂、LangGraph或deepagents | 两条路线都需要新增依赖，不能只给ChatOpenAI追加一个参数   |
| [模型工厂](../../backend/app/llm/factory.py)                              | 根据既有连接配置构造ChatOpenAI；调用方管理异步HTTP客户端，默认无自动重试                 | 可直接复用模型对象与连接服务，不必重做模型配置页面       |
| [provider](../../backend/app/agent_runtime/langchain.py)                  | 单次astream转为文本、用量和finish_reason                                                 | 不能直接当多步骤Agent事件适配器；须增加执行结果/事件映射 |
| [Runner](../../backend/app/execution/scheduler.py)                        | 队列、并发、总时限、授权watcher、取消、终态与恢复                                        | 保留外层调度，在consume内调用Agent执行器                 |
| [RunStore](../../backend/app/execution/store.py)                          | 正文和终态落库、取消优先、CI进度；重启标记interrupted而不重放                            | 继续作为产品状态依据；SDK图完成不自动等于任务成功        |
| [ConversationService](../../backend/app/conversations/service.py)         | 幂等准入、配置/消息快照、创建queued run                                                  | 保留；技能发布和装配解析在本次提交时固定                 |
| [原CI服务（已退役）](../reference/ci-diagnosis/README.md)                 | 装配鉴权、GitHub准备调用、手写有界工具循环、证据和报告校验                               | 工具循环可替换；业务检查和来源保存保留                   |
| [原CI MCP（已退役）](../reference/ci-diagnosis/README.md)                 | 固定只读端点、2025-03-26协议及三项操作                                                   | 已验证实现先保留，迁为官方客户端后需单独真实回归         |
| [对话页面](../../frontend/src/pages/conversations/ConversationPanel.tsx)  | 提交结构化work，观察持久化状态，显示CI报告                                               | 不需要因SDK选择重做页面；通用工具进度需后续增量适配      |

评估时技能表只有正文和元数据，正式版本发布、多实例装配和通用凭证连接仍是草案，任何Agent SDK均不会自动提供这些业务对象。后端架构旧目标图不能替代以上当前代码事实。

## 两条路线比较

| 维度         | A：完整create_deep_agent                                     | B：create_agent按需组合                                      |
| ------------ | ------------------------------------------------------------ | ------------------------------------------------------------ |
| 执行基础     | 官方Agent/LangGraph及Deep Agents默认栈                       | 同一官方Agent/LangGraph基础，显式选择中间件                  |
| 标准Skill    | 传skills时自动装配SkillsMiddleware                           | 显式添加同一个SkillsMiddleware                               |
| 文件工具     | 默认文件工具；可覆盖或限缩                                   | 仅提供本阶段需要的读取工具                                   |
| 委派         | 默认通常有general-purpose子Agent及task工具，可关闭           | 默认没有，真实需求出现后再接官方组件                         |
| 上下文       | 默认压缩、工具调用修补和适用模型的缓存等                     | 按需接官方中间件，顺序由项目维护                             |
| 脚本         | 仍需可执行后端/沙箱，并非构造Agent后自动有隔离算力           | 同样可复用官方执行后端，但需配置环境                         |
| MCP          | 外接官方MCP适配器                                            | 使用同样的适配器                                             |
| 平台集成     | 同样要接授权、取消、记录和交付；额外检查默认工具、委派和压缩 | 同样要接平台边界，但本期行为范围较小                         |
| 安装依赖     | 引入deepagents及其传递依赖                                   | Skills中间件也来自deepagents，依赖成本基本相同               |
| 长期代价     | 复用默认栈维护，需跟踪默认行为和模型profile变更              | 自己维护少量组件清单、顺序及测试，不能继续叠成另一套完整框架 |
| 当前适配程度 | 更适合文件/代码、多步骤探索和委派成为常态的员工              | 更贴近当前普通对话、只读CI及标准技能加载                     |

A可以裁剪，B也可以扩充，两者不是不可逆的技术路线。若B以后需要组装大部分默认栈，应改用A并保留外层业务接口，而不是长期复制官方组装逻辑。

官方依据：[完整栈与定制](https://docs.langchain.com/oss/python/deepagents/customization)、[官方按需组装教程](https://docs.langchain.com/oss/python/langchain/deep-agent-from-scratch)。在本次固定响应样例中，两者模型轮数及首轮提示字符数相同，未证明性能或成本差异。

## 哪些能力复用，哪些由平台负责

| 能力                   | 复用方案                                          | 平台仍需实现/配置                                                |
| ---------------------- | ------------------------------------------------- | ---------------------------------------------------------------- |
| 模型调用与原生工具循环 | create_agent，继续使用现有ChatOpenAI工厂          | 网络生命周期、连接解密、错误归一及实际模型兼容性                 |
| 技能目录和渐进加载     | SkillsMiddleware                                  | 员工获准技能集合、固定发布内容、扫描来源与缓存生命周期           |
| 显式选择技能           | 官方pinned_skills输入，使指引在首轮调用前加载     | 从合法业务入口映射技能，防止用户指定未授权内容                   |
| references/assets读取  | FilesystemMiddleware与官方Backend                 | 只暴露获准版本和资料；业务文件权限、资源类型与留存               |
| 脚本和CLI执行          | 官方sandbox/execute接口及相应后端                 | 沙箱供应、语言依赖、网络/文件挂载、秘密注入、配额与制品管理      |
| 模型/工具调用限额      | ModelCallLimitMiddleware、ToolCallLimitMiddleware | 平台总时限和成本预算；CI每job去重、总调用数等业务预算            |
| 压缩、记忆和委派       | 官方已有组件，按需启用                            | 内容保存范围、来源追溯、数据隔离和效果验证；不默认当员工永久记忆 |
| 结构化输出             | Agent response_format等官方机制可选               | 验证模型支持；CI引用、attempt、覆盖与最终报告仍由程序校验        |
| MCP传输和工具转换      | 官方langchain.mcp/MCPAdapter及FastMCP；按版本验证 | 连接和授权、业务范围、网络策略、身份隔离及来源记录               |
| 执行进度               | 官方astream或typed event streaming提供信号        | 映射并脱敏后落入平台Run/工作轨迹，不能直接对外透传所有事件       |
| 人工审批/恢复          | 官方HITL、interrupt和checkpointer                 | 审批身份、可恢复状态、页面、过期撤权、幂等与审计                 |
| 技能建设、导入和发布   | 复用Agent Skills格式与SDK扫描                     | 包导入校验、来源/许可证、版本、稳定发布、装配及测试流程          |
| 交付和反馈             | 平台现有持久化和CI校验/反馈                       | 通用交付与反馈按需求扩展，SDK最终AIMessage不代表业务验收         |

有现成SDK不代表不需要适配；适配应集中在平台业务边界，避免重写通用解析器、Agent循环、MCP传输或脚本解释器。文件路径权限不能替代GitHub仓库等外部资源范围校验。

## 接入后的执行边界

### 外层Runner与内层Agent

Runner继续领取queued run、复查发起身份、解析模型连接并控制总时限；其内部执行入口构造本次Agent、消费事件并返回最终结果。Agent负责模型与工具步骤，不领取数据库队列、不独立决定产品终态。

先用一个小执行适配入口接收快照、消息、模型、授权检查和事件写入回调，返回正文、用量和交付结果；不先建设多层通用插件平台。继续由应用生命周期持有执行，SSE只读取已存状态，浏览器断开不取消后台工作。

普通聊天统一支持[按需发现、激活已装配技能](../proposals/agent-capabilities/runtime.md#普通聊天的统一运行流程)，这已在 P1 实现；无需能力时可一次模型调用完成，但不能绕过装配解析。CI 继续共用外层 Runner，专用循环暂留到 P2；并保留受信校验。P1 已用 create_agent、SkillsMiddleware、只读 StateBackend 和限额中间件接通普通指引，并完成实际服务与真实模型验收；CI 通用 SDK 循环迁移在 P2。

### 授权、工具与并发

只向SDK提供本次装配允许的技能目录和工具，工具执行前通过官方wrap_tool_call或工具包装层复查当前授权；撤权类异常应终止执行，不能被通用错误处理中间件转成可忽略的业务提示。

仓库和连接从受信装配上下文注入或验证，不让模型覆盖。通用MCP无法自动理解任意工具的业务参数，严格范围仍需上游受限身份或受信适配器。

SDK可并行处理一批工具调用；CI的job去重与预算占用须在并发下原子处理，不能只依赖模型看到的工具Schema或单线程样例。未来开启子Agent时，授权、预算、连接和事件归属须覆盖子图，不能只守住主Agent。

### 流式事件、状态与预算

P1 适配器已区分模型调用、方法激活、最终回答和中断/错误。中间草稿、工具JSON、内部推理和其他子图内容不直接拼入最终助手正文；CI报告仍在检查通过后统一交付。

官方模型/工具限额只是内层限制。技能读取会消耗工具和可能的模型轮次，与GitHub业务调用预算分开计算；CI显式选择可通过pinned_skills省掉一次选择性读取轮次。Graph recursion_limit不是业务轮数、费用或总时限的替代品。

中间件主动结束、interrupt或正常返回图状态，不足以写succeeded。限额建议使用明确错误行为；报告检查、有效输出、取消优先和原子落库继续由平台落实。用量按全部模型调用聚合，未知项保持未知。

### 数据与恢复

首阶段每个run独立构造执行状态，从本次快照和已选消息开始；不引入第二套跨会话历史或自动恢复机制。已发布技能资源采用不可变引用/受控挂载，运行时只暴露本员工获准部分，不为每位员工复制整包。

SDK技能缓存不能越过版本边界复用。若后续按conversation持有图或checkpoint，需处理技能缓存失效、消息双写去重、装配切换和旧工具上下文；不能简单将conversation_id当thread_id后宣称完成持久化。

现有重启interrupted、显式新run重试、不自动重放语义保持。只有确需暂停审批/断点续跑时才设计持久checkpointer和等待态；复用官方保存与恢复机制，同时定义平台身份、任务归属和终态。官方MemorySaver是内存实现，不等于进程重启可恢复。参见[官方HITL](https://docs.langchain.com/oss/python/deepagents/human-in-the-loop)。

现有ci_result是CI专用有界JSON，不自动成为通用事件存储。实现新增通用步骤时应定义最小持久化契约，复用Run和既有页面状态，避免为接SDK预先设计大量新表。

## CI怎样迁移

2026-10-23 目标以[标准技能与通用 MCP](../proposals/skills-and-mcp/README.md)为准：动态连接目录与员工独立工具许可，CI 作为示例进入同一循环；下列专业准备与交付逻辑由受信工具/检查组件复用，不成为新增技能的专用程序模板。

迁移保留既有证据保证：

1. 提交仍校验装配/仓库并冻结方法、请求和限制。
2. CI程序继续读取运行信息和job列表，固定attempt/head_sha及失败job集合。
3. 将本次技能映射为固定内容，显式激活；Agent仅得到必要文件读取与read_failed_job_log业务工具。
4. 业务工具包装层复查授权，固定仓库，原子执行日志次数与job去重限制，保存脱敏来源并返回编号证据。
5. create_agent完成原生工具往返，官方中间件限制模型次数；CI业务逻辑决定何时停止读日志并形成草稿。
6. 原有Pydantic结构、来源行号和覆盖校验、结束复查、Markdown渲染、原子提交及最小反馈继续使用。

CI方法文本能指导工作，不能替换以上受信领域逻辑。首次迁移不同时改报告格式、反馈模型和数据库恢复语义，减少结果差异来源。新旧执行器只在迁移期间受控选择，真实验证通过后删除被替代的手写循环，不长期维持两套。

## MCP复用与版本边界

下述 SDK namespace、版本和缺口记录 2026-10-22 的评估依据；2026-10-23 仅整理目标关系，未重新进行依赖解析或协议实测。实施选型须按当时官方契约与真实回归确定。

MCP适配对A/B均可用，不是完整Deep Agents独有能力。官方当前推荐langchain.mcp.MCPAdapter，支持远程HTTP、stdio和in-process配置；该namespace要求langchain[mcp]>=1.4.0，仍标Beta，应通过小适配边界固定版本后验证，不直接把SDK配置结构作为永久业务API。

新适配器重点覆盖tools，官方迁移说明明确prompts/resources暂缺同等包装，sampling/roots等交互有支持边界；elicitation可能触发图interrupt。不能将“接上MCPAdapter”写成“所有MCP功能兼容”，也不能在当前没有等待态的Run上静默接收审批中断。

建议先用新通用只读MCP验证官方适配器；再迁移现有GitHub固定客户端并做真实回归。确需resources/prompts时评估底层官方客户端和已有适配能力，不继续手写JSON-RPC，也不因新namespace版本更新就丢弃已验证的旧链路。原评估未安装mcp extra或实测该适配器；本次设计整理也未实施。通用连接的动态目录、认证和协议支持按新设计逐项真实验收。

官方依据：[MCP接入](https://docs.langchain.com/oss/python/langchain/mcp)、[迁移与缺口](https://docs.langchain.com/oss/python/migrate/langchain-mcp-adapters)。

## 依赖解析与实际验证

本次临时环境使用Python3.12.13，固定deepagents0.7.30、langchain1.4.7、langchain-core1.6.13、langchain-openai1.7.2、langgraph1.2.16。它是评估候选，不是已批准的生产升级组合。deepagents0.7.30的官方PyPI发布时间为2026-10-22，不能仅因最新就忽略兼容回归。

以完整backend/pyproject.toml约束解析，先发现保留现有锁定值不兼容；放开以下四项后，保留其余已有包锁定版本可成功解析：

| 依赖           | 当前锁定 | 本次候选 | 变动依据                       |
| -------------- | -------- | -------- | ------------------------------ |
| langchain-core | 1.6.10   | 1.6.13   | 所选langchain版本要求          |
| langsmith      | 0.14.8   | 0.14.12  | 所选deepagents最低要求高于当前 |
| tenacity       | 9.2.1    | 9.1.4    | 新增Google SDK要求小于9.2      |
| websockets     | 17.2     | 16.1.1   | 新增Google SDK要求小于17       |

两条路线都安装deepagents，其依赖包含Anthropic和Google模型包，即使项目仍用现有OpenAI兼容接口也会有这些传递依赖。候选新增18项包；不是“按需组合只多一个轻量类”。原评估未改生产依赖；P1 已安装并锁定该兼容组合与 jsonschema，具体安装值以 uv.lock 为准。生产采用时需固定兼容组合并针对升级/降级依赖回归，不能把本次可解析当生产兼容结论。

固定响应模型驱动实际SDK，两条路线各8项加载与工具检查，另6项控制点，共22个布尔检查点通过：

- 首轮只有技能摘要，没有完整正文和引用；实际read_file后正文出现，再读references后资料出现。
- A默认向模型提供8项工具：delete、edit_file、glob、grep、ls、read_file、task、write_file；B仅提供显式选定的ls、read_file。A可配置限缩，此结果不是不可裁剪的限制。
- 官方pinned_skills让显式技能正文在首轮模型调用前可见。
- 自定义授权检查可从官方工具中间件入口在执行前终止；官方模型次数限制阻止额外调用。
- asyncio取消传播到协作式本地工具的finally清理。
- 当前项目模型工厂生成的ChatOpenAI对象能传入两个构造入口；没有使用真实凭证发起推理。

证据：[范围说明](../../../niuma-crew-archive/output/reviews/agent-runtime-sdk-assessment/assessment.json)、[结果](../../../niuma-crew-archive/output/reviews/agent-runtime-sdk-assessment/smoke-result.json)、[可复现脚本](../../../niuma-crew-archive/output/reviews/agent-runtime-sdk-assessment/smoke.py)、[依赖差异](../../../niuma-crew-archive/output/reviews/agent-runtime-sdk-assessment/minimal-dependency-comparison.json)。

限制：模型响应预先指定，不验证模型自主选择、推理质量或Kimi线上兼容；未调用外部MCP，未测试远端撤销、沙箱、持久恢复或生产Run/SSE集成。没有测出吞吐、延迟和成本优势；上述限制属于初始隔离评估；P1 当前回归、真实模型及浏览器验收见[实施记录](agent-model-rebuild.md)。

## 推荐实施顺序与验收

1. 固定候选依赖、增加内部执行入口；保留现有连接工厂和外层Runner。执行当前聊天/CI回归，确认依赖变化没有改变旧行为。
2. 接SkillsMiddleware与只读文件工具，挂载获准固定内容；分别验证自动选择和显式选择、references、资源边界、技能缺失及版本切换。
3. 接平台授权/事件/结果映射；取消、撤权、限额、数据库失败和刷新不能触发重复执行，失败和中断不能被保存为成功。
4. 在同一CI输入上验证新执行器与真实Kimi/GitHub工具往返、引用、覆盖和反馈，再替换手写循环；历史结果继续可读。
5. 导入一个第三方标准Skill并新增第二个只读MCP，证明新增能力无需专用平台业务路由。MCP的连接、作用域、认证失效和协议错误另行验收。
6. 真实业务需要程序执行时再接官方sandbox后端；需要委派、长期记忆、压缩或审批时逐项启用官方组件，不自行重建同类机制。

若实际员工工作转向代码/文件操作、长期探索和受控委派，且默认栈的大部分组件都已被需要，则重新比较采用create_deep_agent的维护成本。届时仍沿用本次执行适配边界、装配、权限、证据和交付，不把更换构造工厂扩大成平台重写。

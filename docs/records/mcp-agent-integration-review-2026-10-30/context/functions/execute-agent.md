## `execute_agent` in backend/app/agent_runtime/langchain.py (L109-L232)

**Purpose:** 在本轮冻结配置上构造 LangChain Agent，运行或恢复 SDK 状态，把完整最终模型回复作为候选 `AgentOutput` 交宿主发布。它检查 SDK 完成、回答形状、当前许可和一类显式网页读取证据，不自行发布业务消息（langchain.py L154-L225；preparation.py L225-L230；coordinator.py L100-L112/L151-L163）。

**Inputs & Assumptions:**

- `input: AgentRequest`：半可信冻结输入；`messages` 内用户文本和历史助手正文不可信，配置由平台冻结。`input_message_id` 取最后一条消息 ID，要求 `messages` 非空；数据类本身未校验非空，`nothing found`（contracts.py L19-L36）。正式调用方由 `ConversationService` 拼接历史成功问答和当前 user 消息（service.py L188-L217），`ConversationPreparation.execution` 构造请求（preparation.py L165-L174）。
- `snapshot`：代码直接索引 `skills`、`selected_skill_ids`、预算、system prompt 等，要求对应字段存在；正式准备器构造这些字段（preparation.py L90-L130/L145-L152），本函数不校验整体 schema（langchain.py L117-L168）。
- `hooks: RuntimeControl`：可信宿主接口，负责 guard、模型计数/完成、工具动作和 checkpoint 引用；本函数信任实现，协议未暴露 ORM/Store（contracts.py L55-L80）。
- `checkpoints`：可信、每 Run 独立 SDK 状态仓；`checkpoint_config` 使用 `input.run_id` 作为 thread ID，正式准备器用 `for_run` 核验 Run metadata（langchain.py L167；checkpoints.py L21-L28/L65-L79；preparation.py L165-L167）。
- `resources`：可信资源适配器或 `None`；**MCP 定义进入 Agent 的条件是 resources truthy**，工具授权中间件条件为 schema_version≥3 且 hooks 带 `begin_tool`（langchain.py L160；middleware.py L158/L178-L182）。有 snapshot MCP 工具却未提供 resources 时，本函数没有拒绝，`nothing found`；工具状态 prompt 仍按 snapshot 生成（langchain.py L160-L164；L30-L56）。正式 bootstrap 同时注入 tools/files，准备器据此创建 resources（bootstrap.py L106-L117；preparation.py L177-L206）。
- 当前日期：`compose_system_prompt` 只组合身份、员工指令、公司规则；本函数只附加工具状态和已确认服务说明，首次 messages 只取 content。自动注入“当前日期/时间”的代码 `nothing found`（preparation.py L15-L31；langchain.py L162-L164/L182-L187）。外部模型服务会不会自行注入日期未知。
- 模型必须因“最新文档/查新”使用 Context7 的机械前置条件：`nothing found`。有匹配工具应调用的系统文本在 langchain.py L42-L44；它是自然语言指导。

---

**Outputs & Effects:**

- 返回 `AgentOutput(str(final.text), usage, optional output_files)`；结构中不含用于“查新”任务的引用列表、所用工具/结果清单或必备证据验收结果（langchain.py L224-L226；contracts.py L39-L43）。
- 创建模型受管 HTTP session、SDK checkpoint writer；调用 guard、记录流/完整模型内容、模型用量、工具与文件操作经中间件/资源进行（langchain.py L146-L166/L196-L225；middleware.py L46-L141；tool_calls.py L223-L292）。模型 session 使用显式配置，不查询业务数据库（llm/factory.py L13-L46）。
- 抛出 `empty_response`、`runtime_interrupted`、预算/递归上限错误及被分类的上游错误；其余异常上抛（langchain.py L171-L232）。`verify_web_reads` 失败直接上抛，不回到 Agent 再查工具或重生成（L215-L232）。
- checkpoint、流内容和工具结果先于最终证据核验持久化/报告；最终失败不能据此推导“未曾向前端展示生成正文”（langchain.py L95-L98/L201/L215-L221；middleware.py L107-L119）。前端实际如何显示失败内容不在本函数内。

---

**Block-by-Block:**

```python
# L117-L136
snapshot = input.snapshot
prepared_skills = prepare_skills(snapshot["skills"], snapshot["selected_skill_ids"])
progress = RunProgress(..., input.recovered_content)
backend = WorkspaceBackend(snapshot, prepared_skills, resources, sandbox_factory=sandbox_factory)
```

- **What:** 同一批技能冻结数据用于文件后端和加载中间件；创建本轮输出状态、工作区/沙箱后端。
- **Why here:** 在 middleware/create_agent 前准备，保持加载校验和实际文件正文一致（L118；skill_loading.py L49-L78）。
- **Assumes:** 所选 skill IDs 均在 `skills` 中，由 capture_skills 契约提供；本函数另行校验 `nothing found`（L119-L122；skill_loading.py L75-L78）。
- **Establishes:** `prepared_skills` 只有 snapshot 中技能与参数，不从当前磁盘目录扩大能力（skill_loading.py L53-L78）。
- **Depended on by:** middleware、pinned_skills/state files、backend（L146-L153/L188-L190）。

```python
# L138-L153
def input_content(message): ...
middleware = build_middleware(...)
```

- **What:** 当前输入可附文件清单；生成 Filesystem/Skills、模型次数限制、工具执行许可、技能加载、模型执行记录中间件。
- **Why here:** middleware 先拥有准备后的技能和后端，再创建 SDK Agent（middleware.py L147-L191）。
- **Assumes:** 平台文件清单是数据，文件权限仍由工具许可决定；文案明确该边界（L140-L143）。
- **Establishes:** 技能加载在模型记录前；模型请求完整字节数包含 system/messages/工具 schema 并拒绝超额（middleware.py L156/L169-L190；L60-L64）。没有运行时 Tool Search/按当前任务再筛 MCP 定义的代码；external_tools 遍历冻结装配工具（tool_calls.py L28-L59）。
- **Depended on by:** 所有模型/工具步骤；它限制允许的调用，但不要求至少一次 MCP 调用（middleware.py L46-L144；tool_calls.py L188-L292）。

```python
# L154-L170
async with checkpoints.writer(...) as saver, model_session(...) as model:
    agent = create_agent(
        model=model,
        tools=external_tools(snapshot, resources, hooks) if resources else [],
        middleware=middleware,
        system_prompt=snapshot["system_prompt"] + _tool_instructions(snapshot) + _server_instructions(snapshot),
        checkpointer=saver,
    )
    ...
    resumed = state.values.get("app_run_id") == input.run_id
```

- **What:** 将每个已装配 MCP 的真实名称、描述和 input schema 构造为 `StructuredTool` 交给 Agent，另加 `read_tool_result`（tool_calls.py L28-L59）。
- **Why here:** 相同 snapshot 供模型定义、调用映射、系统目录和授权使用；SDK 图建立后读取恢复点（L158-L170）。
- **Assumes:** 工具描述/服务指导来自已确认目录；其业务数据由调用方冻结。`_server_instructions` 跳过 auth_required 并按 connection 去重；本函数未对描述内容再做语义审核（L59-L74；tool_calls.py L49-L55）。
- **Establishes:** 模型拥有定义，不代表已经调用。工具 prompt 要求有匹配工具应调用并如实说明失败（L42-L44/L53）；Context7 专用路由、freshness 要求和“检索后才能完成”状态 `nothing found`。
- **Depended on by:** 后续 SDK 正常执行/恢复。应用模型工厂没有设置 tool_choice；本地 SDK `ModelRequest` 初始 tool_choice=None，再原样 bind_tools（llm/factory.py L24-L33；site-packages/langchain/agents/factory.py L1582-L1588/L1483-L1489）。

```python
# L172-L209
if resumed and not state.next:
    ...  # 检查 completed_run_id 后取 final/usage
else:
    value = None if resumed else {"messages": [...], ...}
    await _consume_agent_stream(agent.astream(..., durability="sync"), hooks, progress)
    state = await agent.aget_state(checkpoint_config(input.run_id))
    ...  # 检查 completed_run_id / state.next 后取 final/usage
```

- **What:** 已完成恢复点直接取最后消息；未完成恢复点给 SDK `None` 继续；新 Run 把成功历史和当前正文映射为 HumanMessage/AIMessage，初始化技能文件和 Run 标识。
- **Why here:** 最终结果以已落盘完整 state 为准，而不是最后一个流事件（L203-L209）。
- **Assumes:** `app_run_id`/`completed_run_id` 由本轮可信宿主/中间件设置；`ModelExecutionMiddleware.aafter_agent` 无条件返回本轮 completed_run_id（middleware.py L143-L144）。这只说明图结束，不说明查新目标已满足。
- **Establishes:** 两条分支都要求 SDK 完成标记。**没有 tool_calls 的首次模型回复可直接完成**：本地 SDK 的模型到工具边在零调用时返回 end_destination（site-packages/langchain/agents/factory.py L2016-L2019）。
- **Depended on by:** 完成检查。历史只有成功 user/assistant 正文，无前轮工具消息/取证附件（queries.py L182-L211；service.py L217；L182-L187）。模型 middleware 保留批准历史和当前执行消息，不清除“以前没有工具”的助手正文（middleware.py L48-L59）；工具状态 prompt 对此仅给自然语言纠正（L41-L43）。

```python
# L210-L226
if not isinstance(final, AIMessage) or final.tool_calls or not final.text.strip():
    raise RuntimeFailure("empty_response")
await hooks.guard()
if resources is not None:
    await asyncio.to_thread(verify_web_reads, input.messages[-1]["content"], state.values.get("messages", []), ToolResults(snapshot, resources))
outputs = await asyncio.to_thread(backend.collect_outputs, state.values)
await hooks.guard()
return AgentOutput(str(final.text), usage, {"output_files": outputs} if outputs else None)
```

- **What:** 最终回复必须非空且不含待调用工具，复核许可，核验一类网页阅读，收集 outputs，再复核许可并返回。
- **Why here:** 避免把悬空工具调用或迟到撤权结果作为答案；核验发生在 SDK 结束后（L210-L225）。
- **Assumes:** `verify_web_reads` 定义了本轮需证据任务。它实际只识别带明确 HTTP(S) URL 且读取/阅读/提取/总结等指定动词的输入（tool_results.py L124-L142）。
- **Establishes:** 若没有符合条件 URL，函数直接返回（tool_results.py L145-L148）。因此无 URL 的“最新 LangChain 文档”及显式“使用 Context7”均不触发。即使符合条件，也仅检查成功 ToolMessage、当前 Run result_id、连续读取覆盖全部序列化结果，以及 platform_result.extracted_urls 包含请求 URL（L149-L181），不检查最终文本逐条忠实/版本日期是否最新。
- **Depended on by:** 宿主把返回值视为成功候选。Context7 返回值是否能被 extracted_targets 识别未知；该函数只处理 `results` 下 `raw_content`，或工具原名 tavily_extract 时的 content（tool_results.py L36-L50），没有通用 Context7 freshness/evidence adapter。

```python
# L227-L232
except (ModelCallLimitExceededError, GraphRecursionError):
    raise RuntimeFailure("agent_budget_exceeded") from None
except Exception as error:
    if code := classify_error(error):
        raise RuntimeFailure(code) from None
    raise
```

- **What:** 统一 SDK 预算和已知上游错误，保留其他错误。
- **Why here:** 运行/最终检查共用宿主失败类型。create_agent/model session/state 首次读取在 try 外（L154-L171），不走这两条转换分支。
- **Assumes:** `classify_error` 只识别上游故障；具体分类细节需由 llm 审阅。
- **Establishes:** 没有“工具没用则自动重新规划/修复”分支；工具证据失败直接终止。
- **Depended on by:** coordinator 的终态分类和 publisher（coordinator.py L122-L136/L151-L163）。

---

**Cross-Function Dependencies:**

- Caller `ConversationPreparation.execution.execute`（internal）：正式注入 resources、恢复用量/激活状态、关闭 sandbox/MCP caller；先 tool caller 且 files 存在才创建 resources（preparation.py L177-L206/L208-L239）。
- `external_tools`（internal）：装配项描述与 schema 逐一成为真实 SDK tool；仅筛 kind，不按本次语义进一步筛选。实际调用需 `_current_invocation` 与 binding 匹配（tool_calls.py L28-L59）。
- `build_middleware` / `ModelExecutionMiddleware`（internal）：输入裁剪、预算、许可、格式与用量检查、动作持久化、completed 标记；无工具调用的非空 stop 回复仍记录为成功模型步骤（middleware.py L46-L144/L147-L191）。
- `verify_web_reads` / `ToolResults`（internal）：显式 URL 阅读的窄检查；结果 membership/binding/完整读取覆盖不依赖模型自称（tool_results.py L64-L80/L124-L181）。
- `create_agent`（external-source-available，本地 installed langchain 1.4.7，依赖声明 pyproject.toml L14）：默认 tool_choice=None，工具列表真实绑定，零 tool_calls 结束图；本报告没有访问外网。
- `model_session`（internal）：ChatOpenAI + Chat Completions、max tokens、stream usage、超时/重试；没有 Context7 policy 或强制 tool choice（llm/factory.py L13-L46）。
- `WorkspaceBackend.collect_outputs`（internal）：无 resources 返回空，虚拟/沙箱输出分别采集，执行数量/大小上限后保存；不是回答证据检查（workspace.py L279-L292）。
- Shared state：Run ID 定界 SDK checkpoint；本轮 source 文件经 resources 保留，最后查验只接收本轮 resource source IDs（checkpoints.py L21-L39；tool_results.py L145-L165）。

---

**Offline probe evidence (2026-10-30):**

- 仅创建临时 checkpoint，使用内存 hooks、真实 SDK、脚本假模型，无正式库、无模型网络/MCP 调用。脚本与 JSON：`/tmp/niuma-mcp-audit-20261030/evidence/reproduce_zero_tool.py`、同名 `.json`。
- snapshot 装配 Context7 `query-docs` 定义，bind_tools 捕获到描述/schema，并同时有 `read_tool_result`；工具 choice 为 `None`。
- 输入“查看 LangChain 最新版本的文档有什么新功能”：1 次模型、0 次工具；最终文本“我查阅了最新 LangChain 文档，新增了虚构功能。”被 `execute_agent` 接受为 AgentOutput。
- 输入“使用 Context7 查看 LangChain 最新文档有什么新功能”：相同 1/0 计数、相同文本被接受。
- 输入“读取 https://example.com/docs 页面内容”：相同 1/0 计数，抛 `external_read_unverified`。
- 这是可达路径/证据门槛探针，不测模型自己愿不愿意用工具，不证明任一真实模型或 Context7 上游的成功率。

---

**Open Questions:**

- 用户真实 Run 的模型请求/工具绑定、装配是否包含 resolve+query、账号和描述是否正确，不能由本函数静态分析单独确认；根代理另有真实只读证据，未由本子任务重复访问。
- Context7 当前工具 description/server instructions、最新版本覆盖范围、分页返回语义，需要 MCP 目录/适配层审阅；本函数不保证“查最新”必定得出当前发布版本。
- 员工工作指令/公司规章有没有鼓励直接回答、旧历史是否误导本次输出，需要实际冻结 snapshot/上下文；代码只规定组合顺序（preparation.py L15-L31；langchain.py L162-L164）。
- “查询最新/外部核实”应该是平台全局契约、员工职责配置、用户显式工具指令，还是运行时判断？现有机械门槛只覆盖明确 URL 阅读。此为产品/执行契约决策，不能从当前代码推成已有效需求。
- UI 是否展示被最终核验拒绝前的流式断言，以及 failed Run 能否继续在 UI 中误导用户，需要前端/发布路径核查。

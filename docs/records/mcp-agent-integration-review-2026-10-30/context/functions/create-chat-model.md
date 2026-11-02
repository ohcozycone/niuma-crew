## `create_chat_model` in backend/app/llm/factory.py (L13-L33)

**Purpose:** 将单个已解析模型连接转为保留 `bind_tools` 能力的 `ChatOpenAI`，供通用 Agent 和 CI 专用循环复用（factory.py:L24-L33；agent_runtime/langchain.py:L154-L166；ci_diagnosis/service.py:L24-L28，executor.py:L178-L180）。

**Inputs & Assumptions:**

- `config: LLMConfig`：半可信配置。字段非空、timeout 正数、max_retries 非负由 Pydantic 建立，配置冻结（llm/config.py:L6-L14）；正式调用的 URL 来自 `PRESETS`，模型 ID 来自数据库，密钥由 vault 解密（model_connections/service.py:L195-L210）。本次没有读取正式数据库和密钥。
- `transport: httpx.AsyncClient | None`：可信调用者提供的 HTTP 传输。传入时 timeout 覆盖 config.timeout（factory.py:L17-L20，L30）；通用运行由 `model_session` 创建禁重定向、禁环境代理的独立客户端（L43-L46）。
- `max_tokens: int | None`：可信调用者提供，工厂不检查正数，仅有值时透传（L21-L22）。通用 Agent 取 snapshot.max_output_tokens（agent_runtime/langchain.py:L156）。配置准入的数值范围不在本函数建立。
- 假设目标供应商兼容 OpenAI Chat Completions 工具与 SSE 协议。工厂不验证，`ChatOpenAI.bind_tools` 文档明确作此假设（本地 SDK base.py:L2517-L2519）；正式连接测试仅 GET `/models` 并明确说明不验证生成或 Agent 任务（model_connections/service.py:L212-L225，L247-L256）。工具兼容性验证：nothing found。

**Outputs & Effects:**

- 返回 `ChatOpenAI`，类型注解 `BaseChatModel`，没有添加缩窄能力的 wrapper（factory.py:L15，L24）。实例构造创建 OpenAI SDK 客户端，但此函数自身不发送生成请求；实际调用由 Agent `ainvoke` 完成（本地 SDK factory.py:L1559-L1565）。
- 强制 `use_responses_api=False`、`stream_usage=True`、显式 retries；是否 tool call、具体工具、并行和 strict 均不在本函数设置（factory.py:L24-L33）。
- 工厂无业务数据库写入，无 prompt 修改，无工具筛选，工具来源由调用者负责（factory.py:L13-L33；agent_runtime/langchain.py:L158-L164）。

**Block-by-Block:**

```python
# L16-L22
runtime_options = {}
if transport is not None:
    runtime_options.update(
        http_async_client=transport, default_headers={"User-Agent": "AgentPlatform/0.1"}
    )
if max_tokens is not None:
    runtime_options["max_tokens"] = max_tokens
```

- **What:** 仅有显式 HTTP 客户端时附加客户端与 User-Agent；可选输出预算独立传入。
- **Why here:** 避免向 `ChatOpenAI` 传空 HTTP client；构造参数完整后一次建立实例。
- **Assumes:** 客户端生命周期覆盖异步模型请求。正式调用由 `model_session` 的 async with 保证（L43-L46）。无 transport 的直接工厂调用仅测试等路径使用；构造处没有关闭客户端。
- **Establishes:** 提供客户端时异步请求将使用该客户端（SDK base.py:L1531-L1544）。
- **Depended on by:** MockTransport 能捕获真实 SDK 发出的 JSON；正式 Session 的超时和网络选项跟随该客户端。

```python
# L24-L33
return ChatOpenAI(
    model=config.model_id,
    api_key=config.api_key,
    base_url=config.base_url,
    use_responses_api=False,
    stream_usage=True,
    timeout=transport.timeout if transport is not None else config.timeout,
    max_retries=config.max_retries,
    **runtime_options,
)
```

- **What:** 显式连接建立通用 OpenAI 兼容模型。
- **Why here:** 仅构造实例，工具绑定留到 Agent 当前轮次（agent_runtime/langchain.py:L158-L166；SDK factory.py:L1483-L1491）。
- **Assumes:** 供应商接受工厂与 SDK 转换后的参数。唯一当前 preset 是 Kimi Code 的 `https://api.kimi.com/coding/v1` / `kimi-for-coding`（model_connections/presets.py:L17-L25）；本次未付费调用验证供应商。
- **Establishes:** SDK 不会自动切 Responses API（SDK base.py:L2012-L2014）；重试次数使用明确 config，默认 0（llm/config.py:L14）。
- **Depended on by:** 通用 Agent 的 function tools、SSE、usage 与 CI 的 tool_choice 均依赖这个 OpenAI 协议客户端。

**Cross-Function Dependencies:**

- **Caller `model_session`（internal）：** L43-L46 管理 HTTP 客户端生命周期，硬编码 `httpx.Timeout(60, connect=10)`，因此通过此入口时 config.timeout 不生效。这与 config.py:L13 的“HTTP 客户端覆盖”注释一致；是否未来需要自定义 timeout 是 Open Question，不是本次漏调用的已证原因。
- **Caller `execute_agent`（internal）：** agent_runtime/langchain.py:L158-L166 将 external_tools 与 middleware 提供给 create_agent，未设置 response_format。工具定义来自 snapshot；资源为空时初始 external tools 为 []（L160）。
- **Callee `ChatOpenAI`（external-source-available）：** 本地已安装 langchain 1.4.7 / langchain-core 1.6.13 / langchain-openai 1.7.2 / openai 3.31.0 / httpx 0.28.1，与 backend/uv.lock 的 L1105-L1106 / L1138-L1139 / L1174-L1175 / L1649-L1650 / L858-L859 一致。SDK 源码均在 `backend/.venv/lib/python3.12/site-packages/`。
- **Callee `_get_bound_model`（external-source-available，langchain/agents/factory.py）：** 当前通用路径未用结构化输出；每轮初始 ModelRequest.tool_choice=None（L1581-L1591），工具列表非空时 `bind_tools(final_tools, tool_choice=request.tool_choice, **request.model_settings)`（L1483-L1491）；平台 ModelExecutionMiddleware 只 override messages，未设置 tool_choice/model_settings（agent_runtime/middleware.py:L46-L73）。默认 SDK 工具使用选择没有被平台覆盖。
- **Callee `external_tools`（internal）：** 从每个 snapshot MCP binding 建立 StructuredTool，name=exposed_name、description=description、args_schema=input_schema，末尾添加 read_tool_result（agent_runtime/tool_calls.py:L28-L59）。MCP 原始操作名通过 system prompt 目录映射到哈希化调用名（agent_runtime/langchain.py:L30-L56）；工具实际调用名由 tools/contracts.py:L66-L73 稳定生成。
- **Callee `ChatOpenAI.bind_tools`（external-source-available）：** 每个工具经 convert_to_openai_tool 转换（base.py:L2553-L2555），随后绑定 `tools=formatted_tools`（L2614）。仅 `parallel_tool_calls is not None` 才发并行开关（L2545-L2546）；仅 truthy tool_choice 才发 choice（L2573-L2599）。因此当前通用 Agent 请求没有 tool_choice，也没有 parallel_tool_calls，未强制调用工具且未禁止并行；此结论由下述真实 SDK 请求捕获实证。
- **Callee `_get_request_payload` / `_astream`（external-source-available）：** 普通 Chat Completions 请求合并默认参数、tools 和 messages（base.py:L2031-L2060）；`max_tokens` 被 ChatOpenAI 改写为 `max_completion_tokens`（L3834-L3845）；stream_usage=true 导致 `stream_options.include_usage=true`（L2168-L2172），随后 OpenAI SDK async_client.create(**payload)（L2198）。本次捕获请求正是这些字段。
- **Callee SSE 解析（external-source-available）：** base.py:L554-L590 从标准 `delta.tool_calls` 提取 name/arguments/id/index；langchain_core/messages/ai.py:L672-L684 合并 tool_call_chunks，L555-L571 将 JSON 参数解析到 tool_calls/invalid_tool_calls；SDK factory.py:L2021-L2032 将所有 pending calls 分发到 tools。下述串行/并行探针均证明已完整走到平台 tools.client_factory 的 invoke。
- **Response validation（internal）：** ModelExecutionMiddleware 在 `finish_reason=tool_calls` 却没有 tool_calls、存在 invalid_tool_calls 或非预期 finish_reason 时失败（agent_runtime/middleware.py:L81-L94）；没有“转换出错后回退裸文本回答”的分支（L124-L141）。标准上游 tool_calls 没有被平台丢弃的证据。
- **Normal answer completion（internal+SDK）：** SDK 明确在 AIMessage.tool_calls 为空时结束循环（factory.py:L2016-L2019）；平台只要求最终 AIMessage 无 tool_calls 且有非空正文（agent_runtime/langchain.py:L210-L212）。另有 narrow URL read verifier（L215-L221；tool_results.py:L124-L148），对没有明确 URL 的“查看 LangChain 最新版本文档有什么新功能”不建立外部证据要求。要求此类任务必须外部取证的宿主执行不变量：nothing found。
- **CI caller difference（internal）：** ci_diagnosis/executor.py:L193-L206 第一轮 tool_choice=required，预算用完为 none，其他为 auto；这是独立专用循环，不会自动作用于通用 Agent。相同工厂因此并不阻碍上层选择 required。
- **Shared state：** 工厂不读写全局连接状态，返回模型仅实例拥有 SDK 客户端（factory.py:L13-L33）。

**Offline Probe Evidence:**

- 文件：`/tmp/niuma-mcp-audit-20261030/probes/test_model_wire.py`；运行命令：`PYTHONPATH=/Users/minjo/workspace/niuma-crew/backend:/Users/minjo/workspace/niuma-crew/backend/tests /Users/minjo/workspace/niuma-crew/backend/.venv/bin/python -m pytest -q -s /tmp/niuma-mcp-audit-20261030/probes/test_model_wire.py`（cwd=backend）。首轮 3 个路径通过；追加强制用户提示与失败后虚假完成对照后，结果 `5 passed, 1 warning in 2.65s`。警告为 langchain.mcp beta。
- 范围：真实 API→隔离 SQLite→装配目录→Agent→真实 LangChain/ChatOpenAI/OpenAI SDK；MCP discovery/invoke 为 `Context7Fixture`，模型 HTTP 为 httpx.MockTransport。目录仅为合成的 Context7-shaped `resolve-library-id` 与 `query-docs`，不是已连接账号或真实 Context7 的当日目录；允许域名使用测试假 URL，无外网、无付费模型。
- `wire-direct.json`：用户请求“请查看 LangChain 最新版本的文档有什么新功能。”；捕获请求包含两工具的完整名称映射、description、input schema 以及 read_tool_result；没有 tool_choice/parallel_tool_calls。假上游只输出“LangChain 最新版新增了虚构功能。”并 stop，平台 Run=succeeded、1 次模型请求、0 次 MCP invoke、0 个 tool_call action。证明平台当前接受此行为；不证明真实模型选择不调用的概率。
- `wire-explicit_direct.json`：用户明确要求“必须使用 Context7 查询 LangChain 最新文档再回答；禁止凭记忆回答。”，断言该文本确实进入当前 HTTP 模型请求；上游仍直接输出虚构功能并 stop，平台 Run=succeeded、1 次模型请求、0 个工具 action。强 prompt 没有转化成宿主强制调用不变量。
- `wire-sequential.json`：上游依次 resolve-library-id→query-docs→回答；两次工具参数 JSON 分两段 SSE 返回。3 次模型请求、2 个工具 action、两个 name/arguments 完整达到 MCP fixture，工具结果通过 tool_call_id 回到下一轮；Run=succeeded。
- `wire-parallel.json`：同一轮上游输出两个工具调用，各自参数分片。2 次模型请求、2 个工具 action、两项 id/args 完整；Run=succeeded。此探针只证明并行协议与路由，不证明依赖 resolve 结果的 query 在真实任务中适合并行。
- `wire-error_then_claim.json`：resolve 成功，query-docs 实际返回标准工具 `error`，随后模型声称“我已经成功查询并阅读 Context7 的 LangChain 最新官方文档，新增功能 A。”；最终 Run=succeeded、3 次模型请求、2 个工具 action，其中 1 个 status=failed，末轮请求确实包含 query failed 错误文本。说明“调用过工具”或“工具调用数>0”不能作为完成取证的充分后置条件；服务已把 MCP status 转为 failed（tools/service.py:L554-L588），中间件也保留 failed 工具状态（tool_calls.py:L256-L265），但最终交付只检查正文而未对取证成功作普遍校验（langchain.py:L210-L221）。
- 串行和并行第一轮 SSE 加入 `reasoning_content`，后续模型请求均不包含该字段。SDK 文档和实现明确只处理 OpenAI 标准字段（base.py:L1-L11，L554-L590）。这证明通用适配器不保留该字段；是否目标 Kimi Code 模型要求回传它仍未知。

**Open Questions:**

- 用户发生问题的真实 Run 是否有工具定义、装配账号、上游响应、工具 actions 和服务 instructions：本子任务不读正式数据库与密钥，未知；探针仅证明当前代码路径可以接受无证据直接回答。
- Kimi Code 当前 endpoint 对 `max_completion_tokens`、`stream_options.include_usage`、tool_choice、parallel calls 的兼容性与 thinking/tool reasoning 回传要求未知。本地代码无供应商专用适配；供应商拒绝参数会经 classify_error 显示 upstream_stream_error（llm/errors.py:L14-L25），不是已证“成功却没有调用”的原因。
- SDK `delta.tool_calls` 提取遇缺 function/index 时 `except KeyError: pass`（base.py:L568-L580）；本次只验证标准 OpenAI SSE，没有证据真实上游发送非标准结构。平台 finish_reason=tool_calls 缺调用时有拒绝（middleware.py:L89-L94）；若非标准上游又报 stop，是否静默只保留正文需另行协议探针，不能归因实际案例。
- 工具描述语义、原始名哈希化以及 prompt 优先级会影响模型自选概率，但本探针用受控模型，不衡量遵从率；不存在由本子任务证明的“换 prompt 即解决”结论。

## `capture_tools` in backend/app/agents/tool_grants.py (L207-L266)

**Purpose:** 把员工配置中的工具许可解析为本次发起者的无凭据调用身份，并冻结本轮注册给 Agent 的工具目录、工作区模式与恢复策略。普通对话准备在 `conversations/preparation.py` L140-L152 调用它，返回的 `bindings` 是 `snapshot.tools`，`agent_runtime/tool_calls.py` L28-L55 仅为其中的 MCP 项创建 `StructuredTool`。本记录仅基于源码阅读；未读取开发或正式数据库、密钥，未调用外部服务，未执行测试。

**Inputs & Assumptions:**

- `db`：调用方持有的 SQLAlchemy Session；受信任基础设施。`conversations/service.py` L97-L98、L149-L151 在输入接收事务中调用准备流程；本函数不提交或写入数据库（本文件 L207-L266）。
- `agent_id`：半受信任员工标识。调用前 `ConversationPreparation.prepare` 通过 `configured_agent` 检查存在、启用及绑定大脑（`preparation.py` L68；`agents/service.py` L539-L546）。本函数本身不重复检查。
- `user_id=None`：半受信任身份标识。普通对话入口实际传入已解析 Actor 的 `user_id`（`conversations/service.py` L149-L151）；本函数不验证身份真实性。若省略，个人模式不能解析出调用者自己的连接（L340-L355）。
- 数据库中 grant 和 approved catalog 的字段结构正确：`apply_grants` 只从已确认目录写入 `name` 与 `descriptor_hash`（L159-L173），`ToolService.approve` 校验输入 schema（`tools/service.py` L488-L517）；本函数直接索引目录字段，运行时不再校验形状（L221-L225、L257）。直接数据库写入时维持 JSON 内部字段形状的检查：`nothing found`；ORM 的 `AgentToolGrant.tools`、`ToolConnection.approved_catalog` 仅声明为 JSON（`agents/models.py` L123；`tools/models.py` L31）。
- 已确认目录不含凭据：发现保存时 `save_candidate` 对已解析秘密进行字符串检查（`tools/service.py` L435-L443）；本函数不读取或解密凭据（L207-L266）。远端描述文本整体可信：`nothing found`；它们作为目录数据保存并进入绑定（L227），MCP 服务说明的提示段声明不得改变平台权限（`agent_runtime/langchain.py` L69-L73）。
- 用户意图必须调用某项工具：本函数没有 `content` 或任务输入，`nothing found`。它只冻结许可，不选择本次任务调用工具（L207-L266）。

**Outputs & Effects:**

- 返回 `(bindings, workspace, resumable)`；绑定保留目录中全部字段，并增加员工、发起者、grant/账号/目录修订、调用名、范围及缺账号标志（L226-L251、L266）。
- 没有数据库写入、网络请求、凭据解密或用户可见事件；代码路径只查询并构造本地值（L207-L266）。
- 返回超过 128 个工具或序列化绑定超过 262144 字节时抛 `tool_snapshot_limit`，错误正文仅说明工具数量上限（L264-L265）。
- 本函数不会报告跳过了哪些 grant/tool；所有成功分支最终只返回保留项（L213-L225、L266）。

---

**Block-by-Block:**

```python
# L208-L214
bindings = []
described_connections = set()
workspace = {"mode": "virtual"}
resumable = True
for grant in grants_for(db, agent_id):
    if not grant.enabled:
        continue
```

- **What:** 初始化默认状态，仅处理启用 grant。`grants_for` 按 grant ID 排序查询员工的全部许可（L68-L75）。
- **Why here:** 后续所有目录与身份解析均位于启用检查之后（L215-L251）。
- **Assumes:** 调用方已验证员工和发起者；依据见输入部分。
- **Establishes:** 停用 grant 不产生工具、服务说明或工作区设置；无工具时默认虚拟工作区且允许恢复（L210-L214、L266）。
- **Depended on by:** 后续 `snapshot.tools` 和工具注册均不会看到停用 grant（`preparation.py` L145-L152；`tool_calls.py` L30-L32）。

```python
# L215-L221
template = require_connection(db, grant.tool_connection_id)
connection, personal = resolve_account(db, grant, user_id)
pending = connection is None
connection = connection or template
if not template.enabled:
    continue
catalog = {item["name"]: item for item in connection.approved_catalog}
```

- **What:** 加载模板，解析共享/个人实际账号；解析失败时回退模板目录并标记待连接；模板停用时跳过整个 grant。
- **Why here:** 必须先决定账号，才能选择对应账号已经确认的目录（L221）。
- **Assumes:** 模板存在。ORM 外键为 RESTRICT（`agents/models.py` L119-L121），正常删除先检查 grant 引用（本文件 L86-L103；`tools/service.py` L368-L376）；若不存在，`require_connection` 抛 `tool_connection_not_found`，不静默忽略（`tools/service.py` L58-L62）。
- **Establishes:** 不使用他人的个人账号；未解析账号时使用模板的工具定义供模型触发连接提示，非远端调用（`resolve_account` L334-L367；`tools/service.py` L528-L537）。
- **Depended on by:** `auth_required`、`connection_id` 和后续调用拒绝分支（L231、L237；`tools/service.py` L528-L537）。
- 共享模式只在模板为明确 shared 时返回模板（L338-L339）；模板启用检查由本函数 L219 完成，凭据和服务启用检查延后到实际调用（`tools/service.py` L73-L90、L378-L401）。
- 个人模式优先读取 `(user_id, grant_id)` 显式绑定；没有绑定且调用者是模板创建者时使用模板（L340-L355）。缺连接、非本人、服务不符、连接停用、需要认证但无密文，或者任意 grant 工具摘要不兼容，统一返回 `(None, personal)`（L356-L366）。这些原因没有单独保存在绑定中（L226-L251）。
- 模板停用即使解析出另一可用个人连接也跳过该 grant：启用条件读取的是 `template.enabled`（L219-L220）。没有事件或理由进入输出（L266）。
- 此处不读取 `McpService.enabled`；服务停用检查在实际动作的 `assert_connection`（`tools/service.py` L82）。

```python
# L222-L225
for selected in grant.tools:
    item = catalog.get(selected["name"])
    if not item or item["descriptor_hash"] != selected["descriptor_hash"]:
        continue
```

- **What:** 只保留原始名称仍存在且摘要与员工许可完全相同的工具。
- **Why here:** 在构建绑定前匹配许可，避免把新目录定义自动授给员工。
- **Assumes:** grant 的摘要表示管理员明确选择的定义。`apply_grants` 比较请求的 expected_descriptors 与批准目录后生成 values（L162-L173）。
- **Establishes:** 新增工具不会自动出现，改名/移除/摘要变化的旧工具不会进入本轮绑定（L222-L225）。
- **Depended on by:** `external_tools` 不会注册被跳过项（`tool_calls.py` L30-L55）；`_tool_instructions` 无 tools 时直接返回空串（`langchain.py` L30-L32）。
- 缺项或摘要变化均静默 `continue`，返回值无不可用状态或原因（L224-L225、L266）。账号修改会清空 approved_catalog（`tools/service.py` L339-L350）；作为实际/回退目录的连接为空时所有所选工具自然落入该分支。

```python
# L226-L241（省略纯复制字段）
binding = {
    **item,
    "auth_required": pending,
    "personal_binding_id": personal.id if personal else None,
    "personal_binding_revision": personal.revision if personal else None,
    "binding_id": digest([grant.id, item["name"]]),
    "connection_id": connection.id,
    "config_revision": connection.config_revision,
    "credential_revision": connection.credential_revision,
    "catalog_revision": connection.catalog_revision,
}
```

- **What:** 复制原始描述并冻结身份与许可的修订依据。实际代码还保存 agent/user/account_mode/grant/revision/kind（L228-L241）。
- **Why here:** 后续可把调用关联到确定 grant/tool，且不把凭据送入快照。
- **Assumes:** `item` 中无秘密，依据和边界见输入部分；`digest` 对稳定排序 JSON 求 SHA256（`tools/contracts.py` L9-L12）。
- **Establishes:** binding ID 依赖 grant ID 与原始工具名，而不是本次解析出的连接；真正调用名另外依赖连接 ID（L234、L248-L250）。
- **Depended on by:** `authorize_tool` 通过 binding ID 选快照条目（L288-L296）；`assert_binding` 检查 grant 修订、发起者、当前账号及个人绑定修订（L305-L330）。
- `catalog_revision` 被保存（L240）；`assert_connection` 对目录逐工具摘要及 instructions hash 检查，不直接要求 catalog_revision 相等（`tools/service.py` L73-L90）。

```python
# L242-L250
"server_instructions": connection.approved_instructions
if not pending and connection.id not in described_connections
else "",
"instructions_hash": digest(connection.approved_instructions),
"tool_name": item["name"],
"scope_policy": grant.scope_policy,
"exposed_name": item["name"]
if connection.kind == "native"
else exposed_name(connection.id, item["name"]),
```

- **What:** 每个实际连接只附带一次已批准服务说明；缺个人账号时不附带服务说明，但保留摘要。外部名称由连接 ID + 原始名 SHA256 前 16 位构成（`tools/contracts.py` L66-L73）。
- **Why here:** 多工具共享说明时去重，调用名隔离同名工具。
- **Assumes:** 模型能够使用原始名字与哈希调用名之间的映射；系统提示显式写 `operation`→`call_name` 数据（`langchain.py` L33-L46）。理解该映射并正确选择工具的保证：`nothing found`，需模型行为验证。
- **Establishes:** 本函数不附带服务名称、服务描述、连接展示名称或中文别名；`**item` 是协议目录字段（`tools/adapters/mcp.py` L33-L43）。
- **Depended on by:** `external_tools` 将 exposed_name、原始 description、input_schema 放进 `StructuredTool`（`tool_calls.py` L48-L55）；`_server_instructions` 将非 pending 说明加到系统提示（`langchain.py` L59-L74）。
- `auth_required` 不被追加到 StructuredTool 描述，也不在 `_tool_instructions` 的 operations 映射中（`tool_calls.py` L48-L55；`langchain.py` L33-L46）。模型第一次请求时并没有从这些入口收到明确的逐工具账号缺失状态；只有调用后 `ToolService.call` 产生 `tool_auth_required` 失败结果（`tools/service.py` L528-L537）。

```python
# L252-L263
if connection.kind == "native":
    workspace = {
        "mode": connection.public_config.get("workspace_mode", "virtual"),
        "connection_id": connection.id,
    }
    if binding["recovery"] == "never" or workspace["mode"] == "sandbox":
        resumable = False
else:
    resumable = False
bindings.append(binding)
described_connections.add(connection.id)
```

- **What:** 原生连接指定工作区；有任何外部工具，或原生工具不可重放，或沙箱工作区，均禁用 checkpoint 自动恢复；加入绑定并标记说明已处理。
- **Why here:** 只让真正通过目录过滤的工具影响工作区和恢复策略。
- **Assumes:** 至多一个启用原生工作区；`apply_grants` L169、L198-L201 强制该规则。直接数据库写入时该规则的数据库检查：`nothing found`（`agents/models.py` L110-L129）。
- **Establishes:** 即使外部工具为 pending，仍将 `resumable=False`；若所有工具被过滤，默认 `True` 保留（L217、L224-L225、L259-L261）。
- **Depended on by:** `preparation.py` L145-L152 把值写入 `checkpoint_resumable`。沙箱准备另有就绪校验（`preparation.py` L141-L144）。

```python
# L264-L266
if len(bindings) > 128 or len(json.dumps(bindings, ensure_ascii=False).encode()) > 262144:
    raise InvalidInputError("tool_snapshot_limit", "每轮最多装配 128 个工具。")
return bindings, workspace, resumable
```

- **What:** 在所有工具装配之后执行全局数量及字节上限。
- **Why here:** 依据实际解析后的目录大小检查，而不是 grant 选择数量。
- **Assumes:** JSON 可序列化；来自持久化 JSON 和普通标识/修订字段（L227-L251）。
- **Establishes:** 正常返回的绑定数量 ≤128 且 JSON 字节数 ≤262144。
- **Depended on by:** `ConversationPreparation.prepare` 直接使用返回值，不再次补入跳过项（`preparation.py` L140-L152）。

---

**Cross-Function Dependencies:**

- Callee `grants_for`（internal，L68-L75）：查询指定员工全部许可并按 ID 排序；本函数负责启用过滤。Callee `require_connection`（internal，`tools/service.py` L58-L62）：缺连接抛错，不返回 None。
- Callee `resolve_account`（internal，L334-L367）：native 返回模板；shared 需明确共享；personal 需本人、同服务、启用、必要凭据存在、全部所选摘要匹配；失败统一 None，不发生远端调用。个人绑定写入口在 `personal_tools.py` L51-L97 检查本人连接、同服务、启用与全部定义兼容，使用预期个人绑定修订。
- Callees `digest`、`exposed_name`（internal，`tools/contracts.py` L9-L12、L66-L73）：稳定 JSON 摘要与隔离调用名，无外部调用。
- Caller `ConversationPreparation.prepare`（internal，`preparation.py` L131-L152）：CI 分支不调用本函数，普通聊天调用并放进 snapshot；用户标识来自 `conversations/service.py` L149-L151。`execution/admission.py` L85-L100 对 snapshot/messages 做 deepcopy 后落 Run。
- Consumer `external_tools`（internal，`tool_calls.py` L28-L59）：只注册返回的 MCP 项，外加结果分段阅读工具；工具绑定给 `create_agent`，以及系统提示的原名映射与服务说明（`langchain.py` L158-L166）。没有按本轮自然语言需求进一步筛选的路径。
- Invocation consumer `authorize_tool`/`assert_binding`（internal，L269-L331）：检查所调用定义、grant 活性、修订、账号身份；pending 且仍无账号时允许进入返回连接失败结果的分支；pending 后账号已有连接则要求新任务（L319-L322）。非 pending 最后进入 `assert_connection` 复核连接/凭据修订、服务启用、描述摘要和说明摘要（`tools/service.py` L73-L90）。
- Invocation consumer `ToolService.call`（internal，`tools/service.py` L527-L588）：pending 在 L528-L537 直接返回失败，无远端调用；其他路径复核绑定、构造客户端、比对远端当前定义后调用。MCPClient 每次真实调用重新读取工具目录与说明，并核对目标定义摘要/说明摘要，之后 guard 再执行（`tools/adapters/mcp.py` L136-L162）。stdio 复用会话，继承该 invoke（`tools/adapters/stdio.py` L22、L91-L95）。
- Shared state：`ToolService.update` 身份/密钥或配置变化清空 MCP 批准目录与说明（`tools/service.py` L339-L350）；approve 发布候选并增加目录修订（L513-L519）；apply_grants 维护明确许可（本文件 L134-L204）；个人连接绑定不改员工许可（`personal_tools.py` L88-L97）。
- Invariant coupling：权限冻结决定模型可调用集合；逐动作授权决定该集合现在是否仍允许执行；两者均不证明模型已调用工具。系统提示要求匹配外部操作时使用工具（`langchain.py` L40-L44），本函数没有任务意图与成功调用证据输入（L207）。

---

**Open Questions:**

- 本次 Context7 实例是否真的进入当轮 `Run.config_snapshot.tools`，tools description/input_schema、server instructions、账号模式和目录摘要实际是什么？未读正式数据，未知；需用户授权的脱敏 Run 取证或隔离配置复现。
- 模型不调用时，是否有其他中间件/发布检查强制通用“查最新文档”证据？本函数无此职责。`verify_web_reads` 仅在 `requested_web_reads` 返回明确目标 URL 时继续检查（`tool_results.py` L124-L148），Context7 与“最新版本”意图需根代理继续检查。
- 对“模板停用/目录清空/目标摘要失效导致工具被过滤”的运行状态，其他前后端入口是否提供用户可见诊断？本函数及其 prepare/registration 链未发现；这里只能确认本轮 snapshot 不保留这些原因（L213-L225、L266）。
- `auth_required` 首次不显式告知模型是否是有意的 lazy auth 契约？现行文档明确描述“模型实际请求工具时才返回失败”（`docs/reference/mcp.md` L51-L55），对应测试用 ScriptedModel 预先安排工具调用后断言收到 tool_auth_required（`tests/test_mcp_accounts.py` L50-L90）。该测试不证明自由选择工具的模型会主动调用或知道应提示连接。
- 以 service/connection 元信息识别 Context7 是否依赖工具 description 或 server instructions 中恰好包含名称？`capture_tools` 不显式提供服务名称，只有原始 operation 映射与说明（L226-L251；`langchain.py` L33-L46、L59-L74）；需根代理结合真实/替身描述核对。
- 已追完的上下文预算事实：准备阶段 `size` 在 capture_tools 前只计系统提示、用户文本和 CI 指引（`preparation.py` L83-L89、L140），但真正模型调用前 `ModelExecutionMiddleware` 会计入实际 system message、messages 和 convert_to_openai_tool(request.tools)，再检查 `context_bytes`（`agent_runtime/middleware.py` L60-L64）；因此不能把“工具 schema 未计入最终上下文限额”作为事实。准备阶段历史裁剪是否给工具预留空间仍需另查。

## `capture_tools` in backend/app/agents/tool_grants.py (L187-L246)

**Purpose:** 在接受运行的事务里，把共享员工工具许可转换成针对本次使用者的冻结工具目录、工作区方式和恢复标记。调用方是 `backend/app/conversations/preparation.py:L140-L152`。

**Inputs & Assumptions:**

- db：调用方Session；本函数不新建事务、不提交、不请求上游。
- agent_id：已通过 configured_agent 的员工ID（preparation.py:L68）；user_id 来自提交者身份（参数L66与调用L140）。
- grant：数据库中员工许可，由 apply_grants 写入已批准工具名称/描述hash和scope（tool_grants.py:L114-L184）。对直接损坏JSON grant记录的单独读取校验：nothing found。
- 连接目录：来自 approved_catalog，结构依赖工具批准路径；本函数用name构造索引，没有重做完整目录schema校验（L201）。

**Outputs & Effects:**

返回 `(bindings, workspace, resumable)`（L246）；结果含账号依据、修订、scope、工具schema/说明及元数据，但本函数不取 encrypted_credentials，不解密、不调用MCP。返回目录是否可实际调用还由动作时授权检查决定（L249-L311）。

---

**Block-by-Block:**

```python
# L188-L205
bindings = []
described_connections = set()
workspace = {"mode": "virtual"}
resumable = True
for grant in grants_for(db, agent_id):
    if not grant.enabled:
        continue
    template = require_connection(db, grant.tool_connection_id)
    connection, personal = resolve_account(db, grant, user_id)
    pending = connection is None
    connection = connection or template
    if not template.enabled:
        continue
    catalog = {item["name"]: item for item in connection.approved_catalog}
    for selected in grant.tools:
        item = catalog.get(selected["name"])
        if not item or item["descriptor_hash"] != selected["descriptor_hash"]:
            continue
```

- **What:** 按ID读取员工许可；停用许可/模板不捕获，工具定义摘要不再匹配的单项跳过。未绑定个人账号时，用模板描述构建待连接目录。
- **Why here:** 描述发现与真实凭证调用分开；尚无个人账号不必在接受消息时发起外部请求。
- **Assumes:** resolve_account 区分native、显式shared与personal，校验同一服务、连接拥有者、启用、凭证存在以及工具摘要（L314-L347）。
- **Establishes:** 当前每个输出item都匹配grant记录的已批准描述；pending被显式标记。
- **Depended on by:** 后续冻结 auth_required；真实动作不会把模板账号自动共享给使用者。

```python
# L206-L231, selected fields
binding = {
    **item,
    "agent_id": agent_id, "account_mode": grant.account_mode, "user_id": user_id,
    "auth_required": pending,
    "personal_binding_id": personal.id if personal else None,
    "personal_binding_revision": personal.revision if personal else None,
    "binding_id": digest([grant.id, item["name"]]),
    "grant_id": grant.id, "grant_revision": grant.revision,
    "connection_id": connection.id,
    "config_revision": connection.config_revision,
    "credential_revision": connection.credential_revision,
    "catalog_revision": connection.catalog_revision,
    "kind": connection.kind,
    # L222-L225 include one set of instructions per resolved connection and its hash
    "scope_policy": grant.scope_policy,
    # L228-L230: native name or namespaced remote name
}
```

- **What:** 把当前账号选择和所有许可检查所需标识冻结；同一连接的服务说明只放一份。
- **Why here:** 后续执行用这些身份比对，避免排队期间自动换新凭证、账号或工具定义。
- **Assumes:** `digest/exposed_name` 是稳定派生名（调用自tools.contracts）；本函数不因同名外部工具而共享binding_id。
- **Establishes:** 连接/许可/个人绑定分别有依据；服务说明hash即使未在当前binding重复正文也保存。
- **Depended on by:** assert_binding 比较grant和个人账号，再调用 tools.service.assert_connection 核对连接配置/凭证/工具摘要/说明hash（L285-L311；tools/service.py:L73-L90）。

```python
# L232-L246
if connection.kind == "native":
    workspace = {"mode": connection.public_config.get("workspace_mode", "virtual"),
                 "connection_id": connection.id}
    if binding["recovery"] == "never" or workspace["mode"] == "sandbox":
        resumable = False
else:
    resumable = False
bindings.append(binding)
described_connections.add(connection.id)
# Loop continues
if len(bindings) > 128 or len(json.dumps(bindings, ensure_ascii=False).encode()) > 262144:
    raise InvalidInputError("tool_snapshot_limit", "每轮最多装配 128 个工具。")
return bindings, workspace, resumable
```

- **What:** sandbox、不可恢复native操作及全部远程工具阻止自动恢复；限制工具总数及快照字节。
- **Why here:** 判断基于本轮最终捕获目录，远端只读声明不被视为纯函数证明（L240注释）。
- **Assumes:** 每员工最多启用一份native连接由 apply_grants:L149、L178-L181校验；本函数没有再统计native。
- **Establishes:** 完成返回的目录≤128项、JSON≤256KiB；为空时workspace仍virtual、resumable仍true。
- **Depended on by:** ConversationPreparation把resumable写入Run快照（preparation.py:L145-L152）。

**Cross-Function Dependencies:**

- `grants_for`（internal，L50-L57）按员工ID过滤并排序；`require_connection`（tools/service.py:L58-L62）不存在时报NotFoundError，不返回假连接。
- `resolve_account`（L314-L347）：native直接模板；shared只有template.account_scope=shared才返回；personal查询该用户binding或仅允许创建者默认模板。账号不满足条件返回(None, personal)，不是异常。
- `assert_binding`（L285-L311）：动作时重新比对grant启用/归属/修订与账号；pending仍无账号才保留pending，账号新增后要求重发任务。resolved真实连接还经assert_connection检查。
- `authorize_tool`（L249-L282）：先确定本轮绑定；结果读取保留源grant授权，普通调用还校验arguments范围。
- 调用上下文：ConversationPreparation负责模型、全员规则、技能、输入大小和整个快照，不在此函数决定（preparation.py:L59-L153）。

**Open Questions:**

- 已批准catalog的完整schema验证由tools模块负责，本记录只跟踪本函数依赖字段；未对所有供应商元数据协议逐项取证。
- 对直接数据库写入的不合法account_mode/tools JSON，当前本函数没有修复路径；其实际迁移/数据库约束覆盖由持久化审查汇总。

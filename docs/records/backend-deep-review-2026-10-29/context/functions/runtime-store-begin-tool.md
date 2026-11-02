## `RunStore.begin_tool` in backend/app/execution/store.py (L306–L355)

**Purpose:** 在任何真实工具执行之前，原子申请许可、处理已知历史结果、预留预算并写开始动作（L306–L355）。

---

**Inputs & Assumptions:**

- `id`：可信 Run 标识；`invocation` 是来自模型请求的半可信普通数据。key、绑定、名称、参数和技能身份由 ToolExecutionMiddleware L223–L233 建立，fingerprint 由 ToolInvocation 合约计算。
- `authorize`：受信闭包，由 RunControl.begin_tool L112–L118 注入同一 Session 的现行授权。
- 持久配置快照含本轮预算；接受时从已验证 RuntimeConfig 捕获（preparation.py L103–L128、L145–L151）。
- 并发竞争依赖 SQLite 写入资格：L308 先 reserve_writer 再读运行、历史动作和预算。

---

**Outputs & Effects:**

- 返回 ToolPermit，包含动作键、指纹，以及只读成功动作的可复用结果（L322–L329）。
- 新动作扣全局工具预算，技能读取额外扣技能预算，建立 RunAction 并推进版本；事务失败全部回滚（L339–L355）。
- 非运行、指纹冲突、未知非只读重放及预算不足均拒绝；不调用外部工具。

---

**Block-by-Block:**

```python
# L307–L312
with self.database.transaction() as db:
    reserve_writer(db, Run.__table__)
    row = require_run(db, id)
    if row.status != "running":
        raise ExecutionFailure("runtime_interrupted")
    binding = authorize(db)
```

- **What:** 在单写事务内检查状态和当前许可。
- **Why here:** 不能读后再竞争写锁，否则两次申请可能花同一份预算。
- **Assumes:** require_run 返回当前会话行；已读 queries.py L12–L17 建立存在性。
- **Establishes:** 只有运行中且仍获准的动作进入重放与扣费逻辑。
- **Depended on by:** 后续复用结果和新动作。

```python
# L319–L331
if prior is not None:
    if prior.safe_details.get("fingerprint") != invocation.fingerprint:
        raise ExecutionFailure("runtime_interrupted")
    if binding.get("recovery") == "readonly" and prior.status == "succeeded" and prior.result_payload is not None:
        return ToolPermit(prior.action_key, invocation.fingerprint, prior.result_payload)
    if binding.get("recovery") != "readonly":
        raise ExecutionFailure("tool_result_unknown")
```

- **What:** 同调用键先核对内容指纹；只读成功且有存档才直接重用，非只读未知不能重放。
- **Why here:** 缓存读取也先经过当前授权，不让历史许可替代现行许可。
- **Assumes:** binding.recovery 代表平台批准的恢复策略，不信任远端自称只读；capture_tools 对远端整体标不可恢复（tool_grants.py L238–L242）。
- **Establishes:** 重用结果不会重新发出外部操作。
- **Depended on by:** ToolExecutionMiddleware L235–L241 将 permit.cached 转回 ToolMessage。

```python
# L332–L343
count = sum(1 for action in db.scalars(select(RunAction).where(RunAction.run_id == id, RunAction.kind == "tool_call")) if action.safe_details.get("binding_id") == invocation.binding_id)
if count >= binding["scope_policy"].get("max_calls", 32):
    raise ExecutionFailure("agent_budget_exceeded")
self._reserve(row, "tool_calls")
if invocation.skill_id:
    self._reserve(row, "skill_reads")
```

- **What:** 每绑定与全局预算分别检查；成功和失败的尝试都占名额。
- **Why here:** 已发生但未成功的调用不能获得免费重试机会。
- **Assumes:** `_reserve` 根据冻结字段检查 count+1；store.py L190–L201 建立。派生结果读取使用 result: 绑定，有独立32次上限但共用全局预算，authorize_tool L262–L280 建立。
- **Establishes:** 新动作不会突破同事务当前预算。
- **Depended on by:** `_start_action` 与随后真实 handler。

---

**Cross-Function Dependencies:**

- `authorize_tool/assert_binding`（external-source-available）：绑定未更改、账号/连接/目录当前；技能读取另核对完整路径，普通参数按 scope 检查。
- `_start_action`（internal）：再次检查 running，限制重复 call_key，保留只读重试 attempt，分配唯一序号并建立父模型关联（L212–L265）。
- `ToolExecutionMiddleware._invoke`（external-source-available）：只在 permit 成功后调用 handler，完整结果通过 complete_tool 落盘后才回送。
- Callers：RunControl.begin_tool；共享表 Run/RunAction 也由恢复、停止、finish_action 操作，同库写事务保持顺序。

---

**Open Questions:**

- 远端工具返回值是否语义可信和上游操作是否产生未知副作用，需真实上游验证；此函数只建立调用许可与持久动作事实。

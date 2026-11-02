## `ToolExecutionMiddleware._invoke` in backend/app/agent_runtime/tool_calls.py (L195–L292)

**Purpose:** 把模型的一次工具意图接到宿主授权和真实工具，结果落盘后才交还 SDK。工具意图不等于已经执行。

---

**Inputs & Assumptions:**

- `request.tool_call`（不可信模型输出）：工具名、id 和参数由 SDK 结构化，但仍必须核对当前绑定和路径（L196–L232）。
- `handler`（可信 SDK 调用能力）：执行前由 self.hooks.begin_tool 取得许可；外部 MCP coroutine 还检查 ContextVar 对应绑定并在真实调用前 guard（L34–L41）。
- 当前 Run 的 prepared 技能、snapshot 工具和 resources 是宿主冻结输入；模型不能通过正文添加绑定。
- `read_tool_result` 的 result_id 不可信，先由 ToolResults.load 检查当前 Run 的 source 成员和原始绑定（L209–L214；tool_results.py L64–L80）。

---

**Outputs & Effects:**

- 返回 ToolMessage 或 SDK Command；可发生文件、沙箱或外部 MCP 操作。
- 成功/失败内容和结果元数据通过 complete_tool 保存。明确上游未知异常记 unknown，其他异常 failed；随后仍抛原异常，不假装返回成功（L274–L291）。

---

**Block-by-Block:**

```python
# L215–L234
skill = entry.skill if entry else resource_skill[0] if resource_skill else None
if skill is None and binding is None:
    raise RuntimeFailure(...)
invocation = ToolInvocation(...)
permit = await self.hooks.begin_tool(invocation)
```

- **What:** 技能文件、派生结果读取和普通工具分别映射到自己的许可标识。
- **Why here:** 模型对任意 `/skills` 或宿主路径的请求不能绕过授权。
- **Assumes:** begin_tool 同事务复核许可、预算和运行状态；store.py L306–L355 建立。
- **Establishes:** handler 前已成功持久开始动作或得到受许可历史结果。
- **Depended on by:** 缓存返回和真正工具执行。

```python
# L235–L244
if permit.cached is not None:
    return ToolMessage(content=permit.cached["content"], name=call["name"], tool_call_id=call["id"], status="success" if permit.cached["status"] == "succeeded" else "error")
token = _current_invocation.set(invocation)
try:
    result = await handler(request)
```

- **What:** 只读已保存结果不重发实际操作；新调用以 ContextVar 传递绑定身份。
- **Why here:** 外部 coroutine 不能被未经过宿主门禁的 SDK 路径调用。
- **Assumes:** cached payload 已被同事务授权验证，而不是仅信任本地字典；begin_tool 在所有缓存返回前先 authorize。
- **Establishes:** 工具执行与一份明确的 ToolInvocation 对应。
- **Depended on by:** _preserve_external 来源记录和最终 complete_tool。

```python
# L255–L265
artifact = message.artifact or {}
if isinstance(artifact, dict) and "platform_outcome" in artifact:
    external = artifact["platform_outcome"]
    status = external["status"]
    content, data, sources = await self._preserve_external(invocation, external["data"], status)
```

- **What:** 把实际 MCP 结果保存为不可变来源，并构造有界预览、游标和来源说明。
- **Why here:** 模型上下文不能无限接收远端内容，用户仍能下载原始资料。
- **Assumes:** 平台 artifact 由 external_tools 构造，L42–L44 建立；工具返回正文不直接控制 artifact 信任域。
- **Establishes:** 返回给模型的游标可追到本轮原始结果。
- **Depended on by:** 长结果继续读取和最终网页请求校验。

```python
# L274–L292
except asyncio.CancelledError:
    raise
except Exception as error:
    await self.hooks.complete_tool(permit, ToolOutcome("工具没有取得已确认结果。", ...))
    raise
finally:
    _current_invocation.reset(token)
await self.hooks.complete_tool(permit, outcome)
return result
```

- **What:** 取消交给宿主统一收束；其他故障保存安全状态；结果保存失败就不回送工具消息。
- **Why here:** 未持久化结果不能成为模型已取得证据的依据。
- **Assumes:** complete_tool 失败向外传播，不被 SDK 当作普通成功工具结果。实际存储故障测试证明 Run 不成功；全部第三方中间件未来行为不作假设。
- **Establishes:** ContextVar 无论成功失败都复位，正常返回一定发生在持久完成后。
- **Depended on by:** SDK 下一轮模型输入与取消后的动作一致性。

---

**Cross-Function Dependencies:**

- `ToolResults.load`（internal）：当前 Run 文件成员、原始来源绑定、结构化 envelope。
- `_preserve_external`（internal）：保存原始 envelope/提取来源，限制返回 JSON 大小；语义完整性不保证。
- `RunControl.begin_tool/complete_tool`（external-source-available）：原子开始、状态和结果保存；不允许已结束动作被覆盖。
- `handler`（external-source-available SDK + black-box 远端服务）：实际工具结果可能失败；不推定无副作用。
- Callers：awrap_tool_call；本地文件工具以 workspace_lock 串行，MCP 的本包装层允许独立执行；技能中间件还有自己的加载锁。

---

**Open Questions:**

- 任意第三方 MCP 结果所描述的事实是否成立，需要业务语义验证；此函数只保留来源与实际调用。
- 真实 stdio 子进程和远端沙箱停止的外部环境保证由资源模块另审。

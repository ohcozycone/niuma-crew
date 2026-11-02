## `MCPClient.invoke` in backend/app/tools/adapters/mcp.py (L136-L162)

**Purpose:** 在每次工具调用前重读当前目录和服务说明，核对当前许可依据，最后一次 guard 成功后才执行业务请求。

**Inputs & Assumptions:**

- `name` / `expected_hash`：来自宿主冻结的许可；hash 按 `descriptor` L35-L46 包含原始定义与 SDK 投影。
- `arguments`：模型不可信输入；调用者 ToolService.call L539-L540 先投影并 schema/scope 校验。
- `guard`：可信异步宿主回调，承诺在 awaited 时复核取消、许可和当前身份；本函数不拥有数据库。
- `expected_instructions_hash`：调用者 L554 设置的冻结说明摘要。

**Outputs & Effects:**

- 返回内容、artifact、status 三元组；未改变执行记录。
- 定义/说明变化时抛公开错误并附当前候选目录，ToolService.call L565-L568 将候选保存。

**Block-by-Block:**

```python
# L137-L141
async with self.session() as adapter:
    self.capture_instructions(adapter)
    tools = await self._tools(adapter)
```

- **What:** 握手后绕过目录缓存取得当前可见工具。
- **Why here:** 不能把批准时看到的定义当成远端永远不变。
- **Assumes:** 远端定义不能保证真实实现无变化；协议无法证明实现与说明一致。
- **Establishes:** 当前目录、说明及目标存在性。
- **Depended on by:** L142-L155 定义比对。

```python
# L142-L155
if current is None or current["descriptor_hash"] != expected_hash or (...):
    error.catalog = [value for _, value in tools]
    error.instructions = self.instructions
    raise error
```

- **What:** 任何目标删除、定义/说明变化都停止业务调用。
- **Why here:** guard 和远程执行之前先确认平台批准的操作含义。
- **Assumes:** 同次 list 与 invoke 之间远端仍可能变化；无上游版本原子调用能力，nothing found。
- **Establishes:** 平台发送的 name/schema 依据与当前声明一致。
- **Depended on by:** L157 的远端调用。

```python
# L156-L162
await guard()
value = await tool.ainvoke({"name": name, "args": arguments, "id": "upstream", "type": "tool_call"})
```

- **What:** 目录/网络等待后复核本地授权，然后解释 ToolMessage。
- **Why here:** 等待目录时发生撤权也不会发出工具请求；test_agent_foundations 的 preflight 撤权场景覆盖这点。
- **Assumes:** guard 返回与已经发送外部请求之间无法形成远端事务；在途请求不可撤回。
- **Establishes:** 最近一次可执行本地授权已通过。
- **Depended on by:** ToolService.call L578-L589 对结果脱敏、有界保存投影。

**Cross-Function Dependencies:**

- `session`（internal，L61-L107）：HTTP 受控连接、认证拒绝转公开错误、上下文退出关闭；stdio 子类替换为 Run 范围会话。
- `_tools`（internal，L109-L129）：绕过缓存；最多128项，转换后 catalog 字节/重名检查。
- `capture_instructions`（internal，L55-L59）：说明必须字符串且不超过16KiB。
- `guard`（internal callback）：宿主负责当前许可；本函数不代替 begin_tool 的原子预算记账。
- `as_langchain_tool` / `.ainvoke`（external-source-available）：工具转换及协议调用。

**Open Questions:**

- stdio 接收没有平台在原始 JSON 行解析前的大小闸门；SDK stdio.py L150-L156 累积行后解析。当前仅确认这个限制，未运行超大输出内存压力实验，也不据此宣称宿主已被耗尽。

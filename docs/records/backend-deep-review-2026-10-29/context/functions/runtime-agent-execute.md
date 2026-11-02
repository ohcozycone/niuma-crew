## `execute_agent` in backend/app/agent_runtime/langchain.py (L109–L232)

**Purpose:** 在冻结输入上运行或恢复真实 LangChain Agent，把可见内容通过普通协议交给宿主，完整验证后返回候选，正式业务发布不在此函数内。

---

**Inputs & Assumptions:**

- `input: AgentRequest`（半可信冻结数据）：来自 ConversationPreparation.execution；输入有固定 Run、消息、模型参数、预算、技能与工具。Agent 不接 ORM、Actor 或业务数据库（contracts.py L20–L31）。
- `hooks: RuntimeControl`（可信宿主能力）：声明 guard、动作、内容与存档接口，不公开 Store；具体实现由 RunControl 注入。
- `checkpoints` 是 bootstrap 创建的专用存档；`resources` 为受限资源操作，由 preparation.py L189–L205 按 Run 固定 owner/source/output。
- SDK 状态是否已完成不能从流结束推断；L172–L176、L205–L209 明确检查标记和 pending nodes。

---

**Outputs & Effects:**

- 返回 AgentOutput(text, usage, optional output_files)；可能产生模型/工具请求、SDK checkpoint、来源与输出文件，以及宿主动作与草稿（L154–L225）。
- 正式 Message 与 Run 终态由外部协调器/发布器负责；这里返回的是候选。
- 图预算异常统一成 agent_budget_exceeded；已知供应商错误转换稳定代码，其余异常保留（L226–L232）。

---

**Block-by-Block:**

```python
# L119–L136
prepared_skills = prepare_skills(snapshot["skills"], snapshot["selected_skill_ids"])
progress = RunProgress(snapshot["max_output_bytes"], snapshot["max_reasoning_bytes"], input.recovered_content)
backend = WorkspaceBackend(snapshot, prepared_skills, resources, sandbox_factory=sandbox_factory)
```

- **What:** 用同一份技能投影构建文件后端和加载校验器，用恢复进度延续展示预算。
- **Why here:** 技能检查的正文必须与模型实际读取的正文一致。
- **Assumes:** selected_skill_ids 属于快照目录，capture_skills 在接受时建立；prepare_skills L75–L78 对选定项索引。
- **Establishes:** 读取和中间件共用同一目录、包清单与激活集合。
- **Depended on by:** build_middleware、filesystem 工具和输出收集。

```python
# L154–L169
async with (
    checkpoints.writer(lambda run_id, reference: hooks.checkpoint_saved(reference)) as saver,
    model_session(input.config, max_tokens=snapshot["max_output_tokens"]) as model,
):
    agent = create_agent(...)
```

- **What:** 每次运行拥有自己的存档写入和受管异步模型 HTTP 客户端。
- **Why here:** 正常、异常或取消退出都会关闭本地资源。
- **Assumes:** 外部请求关闭后是否仍完成/计费无法由本地关闭证明；**nothing found** 能保证撤回远端已发生请求，契约也未承诺。
- **Establishes:** 本地客户端与存档的上下文生命周期明确。
- **Depended on by:** SDK 执行、取消、恢复。

```python
# L172–L176, L205–L212
if resumed and not state.next:
    if state.values.get("completed_run_id") != input.run_id:
        raise RuntimeFailure("runtime_interrupted")
# 新执行后重新从已落盘状态取最终消息和用量
if not isinstance(final, AIMessage) or final.tool_calls or not final.text.strip():
    raise RuntimeFailure("empty_response")
```

- **What:** 完成标记、Run 身份、无后续节点和最终非工具 AI 正文共同决定候选是否成立。
- **Why here:** 不将存档中的最后工具或未完成输出当作成功答案。
- **Assumes:** completed_run_id 由 aafter_agent 生成，middleware.py L143–L144 建立；模型文字不能自行写状态字段。
- **Establishes:** 恢复时可只补交可信完成候选，终态是否可发布仍由业务状态判断。
- **Depended on by:** 输出收集与返回。

```python
# L214–L225
await hooks.guard()
if resources is not None:
    await asyncio.to_thread(verify_web_reads, input.messages[-1]["content"], state.values.get("messages", []), ToolResults(snapshot, resources))
outputs = await asyncio.to_thread(backend.collect_outputs, state.values)
await hooks.guard()
return AgentOutput(str(final.text), usage, {"output_files": outputs} if outputs else None)
```

- **What:** 确认当前许可、窄网页阅读证据、输出收集，再次授权后返回。
- **Why here:** 文件收集或长结果检查期间也可能撤权，不能只检查模型开始。
- **Assumes:** 网页提取文本等同真实完整页面的证明：**nothing found**；verify_web_reads 只证明结构化来源和送模区间，tool_results.py L145–L181。
- **Establishes:** 候选具备当前代码支持的完成与资料范围依据；不是语义正确性认证。
- **Depended on by:** 协调器成功候选和最终事务授权。

---

**Cross-Function Dependencies:**

- `build_middleware`（internal-source-available）：模型上下文检查、原子开始动作、用量和技能实际激活。
- `_consume_agent_stream`（internal）：过滤仅模型节点 AIMessageChunk，完整模型结果保留在 SDK 状态。
- `WorkspaceBackend.collect_outputs`（internal）：有界文件收集；沙箱模式先停止工作负载，后收集普通文件。
- `CheckpointStore.writer`（internal）：SQLite 存档错误转 checkpoint_unavailable；on_saved 只通知引用。
- `create_agent/aget_state/astream`（external-source-available，已安装 SDK）：图语义由实际 SDK 测试覆盖，未证明全部供应商行为。
- Callers：准备器中的 execute 闭包；共享状态只有当前 Run 的 SDK 数据和注入资源，不直接共享业务 Session。

---

**Open Questions:**

- 真实供应商的额外 reasoning、原生协议或不标准流与当前适配是否一致，需逐供应商验收。
- Frontend 如何渲染最终 Markdown 不在该函数范围。

## `CiDiagnosisExecutor.execute` in backend/app/ci_diagnosis/executor.py (L24–L347)

**Purpose:** 对一个固定仓库的失败 GitHub 运行执行有界、可引用的诊断，返回专业候选，不自行发布业务报告。

---

**Inputs & Assumptions:**

- `input.snapshot[ci]`（半可信冻结事实）：仓库、运行 id、技能正文、关系和凭证指纹来自 CiDiagnosisService.capture，service.py L73–L102。
- `hooks`、`save_diagnosis`（可信注入能力）：持续现行授权、动作和专业进度；进度服务拒绝 report/delivered/feedback、终态和超量，service.py L138–L173。
- 外部元数据、job 和日志不可信。id/attempt/completed/failure 在 L88–L95 校验；job 所属 run/attempt 在 L119–L123 校验。
- 固定专业预算来自当前 CI 契约：4 模型轮、2 份日志、最多5次 MCP业务调用，代码 L61–L62、L181、L232–L239 建立；不是普通聊天 model_calls 计数。

---

**Outputs & Effects:**

- 返回 `(rendered_text, usage, result)`，result.phase 为 ready_to_publish（L342–L347）。
- 模型前主动读元数据/job 列表；模型只选已枚举失败日志；所有网络等待在数据库事务外。
- 分阶段保存专业过程和来源、实际动作与用量。报告结构/引用有界重写，最终失败则无成功候选。

---

**Block-by-Block:**

```python
# L59–L78
async def call(tool, args):
    await guard()
    if len(result["calls"]) >= 5:
        raise ExecutionFailure("ci_budget_exceeded")
    # 保存意图 → 持久开始动作 → 真实 mcp.call → 完成动作和进度
```

- **What:** 把每个 MCP 业务调用绑定现行许可、固定总量和动作证据。
- **Why here:** 单独握手不等于每次业务读取都获准。
- **Assumes:** mcp.call 只允许固定三种方法，mcp.py L97–L99 建立；参数由本函数构造，不交给模型任意填写 owner/repo。
- **Establishes:** 模型能影响的是失败 job 选择，而不是任意仓库/URL。
- **Depended on by:** 元数据、列表、日志和结束复查全部共用此路径。

```python
# L88–L136
attempt, status = find(metadata, "run_attempt"), find(metadata, "status")
# 校验目标后，仅从本run/attempt的失败job建 failed 字典与 coverage
```

- **What:** 固定调查批次、SHA 和失败 job 白名单，记录第一页是否完整。
- **Why here:** 不混用重跑后的日志或来自其他运行的 job。
- **Assumes:** 已知 MCP 包装中的字段能由 find 找到，mcp.py L114–L128 递归首个匹配字段；真实上游结构稳定需环境验证。
- **Establishes:** 后续日志允许列表和报告目标有明确批次。
- **Depended on by:** 读取工具枚举、日志 job 校验、最终 target/coverage。

```python
# L181–L206, L231–L250
for round_number in range(4):
    await guard()
    # 限上下文；首次required，日志用完强制none；核验工具名、job、去重和call id
```

- **What:** 每一轮前检查当前权限和上下文，限制调用内容、日志数与模型轮数。
- **Why here:** 文本“请用日志”不足以建立实际取证，首轮未产生工具请求会在 L308–L309 失败。
- **Assumes:** 模型工具请求不会绕过代码检查。实际 handler 参数由 L252–L261 固定；即使模型要求未知 job，也在网络调用前拒绝。
- **Establishes:** 当前日志 budget 已花费和未读取 job 可确定记录。
- **Depended on by:** 模型下一轮输入、报告覆盖计算。

```python
# L263–L306
text = find(raw, "logs_content")
# 非空校验 → redact → 尾部16384字节 → 固定S编号/散列 → 带行号的ToolMessage
```

- **What:** 保存模型实际可引用的有界脱敏快照，原始日志被截断就明确标记。
- **Why here:** 引用行号必须对应保存并送模的相同文本，不能引用未取得内容。
- **Assumes:** redact 能识别所有业务秘密的证明：**nothing found**；report.py L16–L27 只去已知 ANSI、私钥、GitHub token 和 Authorization 模式，契约也承认局限。
- **Establishes:** source id/job/sha/行号可追溯。
- **Depended on by:** validate_report 与最终确定性引用展示。

```python
# L310–L325, L331–L347
draft = validate_report(Draft.model_validate_json(text), result["sources"])
# 不合格在剩余轮数内追加纠正要求；最终复查attempt/head_sha，补coverage并返回候选
```

- **What:** 形式和引用校验后再复查远端调查批次，程序计算覆盖范围。
- **Why here:** 模型不能决定自己“调查了多少”；也不能在目标已变化时混合交付。
- **Assumes:** 有效行号就证明解释语义正确：**nothing found**；validate_report 只核 job/source/行范围/覆盖，report.py L30–L49。
- **Establishes:** 候选具备格式、来源范围和本次目标一致性依据。
- **Depended on by:** PublishRun 调 publish_diagnosis，再次检查报告并与 Message/Run 同事务交付。

---

**Cross-Function Dependencies:**

- `GitHubMCP.initialize/call`（external-source-available）：固定HTTPS端点、协议和工具白名单，响应有界；真实服务为 external-black-box，未请求。
- `model_session`（external-source-available）：受管 AsyncClient，关闭重定向/环境代理，默认无SDK重试。
- `validate_report/render/redact`（internal）：来源一致性和确定性展示，非语义裁判。
- `save_diagnosis`（external-source-available）：专业状态字段/大小/运行状态和双版本原子推进。
- Callers：ConversationPreparation.execution 的专业 execute 分支；共享状态只有本 Run 的专业进度和宿主动作，CI 不自动恢复重放。

---

**Open Questions:**

- 当前真实 GitHub MCP 的包装结构、日志保留情况和 token 许可未连接验收。
- 模型诊断净省时、根因准确率需真实样例评测，代码形式校验不能回答。

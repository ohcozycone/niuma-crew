# 最终证据失败的展示边界与历史来源信息

日期：2026-10-30。范围：只读代码；真实 SDK + 隔离测试库/假模型探针；未读取正式库、未真实调用模型/MCP。此补充不把“过程可见”直接定性为缺陷。

## 结论

1. 最终证据核验前，普通模型生成文字可以被公开读取为 `content_state=draft`，前端在主正文位置展示并标“生成中”；这是当前明确设计。是否某次实际 SSE 在最终失败前采样到该草稿，取决于生成和轮询时序。
2. `external_read_unverified` 后，正式 Message 正文为空，主正文不会继续保留被否定结论；页面标“执行失败”，显示“未发布模型声称的读取结论”错误。原文字仍保存在模型步骤，用户可展开“执行过程 → 本轮过程文字”查看。
3. 因此，当前证据不足以把该路径单列为“失败结论仍被发布”的 finding。它是有状态区分的草稿/过程展示；核验失败终态的正式正文确实被清空。
4. “无 URL 查新、零调用仍成功”的回复会进入后续模型历史，其“已逐条核实”表述以纯助手正文保留，没有可用于鉴别该表述来源的工具证据/状态 metadata；这可作为主缺陷的影响扩散事实，不证明它造成下一轮幻觉，也不宜单独把正常的正文历史策略列为缺陷。

## 运行、持久化、读取、UI 链路

| 环节         | 已确认行为                                                                                                                                           | 代码证据                                                                                                                            |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| 普通执行策略 | `publish_partial=True`；只决定故障时显式 `partial_text` 可否作为正文候选，不等于将所有过程草稿发布成正式正文                                         | preparation.py L241；execution/contracts.py L40-L43；coordinator.py L103-L109/L133-L134                                             |
| 流式过程     | SDK 模型片段交 `hooks.report_content`；RunControl 缓冲，由 watcher 按 flush_interval 写入仍 running 的模型步骤                                       | langchain.py L87-L98；control.py L106-L107/L144-L148；coordinator.py L41-L58；store.py L151-L176                                    |
| 完整模型响应 | middleware 在最终业务证据核验前 `hooks.finish(...content=...)`，模型动作完成与完整正文持久化                                                         | middleware.py L107-L119；control.py L81-L95；store.py L274-L304；langchain.py L203-L221                                             |
| 活动回复投影 | ACTIVE 时选择最新无 tool_calls 模型步骤 output_text；有非空文本则 `draft`，尚未写 Message.body                                                       | queries.py L94-L121；writes.py L68-L74                                                                                              |
| REST         | 生产实际读取入口为 `/api/conversations/{id}/responses/{response_id}`；`/api/runs` 是历史测试适配，正式应用没有此兼容路由                             | api/routes/conversations.py L158-L162；tests/scenario_client.py L1-L5/L43-L56                                                       |
| SSE          | 使用同一 queries.response；版本增长发 `response.snapshot`，终态发 `response.finished` 后退出，不转发未经持久化 token                                 | api/conversation_streaming.py L48-L64                                                                                               |
| 前端接收     | 两类 SSE 事件共用 receive；后端 reply.content 直接映射到本条消息，不从 model steps 自行选择正文                                                      | lib/api/conversationTransport.ts L78-L98；lib/api/conversations.ts L254；conversationState.ts L181-L195                             |
| 草稿 UI      | 主正文 Markdown 使用 active 流式模式；状态标题在 draft 时“生成中”，不是“已完成”                                                                      | ConversationMessage.tsx L63-L70；lib/api/conversations.ts L255-L264                                                                 |
| 证据失败     | verify_web_reads 抛 RuntimeFailure，未附 partial_text；coordinator 将 text 设为空并以 failed 发布；publisher 将内容交给 Message.body=content or None | tool_results.py L180-L181；contracts.py L83-L86；coordinator.py L122-L134/L153-L163；publication.py L33-L54/L77；writes.py L90-L105 |
| 终态 UI      | read_response 终态从 Message.body 取 content，不退回步骤文字；空内容 content_state=empty；主区域“本次没有生成文本”加失败状态/具体错误                | queries.py L94-L130；ConversationMessage.tsx L63-L79；lib/api/conversations.ts L111-L118；execution/errors.py L52                   |
| 过程保留     | 未核验文字仍是已成功返回的模型步骤 output_text；整次执行默认折叠，非活动/正文不相同则可展示子项“本轮过程文字”；顶层仍标执行失败                      | RunActions.tsx L34-L40/L210-L218/L234-L268                                                                                          |

当前契约明确允许活动草稿、成功正文和其他终态允许片段/空串；普通故障只能保留执行器明确给出的片段（docs/reference/runtime.md L41-L59）。现有 UI 没有把运行中草稿明确写成“未核验”，使用的是“生成中”；这是现行状态用语，不足以单独证明违约。

`ChatMessage.published` 当前含义是终态，而非 content_state=complete：读取与更新均设置 `!isActive(status)`（api/conversations.ts L92-L99；conversationState.ts L182-L191）。因此 `ConversationMessage.tsx` L73-L75 的“未完成的输出”分支对常规终态 partial 不会出现，但后端失败 error 会附“已保留未完成的输出”（queries.py L124-L127）。本次证据失败是 empty，与该 partial 标签问题无关；未把它列入本审查 finding。

## 隔离探针

脚本：`/tmp/niuma-mcp-audit-20261030/evidence/test_output_projection.py`。

命令：

```sh
PYTHONPATH=backend:backend/tests backend/.venv/bin/python -m pytest -p conftest /tmp/niuma-mcp-audit-20261030/evidence/test_output_projection.py -q
```

结果：`2 passed in 0.51s`。使用现行 conftest 隔离迁移库、假模型和真实 SDK。没有业务代码改动。

第一项在 verify_web_reads 入口读取同一个公开投影，再让原始核验执行，最后读取终态/SSE：

| 时点       | status  | content_state | 主 content                             | steps[0].output_text              |
| ---------- | ------- | ------------- | -------------------------------------- | --------------------------------- |
| 核验前     | running | draft         | 我已经读取网页，网页介绍虚构的新功能。 | 同左，model_call status=succeeded |
| 核验失败后 | failed  | empty         | 空                                     | 仍保留原文字                      |

终态 SSE 为 `response.finished`，携带 empty content 与 `external_read_unverified`。这证明可读草稿状态和最终隔离，不证明用户在某次真实运行中必然看到失败前草稿；本探针没有运行浏览器实际渲染。完整公开结果：`evidence/output-projection.json`。

## 历史 provenance：可以证明与不能证明的内容

- 新 Run 的历史仅选 `Run.status == succeeded` 的完整 user/assistant 对，按数量和字节预算裁剪（queries.py L182-L211）。所以明确 URL 核验失败的文字不会进入后续模型历史。本探针在其后提交“继续”，冻结 input_snapshot 仅含当前 user，已断言通过。
- 对无 URL 查新，假模型零工具声称“我已经查过官方文档并逐条核实”，当前检查接受成功；后续“展开说明功能甲”的 input_snapshot 含三条普通消息，其中第二条是上述助手文字，键只有 id/role/content。完整证据 `evidence/history-provenance.json`。
- execute_agent 将它构造为普通 AIMessage；ModelExecutionMiddleware 保留批准历史，工具状态提示仅提醒历史答复对工具可用性的判断不能代表当前（langchain.py L182-L187/L41-L43；middleware.py L48-L59）。后续模型输入没有此历史回复的“零工具调用/未核实”标记；实际动作仍可供 UI/后端独立审计，不能说平台没有保存 provenance（store.py L70-L90；queries.py L122；RunActions.tsx L247-L275）。
- 可证明影响：该未经工具核实的断言会被后续模型看见，而输入本身不携带鉴别其核实依据的数据。
- 不能证明影响：这必然使模型继续胡编、一定优先于 system prompt、或是这次 LangChain 首轮零调用的原因。上述因果需要真实模型对照评测，当前探针只验证数据流。

## 是否独立 finding

- 草稿提前可见/失败过程保留：不独立列。失败被明确表示，正式正文为空，过程文字有独立入口和标签，符合现行草稿/过程契约。
- 纯正文历史缺少逐条来源 metadata：不独立列。它体现主问题的后续影响；直接修复点仍是“外部查新/显式工具要求未核实却被接受成功”，否则给历史补标签也不能修复首轮假核实。

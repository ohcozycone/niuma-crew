# 对话执行过程展示

| 项目     | 内容                                                                                                                                          |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| 设计状态 | 已采纳（2026-10-24）                                                                                                                          |
| 实施状态 | 已实现；验证见[会话重构记录](../records/conversation-state-management.md)                                                                     |
| 范围     | 基于现有 Run / RunStep，不增加 commentary 或模型调用                                                                                          |
| 关联     | [状态管理](conversation-state-management.md)、[现行运行契约](../reference/runtime.md)、[现行对话交互](../reference/conversations.md#前端交互) |

## 消息布局与组件职责

助手消息先展示整次执行的可折叠摘要，再展示流式或最终回答。摘要收起显示运行状态、已知耗时与实际步骤数；零步骤不显示空过程。展开按真实 sequence 呈现模型、工具和技能加载；没有预设的“思考、工具、结论”固定三段式。

官方 shadcn/ui Base UI 组件提供 Message / Bubble、Trace / TraceCollapsible、Input Group 和 Message Scroller。保留官方组合方式，样式复用当前主题语义令牌；不保留旧 AI Elements 包装层。Markdown 由独立 Streamdown 组件渲染。

## 数据来源

| 内容               | 来源                                                   |
| ------------------ | ------------------------------------------------------ |
| 整次执行状态与耗时 | Run.status、started_at、finished_at                    |
| 执行摘要           | step_count、current_activity，均读取真实持久化步骤     |
| 模型记录           | kind=model_call，轮次来自 safe_details.round           |
| 可展开的模型思考   | reasoning_text / reasoning_truncated；没有内容则不显示 |
| 工具记录           | kind=tool_call，公开的 tool/name 及真实状态            |
| 技能加载           | kind=skill_activation，单独显示，不伪造工具            |
| 中间轮文字         | output_text，保留在对应模型步骤                        |
| 回答正文           | 活跃非工具轮次的草稿，终态以 assistant_content 替换    |

工具请求意图不等于开始执行，模型调用完成不等于 Run 成功。工具详情只显示既有公开字段，不公开原始参数、内部路径、技能全文或 ToolMessage。失败、停止和中断均保留独立状态，不映射为成功。

## 查询与折叠

后续[统一读取增量](conversation-message-state.md)采用 history 返回正文与全部公开步骤、SSE 更新相同 Run 结构。步骤展示只读取已有状态并本地分页，折叠和翻页不发请求；正文没有变化的取消也通过终态快照同步步骤。

外层折叠不会销毁内层展开选择，行以 step.id 为 key。最终正文不在模型过程里重复显示。普通聊天重启后可继续同一 Run，重连只读，不自动重试。

## 验证入口

[RunSteps 测试](../../frontend/src/pages/conversations/RunActions.test.tsx)、[会话 hook 测试](../../frontend/src/pages/conversations/useConversationController.test.tsx)、[真实 SDK 流式测试](../../backend/tests/test_runtime_streaming.py)。视觉和实际验收进入 records；替身验证不代表已测试真实上游模型。

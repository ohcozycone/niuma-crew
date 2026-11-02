# 对话状态与执行过程展示

| 项目     | 内容                                                                                                                          |
| -------- | ----------------------------------------------------------------------------------------------------------------------------- |
| 设计状态 | 已采纳（2026-10-24）                                                                                                          |
| 实施状态 | 已实现                                                                                                                        |
| 范围     | 普通对话消息、Run、提交、停止、重试、重连及执行记录；保留现有专用入口                                                         |
| 关联     | [对话契约](../reference/conversations.md)、[运行契约](../reference/runtime.md)、[展示方案](conversation-execution-display.md) |

## 接口与状态

会话状态和命令由局部协调器管理；公开访问经后续[双入口改造](conversation-hooks.md)收敛为 useConversation/useMessage。会话负责消息顺序、历史和提交恢复，消息负责指定回复的状态和操作；Provider 接收 ID、transport 和身份隔离存储键，不读取路由或导航。

本轮使用局部 reducer，不引入 Zustand、Provider 或跨页面缓存。输入和技能选择留在 Composer。快照按 revision 拒绝重复或乱序数据，全文替换。历史消息保留引用，正文和过程各有更新边界。

## 提交与恢复

新草稿本地分配稳定 UUID 并立即打开，首条请求携带 agent_id，原子创建业务 Conversation 和 Run。未确认提交保存原始输入及幂等键，刷新先只读核对，显式 retry 使用原键；挂载和 reconnect 不提交工作。现有 UUID 列足够，无须迁移或重置数据库。

status 为 loading、ready、submitted、streaming。断线不把 Run 改成失败，也不解除忙碌状态。停止等待服务端确认；提交中的停止意图确认接受后再执行。retry 仅重试未确认请求，或末次 failed/cancelled/interrupted Run。普通聊天重启续跑仍使用原 Run；成功答案重新生成不属于本轮。

## 组件与主题

采用官方 shadcn/ui Base UI 的 Message、Message Scroller、Trace / TraceCollapsible、Input Group，移除旧 AI Elements 接入。Streamdown 独立渲染 Markdown。组件交互保留官方结构，视觉接入项目语义令牌，继承已有字体、日夜颜色、圆角和焦点。

助手消息先显示可折叠执行过程，再显示草稿或最终正文。过程按实际步骤排序，reasoning 有内容才展示。不增加 commentary、进度上报工具或额外模型调用。模型中间文字仍使用 output_text，不冒充 commentary。

后续[统一读取增量](conversation-message-state.md)已将历史正文与步骤放入同一次响应，SSE 使用相同 Run 结构；步骤只读取已有状态并在组件内部分页。步骤数量、执行时间与活动来自实际持久化步骤。

## 实施与验收

后端补首次接受、幂等请求查询、步骤数量及活动摘要，保留权限、事务、checkpoint 和持久化 SSE。前端提取 hook、纯合并规则、订阅和步骤读取，页面组合界面。

验收覆盖重复快照、未知提交、同键重试、取消竞争、断线、StrictMode 清理、切换会话迟到响应、分页、终态同步、Markdown 安全和日夜/窄屏。现行规则已同步 reference，实际验证见[验收记录](../records/conversation-state-management.md)。

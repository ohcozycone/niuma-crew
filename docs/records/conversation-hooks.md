# 会话与消息双入口验收

源码链接已按当前位置修复；本文保留记录时的名称和结论，当前行为以现行契约为准。

日期：2026-10-25。范围为当前工作区的会话 Provider、useConversation/useMessage、消息读取投影、现有停止/重试/复制及页面接入。未新增点赞、分享、收藏或后端接口，未修改业务表和 checkpoint 存储。实施依据见[方案](../proposals/conversation-hooks.md)，当前调用与边界见[模块说明](../../frontend/src/pages/conversations/README.md)。

## 实际变更

ConversationProvider 在当前页面按会话 ID 与身份存储键创建作用域，内部协调器复用已有 history/SSE、命令幂等与恢复。Context 传递稳定实例，layout effect 只发布已提交的读取投影。两个公开 Hook 使用 useSyncExternalStore 读取会话或单条消息快照，多次消费不重复初始化网络。

useConversation 公开消息 ID 顺序、元信息、历史与 phase，负责发送、重连、待确认提交的原键重发和停止意图。useMessage 显式接收消息 ID，公开正文、执行 status、步骤、用量、执行错误、消息操作状态和绑定 ID 的停止/重试/复制。null 或未加载 ID 返回空消息，不请求、不追随最新记录；省略 ID 为无效调用。首轮实现提供 activeMessageId、latestMessageId 和 latestAssistantMessageId，同日字段精简见下文。

页面列表按 ID 渲染，消息组件内部读取。步骤分页改为私有展示逻辑；已有气泡反馈、Markdown、Trace、CI 报告与复制按钮继续接入。提交错误、连接错误、消息操作错误和 Run 执行错误分别保存。历史窗口仍保持连续性，读取索引覆盖最新与当前历史窗口；元信息和历史跨过新任务接受时间时，协调器补齐消息页。

## 实际验证

| 检查               | 结果                                                                              |
| ------------------ | --------------------------------------------------------------------------------- |
| 前端 Vitest 全量   | 33 文件、291 项通过                                                               |
| make lint-frontend | ESLint、TypeScript 与 Prettier 通过                                               |
| 后端定向接口测试   | test_conversation_message_state.py、test_conversation_submission.py，共 10 项通过 |
| make build         | 生产构建与压缩资源生成通过；仍有既有 Markdown/语法高亮大分块提示                  |
| make check-docs    | 当前链接、锚点和索引检查通过                                                      |

[消息入口测试](../../frontend/src/pages/conversations/useMessage.test.tsx)验证多个消费者只加载一次并共享一条订阅，正文片段不改变列表或无关消息快照；null/未加载/省略 ID 行为；历史定位后的消息读取；活动消息读取补齐；停止 pending 与执行状态分离；失败重试新增回答并保留原步骤；过期操作拒绝；复制读取当前正文；消息卸载不关闭订阅；StrictMode 与身份切换释放旧作用域；未知提交原键重发及错误隔离。

[协调器回归](../../frontend/src/pages/conversations/useConversationController.test.tsx)覆盖原有发送、停止意图、提交恢复、重连、取消失败、迟到 history、乱序与终态保护。页面、消息窗口、步骤、问题目录及全站现有前端测试同时通过。静态检查曾检出状态字段重命名遗漏与未使用绑定，均修复后复验通过。

## 未覆盖范围

未进行真实模型调用、浏览器视觉手验或高负载压测。后端只运行相关 10 项接口回归，未将既往全量通过记录作为本轮结果。SSE 仍为完整快照协议，本次不改变其带宽取舍。

## 同日字段精简复验

2026-10-25 按调用方显式传 ID 的边界，将定位字段精简为 lastMessageId。输入区直接读取 useMessage(lastMessageId)，执行状态及停止、重试资格由消息入口提供。历史窗口和执行结束均不改变 lastMessageId，重试接受后指向新消息。消息测试通过实际组合两个 Hook，验证停止确认、终态读取和元信息/history 跨接受时刻的补齐。

本次消息入口、协调器和页面的定向测试共 3 文件、37 项通过，make lint-frontend、make build 和文档检查通过；构建仍有既有大分块提示。全量测试为 287 项通过、4 项失败：ConversationOutline 两项仍查找“打开问题目录”按钮，当前组件已改为问题刻度入口；ConversationRuler 两项预期旧刻度位置，与当前 10px 间隔不符。两组件均不依赖本次修改的 Hook，未改动这两个模块及其测试。

文档检查使用 /tmp 下的 UV_CACHE_DIR，避免受限环境访问用户级缓存。没有后端改动，未重跑后端测试；未覆盖范围同上。

# 对话正文与步骤统一读取验收

源码链接已按当前位置修复；本文保留记录时的名称和结论，当前行为以现行契约为准。

日期：2026-10-24。范围是本次工作区中的消息 DTO、Run 投影、history/SSE 与会话 Hooks；使用临时 SQLite、假模型和前端测试替身，没有访问开发业务数据或真实模型。现行规则见[对话契约](../reference/conversations.md)、[运行契约](../reference/runtime.md)与[会话模块](../../frontend/src/pages/conversations/README.md)，实施依据见[增量方案](../proposals/conversation-message-state.md)。

## 实际变更

明确 Conversation 包含多条 Message，每条助手 Message 关联一个 Run，Run 包含多条 RunStep。消息使用 run 携带完整执行快照，替换平铺的执行摘要字段；history、命令响应、Run 查询与 SSE 共用公开投影。存储继续使用 checkpoint 与既有 RunStep，无数据库迁移。

会话入口改名 useConversationSession，观察连接改名 useRunSubscription。useRunSteps(run) 仅读取已有步骤并维护本地分页，不接收 open、revision 或 status，不再请求步骤接口。组件直接读取 message.run，删除 execution 摘要与当前模型覆盖步骤的二次拼接；未变化步骤保留对象引用。独立步骤 API 继续可用，前端已无调用入口。

## 验证结果

| 检查               | 实际结果                                                                                                                      |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| 后端 pytest 全量   | 首次 366 通过，17 项因沙箱禁止本机端口监听失败；允许本机回环监听后，这 17 项 checkpoint/进程测试单独全部通过，合计覆盖 383 项 |
| 前端 Vitest 全量   | 32 文件、276 项通过，其中对话及接口相关 9 文件、44 项通过                                                                     |
| make lint-backend  | Ruff 与格式通过                                                                                                               |
| make lint-frontend | ESLint、TypeScript 与 Prettier 通过；修正问题目录测试中已有的无效 getByRole exact 参数                                        |
| make build         | 首次清理 dist/assets 时出现 ENOTEMPTY，随后重跑通过；仍有现有 Markdown/语法高亮大分块提示                                     |
| make check-docs    | 路径、锚点及索引检查通过                                                                                                      |

[后端统一读取测试](../../backend/tests/test_conversation_message_state.py)验证：单页多个 Run 只批量查询一次步骤；102 条步骤完整返回；before/after/around 均携带正文和步骤；实时正文、思考与步骤处于同一版本；终态与 history 一致；重试步骤归属原助手消息；读取仍要求运行权限。

[会话测试](../../frontend/src/pages/conversations/useConversationController.test.tsx)验证：history 直接恢复正文和步骤，无额外 Run 读取；正文和步骤原子合并；重复、乱序、迟到 history 与终态回退处理；未变化行引用保留；断线读取完整快照恢复步骤。既有提交幂等、停止、重试、StrictMode 与切换会话隔离回归通过。[步骤组件测试](../../frontend/src/pages/conversations/RunActions.test.tsx)验证展开、流式更新、取消、嵌套折叠及超过 100 条的本地分页均无网络请求，过程文字继续按纯文本展示。

## 边界

没有进行真实模型调用、浏览器视觉手验或高负载带宽测试。SSE 仍采用完整快照，包含全部公开步骤后体积会增加；当前通过批量读取、既有保存间隔和执行预算控制成本，前端只重渲染变化的步骤行。本次没有引入 delta 或新的事件存储。

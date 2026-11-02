# 按运行链路阅读代码

从[运行观测指南](observing-runtime.md)在页面做一次操作，再用本页找对应入口。先弄清输入、写入、后台启动和最终提交各在哪，不必先读完全部文件。

## 先建立整体

1. 阅读[总体架构](../architecture/overview.md)、[后端职责](../architecture/backend.md)和[Agent 边界](../architecture/agent-runtime.md)。Conversation 保存持续对话，Message 保存一条输入或回复，Run 记录一次处理；它们各有不同生命周期。
2. 用[后端目录与职责](../architecture/backend.md#工程目录与应用包)和 [API 模块](../../backend/app/api/README.md)定位文件；业务含义以[现行契约](../README.md#现行契约)为准。方案目录中的旧目标树只代表设计时点。
3. 读 [bootstrap.py](../../backend/app/bootstrap.py)：看数据库、服务、Runner、SDK 存档如何装配，以及启动、恢复和关闭的责任。

## 一次配置保存

1. [useAgentDirectory](../../frontend/src/pages/agents/useAgentDirectory.ts) 读摘要；[useAgentEditor](../../frontend/src/pages/agents/useAgentEditor.ts) 按 ID 读完整详情并保存。目录不承担编辑草稿。
2. [客户端 agents.ts](../../frontend/src/lib/api/agents.ts) → [员工路由](../../backend/app/api/routes/agents.py) → [AgentService](../../backend/app/agents/service.py)。路由取得 Actor，服务检查操作权限；核对预期版本、技能和模型引用，以及员工和装配的同事务保存。执行期间的配置读取另见 [execution_config](../../backend/app/agents/execution_config.py)，它参与调用方事务，不要求配置管理权限。
3. [AgentStore](../../frontend/src/state/agents/agentStore.ts) 合并已保存摘要并更新受影响列表；[WorkspaceData](../../frontend/src/state/workspace/workspaceData.ts) 组合跨业务同步。[导航摘要](../../frontend/src/components/navigation/useNavigationSummary.ts) 与目录订阅同一数据。共享范围和接入方式见[状态模块](../../frontend/src/state/README.md)，编辑保护见 [useEditing](../../frontend/src/state/editing/useEditing.ts)。

## 一次发送与回复

1. [useConversationController](../../frontend/src/pages/conversations/useConversationController.ts) 固定幂等键并保存待确认记录；[API 客户端](../../frontend/src/lib/api/conversations.ts) 发 messages 命令。超时后先确认原请求，不重新生成键。
2. [router](../../backend/app/api/routes/conversations.py) → [ConversationService](../../backend/app/conversations/service.py)。接受事务调用 [preparation](../../backend/app/conversations/preparation.py) 捕获依据，保存输入、助手回复、Run 和关联；提交成功后才返回接受结果。
3. [scheduler](../../backend/app/execution/scheduler.py) 领取排队 Run，经 [coordinator](../../backend/app/execution/coordinator.py) 驱动；[authorization](../../backend/app/conversations/authorization.py) 组合当前会话、员工、方法和模型检查。运行不由 SSE 请求持有。
4. [RunControl](../../backend/app/execution/control.py) 和 [RunStore](../../backend/app/execution/store.py) 管预算、动作、取消和保存。[agent_runtime/langchain.py](../../backend/app/agent_runtime/langchain.py) 驱动 SDK，片段解析留在 [streaming.py](../../backend/app/agent_runtime/streaming.py)。模型开始前的授权、预算和动作在同一事务保存。
5. Agent 返回候选答案，[PublishRun](../../backend/app/conversations/publication.py) 再复核并原子写正文、输出文件关联、终态及占用释放。SDK 输出不等于已保存的成功结果。
6. [queries](../../backend/app/conversations/queries.py) 统一生成助手显示内容；[SSE](../../backend/app/api/conversation_streaming.py) 只读已提交快照；[useResponseSubscription](../../frontend/src/pages/conversations/useResponseSubscription.ts) 合并回复和对话范围版本；[useConversation](../../frontend/src/pages/conversations/useConversation.ts) 与 [useMessage](../../frontend/src/pages/conversations/useMessage.ts) 服务不同粒度的页面消费。

## 看完正常流程再读异常

依次查显式停止、断线、请求结果不确定、配置撤销、存储失败和进程重启。每次回答：谁发现、谁保存状态、哪一步之后禁止外部调用、刷新后从哪里恢复。对应测试从 [test_response_contract.py](../../backend/tests/test_response_contract.py)、[test_runtime_boundaries.py](../../backend/tests/test_runtime_boundaries.py)、[test_conversations.py](../../backend/tests/test_conversations.py) 和 [checkpoint 子进程测试](../../backend/tests/test_checkpoint_runtime.py) 进入。

工具链路继续读 [tools 三类服务](../../backend/app/tools/README.md)、[员工工具许可](../../backend/app/agents/tool_grants.py)和[本人账号绑定](../../backend/app/agents/tool_account_bindings.py)：区分账号维护、员工许可与一次实际调用。它们决定模型能执行哪些操作；产品管理 API 不会自动成为模型工具。原 CI 诊断试验已[退役](../reference/ci-diagnosis/README.md)，不再作为运行链路的学习入口。

# SQLite checkpoint 聊天接入方案

| 项目     | 内容                                                                                         |
| -------- | -------------------------------------------------------------------------------------------- |
| 设计状态 | 已采纳                                                                                       |
| 实施状态 | 隔离实验与正式 Conversation/Runner 已接入，行为已合入现行契约                                |
| 更新日期 | 2026-10-24                                                                                   |
| 范围     | 当前锁定 SDK、AsyncSqliteSaver、多轮消息、历史读取和进程重启恢复                             |
| 当前入口 | [现行运行契约](../reference/runtime.md)、[运行器模块](../../backend/app/execution/README.md) |

## 正式接入

采用 AsyncSqliteSaver，Conversation 固定 thread 并保存成功引用；Run 保存已接受命令、消息顺序、执行与公开存档引用及预算；移除 Message 正文表。普通聊天自动恢复同一 Run，CI 专业执行器继续保留中断后显式重试的边界。

存档使用业务库旁的独立文件，由 SDK 自管表，避免 Alembic 管理 SDK 结构，也避免 SDK 写入等待业务写锁而相互阻塞。异步执行使用 AsyncSqliteSaver，同步查询使用同包 SqliteSaver。完整消息保留、公开历史过滤、模型输入裁剪、提交间隙、授权及预算规则已经合入[运行契约](../reference/runtime.md#checkpoint历史与恢复)；迁移和双文件备份见[维护指南](../guides/backend-operations.md#数据库迁移)。

正式实现见[checkpoint 适配](../../backend/app/agent_runtime/checkpoints.py)、[对话查询](../../backend/app/conversations/queries.py)、[RunStore](../../backend/app/execution/store.py)和[进程回归](../../backend/tests/test_checkpoint_runtime.py)，结果见[接入验收](../records/agent-model-rebuild.md)。PostgreSQL、多进程领取、CI 图恢复、历史压缩及存档清理不在此增量。

## 执行起点精简

已采纳并实现。移除 `runs.base_checkpoint_id`：首次执行直接读取 `conversations.checkpoint_id`，恢复优先使用该 Run 的执行存档，历史继续读取公开输出存档。同一会话最多一个活跃 Run，且只有成功结束才能推进会话引用，因此执行期间的起点不会变化；本增量不增加历史起点重放能力。

通过新增正式迁移删除该列，不修改已生效的初始基线，不改动 SDK 存档。验收覆盖新旧库迁移与数据保留、多轮上下文、失败后继续、重启历史读取、执行中断恢复，以及图完成但业务尚未提交时的恢复。实际结果见[执行起点精简验收](../records/run-checkpoint-start.md)。

以下保留此前隔离实验的方案与复现入口；其简化 HTTP 接口不属于正式对话 API。

## 一次对话如何执行

1. 第一轮只提交“上海住宿标准多少？”。模型请求测试制度工具，工具返回每晚 500 元，模型据此回答；SDK 将消息和执行位置写入 SQLite。
2. 第二轮在同一 thread 只提交“住三晚呢？”。模型必须从已保存的工具结果取得每晚标准，回答三晚 1500 元。
3. 历史接口调用 aget_state，只返回用户消息及最终回答，不拼接历次 checkpoint，也不公开工具正文和请求工具时的中间文字。
4. 停止服务后，用同一个 SQLite 文件启动新的后端进程。新进程不调用模型即可读到原历史，再发送追问仍能使用原资料。
5. 另一条对话在工具结果已存盘、下一轮模型尚未完成时强制终止进程。重启后从 pending nodes 恢复；已存盘的工具结果应被复用，不能再次调用工具。

采用当前项目的 create_agent 和 astream，流模式保持 messages/updates、事件版本 v2。实验使用 sync 持久化模式，先确认存档可靠写入，再推进下一图步。没有模拟网络 token 原地续传：被中断的模型调用允许重新执行。

## 实验和业务的边界

实验只绑定本机地址，使用假资料，不提供真实账号、授权、Run 领取、取消或费用预算。恢复通过显式接口触发，用来证明重启后的新进程能继续图执行；正式 Runner 已实现自动发现和恢复，详见前述现行契约。

实验没有摘要或删除旧消息，历史保留完整原文。正式业务的模型输入裁剪、失败分支、幂等、提交间隙、授权与预算另由正式进程测试验证，不能由实验通过直接推断。

## 验收入口

运行 `make verify-checkpoint` 可重复验收。它启动新的后端子进程并用临时 SQLite 文件验证，不访问开发业务库。实现见[实验后端](../../backend/experiments/sqlite_checkpoint_chat.py)和[进程级测试](../../backend/tests/test_sqlite_checkpoints.py)，本次实际结果见[验收记录](../records/sqlite-checkpoint-chat.md)。

使用真实 AsyncSqliteSaver 和真实文件数据库，覆盖以下结果：

- 同一 thread 的两轮请求只传新消息，得到四条公开消息。
- 另一 thread 无法使用前一条对话的住宿资料。
- 读取历史不增加模型或工具调用次数，历史不含内部工具资料。
- 重启新进程后，历史保持原样并能继续追问。
- 工具结果已持久化后强制终止进程，恢复只调用未完成的模型节点。
- 已完成的 thread 拒绝重复 resume，不再调用模型。

实际命令、锁定版本、结果和未覆盖项写入验收记录。实验本身不修改业务库；正式初始基线直接采用 SDK checkpoint 保存完整消息，不设置业务消息表或旧数据导入路径，结果另见正式接入记录。

## 手动复现

运行 `make dev-checkpoint`，在另一个终端执行以下命令。同一 UUID 表示同一条对话，第二次发送只包含追问：

```bash
curl -s http://127.0.0.1:8001/threads/11111111-1111-4111-8111-111111111111/messages \
  -H 'Content-Type: application/json' -d '{"text":"上海住宿标准多少？"}'
curl -s http://127.0.0.1:8001/threads/11111111-1111-4111-8111-111111111111/history
curl -s http://127.0.0.1:8001/threads/11111111-1111-4111-8111-111111111111/messages \
  -H 'Content-Type: application/json' -d '{"text":"住三晚呢？"}'
curl -s http://127.0.0.1:8001/threads/11111111-1111-4111-8111-111111111111/history
```

发送返回 202，需等历史中的 running 为 false、pending_nodes 为空后再发送下一轮。停止并重新运行后端，使用同一 CHECKPOINT_DB；历史读取无需再次发消息。

验证中途恢复时，以 `cd backend && uv run python -m experiments.sqlite_checkpoint_chat --db /tmp/niuma-checkpoint-recovery.sqlite --pause-after-lookup` 启动，发送第一问。历史出现 pending_nodes 为 model 后强制终止进程，去掉 pause 参数、使用同一数据库重启，再 POST `/threads/{thread_id}/resume`。没有待恢复执行或同一条对话仍在执行时返回 409。

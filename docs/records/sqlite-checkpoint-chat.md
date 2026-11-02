# SQLite checkpoint 聊天隔离验证

日期：2026-10-24。范围：本次新增的[实验后端](../../backend/experiments/sqlite_checkpoint_chat.py)及[进程级测试](../../backend/tests/test_sqlite_checkpoints.py)。设计见[最小验证方案](../proposals/sqlite-checkpoint-chat.md)。本记录不表示正式对话 API、Runner 或业务数据库已改用 checkpoint。

## 环境与方法

使用项目 Python 3.12 环境和锁文件中的 LangChain 1.4.7、LangGraph 1.2.16、langgraph-checkpoint 4.3.0、Deep Agents 0.7.30。新增开发依赖 langgraph-checkpoint-sqlite 3.1.2，其传递依赖为 aiosqlite 0.22.1、sqlite-vec 0.1.9；既有 SDK 版本未升级。

FastAPI 实验后端只绑定本机，使用临时 SQLite 文件和确定性假模型。模型在首轮请求测试制度工具；第二轮必须从恢复的工具消息中取得金额，不从模型实例保存金额。执行方式为 create_agent、astream 的 messages/updates v2 和 sync 持久化。历史由 aget_state 读取，过滤工具消息及请求工具时的模型中间文字，不另建 messages 表。

每次启动均为真实 Uvicorn 子进程。重启用新的进程、新的模型和新的 AsyncSqliteSaver 连接打开原文件；崩溃实验用进程 kill，不让正常关闭逻辑先做善后。

## 实际结果

运行 `make verify-checkpoint`，3 项进程级测试通过（2.52 秒）：

| 测试                         | 观察结果                                                                                                                                                                                                       |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 多轮、只读历史和 thread 隔离 | 首轮回答每晚 500 元；第二轮只传“三晚”追问，回答 1500 元；公开历史恰有四条消息，原消息 ID 保持不变。反复读取不增加模型或工具次数。另一 thread 没有前一条对话的制度资料。数据库只有 SDK 存档表，没有 messages 表 |
| 新后端进程读取与追问         | 停止首个进程，第二个进程读取同一 SQLite 后历史及消息 ID 不变，模型调用数仍为零；只发送追问即可继续，重启后调用模型 1 次、工具 0 次                                                                             |
| 强制终止与未完成执行恢复     | 工具结果已落盘、下一模型节点尚未完成时 kill；新进程读取到原 checkpoint 和 pending model；显式 resume 后得到完整回答，模型调用 1 次、工具 0 次，用户问题没有重复追加；完成后重复 resume 返回 409                |

`make lint-backend` 通过 Ruff 检查和格式检查；`make check-docs` 检查 130 份 Markdown、1516 个本地链接，错误为零。新增及修改的 Markdown 使用前端现有 Prettier 3.9.10、printWidth 100 格式化。

## 限制与后续

测试证明的是跨后端进程的 SQLite 持久化、历史读取和图节点恢复，没有调用真实供应商，也没有测量生产容量或并发写入性能。

恢复由实验接口显式触发；正式 Runner 尚未自动发现和恢复 Run。实验不覆盖账号和资源授权、冻结配置、模型与技能预算、取消语义、失败分支采用、业务提交对账或 SDK 技能中间件恢复。它使用自定义假工具，不代表现有 StateBackend 技能栈已经验证。

现行应用继续使用原 Message 表及重启标 interrupted 的规则。下一步可按聊天方案接入 Conversation/Run 引用和历史投影，并补齐上述业务故障验证。

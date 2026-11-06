# 对话内容与回复接纳

Conversation 保存交流归属，Message 保存输入和正式回复，ConversationRun 保存业务消息与执行 Run 的关联。Run 不是消息，对话不再拥有通用执行准备、授权组合或 Run 终态写入。

## 接受和历史

service.py 检查调用权限和对话归属，通过 execution/service 的同事务入口捕获合法固定配置和附件、选择成功接纳的线程基点，再登记工作。输入消息、空助手 Message、Run 与关联在同一事务提交。Run 由执行侧发号，空助手消息复用同一 ID，提供稳定的 response_id，失败重试沿用输入、新建 Run 和回复。

queries.py 提供消息、提问导航、快照和回复投影；摘要随快照及回复返回；页面历史只读取正式消息，不读取 SDK。正常追问新建 Run 并沿用稳定线程中已成功接纳的明确存档，只提交本次问题；没有续接基点时从本次输入开始；选定基点却缺失存档或线程不一致时明确拒绝，不导入 Message。知识历史复核及来源记录继续由 knowledge 的公开能力完成，详见[知识契约](../../../docs/reference/knowledge.md#员工个人装配与正式问答)。

员工个人页的完成轮数也由 queries.py 直接聚合，权限和所有者范围与合法历史一致；只有成功且已接纳的绑定计入，按原输入 ID 去重，不遍历消息正文或增加持久计数。统计接口和边界见[员工完成轮数](../../../docs/reference/conversations.md#员工完成轮数)。

## 两种完成

执行侧先保存完整成果和 Run 成功。acceptance.py 随后按持久关联，在自己的短事务复核当前许可，幂等保存正式正文、附件和处理时间并释放占用。临时错误记录尝试及下次处理时间，指数退避最长 60 秒；明确权限或资源拒绝记录为接纳失败。接纳不修改 Run 成功，不再次调用模型或工具。

回复的 status 表达执行事实，acceptance 表达 pending、accepted 或 failed。等待接纳时可以显示执行成果，但 content_state 为 draft；接纳后正文来自 Message。回复 version 组合执行修订和接纳处理版本，避免前端漏掉只改变接纳状态的更新。

取消由 service 核对对话和回复身份后调用运行公开操作，已经成功的 Run 不可再取消。SSE 只观察已保存内容，断线不取消工作，pending 时继续观察。完整接口和恢复边界见[运行契约](../../../docs/reference/runtime.md)及[对话契约](../../../docs/reference/conversations.md)。

## 文件职责

| 文件                   | 责任                                             |
| ---------------------- | ------------------------------------------------ |
| service.py             | 首次发送原子创建、提交、重试和准确目标的取消授权 |
| writes.py              | 参与当前事务的消息与关联写入，不自行提交         |
| acceptance.py          | 对话结果接纳、持久失败记录和恢复扫描             |
| queries.py、schemas.py | 合法历史和页面读取投影                           |
| models.py              | 对话、消息、业务关联与接纳处理字段               |
| files.py               | 对话附件可见性、下载和消息文件持有查询           |

员工配置、通用执行准备和当前授权分别见[配置捕获](../execution/snapshot.py)、[单次执行任务](../execution/runtime/task.py)、[授权组合](../execution/service.py)。实施及自审见重构报告。

## 执行详情入口

全局及员工历史通过日志弹窗查看执行证据。queries 核对 ConversationRun，再读取通用执行视图，并投影原问题、交付状态和同题尝试；不读取 checkpoint，不重新执行或接纳。列表 q 同时支持主题关键词及完整 Conversation ID、Run ID，后者可以命中旧尝试，并通过 matched_response_id 与最近回复分开返回；ID 查询继续应用原有所有者、员工及状态范围。见[契约](../../../docs/reference/execution-evidence.md)。

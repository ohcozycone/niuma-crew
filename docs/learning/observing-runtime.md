# 从页面逐步观察一次回复怎样完成

从页面入手可以建立整体认识。要看清完整机制，需要把一次操作继续追到数据库、后台执行和最终发布：页面说明用户想做什么，接口说明系统接受了什么，后台和持久记录说明实际发生了什么。

本流程对应当前实现，按由浅到深的顺序操作。先观察现有页面和历史，再发起模型或已装配工具的请求。真实调用会使用当前配置的上游服务；离线替身测试和真实上游的结果分别判断。

## 1. 准备三个观察位置

1. 打开应用，使用现有管理员账号登录。游客能浏览公开资源，不能提交工作或修改配置。
2. 打开浏览器开发者工具的 Network，勾选保留请求记录，筛选 `/api/`。先看方法、URL、状态码和响应，再看发起请求的前端文件。
3. 保留开发服务日志。正常由 `make dev` 启动；后台存活看 `/health`，执行服务能否接单看 `/ready`。当前地址和启动日志位置以本轮[实施记录](../records/platform-refactor-implementation.md)为准。

不要一开始同时打开所有模块。每一轮只跟踪一个用户动作，记下它的对话 ID、回复 ID 和请求键。配置页尚不需要理解 Agent 循环。

## 2. 先观察一个普通配置接口

进入员工目录，再打开一位员工的详情。

| 操作           | 应看到的请求                          | 观察重点                               |
| -------------- | ------------------------------------- | -------------------------------------- |
| 打开工作台     | configuration-summary 与有界收藏查询  | 外壳只需计数和链接，不读取所有指令     |
| 浏览员工目录   | GET /api/agents，游客为 public/agents | 分页、筛选、摘要字段；没有完整工作指令 |
| 打开员工编辑   | GET /api/agents/{id} 与当前方法选择页 | 详情才有完整指令、装配参数与修订       |
| 修改启停或收藏 | PATCH /api/agents/{id}                | 请求带预期修订，写入后目录和摘要刷新   |

只读观察时无需真的修改配置。如果选择修改，保存前记下原值，观察完恢复。

这条链路是：页面 → 局部 Hook → agents API 客户端 → API 路由 → AgentService → 数据库。路由解析 HTTP 参数和身份、转换响应；AgentService 检查操作权限，在事务内维护配置和装配规则。这里没有额外的 ApiAgentService 转发。

阅读入口：[useAgentDirectory](../../frontend/src/pages/agents/useAgentDirectory.ts)、[useAgentEditor](../../frontend/src/pages/agents/useAgentEditor.ts)、[agents 客户端](../../frontend/src/lib/api/agents.ts)、[员工路由](../../backend/app/api/routes/agents.py)、[员工服务](../../backend/app/agents/service.py)。

这一轮完成后，应能解释「为什么目录数据不能直接当成完整配置保存」以及「为什么每个 router 不必再配一个 service」。

### 按页面补齐其他模块

员工配置链路理解后，用同样方法补齐下面几组。每组先读取，再按需要观察一次保存；不必把相同的 CRUD 流程重复逐行阅读。

| 页面或操作           | 主要接口族与后端入口                                                                                                                                                                             | 需要新增的理解                                                                     |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------- |
| 登录、游客与退出     | /api/auth， [auth 路由](../../backend/app/api/routes/auth.py) → [AuthService](../../backend/app/auth/service.py)                                                                                 | Cookie 怎样变成 Actor，操作权限与资源归属为何继续检查；GitHub 跳转是另一种认证入口 |
| 技能目录与编辑       | /api/skills、/api/public/skills，[技能服务](../../backend/app/skills/service.py)                                                                                                                 | 摘要与指令详情分开，方法保存不等于员工已装配，也不授予外部工具权限                 |
| 大脑配置             | /api/model-connections，[连接服务](../../backend/app/model_connections/service.py)                                                                                                               | 保存不生成回答，连接检查与生成是不同调用，凭证与配置分别修订                       |
| 知识页的规章制度     | /api/organization-rules，[规则服务](../../backend/app/organization_rules/service.py)                                                                                                             | 预期版本与冲突，编辑影响后续接受；知识文档当前仍为静态教学内容                     |
| 侧栏、收藏与全局搜索 | configuration-summary、员工/技能分页查询，[导航 Hook](../../frontend/src/components/navigation/useNavigationSummary.ts) 与 [搜索组件](../../frontend/src/components/navigation/GlobalSearch.tsx) | 一个前端功能可以组合多个接口；目录与侧栏复用共享员工摘要及收藏查询                 |
| MCP 连接与工具清单   | /api/tools，[连接维护](../../backend/app/tools/connections.py)、[工具清单](../../backend/app/tools/catalogs.py)                                                                                  | 保存账号、读取和确认工具清单是不同步骤；确认后仍需员工许可和本人账号绑定           |

完整接口清单用后端 `http://127.0.0.1:8000/docs` 或 `/openapi.json` 查漏，类型看 schema，业务原因沿所属服务追踪。登录回调等协议入口可能不在 OpenAPI 页面展示，实际路由仍是依据。没有发请求的静态页面无需寻找不存在的后端接口。

每个操作写一行观测笔记：页面动作、请求方法/URL、关键 ID、路由、服务、读写的记录、事务何时结束、失败如何显示。先积累真实链路，再回头看目录树，容易发现哪些是页面组合、哪些是业务规则。

## 3. 先读一段现有对话

打开已有对话，观察 `GET /api/conversations/{id}/snapshot`。它一次返回：

- 当前对话摘要，包括 version、active_response_id、last_response_id；
- 当前员工的安全摘要；
- 最新连续消息窗口及分页游标；
- 提问数量和最近提问标识。

展开一条用户消息与一条助手消息。用户记录主要是原文和顺序；助手读取结构还带处理状态、正文完整性、步骤、错误与用量。

助手的 `id` 就是 `response_id`，也是助手 Message 的 ID。公开接口不要求你先找到内部 Run。`content` 已经由服务器选好，`content_state` 区分 empty、draft、complete、partial；`status` 单独说明是否还在处理。

历史翻页使用 messages 接口，问题目录使用 questions，预览使用 preview。它们解决不同阅读需求，不是每个后端数据表都配一个页面。

阅读入口：[对话控制器](../../frontend/src/pages/conversations/useConversationController.ts)、[读取实现](../../backend/app/conversations/queries.py)、[公开结构](../../backend/app/conversations/schemas.py)。查询测试会在两次 SELECT 之间并发提交新输入，验证 snapshot 不混合两个时点。

## 4. 跟踪一次普通发送

选择一位已启用、已装配模型的员工，先发送一条不需要外部工具的简短问题。

在 Network 中找到：

```text
POST /api/conversations/{conversation_id}/messages
```

记录四项：请求的 client_request_id、返回的 conversation.id、input_message.id、response.id。首次提交可以携带 agent_id，由客户端先生成对话 UUID；服务端在接受事务中原子创建。

第一次接受返回 202，不表示模型已经完成。响应已经给出用户记录和空助手记录，正文仍可能是 empty。重复确认同一请求应使用原键；同键重放返回 200 和原记录的当前视图，不再新建一份工作。

此时已经保存的是：对话、用户原文、空助手 Message、Run、冻结输入和关联。模型调用尚在事务之外。任一检查拒绝，这些写入整体回滚。

阅读顺序：[send 路由](../../backend/app/api/routes/conversations.py) → [submit 请求服务](../../backend/app/conversations/service.py) → [prepare 固定依据](../../backend/app/conversations/preparation.py) → [RunAdmission](../../backend/app/execution/admission.py) → [bind_run](../../backend/app/conversations/writes.py)。

命令服务归 conversations，组织对话目标、幂等与接受事务；HTTP 路由只适配请求和响应。准备、授权与发布同样归 conversations，由 bootstrap 装配给请求和后台使用。

这一轮的检查问题是：关闭浏览器后，系统是否仍知道已经接受的工作？答案来自已提交的记录，而不是浏览器内存。

## 5. 观察后台怎样接手

接受之后，HTTP 请求就可以结束，后台调度器独立运行。

```text
scheduler 扫描 queued
    → coordinator 复核授权并领取
    → preparation 从冻结依据准备执行函数
    → agent_runtime 驱动模型与已许可工具
```

日志中 `submission.accepted` 能关联对话、回复和请求键；`execution.started` 标识内部运行已被领取。普通模型动作开始后会出现 `model.started`。这些日志只记录标识和状态，不输出输入原文、提示词或密钥。

排队、运行状态有时变化很快，页面可能来不及显示每个中间状态。不要为了观察而假设缺少状态，或随意放宽预算。需要逐步定位时，可以在隔离测试中使用假模型或断点。

阅读入口：[scheduler](../../backend/app/execution/scheduler.py)、[coordinator](../../backend/app/execution/coordinator.py)、[共享授权](../../backend/app/conversations/authorization.py)。

此时应能区分两件事：调度器决定什么时候开始这次处理；Agent 决定处理过程中下一次请求模型、读取方法还是调用已装配工具。

## 6. 观察模型、方法和步骤

普通 Agent 得到的是冻结输入、当前模型配置、预算和专用恢复资源。它没有应用数据库、员工服务或完整执行 Store。

一次模型调用的顺序是：申请开始 → 同事务复核许可、扣减预算并保存动作 → 实际调用模型 → 记录结果和用量。保存开始记录失败，就不能继续发出模型请求。

如果模型请求读取方法，页面会出现实际工具步骤和方法激活。模型说「我要读取」只是意图；工具步骤成功才说明读取发生，激活动作成功才说明方法完整装入。

观察 MCP 或文件操作时也按实际步骤判断。员工装配决定允许调用哪些操作；个人账号绑定决定使用谁的连接。工具模块负责远端调用，文件与命令分别受文件许可和沙箱边界约束；工具返回成功也不等于最终回复已经发布。

SDK 的 system、tool 或内部 AI 消息数量可能多于页面消息。它们用于内部循环与恢复，不会自动变成用户可阅读的 Message。用户提交仍是一条输入，对应一次助手回复；中间动作在执行过程里观察。

阅读顺序：[LangChain 循环](../../backend/app/agent_runtime/langchain.py) → [middleware](../../backend/app/agent_runtime/middleware.py) → [方法加载](../../backend/app/agent_runtime/skill_loading.py) → [RunControl](../../backend/app/execution/control.py) → [Store](../../backend/app/execution/store.py)。

[streaming](../../backend/app/agent_runtime/streaming.py) 识别 SDK 片段、完整响应和工具轮，宿主只接收普通内容。前端执行过程可以折叠步骤，但不决定哪一轮文字成为回复。

## 7. 区分「正在显示」与「已经交付」

在 Network 的事件流中观察：

```text
GET /api/conversations/{conversation_id}/responses/{response_id}/events
```

response.snapshot 和 response.finished 都携带同一种 ResponseSnapshot：当前对话摘要，加该回复的当前读取结构。事件来自已经保存的数据；不是把未落盘 token 直接转发给浏览器。

生成中看到 draft，说明有已保存的可见草稿。Agent 返回完整候选后，协调器还要调用 PublishRun。在一个事务中，系统复核当前状态与权限，保存最终正文、输出文件关联、Run 终态并释放活动占用。

提交成功后才可观察到 `execution.published` 和 response.finished。随后重新读取 snapshot 或历史，应能看到同一份最终正文。完整文字出现在 SDK 存档中，不能替代这一步。

阅读入口：[发布流程](../../backend/app/conversations/publication.py)、[内容写入](../../backend/app/conversations/writes.py)、[SSE 连接管理](../../backend/app/api/conversation_streaming.py)。

## 8. 用只读查询把页面和运行记录对上

先核对 APP_DATA_DIR/DATABASE_URL。以下示例采用本地示例配置的目录；如果配置不同，替换路径。不要修改数据库来模拟正常业务操作。

```bash
sqlite3 -readonly "$HOME/.niuma-crew/data/app.db"
```

把下面的对话标识替换为 Network 中记录的 ID：

```sql
.headers on
.mode column
SELECT c.id AS conversation_id, c.revision AS scope_version,
       cr.input_message_id, cr.reply_message_id, cr.active,
       r.id AS run_id, r.status, r.revision AS response_version,
       r.model_calls, r.skill_reads, r.started_at, r.finished_at
FROM conversations c
JOIN conversation_runs cr ON cr.conversation_id = c.id
JOIN runs r ON r.id = cr.run_id
WHERE c.id = '这里填对话ID'
ORDER BY r.created_at;
```

`reply_message_id` 对应页面 response.id；同一行的 run_id 对应后台日志。继续按 Run ID 查看实际动作：

```sql
SELECT sequence, action_key, kind, status, skill_id, error_code
FROM run_actions
WHERE run_id = '这里填运行ID'
ORDER BY sequence;
```

最后核对内容与状态的分工：

```sql
SELECT sequence, role, id, length(body) AS final_body_length
FROM messages
WHERE conversation_id = '这里填对话ID'
ORDER BY sequence;
```

用户正文在接受时就保存；助手最终正文由发布流程写入。NULL 正文的失败回复仍有记录。运行中的草稿主要在动作中，不逐 token 改写最终正文。

## 9. 再观察停止、断线与重试

每次只做一个实验，保留前一轮的三个标识。

| 实验         | 操作                                  | 应解释的结果                                                             |
| ------------ | ------------------------------------- | ------------------------------------------------------------------------ |
| 停止         | 运行中点击停止                        | POST 精确指向该 response_id；running 先变 cancelling，最后结束并释放占用 |
| 离开页面     | 关闭观察页面，再重新打开              | SSE 释放，后台继续；重新 GET 读取当前结果                                |
| 失败重试     | 对允许重试的末次失败/停止回复点击重试 | 服务端 can_retry 为 true，原输入 ID 不变，新回复和 Run，旧失败记录保留   |
| 核对未知提交 | 观察网络异常后的恢复                  | GET requests/{key} 或原键重发，不换键制造第二次工作                      |

快速回复可能在点击停止前就成功，此时返回已有终态是正确的幂等行为。不要靠误改真实凭证制造失败。可先读[运行边界测试](../../backend/tests/test_runtime_boundaries.py)、[公开协议测试](../../backend/tests/test_response_contract.py)，用它们稳定复现保存失败和竞争。

对照数据库，应看到一次重试增加助手记录与 Run，用户原文仍只有一份。后续上下文只选成功问答，失败片段不作为成功历史继续传入模型。

## 10. 最后理解重启恢复

普通 Agent 的 checkpoint 是内部恢复资料。重启时，仍活动且存档可信的运行可以继续，预算和原开始时间保留；可信完成但业务未交付时只补发布。已终止记录保持不变。真实重启可能重发尚未落盘的模型请求，先用隔离[进程恢复测试](../../backend/tests/test_checkpoint_runtime.py)学习，再在理解现有数据与成本后自行实验。

已退役的 CI 诊断试验只保留原有对话正文与运行历史，不能恢复或重试。旧浏览器待确认输入不能改成普通消息自动发送；处理方式见[退役说明](../reference/ci-diagnosis/README.md)。GitHub 登录和普通 MCP 工具不受此退役影响。

当前没有计划模式、目标模式或独立任务实体，不为学习流程虚构对应页面和接口。

## 11. 怎样判断已经理解了全貌

不要求记住全部文件。能独立解释下面的问题，再进入细节源码：

1. 为什么 HTTP 返回 202 后，模型还可能没有开始？
2. 为什么回复 ID 在空正文时已经存在，而 Run 另有内部 ID？
3. 为什么一个回复能有多次模型/工具动作，却只有一份最终正文？
4. 为什么关闭页面不等于停止，而重试必须产生新回复？
5. 为什么有 SDK 完成存档仍可能没有业务成功？
6. 哪些事实来自页面，哪些必须从已提交的运行、动作或发布记录判断？

页面操作是入口，数据库和后台给出事实闭环。目录树用于找位置，调用关系用于解释行为，两者配合才能理解整个运行机制。

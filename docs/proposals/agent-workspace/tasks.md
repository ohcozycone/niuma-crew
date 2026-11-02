# 任务、成果与接口增量

| 项目     | 内容                                                                                                                                                               |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 设计状态 | 草案；[总体方案](README.md)的 W2 契约，W3/W4 扩展另由运行设计维护                                                                                                  |
| 实施状态 | 未开始；本文路径、数据与约束均为拟议，不是当前 API                                                                                                                 |
| 更新日期 | 2026-10-27                                                                                                                                                         |
| 范围     | 工作页读模型、任务输入、Run 来源、成果版本、验收、权限、迁移和故障一致性                                                                                           |
| 相关入口 | [当前对话](../../reference/conversations.md)、[当前 Run](../../reference/runtime.md)、[现有模型](../../../backend/app/execution/models.py)、[运行演进](runtime.md) |

## 1. W2 的明确范围

2026-10-27 补充：当前先补基础工具能力，能力组织与工作流形态[后续再讨论](../configurable-workflows.md)。下述首个任务类型及代码注册属于本草案的窄切片，不据此确定所有未来场景的组织方式；本轮不推进 Task 或配置化工作流实现。

首个任务类型为 `draft_response_v1`，展示名称“答复草稿”，要求明确目标、提供资料及预期结果。执行使用既有受限 Agent，不开放未获准工具。初期接收粘贴资料，输出一份 Markdown 成果，不接任意 URL 抓取、文件上传或外部写入。

用户材料按待处理资料传入，不作为系统指令，也不授予额外工具、文件或账号权限。

任务类型由受信注册定义提供输入校验、执行策略和交付检查。首版一个定义即可，不先新增模板管理表或给 Agent 增加唯一 `execution_profile`。就绪判断根据定义所需能力、员工启停、模型和身份计算，不按姓名、头像或岗位名称分派。

任务拥有者固定为创建人，员工在创建后固定；更换员工或接受后追加工作均新建任务。Task 不硬删除；关闭未完成任务保留输入和历史。任务没有专用 Conversation，来源对话仅用于追溯。

## 2. 输入与版本

任务输入为 `input_draft = {goal, background, materials, expected_output, acceptance_criteria}`。goal 与 expected_output 非空；acceptance_criteria 为 1—10 条非空要求；materials 为 1—10 份 `{kind: pasted, title, content}`。首版建议整个规范化输入不超过 64 KiB UTF-8，超限明确拒绝，不能静默裁剪。title 为 1—100 字符，所有大小上限均为首版工程默认，实施时配置并做边界检查。

每次输入真实变化递增 `input_revision`；Task 的 `revision` 还随提交、终态、验收及关闭变化。前者标识成果依据哪份输入，后者处理并发，不可混用。

Run 接受时复制输入、material 定位 ID、任务类型、显式选择的方法、员工和模型非秘密配置、规则及现有授权依据。素材引用的定位在该快照内解释，不能让后来的草稿改写历史。接入真实知识时，增加获准 release/version 引用并复用[知识访问方案](../knowledge-assistant/access.md)，不把整个知识库正文复制进 Task 表。

从对话交办时，创建接口接收来源 conversation ID 与明确选择的 message ID。服务端校验本人、同员工、消息归属和大小后取得正文；用户可预览编辑，编辑后的材料标为用户整理，不能冒充原消息逐字证据。原始选择引用只作为来源，执行输入以此次确定的快照为准。

## 3. 状态与命令

### 3.1 Task 的业务状态

| 当前状态                   | 允许动作                                         | 转移与限制                                                      |
| -------------------------- | ------------------------------------------------ | --------------------------------------------------------------- |
| `draft` 草稿               | 改输入、首次执行、关闭                           | 接受执行后 `active`                                             |
| `active` 处理中            | 观察、停止当前 Run                               | W2 排队/执行均在此状态，不允许改输入或验收                      |
| `awaiting_review` 待验收   | 接受、要求修订、关闭                             | 接受到 `accepted`；要求修订到 `changes_requested`，均不调用模型 |
| `changes_requested` 待修订 | 改输入、按意见执行、未改输入时接受当前成果、关闭 | 接受 revise 后 active；接受当前成果则 accepted                  |
| `needs_attention` 需处理   | 改输入、重新执行或重试、关闭                     | 用何种命令由输入是否变化及前次终态决定                          |
| `accepted` 已接受          | 读取、以明确成果作为新工作来源                   | 终态，不覆盖旧成果，不在原任务继续执行                          |
| `closed` 已关闭            | 读取、以明确输入新建任务                         | 终态，记录原因；不是执行成功                                    |

Run 成功并保存合格成果时，Task 到 awaiting_review；失败、取消或重启中断时到 needs_attention。W3 的 waiting 仍属于 active，页面单独提示等待原因。Task 状态不能代替 Run 的技术状态。

`current_deliverable_id` 指最近一次形成的成果。新尝试失败时可以保留此引用供查阅，但其 input_revision 与最新输入不同，或任务不处于 awaiting_review/changes_requested 时，不可接受旧成果；页面标为“上一版”。

### 3.2 执行命令

| 命令      | 允许条件                                                         | 冻结与历史                                                                   |
| --------- | ---------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `execute` | draft；或 needs_attention 且需要新执行                           | 接受当前草稿和当前配置，创建新 Run                                           |
| `retry`   | 最新 Run 为 failed/cancelled/interrupted，且 input_revision 未变 | 输入沿用该快照，能力与配置按当前重新捕获；标记 retry_of_run_id。不是断点恢复 |
| `revise`  | changes_requested，携带最新 review ID                            | 冻结当前草稿、该修订意见与明确的前次成果引用，创建新 Run                     |

retry 不承诺逐字复现或恢复旧外部环境；retry 的输入未变但配置可能更新，提交页说明这一点。同键网络重发返回原 Run，不能再次捕获配置。W3 的 resume 沿用同一个 Run，不走此表的重试路径。

Review 追加保存，不覆盖历史意见。若要求修订后尚未改变输入、没有新 Run，用户可以显式接受仍为当前版本的成果，追加 accepted 记录，不强迫生成一次相同结果。输入已变或新尝试开始后，旧成果不再可接受；accepted 为任务终态。执行 revise 时必须引用该任务最新的 changes_requested 决定。

## 4. 数据增量与强制约束

以下为目标设计，不添加迁移代码。各新表沿用现有 UUID TEXT 主键和 UTC 时间编码，均有 created_at/updated_at；ID、时间在应用产生，除表中说明外没有业务缺省值。D 为数据库强制，A 为应用校验；网络调用始终在事务外。

### 4.1 tasks

| 字段                                  | 类型             | 可空 | 默认                | 含义与约束                                                                          |
| ------------------------------------- | ---------------- | ---- | ------------------- | ----------------------------------------------------------------------------------- |
| id                                    | UUID TEXT        | 否   | 应用 UUID           | D：PK                                                                               |
| owner_user_id                         | UUID TEXT        | 否   | 当前用户            | D：FK users；A：创建后不改，资源读取不被 resources:all 绕过                         |
| agent_id                              | UUID TEXT        | 否   | 无                  | D：FK agents；A：创建后不改，提交复核启停/就绪                                      |
| task_type                             | TEXT             | 否   | `draft_response_v1` | A：受信注册中的已启用类型，非客户端执行器名称                                       |
| title                                 | TEXT             | 否   | 无                  | D/A：长度 1—100，去空白后非空                                                       |
| input_draft                           | JSON             | 否   | 无                  | D：对象；A：按第 2 节校验                                                           |
| input_revision / revision             | INTEGER          | 否   | 1 / 1               | D：均 > 0；A：各自按真实变更递增                                                    |
| state                                 | TEXT             | 否   | `draft`             | D：第 3 节枚举；A：状态转移                                                         |
| source_conversation_id                | UUID TEXT        | 是   | NULL                | D：FK conversations，删除 RESTRICT；A：来源必须本人且同员工                         |
| source_message_ids                    | JSON             | 否   | `[]`                | D：数组；A：至多 20 条且均属于来源对话，不作为执行时重新拼接历史的依据              |
| current_deliverable_id                | UUID TEXT        | 是   | NULL                | D：与本任务复合 FK 到 deliverables；先空值创建，交付事务更新                        |
| client_request_id / request_hash      | UUID TEXT / TEXT | 否   | 无                  | D：owner 与创建 request ID 唯一；A：摘要包括初始输入和来源                          |
| closed_reason                         | TEXT             | 是   | NULL                | A：closed 必填，其他状态为空；上限 1000 字符                                        |
| close_request_id / close_request_hash | UUID TEXT / TEXT | 是   | NULL                | A：关闭时同事务保存，用于在 revision 已变化后识别同一次关闭的重放；非 closed 时为空 |

列表索引 `(owner_user_id, updated_at, id)`、`(owner_user_id, agent_id, state, updated_at, id)` 服务本人总览与员工页。Task 没有公开投影；owner 条件先进入查询，再计算数量和分页。

### 4.2 runs 的 W2 增量

| 字段/约束                                              | 类型与变化                                 | 空值和默认                                      | 规则                                                                                                           |
| ------------------------------------------------------ | ------------------------------------------ | ----------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| origin_kind                                            | 新增 TEXT                                  | 否；迁移旧值为 `conversation`，新建必须显式赋值 | D：仅 conversation/task                                                                                        |
| task_id                                                | 新增 UUID TEXT FK tasks                    | 是；默认 NULL                                   | D：与 origin_kind 的 XOR 约束                                                                                  |
| conversation_id / input_message_id / output_message_id | 原列改可空                                 | 旧数据保持；任务 Run 均为 NULL                  | D：聊天 Run 三项非空且 task_id 空；任务 Run task_id 非空且三项均空                                             |
| context_message_ids                                    | 保留 JSON                                  | 否；任务为 `[]`                                 | A：任务输入来自 task 快照，不取整段聊天历史                                                                    |
| retry_of_run_id                                        | 保留可空列                                 | 默认 NULL                                       | D：保留聊天复合 FK；新增 `(task_id, retry_of_run_id)` 同任务复合 FK，并提供被引用唯一键；A：只允许最新失败尝试 |
| 活跃唯一约束                                           | 保留对话部分唯一索引，新增任务部分唯一索引 | W2 范围 queued/running/cancelling               | D：同 Task 最多一个活跃 Run，与聊天共用全局额度                                                                |

不要只把消息列改成 nullable 而缺失来源校验。读取、取消、步骤和 SSE 按 origin_kind 分派资源授权；未授权统一 404，不能先返回 run 元数据再校验 Task。

任务 Run 在实施时升级现行快照协议，包含 `origin`、task/input revision、规范化输入、task_type 与执行契约版本，以及既有能力依据，具体版本在实施时确定。现行聊天及历史快照原样保留；新 schema 不为旧执行补造证据。重试按当前可执行契约新建。

### 4.3 deliverables

| 字段                  | 类型           | 可空 | 默认                | 含义与约束                                                                                         |
| --------------------- | -------------- | ---- | ------------------- | -------------------------------------------------------------------------------------------------- |
| id / task_id / run_id | UUID TEXT      | 否   | 应用 UUID / 无 / 无 | D：PK；task FK；`(task_id, run_id)` FK 到同任务 Run；run_id UNIQUE                                 |
| version               | INTEGER        | 否   | 无                  | D：> 0，`(task_id, version)` UNIQUE；在持有任务写资格的交付事务分配，不在模型中分配                |
| input_revision        | INTEGER        | 否   | 无                  | D：> 0；A：等于本 Run 输入快照的版本                                                               |
| kind / schema_version | TEXT / INTEGER | 否   | `markdown` / 1      | D：W2 仅 markdown；版本 > 0                                                                        |
| title / body          | TEXT / JSON    | 否   | 无                  | A：title 非空；body 包含 markdown、limitations、evidence_refs，引用只指本轮合法材料/获准知识依据   |
| validation_summary    | JSON           | 否   | 无                  | D：对象；A：结构、必需字段与引用定位检查结果，由受信校验器记录；语义覆盖与正确性不伪装成确定性检查 |

提供 `(task_id, id)` 唯一键，供 Task 当前成果和 Review 复合引用。正文一经交付不可覆盖。W2 每个成功任务 Run 恰有一份成果；失败/取消可以保存诊断，不创建可验收成果。

资料不足可以形成明确说明限制的合格草稿；程序检查不保证语义正确。必要字段或引用定位失败则 Run failed，不用空白成果伪装成功。最终是否可用仍由 Review 判断。

### 4.4 task_reviews

| 字段                             | 类型             | 可空 | 默认                | 含义与约束                                          |
| -------------------------------- | ---------------- | ---- | ------------------- | --------------------------------------------------- |
| id / task_id / deliverable_id    | UUID TEXT        | 否   | 应用 UUID / 无 / 无 | D：PK、task FK、`(task_id, deliverable_id)` 复合 FK |
| reviewer_user_id                 | UUID TEXT        | 否   | 当前用户            | D：FK users；A：等于任务 owner，具备 review 能力    |
| decision                         | TEXT             | 否   | 无                  | D：accepted/changes_requested                       |
| reasons                          | JSON             | 否   | `[]`                | D：数组；A：要求修订至少一项，含类别与具体说明      |
| review_seconds                   | INTEGER          | 是   | NULL                | D：非负；未知不记 0                                 |
| client_request_id / request_hash | UUID TEXT / TEXT | 否   | 无                  | D：reviewer 与请求 ID 唯一；A：请求摘要校验         |

Review 增加非空 INTEGER `task_revision`，无业务默认值，取本次验收事务递增后的 Task revision；数据库要求 > 0 且 `(task_id, task_revision)` UNIQUE，提供稳定的决定顺序。允许同版先要求修订再显式接受，但每条记录不可改。accepted 必须由针对 current_deliverable_id、匹配当前输入的 accepted Review 与 Task 状态同事务产生。

删除默认 RESTRICT：员工被任务引用后不能硬删除；停用仍可读历史。当前无 Task/Deliverable/Review 硬删除 API。文件存储及保留期限不在 W2 范围，不将后续二进制文件塞入 body。

## 5. 接口与安全投影

### 5.1 权限

W2 新增 `tasks:create/read/update/execute/review/close` 能力，首期仅赋予现有 admin；运行读取和停止同时检查原 run 能力及任务 owner。guest/member 不因有 GitHub 登录获得新权限。

owner 检查独立于 `resources:all`。员工仍可公开展示，但员工页的工作、成果和计数私有。来源对话不因任务链接获得新共享范围；私有知识的 actor=库 owner=任务 owner 条件复用知识方案。缓存、导出、SSE 和直接成果 ID 都不能绕过。

### 5.2 拟议接口

所有写入使用当前 Cookie/Origin/JSON 约定；创建、执行、验收和关闭带 client_request_id 并校验内容摘要。PATCH 带 expected_revision，不隐式启动执行。

新建页的“交办并执行”可以是一次用户动作，内部依次保存草稿、接受 Run，分别保留稳定的创建和执行 request ID。第二步失败时展示已保存草稿及明确错误，重试沿用相应 ID；不能再次创建 Task。草稿保存和执行不是跨网络请求的原子事务。

| 方法与路径                                          | 用途/权限                                                                              | 成功             | 主要错误                                 |
| --------------------------------------------------- | -------------------------------------------------------------------------------------- | ---------------- | ---------------------------------------- |
| `GET /api/agents/{id}/workspace`                    | W1；有员工私有读取能力；返回安全摘要、就绪原因、本人最近对话；W2 增加本人任务/成果摘要 | 200              | 401/403、404                             |
| `GET /api/public/agents/{id}/workspace`             | W1；只读公开员工介绍，活动字段与计数均不存在                                           | 200              | 404                                      |
| `POST /api/tasks`                                   | tasks:create；保存草稿，可带来源选择                                                   | 201；重放 200    | 403、404、409 幂等冲突、422              |
| `GET /api/tasks`、`GET /api/tasks/{id}`             | tasks:read + owner；分页与详情                                                         | 200              | 403、404                                 |
| `PATCH /api/tasks/{id}`                             | tasks:update + owner；仅允许可编辑状态；改 title/input_draft                           | 200              | 404、409 状态/修订冲突、422              |
| `POST /api/tasks/{id}/runs`                         | tasks:execute + runs:create + owner；execute/retry/revise                              | 202；重放 200    | 404、409、422、429、503                  |
| `POST /api/tasks/{id}/reviews`                      | tasks:review + owner；绑定当前成果与 expected_revision                                 | 201；重放 200    | 404、409 旧版本/已接受/修订冲突、422     |
| `POST /api/tasks/{id}/close`                        | tasks:close + owner；记录放弃原因，无活跃 Run 才允许                                   | 200；重放 200    | 404、409、422                            |
| `GET /api/tasks/{id}/deliverables/{deliverable_id}` | tasks:read + owner；读取指定历史版本，不要求它仍为当前版                               | 200              | 404，包括成果属于其他任务                |
| `GET /api/tasks/{id}/events`                        | tasks:read + owner；持久化任务和当前执行的聚合快照                                     | SSE              | 401/404、503                             |
| 现有 `GET /api/runs/{id}`、steps、events、cancel    | W2 扩展到两种来源；先授权所属主体                                                      | 沿用现有成功状态 | 404、409；不得走聊天重试接口重试任务 Run |

任务列表接受 `agent_id`、`state`、`offset`、`limit`；默认 20、最多 100，按 updated_at/id 倒序。状态非法 422；数量和列表使用相同 owner/filter 条件。工作页近期列表默认各 5 项，提供到带员工筛选的完整列表链接，不通过当前页推算总数。

Run 响应增加 `origin_kind` 和 `task_id`，按来源形成判别联合。聊天响应保留原 conversation/message ID 和 assistant_content；任务响应提供执行元数据及成果摘要/引用，不伪造 assistant_content。前端聊天入口只消费 conversation 类型，Task 页消费 task 类型；不能把可空 ID 断言成字符串复用。

任务 SSE 包含 `task_revision`、`active_run_id`、`run_revision` 及安全摘要；Task 业务修订不随每个模型步骤增长。每次已提交 Run 变化仍通过 run_revision 可观察。重连发送最新完整快照，事件 ID 是上述版本组合，不承诺完整事件重放。终态、验收和关闭后仍可从详情补齐，SSE 不驱动执行。

### 5.3 写入示例与空值语义

任务执行请求示例：

```json
{
  "operation": "revise",
  "expected_revision": 8,
  "review_id": "<latest-review-id>",
  "client_request_id": "<new-request-uuid>"
}
```

body 中不能覆盖 owner、员工、模型凭证或执行器类型。请求摘要包含 task ID、operation、输入依据与 review/retry 目标，避免同键跨任务复用。

PATCH 省略字段表示保留；title/input_draft 显式 null 拒绝；输入整体替换，空列表只在输入规范允许时接受。先检查同键同内容重放，再判断已因原请求变化的 revision，避免成功响应丢失后被误判为冲突。所有新写入失败保留前端草稿。

## 6. 原子事务与竞争

| 操作       | 同一短事务必须包含                                                                                                     |
| ---------- | ---------------------------------------------------------------------------------------------------------------------- |
| 接受执行   | 幂等检查、owner/能力/状态/修订/额度、冻结输入和配置、queued Run、Task active及revision；任一步失败都不接受工作         |
| 交付       | 再查取消/授权/当前 Run、分配成果版本、保存 Deliverable、Run succeeded、关闭步骤、Task awaiting_review/current成果/修订 |
| 失败或停止 | Run 终态、步骤收尾、Task needs_attention及revision；取消优先于迟到成功                                                 |
| 验收       | 幂等、owner、预期修订、当前成果/输入对应关系、Review、Task accepted或changes_requested                                 |
| 关闭       | 幂等、owner、状态、无活跃 Run、closed_reason和Task revision                                                            |

模型/工具/成果检查先在事务外完成；写结果时再次校验状态。不能先写 Run succeeded 再另一个事务保存成果。一个任务一个活跃 Run 的数据库索引兜底；配额统计覆盖两种来源，不另建任务专用并发池来绕过限制。

## 7. 迁移、兼容与恢复

1. 使用隔离旧库验证：创建 Task/成果/Review 表，重建 SQLite runs 以放宽列并增加 XOR、索引和复合 FK；停机窗口内完成，不能边写边复制。
2. 旧 Run 全部保留 conversation 来源、原 ID、消息、快照、CI结果和步骤；不回填 Task，不批量将旧回答变成果。新 origin 字段只描述来源。
3. 后端先具备双来源读写与严格授权，任务入口保持关闭；旧聊天和历史查询验收后，再发布 W1/W2 前端并开启任务。
4. W2 重启仍将非终态 Run interrupted，同时将相关 Task active 修复为 needs_attention；没有原子保存的成果不对外展示。任务读取不能永久卡 active。
5. 关闭新任务接受后可回退旧前端；一旦产生任务 Run，不能直接把 nullable 列改回 NOT NULL 或启动旧后端。回退需恢复迁移前数据库备份及匹配程序；期间新任务数据先导出保全，不承诺无损降级。

迁移编号在实施时取当前下一号，本设计不预占正式迁移文件。数据库/密钥备份遵循[现行操作指南](../../guides/backend-operations.md)。

## 8. W2 验收清单

必须覆盖普通对话与 CI 历史保持、任务独立于消息、来源选择不泄露、跨 owner/跨任务 ID、同键不同内容、双标签提交/验收、要求修订不执行、旧成果不能验收、停止/迟到响应、持久化失败、重启修复、员工停用及知识范围撤销。执行效果另用真实资料人工判断，不用替身生成的漂亮正文证明价值。

本次仅完成目标契约设计，未运行迁移、API或真实模型验收。

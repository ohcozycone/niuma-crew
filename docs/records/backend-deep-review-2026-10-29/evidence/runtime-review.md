# 对话、执行与 Agent 运行独立评审证据

审查开始于 2026-10-29，证据整理完成于 2026-10-30（北京时间）。本组检查 `conversations`、`execution`、`agent_runtime`、`ci_diagnosis`、`llm` 全部 44 个 Python 文件，以及各模块 README 和相关测试。文件数、行数、摘要、导入及逐文件结论见 `runtime-coverage.json`。工作区没有可解析的 HEAD，本记录按文件 SHA-256 固定审查对象；不将不存在的提交号写成基线。

这五组模块的主要拆分合理：对话模块拥有“这条回复怎样成为正式消息”，执行模块拥有“这次尝试怎样被可靠地运行”，Agent 模块拥有“模型和工具怎样往返”。最需要先处理的是失败部分正文的发布授权缺口；本组另实测到对话列表的重复查询。没有因为缺少 Repository、纯领域实体、全局 `__all__` 或文件超过某个行数就判定设计错误。

## 1. 已复现的问题

### RT-01：撤权以后，输出超限的失败分支仍能交付新的部分正文

- **优先级：P1；证据等级：已隔离复现，置信度高。** 影响普通聊天允许保留部分输出的运行；CI 的 `allow_partial_output=False` 不走此发布行为。
- **触发条件：** 模型已获准开始 → 本轮等待期间员工停用 → 周期看护尚未察觉 → 模型以 `finish_reason=length` 返回正文。动态探针已复现员工停用；会话或装配失效可到达同一漏检分支是静态推断，本组没有逐一动态复现。
- **调用链：** `agent_runtime/middleware.py:81–88` 生成包含 `partial_text` 的失败；`execution/coordinator.py:122–134` 将其作为失败候选正文；`conversations/publication.py:38–54` 只在 `succeeded` 分支重新授权；`:77` 调 `writes.publish_conversation`，后者在 `writes.py:92–105` 将正文写入助手消息。
- **用户可见结果：** 已撤权的运行仍出现新的正式 `partial` 消息，错误是 `output_limit_exceeded`，而不是撤权对应的错误或无新增正文。这与 `docs/reference/runtime.md` 中“撤权不增加可见正文”不一致。
- **实际验证：** `/tmp/niuma-runtime-review/test_review_probes.py` 内，一个探针直接调用真实发布器；另一个通过真实 LangChain SDK、生产协调器与发布器运行假模型。假模型先等待独立看护完成初次检查，随后停用员工并返回 length 响应；结果为 `failed/output_limit_exceeded`，`assistant_content=撤权后模型的部分正文`。仅使用 pytest 临时目录中的完整迁移库及假模型。
- **建议：** 任何会新增业务可见正文的发布都在同一写事务内复核当前授权；撤权不携带新增正文。不能只在正常成功分支做此检查。补上“撤权 + 可保留部分输出失败”的组合回归，覆盖员工、会话和工具许可撤销。
- **现有测试覆盖与缺口：** `test_runtime_streaming.py` 已覆盖活跃配置撤销；`test_conversations.py` 已覆盖部分输出失败和会话撤销，但这两个条件的组合未覆盖。现有测试通过不排除此组合。

### RT-02：对话列表随条目增加重复取员工和回复标识

- **优先级：P2，性能改进；证据等级：查询数量已测量，线上影响未测量。** 不应据此声称线上已经卡顿。
- `conversations/queries.py:250–273` 对列表逐行调用 `read_conversation`；后者 `:218` 取员工，`:222–232` 分别查询最新和活动回复。
- 只调用正式 `ConversationQueries.list`，用 SQLAlchemy 事件计数，5 个对话产生 **17 条 SELECT**，即本次情形为 `2 + 3N`；未包含身份解析或其他 API 请求。探针在同一个员工的 5 个对话上执行。
- 建议列表路径一次批取员工名称、末次回复和活动回复；保留单条投影函数供详情使用。先以查询数回归守住改进，再按实际规模测延迟，不为此引入缓存一致性问题。

## 2. 当前调用链与归属

1. `api/routes/conversations/service.py:65–224` 接受命令，先取得 SQLite 写入资格，处理同键重放、容量、对话空闲、重试目标、附件与上下文，然后原子保存用户 Message、空助手 Message、Run 和 ConversationRun。该服务不运行模型。
2. `conversations/preparation.py:61–153` 固定员工指令、全员规则、技能/工具、模型修订和预算。快照固定方法内容，不冻结许可；`authorization.py:17–57` 继续读当前身份、装配、连接及曾用工具。
3. `execution/scheduler.py:29–55` 持有单宿主文件锁，恢复活跃运行并启动扫描；`:84–123` 处理存储降级、队列时限与并发。
4. `execution/coordinator.py:70–112` 限制剩余总时长，授权、领取、准备，并行运行执行任务和看护。`RunControl` 将 SDK 无关的动作、内容和授权请求交给 `RunStore`。
5. 普通聊天进入 `agent_runtime/langchain.py:109–232`，构建技能与工具、中间件、独立 checkpoint 和受管模型客户端。中间件在模型/工具真正开始前完成授权、预算和动作记录。
6. CI 进入 `ci_diagnosis/executor.py:24–347`：核对运行元数据与 attempt、枚举失败 job、由模型选不超过两份日志、校验引用、复查目标，返回待发布候选。固定 4 轮模型/5 次 MCP 业务调用是专业契约，不是普通聊天 `Run.model_calls` 的实现遗漏。
7. `conversations/publication.py:33–78` 在一个业务事务中写终态、专业报告或输出文件关系、助手正文和占用释放。取消先被转换成 cancelled，迟到成功不能覆盖终态。RT-01 是该流程的失败正文分支缺口。

## 3. 五个模块的内部分析

### conversations：内容和回复交付的业务所有者

**文件职责。** `models.py` 定义 Conversation、Message、ConversationRun 和 MessageFile；`writes.py` 只参与调用方事务；`queries.py` 生成对话、历史、问题目录、首屏和回复视图；`schemas.py` 定义这些协议；`preparation.py` 组装冻结输入；`authorization.py` 组合现行许可；`publication.py` 提交最终交付；`files.py` 组合文件可见性和保留关系。空 `__init__.py` 没有制造另一套聚合接口。

**边界判断。** 该模块认识员工、模型连接、技能、工具和 CI，是因为回复接受和交付必须组合这些规则，不能据此直接判定“耦合过多”。执行器通过 bootstrap 注入这些能力，执行核心不反向导入业务。`queries.py` 543 行包含多个读取用途，但都围绕同一交流数据，不能仅按长度要求拆包。若下一轮实质改动问题目录，可将问题检索/预览移入 `question_queries.py`；当前优先解决 RT-02，避免只移动代码。

**状态与事务。** 用户正文和消息身份通过 ORM 验证器保护；同对话复合外键、序号唯一和活动唯一由数据库兜底（`models.py:43–86`）。这些验证器不代表任意直接 SQL 都不可改写历史；测试证明的是应用写入口。`select_context` 仅纳入成功问答，不取 SDK 中间消息（`queries.py:182–211`）。因此失败重试不会将工具正文或失败片段变成下一轮上下文。

**权限与错误。** 列表按 owner 过滤；详情检查 owner；消息和回复另需 runs:read。公开步骤选字段，不返回 config_snapshot 和 result_payload。发布的成功分支会复核许可，失败部分正文需修复 RT-01。文件下载明确区分已关联 Message 的附件/输出与该对话 Run 的来源资料（`files.py:45–71`）；来源资料可在失败后保留，不能混称所有文件都必须先成功发布。

**命名与组织建议。** `prepare` 表示接受时捕获、`execution` 表示后台构造执行策略，英文语义略宽；如果今后频繁误用，可重命名为 `capture_request` / `prepare_execution`，目前有 README 和实际调用方，属于可读性建议。`files.py` 未进入本模块 README 职责表，入口说明需补齐。

**测试证据。** `test_conversation_submission.py` 覆盖首次创建回滚、同键并发、员工冲突和权限；`test_conversation_message_state.py` 覆盖正文/步骤同快照和重试保留；`test_conversations.py` 覆盖双向分页、问题锚点、上下文、取消、故障及配置冻结；`test_execution_boundaries.py` 覆盖发布回滚和提交/取消竞争。旧测试 URL 经 `scenario_client.py` 翻译，不能据测试文本声称应用仍支持旧 `/api/runs`。

### execution：一次运行尝试的可靠性

**文件职责。** `admission.py` 做请求摘要、重放、容量与 Run 登记；`config.py` 集中预算和周期；`contracts.py` 定义运行策略、状态、快照与完成意图；`models.py` 保存 Run/RunAction；`queries.py` 仅内部存在性与 owner 范围；`store.py` 实现短事务状态和动作；`control.py` 提供受限操作与缓冲；`coordinator.py` 看护一次尝试；`scheduler.py` 管全局队列、进程锁和关闭；`errors.py` 集中稳定失败语义。目录划分依据生命周期，没有 service/store/repository 的重复转发层。

**关键约束。** 模型开始通过 `start_model` 在同一事务授权、扣预算、建动作；工具开始通过 `begin_tool` 同时校验指纹、是否允许只读重用、每绑定和全局预算。它们在 `reserve_writer` 后读取竞争状态，记录失败时回滚预算，外部动作不会先发出。`finish_action` 拒绝结束步骤被迟到内容覆盖。中断模型或工具的结果是 unknown，不冒称未执行；未知用量保持空值（`store.py:128–149`）。

**取消与恢复。** 浏览器订阅不拥有运行；显式停止写 cancelling，watcher 观察后取消任务，发布器保证持久取消优先。重启保留 started_at、预算和成功技能动作；未知/不支持快照或不可恢复运行收束 interrupted。只读本地能力可恢复，远程工具和有副作用工作区不自动重放。单主机文件锁是明确产品约束，不能当作“分布式能力缺失”缺陷。

**可维护性。** `RunSpec` 仅定义部分动态快照键，多个边界仍靠 `dict` 和注入对象的约定；例如 `RunControl.authorize` 的标注只写一个参数，实际调用还传 db / invocation（`control.py:38,54,76,117`）。这会减弱类型工具对后续扩展的约束，但本次未证明运行错误。优先为 prepare/authorize/publish、恢复状态及工具快照补与真实调用一致的 Protocol/TypedDict，不需要把所有 ORM 都抽成仓储。

**测试证据。** `test_runtime_boundaries.py` 证明独立 SDK 不落业务动作、模型记录失败回滚预算和导入方向；`test_execution_boundaries.py` 证明消息和终态原子提交；`test_checkpoint_runtime.py` 用正式应用子进程覆盖 kill/terminate、补发布、预算与撤权；`test_agent_foundations.py` 覆盖最后名额的并发工具申请。

### agent_runtime：模型与工具循环的适配层

**文件职责。** `contracts.py` 提供普通输入输出与 RuntimeControl；`langchain.py` 拥有创建图、流消费和可信完成判断；`middleware.py` 管模型上下文、动作与用量；`streaming.py` 合并 SDK 片段；`skill_loading.py` 投影方法并记录实际激活；`checkpoints.py` 拥有 SDK SQLite；`resources.py` 注入工具/文件/沙箱操作；`tool_calls.py` 是工具宿主门禁；`tool_results.py` 管本 Run 结果游标及网页证据；`workspace.py` 路由虚拟路径；`sandbox_backend.py` 适配受限用户执行和输出收集。文件名与责任基本一一对应。

**真实执行。** 模型声称“已用技能”不会创建激活动作；完整读取成功才激活，显式选定技能也先确认 SDK 注入正文。工具调用参数、绑定和预算在 handler 前检查，结果持久化成功后才返回 ToolMessage。原始 MCP 结果保存为不可变来源，模型得到有界预览与本轮游标；继续读取仍带来源许可。它不是任意主机文件读取接口（`tool_calls.py:195–292`、`tool_results.py:64–114`）。

**完成与恢复。** SDK 流结束不足以成功：检查完整状态的 completed_run_id、无待执行节点、最终 AIMessage 既有正文又没有工具调用，随后再授权、验证网页证据、收集输出，并再次授权（`langchain.py:169–225`）。完整消息覆盖暂存片段，迟到片段不会追加（`streaming.py:29–37,60–64`）。checkpoint 元数据还须与原 Run 匹配。

**工具与文件边界。** `/skills`、`/sources`、`/inputs` 只读，工作/输出目录单独许可。Sandbox 以 UID/GID 1000 执行，收集输出前停止工作负载并拒绝符号链接与非常规文件（`sandbox_backend.py:39–109`）。这是代码侧约束；未连接真实 OpenSandbox，因此不宣称远端镜像、挂载和系统隔离已验证。

**限制与建议。** 网页发布校验是窄规则，依据明确动词+URL、实际结构化提取来源和送模区间，不能判定文意理解正确，也不证明正文没被登录页替代。工作区和工具文件协作复杂，目前有可替换资源与独立测试，保留此拆分。`langchain.py` 顶部仍提 `hooks.progress`，协议已改成 `report_content`，是说明漂移；Agent README 未列工具/工作区文件，建议同步维护入口。不要把事实性回答质量当作静态代码检查已经证明。

### ci_diagnosis：固定范围的专业调查

**文件职责。** `contracts.py` 定义固定技能、目标 URL、报告和反馈；`mcp.py` 只访问固定 GitHub 只读端点并规范已知包装；`service.py` 管安装、冻结、持续范围、进度与反馈；`executor.py` 管有界取证循环；`report.py` 脱敏、检查来源和确定性渲染；`models.py` 独立保存专业状态。它保留专用循环有实际意义：模型只能从已枚举失败 job 选日志，不能任意选择仓库或 MCP method。

**权限与事实。** 目标仓库必须与员工实际关系匹配；凭证只保留指纹。读取先核验 id/attempt/失败状态，job 列表归属要匹配；报告引用须来自本次已读 job 的有效来源和行号，每份已读来源都要被覆盖；发布前复查 attempt/head_sha。算法并不证明模型写的根因与行内容在语义上相符，这是正常的证据形式边界。

**故障与事务。** save_progress 拒绝 report、delivered、feedback、额外字段、超量和终态更新；专业 revision 和公开 Run revision 同事务推进。返回 ready_to_publish 后才由业务发布器保存正式报告，不靠 SSE 或执行器直接宣告交付。失败保留调查过程，反馈只有成功且有正式报告才允许，一致内容幂等，异值冲突。

**组织建议。** `executor.execute` 在 324 行内串起初始化、取证、模型轮、重写和最终验证；保持单函数便于看完整顺序，但后续改变工具或报告协议时，建议按“收集目标”“读取日志”“模型草稿”“最终校验”提取局部协作，不把这套专业流程搬进通用 Run。固定预算来自专业契约，不能简单替换成普通聊天模型计数而改变行为。

**文档差异。** `docs/reference/ci-diagnosis/data.md:3` 仍称迁移 head=0005，`:17` 称快照 schema 2，末尾还将通用工具、标准 Skill/MCP 视为后续；实际当前迁移到 0011，`execution/contracts.py:10` 为快照 3，技能包和通用工具已接入。应修正“当前”说明，历史迁移动机可保留。

**测试证据。** `test_ci_diagnosis.py` 覆盖完整回路、伪造引用、attempt 变化、未知 job、取消/范围撤销、两日志预算、报告大小、进度拒绝和反馈幂等，使用受控 MCP 与假模型。本组没有连接真实 GitHub MCP 或付费模型，真实供应商兼容性未知。

### llm：显式模型参数与供应商边缘

`config.py` 的不可变 LLMConfig 通过 SecretStr 隐藏普通表示，非加密存储；`factory.py` 构造 ChatOpenAI 和统一生命周期；`usage.py` 解析供应商用量并保守累计；`errors.py` 只分类已知供应商错误；`__init__.py` 只有模块说明。工厂不查业务数据库、不取员工、不散读环境。这一层保持很小，职责合适。

实际只支持 OpenAI 兼容 Chat Completions，不能从 base_url 推断支持任意供应商原生协议。默认不自动重试，注入 HTTP 客户端关闭环境代理/重定向并由 async with 关闭；未报告的用量不会按文字长度估算。`test_llm.py` 和 `test_conversations.py` 的 MockTransport 验证参数、原生工具和实际 SSE 适配，不等于真实上游验收。

## 4. ECC 12 层适用性

| 层          | 当前事实与证据                                                                                      | 本次判断                                                   |
| ----------- | --------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| 1 系统提示  | `preparation.py:17–35` 组合公司规则/员工身份；`langchain.py:29–76` 组合本轮工具和来源标记说明       | 适用；未证明提示冲突导致实际退化                           |
| 2 会话历史  | `queries.py:182–211` 只选成功问答；`middleware.py:44–57` 选本轮允许消息                             | 适用；失败与工具中间内容未作为正式历史送模                 |
| 3 长期记忆  | 五组生产代码未见跨会话记忆写入/召回                                                                 | 不适用，不能因未实现记忆记缺陷                             |
| 4 蒸馏      | 无历史蒸馏流程                                                                                      | 不适用                                                     |
| 5 主动召回  | 无独立记忆召回/二次总结                                                                             | 不适用                                                     |
| 6 工具选择  | 普通模型从冻结目录选工具；CI 首轮要求日志，白名单再校验                                             | 适用；不能把所有普通聊天都强制工具                         |
| 7 工具执行  | `tool_calls.py:234–291` 开始许可、执行、持久结果；`store.py:306–355` 原子预算                       | 适用；模型声明与实际记录区分明确                           |
| 8 工具解释  | 本轮结果游标和网页提取范围校验；CI source/job/line 校验                                             | 适用；语义正确性与全文完整性仍需模型/真实上游评估          |
| 9 答案组织  | 普通正文保留模型输出，CI `report.render` 确定性排版                                                 | 适用；RT-01 是交付许可分支问题                             |
| 10 平台传输 | 普通 ContentUpdate→持久 RunAction→统一助手视图                                                      | 后端适用；前端最终渲染不在本组范围                         |
| 11 隐式修复 | 普通路径无二次答案修复，SDK max_retries 默认 0；CI 引用失败会在4轮内请求重写（executor.py:318–323） | CI 有明确有界修正，实际轮次/用量可观察；未确认隐藏无限重试 |
| 12 持久化   | Message 保存业务结果，SDK checkpoint 按 Run 隔离，有完成标记/版本校验                               | 适用；取消和终态不因存档完整而复活                         |

## 5. 实际验证与未知项

本组运行：

```text
cd backend
PYTHONPATH=tests:. .venv/bin/python -m pytest -q -s /tmp/niuma-runtime-review/test_review_probes.py
3 passed, 1 warning in 2.11s

OBSERVED partial publish after revocation: failed 撤权后新增的部分正文
OBSERVED real SDK partial publish: failed output_limit_exceeded 撤权后模型的部分正文
OBSERVED conversation list: 5 conversations 17 SELECTs
```

该三个探针验证的是缺陷确实存在和查询数事实，**不是修复已通过**。探针位于临时目录，未修改业务代码。复现原文与运行输出另保存为本目录 `runtime-review-probes.py`、`runtime-review-probes.log`。全仓 Ruff/类型/pytest 由主评审统一执行，本组不重复运行或以历史通过代替本次结果。

未覆盖：真实模型回答质量、实际 GitHub MCP 结构与认证、真实 OpenSandbox 的系统/容器隔离、生产负载延迟、跨主机运行；前两者不能由假模型/MockTransport 推定。当前单主机单宿主不是未知行为，而是明确限制。报告仅对本次文件摘要对应的代码负责。

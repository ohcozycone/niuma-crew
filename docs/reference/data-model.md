# 当前数据模型与约束入口

字段、空值和约束以所属 ORM 与[正式迁移](../../backend/migrations/versions/)为准。行为见[对话](conversations.md)、[运行](runtime.md)和[MCP](mcp.md)契约；历史迁移中的旧表不代表当前仍提供对应功能。

## 当前表与所有者

| 表                                                                    | 所有者                                                        | 职责                                                                      |
| --------------------------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------------- |
| users、auth_sessions、external_identities                             | [auth](../../backend/app/auth/models.py)                      | 用户、登录会话及外部身份                                                  |
| agents、agent_skills                                                  | [employees](../../backend/app/employees/models.py)            | 员工配置与技能选择、参数和修订                                            |
| agent_tool_grants、personal_tool_bindings                             | [employees](../../backend/app/employees/models.py)            | 员工工具许可与使用者的账号选择                                            |
| skills                                                                | [skills](../../backend/app/skills/models.py)                  | 方法正文、包文件清单、参数规范、启停与修订                                |
| mcp_services、tool_connections                                        | [tools](../../backend/app/mcp/models.py)                      | 服务定义、账号密文、候选及已确认工具清单                                  |
| model_connections                                                     | [模型连接](../../backend/app/model_connections/models.py)     | 模型选择、密文和配置/凭据修订                                             |
| organization_rules                                                    | [共享规则](../../backend/app/employees/organization_rules.py) | 全员共用的一份工作规范及修订                                              |
| conversations、messages、conversation_runs、message_files             | [对话](../../backend/app/conversations/models.py)             | 消息内容、顺序、归属、处理关联和附件引用                                  |
| evaluation_batches、evaluation_cases                                  | [员工考核](../../backend/app/evaluations/models.py)           | 本人考核批次、题目快照、Run关联及评分                                     |
| runs、run_actions                                                     | [执行](../../backend/app/execution/models.py)                 | 处理尝试、固定输入、预算、实际动作及状态                                  |
| knowledge_bases、knowledge_documents、knowledge_chunks、knowledge_fts | [知识库](../../backend/app/knowledge/models.py)               | 本人库、原件关联、固定正文、切片和 FTS5；行为见[知识库契约](knowledge.md) |
| stored_files                                                          | [文件](../../backend/app/files/models.py)                     | 持久文件归属、位置、摘要和大小，字节保存在库外                            |
| sandbox_resources                                                     | [沙箱](../../backend/app/environments/models.py)              | 环境归属、远端标识、期限及待清理状态                                      |

SDK 的旁置 .checkpoints.db 只负责内部恢复，不进入业务 ORM，也不作为历史读取来源。CI 试验专用表已退役，共享 Run 和消息保留；处置见退役数据说明。

知识库拥有 `knowledge_vector_indexes` 和 `knowledge_vector_memberships` 两张派生表，分别保存模型/来源依据、Chroma 发布指针和当前代片段成员；数字向量只在 Chroma 持久目录保存。见 [ORM](../../backend/app/knowledge/models.py)、[0023 迁移](../../backend/migrations/versions/0023_knowledge_chroma.py)与[向量契约](knowledge.md#硅基流动向量接入)。0023 直接删除旧向量派生数据，需要重新构建；原文和关键词索引保留。

`knowledge_processing_batches` 与 `knowledge_processing_items` 保存手动处理的规则快照及逐文件执行结果。文档可以只有原件、没有活动正文和片段；文件删除后保留任务历史，子任务不通过文档外键级联删除。[0015 迁移](../../backend/migrations/versions/0015_knowledge_processing.py)将既有正文标为关键词就绪，并为文档的提交标识和内容摘要设置稳定的独立唯一约束名。

库级短章节合并覆盖由[0016迁移](../../backend/migrations/versions/0016_knowledge_chunk_preview.py)新增；章节父标识、标题路径及合并来源保存在JSON快照，已有快照字段缺失时兼容读取，不自动改写历史索引。

## 共用值与关键约束

1. Message 的用户输入非空且不可覆盖；助手接受时即有 ID 和 sequence，结束时保存完整、允许的部分正文或 NULL。Message 不另存一套运行状态。
2. ConversationRun 以 Run ID 为主键，run_id 同时引用 Run 和助手 Message，助手直接复用执行 ID；输入与回复的复合外键保证属于同一对话。sequence 只存 Message。
3. 一个对话最多一份 active 关联，由部分唯一索引兜底。接受、释放和 Conversation.revision 更新在各自事务内完成。
4. Run 保存幂等依据、身份、输入和配置快照、预算、动作版本、用量、错误和恢复引用，另存执行成果 result_text/result_data，正式对话回复仍在 Message。RunAction 的运行内 sequence/action_key 唯一；未知远端结果标 unknown，不冒充成功。
5. 员工配置与装配、账号配置/凭据修订与旧目录失效分别原子保存。个人账号绑定引用员工已有许可，不扩大许可或复制凭据。
6. 执行完成事务提交成果和 Run 终态；对话接纳事务提交 Message、附件与占用释放。ConversationRun 保存 handled_at、acceptance_attempts、acceptance_error 和 next_acceptance_at，支持重启与退避处理。终态成果受数据库触发器保护，不允许覆盖。

Conversation、Message、Run 及其外键使用 NumericID；其他资源继续 UUID。共用数字标识、UUID、UTC 与 JSON 机制见[数据库字段](../../backend/app/infrastructure/database/fields.py)。[模型注册](../../backend/app/infrastructure/database/models.py)用于迁移发现，不作为业务模型导入入口。

## 迁移与恢复

历史 [0005](../../backend/migrations/versions/0005_message_delivery.py) 完成消息正文和旧专业数据归位；这段升级链继续保留。[0012](../../backend/migrations/versions/0012_retire_ci_diagnosis.py) 在其后删除 CI 专用表和字段，精确清理固定技能及装配，将活跃试验安全收尾，保留普通记录和已交付文本，不改写 SDK 存档。

升级前停止后端及其他写入/同步入口，成套备份业务库、checkpoint、主密钥和技能资产。应用启动不自动迁移。删除的专业数据不能靠空壳降级恢复，回退使用成套备份。操作见[后端指南](../guides/backend-operations.md#数据库与本地文件配置)。

员工个人知识设置、选库关系及Run证据分别由knowledge_employee_settings、knowledge_employee_libraries、knowledge_run_evidence维护，见[0017迁移](../../backend/migrations/versions/0017_employee_knowledge.py)。用户/员工唯一设置带修订，证据按Run和证据ID唯一；证据不以文档/Chunk外键级联删除历史，而在当前授权时逐项检查活动Chunk与快照，既保留审计依据又不扩展旧来源读取许可。

连续追问只将当前上下文中已成功引用、且重新通过当前权限与Chunk核验的历史证据登记到新Run，可保留原证据ID；复合主键仍隔离每次运行。新Run配置中的knowledge.history_evidence冻结来源Run、片段预览和精确链接，保存来源沿用依据，不允许仅凭一个旧编号在运行中查询其他Run。规范见[知识契约](knowledge.md#员工个人装配与正式问答)。

[0019 迁移](../../backend/migrations/versions/0019_independent_run_results.py)新增独立成果和应用处理字段，保留已有正文及已处理关联；不自动运行部署库迁移。该版本只在新增字段没有不可还原的成果或未接纳状态时允许降级；存在独立工作、结构化成果或未接纳结果时拒绝，需恢复已验证备份。

## 连续线程与单次执行

[0020 迁移](../../backend/migrations/versions/0020_execution_threads.py)新增 Run.thread_id、base_run_id、base_checkpoint_id。Thread 是 SDK 状态范围，不新建业务 Thread 表；同一对话使用稳定标识，独立任务默认以自身 Run 标识隔离。base_run_id 外键关联既往 Run；运行时核对实际存档的归属和可信完成标记。

部分唯一索引 uq_runs_thread_active 保证非空线程同时最多一份 queued/running/cancelling Run；对话自身的活动关联约束继续保留。旧 Run 回填 thread_id=id，原 checkpoint 文件和编号不改写，保持旧执行恢复依据。这是 0020 的历史迁移行为；当前 0021 清库重建，不保留历史回填。

已经产生共享线程或存档起点引用后，迁移拒绝直接降级，需使用升级前的一致备份恢复；不能只回退 Python 文件。

## 数字标识与本次重建

[0021](../../backend/migrations/versions/0021_numeric_execution.py)只接受相关表为空时建立新结构，不转换旧记录。identifier_sequence 的单行 next_value 在受理事务用 UPDATE RETURNING 原子分配；Conversation、用户 Message、Run 共用 12 位号段，助手 Message 复用 Run.id。重启不重置，耗尽拒绝受理，失败事务整体回滚。Run.thread_id 必填，ConversationRun 移除重复 reply_message_id；Run、消息、附件、动作、沙箱及知识证据外键一起使用整数。

本次按授权停止服务，清理业务库、SDK 存档及其 WAL/SHM 和项目运行文件后创建空库。密钥、环境配置、共享技能源码保留。清库只用于本次切换，不成为启动动作；后续迁移仍显式执行。

[0022迁移](../../backend/migrations/versions/0022_employee_evaluations.py)只新增考核批次及逐题记录，保留现有员工、消息和独立成果；题目Run关联同事务提交，考核不创建对话。考核记录不支持有损降级，恢复需使用升级前备份。行为见[员工考核契约](employee-evaluations.md)。

## 执行证据增量（0024）

[0024 迁移](../../backend/migrations/versions/0024_action_evidence.py)只扩展原 RunAction 的请求/响应文件外键和 StoredFile 的 evidence 用途；不新建 tracing 表。文件内容在库外，关联、权限、配额及清理见[执行详情契约](execution-evidence.md)。

# 员工与技能当前数据结构

当前结构以[正式迁移](../../../backend/migrations/versions/)与 ORM 为准。配置与执行分开；Message 直接保存用户输入和助手最终正文，run_actions 保存实际过程，checkpoint 只保存 SDK 恢复状态。工具、账号和员工许可见[MCP 契约](../mcp.md)，知识实体、Embedding和个人员工知识装配由独立[知识模块](../knowledge.md)维护，不写共享员工配置。字段类型、空值、默认和约束从[现行数据模型](../data-model.md)进入所属 ORM 和正式迁移，后续字段仅在目标方案维护，本文件说明当前结构如何协作。

## 当前结构与目标边界

| 对象       | 当前存储                                                      | 关系与职责                                               |
| ---------- | ------------------------------------------------------------- | -------------------------------------------------------- |
| 员工       | agents                                                        | 岗位与展示；单模型连接外键；配置 revision                |
| 技能       | skills + 不可变字节目录                                       | 当前源文与文件清单、参数规范、启停和 revision；无发布表  |
| 装配       | agent_skills                                                  | 联合主键(agent_id,skill_id)；一份参数、启停及关系修订    |
| 大脑       | model_connections                                             | 加密凭证、chat 类别、启停、配置/凭证修订；不复制员工指令 |
| 对话与运行 | conversations、messages、conversation_runs、runs、run_actions | 交流归属与消息、执行关联、冻结依据及实际动作             |
| 身份与规则 | users、auth_sessions、external_identities、organization_rules | 当前身份权限与全员规则；登录身份不是工具凭证             |

员工名称的目录范围、归一与冲突语义见[接口契约](api.md#员工接口)，数据库通过 `ix_agents_name` 唯一索引兜底；业务关联始终使用 UUID。

员工只通过 model_connection_id 绑定模型，连接持有实际模型标识和凭证。员工 system_prompt、example_tasks、deliverables 仍是员工自身字段；列表投影精简不改变主体归属。

## 关系与事务

员工删除级联删除 agent_skills；技能被装配时拒绝删除。关系不增加独立 ID，不支持同员工同技能多实例。配置和关系变化同事务保存，先取得 SQLite 写锁再核对预期修订；无实际变化不递增。删除后重建关系通过新员工修订及创建时间防止旧运行误认许可。

技能规范变更校验现有启用参数；正文修改不回写旧运行。运行接受时保存固定正文、哈希、参数与修订；每次动作复核当前启停、关系及模型修订。固定方法与实时许可承担不同职责。

0009 为 skills 增加 skill_md 与 package_manifest，不增加员工副本、每文件权限表或业务版本表。旧记录保留字段，按需编译主文；标准包的支持文件在 SKILL_STORAGE_DIR 按摘要不可变保存。Run 捕获主文与清单后仍可读取旧摘要；不得用附件 TTL 删除旧字节，当前资产自动 GC 后置。备份恢复必须覆盖数据库与技能字节目录。

run_actions 使用自己的稳定 ID、运行内 sequence 和 action_key，后两者分别唯一；宿主持久化真实动作，模型说“使用了技能”不会生成激活记录。终态关闭未结束步骤；普通聊天重启从 checkpoint 恢复原 Run，退役工作和未知协议不自动执行，不补造历史步骤。

## 迁移与验证

当前初始迁移 [0001](../../../backend/migrations/versions/0001_initial_schema.py) 直接建立 Agent、共享技能、配置修订、参数化关系、对话与运行结构，初始化一条空白规章制度。后续 [0003](../../../backend/migrations/versions/0003_unique_agent_name.py) 增加员工名称唯一索引，保留已有数据；旧库存在重名时拒绝升级，不自动改名或删除。应用启动不创建业务表或转换旧数据；SDK 恢复表在执行首次使用时按需初始化，历史读取不打开存档。

历史 0004/0005 完成存档与消息归位；后续退役迁移删除 CI 专用表、员工专用字段和固定试验装配，保留消息及共享运行历史，阻止旧试验继续执行。当前快照使用 schema 3，兼容旧 schema 2 的受限恢复；初始化及升级见[数据入口](../data-model.md#迁移与恢复)。

接口见[管理契约](api.md)，验证见[存储](../../../backend/tests/test_agent_skill_storage.py)、[初始迁移](../../../backend/tests/test_migrations.py)、[配置事务](../../../backend/tests/test_configuration_api.py)和[SDK 执行](../../../backend/tests/test_capability_runtime.py)。

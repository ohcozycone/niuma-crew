# 能力资源目标字段与约束草案

2026-10-27 增量：通用工具、许可、文件与沙箱接线已按[当前数据模型](../../reference/data-model.md)落地。本文仍是完整目标草案，其中未开放字段/协议不能据此视为已支持；当前工具字段与生命周期见[基础工具契约](../../reference/agent-tools.md)。

设计状态：草案；标准 Skill/MCP 与知识按阶段设计。实施状态：后续实体未实施；已落地的当前 11 表及字段实现见[现行数据模型](../../reference/data-model.md)。更新日期：2026-10-24。

本文件只维护拟议增量，保留当前字段是为了说明目标兼容关系，不能将表格当作已建表清单。方案及状态见[总览](README.md)。

## 阅读方式与表的分组

本版保留当前 admin/member 与外部登录身份，不改变现有 member 权限。本文是本版目标字段、外键、索引和保留规则的详细来源。本字典是目标增量字段的维护位置；当前事实从现行数据模型进入代码和迁移。[当前结构说明](../../reference/agent-configuration/data.md)解释协作，正式迁移是实际执行代码。P1/P2/P3/P4 是设计阶段，不是 Alembic revision；标准 Skill/MCP 按[新设计](../skills-and-mcp/README.md)调整目标，后续按实际实体分期引入，评测另见专项；不以旧表总数约束实现。

| 查阅内容                      | 章节                                                         |
| ----------------------------- | ------------------------------------------------------------ |
| 员工、模型与编辑修订          | [员工与大脑](#员工与大脑)                                    |
| 当前共享方法与参数化选择      | [技能定义、发布与装配](#技能定义发布与装配)                  |
| 动态 MCP 目录、连接与员工授权 | [工具定义、连接与装配授权](#工具定义连接与装配授权)          |
| 原文、发布、后台作业及回答    | [知识资产、处理与发布](#知识资产处理与发布)                  |
| 既有聊天主体、步骤、获准资料  | [运行允许目录、实际动作与回答](#运行允许目录实际动作与回答)  |
| 引用、原子写入、删除与索引    | [完整性](#完整性事务与版本解析)、[生命周期](#生命周期与索引) |

本版不建立技能发布审核中心、独立装配实例、不可变装配修订或单独的运行允许目录表。标准包通过不可变内容制品固定资源；MCP 目录保存在连接的获准快照，不为每项外部工具新增业务表。

## 范围与通用约定

类型沿用 SQLite：UUID 是规范化 TEXT，时间为 UTC TEXT，布尔为 INTEGER 0/1；JSON 是合法 JSON TEXT 的逻辑类型。`无` 表示必须显式提供，NULL 不等于可省略非空字段。

| 公共字段   | 类型     | 可空 | 默认             | 约束                          |
| ---------- | -------- | ---- | ---------------- | ----------------------------- |
| id         | UUID     | 否   | 应用生成 UUID v4 | 稳定主键；旧 UUID 不重写      |
| created_at | UTC time | 否   | 当前时间         | 创建或封存时间                |
| updated_at | UTC time | 否   | 当前时间         | 仅可变实体；应用/ORM 更新维护 |

每个实体是否采用公共字段在其开头说明。正整数 revision 用于条件更新，不自动表示另有历史记录。所有 JSON 列至少验证合法类型，字段语义、数组元素和引用范围另由应用校验。空授权对象不解释为全部资源。秘密、客户端任意路径和模型私有推理不进入响应、快照或轨迹。

未特别指定的引用使用 NO ACTION/RESTRICT，不级联删除共享资源和历史。复合外键的目标都需相应 UNIQUE。可空头指针用于在同一事务按“父行 → 子行 → 回填指针”创建，普通即时外键即可；业务事务必须完成回填，不将半成品配置提交为可用。本版不依赖循环外键的延迟检查。不可变内容由应用写入边界及迁移测试保证，哈希、JSON CHECK 或 updated_at 本身不能保证不可变。

## 员工与大脑

### agents（保留主体、调整字段）

阶段：P1；知识字段 P3。使用公共 ID、created_at、updated_at。

| 字段                                | 类型          | 可空               | 默认                   | 含义与约束                                       |
| ----------------------------------- | ------------- | ------------------ | ---------------------- | ------------------------------------------------ |
| code / name / avatar_id             | text          | code 是，其余否    | NULL / 无 / 无         | 保留当前编号唯一、非空名称与头像规则             |
| category / description / role_label | text          | 仅 role_label 可空 | 其他 / 空字符串 / NULL | 当前分类和职责展示，不作为权限                   |
| system_prompt                       | text          | 否                 | 空字符串               | 员工岗位指令，仍在主表                           |
| is_active / is_favorite             | bool          | 否                 | true / false           | 保留启停和平台共享收藏语义                       |
| example_tasks / deliverables        | JSON string[] | 否                 | [] / []                | 展示用字符串数组，不是实际交付物                 |
| model_connection_id                 | UUID FK       | 是                 | NULL                   | 引用 model_connections；应用校验为启用 chat 连接 |
| revision                            | int           | 否                 | 1                      | 员工配置、技能关系及授权变化同事务递增；条件更新 |
| knowledge_base_id                   | UUID FK       | 是                 | NULL                   | P3 引用知识库；首版每员工最多一个                |
| knowledge_strategy                  | enum          | 是                 | NULL                   | P3 full_context/hybrid；与库引用同时空或同时存在 |

保留当前 ID、code 唯一、布尔和展示数组 CHECK；增加 revision > 0 及知识引用/策略空值组合 CHECK。知识绑定仅由有权的当前拥有者修改，新目标须可访问；不可见详情不回显私有库 ID，省略字段不能清空绑定。模型和库外键建立反向索引；列表稳定排序索引 `(created_at, id)` 在有分页数据后用查询计划验证。

员工模型通过 model_connection_id 绑定；`ci_repository` 在 P2 的参数与授权回填验收后退出。迁移前不删值。知识归属、发布与策略可用性是应用规则。已被对话引用的员工仍拒绝硬删除。

### model_connections（保留共享连接）

阶段：P1 修订；capability 在 P4 使用。使用公共 ID、created_at、updated_at。

| 字段                                  | 类型 | 可空 | 默认  | 含义与约束                         |
| ------------------------------------- | ---- | ---- | ----- | ---------------------------------- |
| name / preset_id / model_id           | text | 否   | 无    | 保留当前名称唯一与受控预设规则     |
| encrypted_api_key                     | text | 否   | 无    | 凭证密文，不回显                   |
| capability                            | enum | 否   | chat  | chat/embedding；旧行回填 chat      |
| enabled                               | bool | 否   | true  | 当前是否允许调用                   |
| config_revision / credential_revision | int  | 否   | 1 / 1 | 配置、凭证分别递增；更新携带预期值 |

保留当前字段 CHECK，新增正整数和能力枚举约束。能力类型及 provider 身份在有引用时不可原地替换；知识规则引用的 embedding 模型变化建立新连接/发布，避免旧索引换向量空间。

员工或活跃运行引用时拒绝删除；已结束 Run 的连接引用继续沿用 SET NULL，非秘密快照保留。运行每次模型请求前检查捕获的修订；配置/凭证修订变更后旧运行停止后续调用，不透明切账号。

## 技能定义、发布与装配

本节保留旧标题锚点。P1 当前字段仍有效；下述标准包扩展为设计草案，尚未建表或提供接口。内容制品服务运行可追溯，不引入发布审批与多实例。

### skills（共享定义与当前内容指针）

使用公共 ID、created_at、updated_at；原有 UUID 保留。

| 字段                                             | 类型        | 可空 | 默认                 | 含义与约束                                                     |
| ------------------------------------------------ | ----------- | ---- | -------------------- | -------------------------------------------------------------- |
| name / category / description                    | text        | 否   | 无 / 其他 / 空字符串 | P1 展示字段；标准名从内容解析，显示别名可为中文，不替代稳定 ID |
| instructions                                     | text        | 否   | 空字符串             | P1 当前真源；标准包切换后仅作兼容读取投影，不能与包分别写入    |
| input_description / output_description / example | text        | 否   | 空字符串             | 展示或派生说明，未声明机器约束时不视为强制执行契约             |
| configuration_schema                             | JSON object | 否   | {}                   | P1 非秘密参数表单规范；空规范仅允许空参数                      |
| is_active / revision                             | bool / int  | 否   | true / 1             | P1 启停与条件更新；禁用阻止后续使用                            |
| current_artifact_id                              | UUID FK     | 是   | NULL                 | 新增；引用同一技能的 skill_artifacts；草稿可空，可用时必须有效 |
| host_configuration                               | JSON object | 否   | {}                   | 新增；平台附加的依赖映射要求、可选受信交付检查引用；不修改原包 |

保留名称非空、JSON 类型、布尔与正修订约束。current_artifact_id 与技能 ID 使用同技能复合 FK；创建按父行→制品→回填指针提交。技能编辑产生新内容制品后条件更新当前指针，失败保留旧内容；无内容的草稿可以保存但不可激活。

参数规范改动预检启用关系，不兼容先停用并迁移，不静默丢参数。host_configuration 中的需求不等于授权；交付检查只能引用受信注册表的确定版本，不允许包提供任意代码入口。

### skill_artifacts（不可变标准内容）

新增，阶段对应标准内容 S1。使用公共 ID、created_at，无 updated_at。

| 字段                        | 类型        | 可空 | 默认 | 含义与约束                                                          |
| --------------------------- | ----------- | ---- | ---- | ------------------------------------------------------------------- |
| skill_id                    | UUID FK     | 否   | 无   | 所属共享技能；不覆盖其他技能的来源归属                              |
| content_hash                | text        | 否   | 无   | 规范化文件清单及各文件内容摘要的确定摘要                            |
| standard_name / description | text        | 否   | 无   | 从 SKILL.md 解析，按标准约束校验；原文保留                          |
| source                      | JSON object | 否   | 无   | 内置/自建/上传/仓库来源；记录已解析提交或内容依据，不能只存浮动分支 |
| manifest                    | JSON array  | 否   | 无   | 相对路径、媒体类型、大小、每文件摘要和受控制品引用                  |
| storage_ref                 | text        | 否   | 无   | 应用数据目录中的内容寻址引用；不是客户端任意路径                    |
| compatibility               | JSON object | 否   | {}   | 已检查能力、缺依赖与明确限制；不表示所有员工永久就绪                |

UNIQUE(skill_id, content_hash)、UNIQUE(id, skill_id)，skill_id FK RESTRICT。文件内容先写暂存、验证并原子移入受控存储，再提交制品和当前指针；事务失败可留下未引用文件，不能留下指向缺文件的可用记录。目录遍历、符号链接和超限由应用拒绝。

Run 保存制品 ID、摘要和平台附加配置快照。首批不提供制品永久删除；当前指针移动不删除旧资源。JSON 中的历史引用由应用保留策略检查，不能声称数据库外键已覆盖所有快照。之后建设清理时须先建立完整引用审计。

### agent_skills（保留联合主键）

P1 已实现主体；tool_bindings 为新增草案，无独立装配 ID。

| 字段                    | 类型               | 可空 | 默认      | 含义与约束                                                      |
| ----------------------- | ------------------ | ---- | --------- | --------------------------------------------------------------- |
| agent_id / skill_id     | UUID FK            | 否   | 无        | 联合主键；员工与共享技能                                        |
| created_at / updated_at | UTC time           | 否   | 当前时间  | 保留原装配时间与当前配置更新时间                                |
| enabled / parameters    | bool / JSON object | 否   | true / {} | 启停及非秘密参数                                                |
| revision                | int                | 否   | 1         | 参数、启停或依赖映射变化递增                                    |
| tool_bindings           | JSON object        | 否   | {}        | 可选需求键→connection_id 与 tool_name；只能映射到该员工已有许可 |

员工删除 CASCADE，技能删除 RESTRICT，保留 skill_id 反向索引及 JSON/布尔/正修订约束。映射元素的同员工许可与目录匹配由应用在聚合保存事务中校验；JSON 不形成数据库外键。关系与员工修订同事务更新。

解除技能不自动撤销员工独立工具许可；界面提示仍可使用的工具。反过来撤销许可后，依赖该工具的技能显示未就绪，旧运行后续调用被阻止。是否保留待补配置由就绪状态表达，不伪造工具授权。

## 工具定义、连接与装配授权

内置工具与领域校验器由受信代码登记；MCP 工具来自管理员批准连接的动态发现。二者共用授权和运行契约。旧 skill_tools、agent_skill_tools 是未实施的目标，现由平台附加需求映射与独立 agent_tool_grants 取代。

### tool_connections（连接与获准目录）

新增，阶段对应通用 MCP S2。使用公共 ID、created_at、updated_at。

同一模型可先支持[CI 凭证连接化](../skills-and-mcp/ci-connection-migration.md)：首批仅 mcp_http、GitHub 只读预设与 Bearer，连接持有密文，不另建每员工凭证表。该先行增量不表示下表所有协议与认证类型均已开放。

| 字段                                  | 类型        | 可空 | 默认  | 含义与约束                                                           |
| ------------------------------------- | ----------- | ---- | ----- | -------------------------------------------------------------------- |
| name / kind                           | text / enum | 否   | 无    | 管理名称；首批 mcp_http/native，stdio 另阶段设计                     |
| provider_key                          | text        | 是   | NULL  | native 工具的受信注册标识；mcp_http 不要求逐服务代码提供者           |
| auth_type                             | enum        | 否   | 无    | 首批 none/bearer/header；OAuth 在实现前不可标可用                    |
| public_config                         | JSON object | 否   | {}    | 非秘密地址与传输配置，须经过部署网络策略校验                         |
| encrypted_credentials                 | text        | 是   | NULL  | none 可空；启用的其他认证须有受保护密文，显式清除须同时停用连接      |
| approved_catalog                      | JSON array  | 否   | []    | 已审核工具名、描述、schema、相关元数据与 descriptor_hash；空即无工具 |
| catalog_revision                      | int         | 否   | 1     | 目录批准/撤销时递增；单纯发现候选不扩权                              |
| discovery_candidate                   | JSON object | 是   | NULL  | 事务外发现的候选、摘要、基线修订与有效期；批准须核对仍有效           |
| enabled                               | bool        | 否   | true  | 禁用阻止后续调用                                                     |
| config_revision / credential_revision | int         | 否   | 1 / 1 | 配置与秘密分别修订，不在旧运行中透明换账号                           |
| created_by_user_id                    | UUID FK     | 是   | NULL  | 创建审计；旧身份迁入不伪造历史设置人                                 |

名称唯一、JSON 类型、枚举与正修订为数据库约束；地址、认证兼容、目录元素唯一和摘要匹配由应用校验。mcp_http 不接受 native provider_key；native 必须来自受信代码。认证更新不得通过空字符串意外清空；接口提供明确清除语义。

先事务外读取候选，再以预期修订短事务批准目录。新增工具不进入既有员工许可；获准工具的相关描述/schema/元数据变化令旧许可的该工具摘要失配，须重新批准，不能自动接受新权限。首次连接及每次工具调用前重查远端目录，失配停止受影响工具并保存待审核候选，无法检查则不继续调用；协议通知可使缓存失效。相同 schema 下的远端实现变化及检查/调用竞态仍无法完全证明，错误与重验结果需实际记录。

当前许可引用连接时 RESTRICT 删除；先停用并解除许可。已结束步骤 FK 可 SET NULL，并保留非秘密来源快照。凭证不进入目录或 API，响应只含认证是否配置及测试结果。

### agent_tool_grants（员工独立工具许可）

新增，阶段 S2。使用公共 ID、created_at、updated_at。

| 字段                          | 类型        | 可空 | 默认     | 含义与约束                                                              |
| ----------------------------- | ----------- | ---- | -------- | ----------------------------------------------------------------------- |
| agent_id / tool_connection_id | UUID FK     | 否   | 无       | UNIQUE；每员工每连接一份许可，可被多个 Skill 使用                       |
| tools                         | JSON array  | 否   | []       | 明确工具名、获准 descriptor_hash 和受支持参数约束；不接受通配符自动授权 |
| scope_policy                  | JSON object | 否   | 无       | 明确由受限上游身份保障，或引用受信范围解释器及参数；空对象不放行        |
| enabled / revision            | bool / int  | 否   | true / 1 | 许可启停与条件更新                                                      |
| grant_origin                  | enum        | 否   | admin    | admin/legacy_ci，后者仅迁移写入                                         |
| granted_by_user_id            | UUID FK     | 是   | NULL     | admin 来源必须真实设置人；旧迁入允许 NULL                               |

员工 FK CASCADE，连接 FK RESTRICT；按连接建反向索引。CHECK JSON 类型、正修订及来源/设置人组合。工具摘要是否在获准目录、scope_policy 是否可强制执行、参数约束与操作语义由应用检查。

许可变更与 agents.revision 同事务；不因为某 Skill 被修改就扩大许可。连接许可中的资源范围与 Skill 参数的任务默认值分别保存，宿主验证匹配。标准 schema 和只读注解不自动解释任意服务的业务范围。

CI 先行迁入的 scope_policy 除原仓库和 method 上限，还保留受信的旧 CI 执行上下文限制，防止旧权限自动扩展到任意任务。grant_origin 仅记录来源，不能代替策略检查；后续放宽上下文须显式复核并递增许可修订，细则见[连接化迁移](../skills-and-mcp/ci-connection-migration.md#4-员工许可默认目标与工具选择)。

## 知识资产、处理与发布

这些表来自既有知识助手的资料编辑、发布、引用和反馈要求。原文件和不可变索引放应用数据目录，关系与规范化正文放 SQLite；不因图中出现知识模块而先部署独立向量数据库。下列同库引用使用复合 FK，管理权限按 owner_user_id 校验。

### knowledge_bases（资料归属与当前发布）

阶段：P3。使用公共 ID、created_at、updated_at。

| 字段                       | 类型           | 可空 | 默认       | 含义与约束                                           |
| -------------------------- | -------------- | ---- | ---------- | ---------------------------------------------------- |
| owner_user_id / name       | UUID FK / text | 否   | 无         | 资料创建者与非空库名称                               |
| category                   | text           | 是   | NULL       | 管理标签，不作为权限                                 |
| status / revision          | enum / int     | 否   | active / 1 | active/archived；编辑和发布条件更新                  |
| default_processing_rule_id | UUID FK        | 是   | NULL       | 本库默认规则；仅创建组装期间可空，业务创建同事务回填 |
| active_release_id          | UUID FK        | 是   | NULL       | 当前本库 ready 发布，首次发布前可空                  |

UNIQUE(id)；复合 FK(default_processing_rule_id, id) → rules(id, knowledge_base_id)，FK(active_release_id, id) → releases(id, knowledge_base_id)。先建库空指针，再建默认规则并回填，无需延迟 FK。按 owner_user_id/updated_at/id 查询。

归档立即阻止后续知识调用，历史内容仍按权限保护。库不硬删历史证据。切发布必须检查 ready 与预期库 revision，单事务更新指针和修订。

### knowledge_groups（一级文档分组）

阶段：P3。使用公共 ID、created_at、updated_at。

| 字段                                | 类型                  | 可空 | 默认  | 含义与约束                      |
| ----------------------------------- | --------------------- | ---- | ----- | ------------------------------- |
| knowledge_base_id / name / name_key | UUID FK / text / text | 否   | 无    | 同库分组；name_key 为规范化名称 |
| sort_order / revision               | int                   | 否   | 0 / 1 | 管理排序与编辑条件更新          |

UNIQUE(id, knowledge_base_id)、UNIQUE(knowledge_base_id, name_key)。不加 parent_id。删除组先在同事务将相关文档 group_id 置空，再删组；不能在复合外键上 SET NULL 连带清空库 ID。分组、标签不改变已发布选材。

### knowledge_sources（稳定接入出处）

阶段：P3。使用公共 ID、created_at、updated_at。

| 字段                     | 类型           | 可空 | 默认   | 含义与约束                             |
| ------------------------ | -------------- | ---- | ------ | -------------------------------------- |
| knowledge_base_id / name | UUID FK / text | 否   | 无     | 本库来源身份与非空名称                 |
| kind / revision          | enum / int     | 否   | 无 / 1 | manual/builtin_sample；创建时明确 kind |

UNIQUE(id, knowledge_base_id)，按库/kind 查询。来源身份与 `(source_id, source_item_key)` 支持样例重复导入和后续追踪；不随每次上传创建来源。已有文档引用时拒绝删除。不预建 Wiki 凭证、游标和同步配置。

### knowledge_documents（文档稳定身份与管理头）

阶段：P3。使用公共 ID、created_at、updated_at。

| 字段                                            | 类型                       | 可空 | 默认          | 含义与约束                                                 |
| ----------------------------------------------- | -------------------------- | ---- | ------------- | ---------------------------------------------------------- |
| knowledge_base_id / source_id / source_item_key | UUID / UUID / text         | 否   | 无            | 同库来源及稳定条目标识；不按同名合并                       |
| title                                           | text                       | 否   | 无            | 当前版本标题的管理投影，内容替换时同事务同步               |
| group_id                                        | UUID FK                    | 是   | NULL          | 同库一级组；NULL 为未分组                                  |
| tags / enabled / revision                       | JSON string[] / bool / int | 否   | [] / true / 1 | 当前标签、候选启用状态与编辑控制                           |
| current_version_id                              | UUID FK                    | 是   | NULL          | 当前候选内容；导入成功同事务建立版本并回填，不代表线上发布 |

UNIQUE(id, knowledge_base_id)、UNIQUE(source_id, source_item_key)。来源/分组复合引用同库；FK(current_version_id, id, knowledge_base_id) → versions(id, document_id, knowledge_base_id)。新建先空头，再版本和回填；业务成功前头不可缺失。

按库/组/更新时间/id 索引；标题重名不合并。标签移组不产生内容版本，影响回答的标题、来源说明和正文变化需新版本。停用候选文档不偷偷改旧发布。

### knowledge_document_versions（不可变内容）

阶段：P3。使用公共 ID、created_at；无 updated_at。

| 字段                                      | 类型               | 可空 | 默认          | 含义与约束                                       |
| ----------------------------------------- | ------------------ | ---- | ------------- | ------------------------------------------------ |
| knowledge_base_id / document_id / version | UUID / UUID / int  | 否   | 无            | 所属文档及正整数版本                             |
| title / text / content_hash               | text               | 否   | 无            | 标题与规范化原文；哈希覆盖影响回答的内容和元信息 |
| source_label / metadata                   | text / JSON object | 否   | 空字符串 / {} | 来源、内容状态和生效依据；未知不推断已实现       |
| original_ref                              | text               | 是   | NULL          | 服务端原文件引用，不是任意客户端路径             |

FK(document_id, knowledge_base_id) → documents(id, knowledge_base_id)；UNIQUE(document_id, version)、UNIQUE(id, document_id, knowledge_base_id)、UNIQUE(id, knowledge_base_id)。保存后不覆盖；内容相同可共享原文件存储，但不合并不同文档身份。解析或清洗若改变固定正文，即使原件不变也建立新内容版本；仅切分或向量模型变化可复用原文版本并创建新发布。

### knowledge_processing_rules（不可变处理规则）

阶段：P3；embedding 在 P4。使用公共 ID、created_at；无 updated_at。

| 字段                        | 类型          | 可空 | 默认 | 含义与约束                                            |
| --------------------------- | ------------- | ---- | ---- | ----------------------------------------------------- |
| knowledge_base_id / version | UUID FK / int | 否   | 无   | 同库规则版本唯一                                      |
| parameters                  | JSON object   | 否   | 无   | 受控解析、清洗、切片、分词和适配版本参数              |
| embedding_connection_id     | UUID FK       | 是   | NULL | full_context 可空；hybrid 必须为支持的 embedding 连接 |

UNIQUE(knowledge_base_id, version)、UNIQUE(id, knowledge_base_id)。发布固定规则，修改默认规则新建记录。实际模型、维度及配置修订在发布 manifest 中封存，向量空间不兼容时创建新连接和发布，不能改旧索引的解释。

### knowledge_source_blocks（可定位的原文区间）

阶段：P3。使用公共 ID、created_at；无 updated_at。

| 字段                                    | 类型                      | 可空 | 默认 | 含义与约束                                            |
| --------------------------------------- | ------------------------- | ---- | ---- | ----------------------------------------------------- |
| knowledge_base_id / document_version_id | UUID FK                   | 否   | 无   | 同库不可变原文版本                                    |
| parser_version / ordinal                | text / int                | 否   | 无   | 受控解析版本与正整数顺序                              |
| text / source_range / content_hash      | text / JSON object / text | 否   | 无   | 正文片段、规范化正文 Unicode 字符区间与来源位置、摘要 |

FK(document_version_id, knowledge_base_id) → versions(id, knowledge_base_id)；UNIQUE(document_version_id, parser_version, ordinal)、UNIQUE(id, knowledge_base_id)。按文档版本、解析版本、ordinal 查询。

解析块保存后不可改。source_range 保存 canonical_start/canonical_end，表示文档版本固定正文中的 Unicode 字符区间 `[start,end)`，并用 locator 补充页码、段落或表格行；展示行号可派生。应用核对区间与原文一致，前端不把该偏移当 UTF-16 下标使用。检索切片是派生索引数据，通过来源块 ID 和块内 Unicode 区间映射，不另建核心 chunk 表。发布 manifest 固定解析版本，不能从另一解析结果取块冒充。具体映射样例见[Notion 来源契约](https://app.notion.com/p/409eab92f600811d938acc26b4bd8d62)。

### knowledge_releases（确定的选材和产物）

阶段：P3。使用公共 ID、created_at；building 阶段可保留 updated_at，ready 后只允许状态控制。

| 字段                                             | 类型               | 可空           | 默认      | 含义与约束                                                                     |
| ------------------------------------------------ | ------------------ | -------------- | --------- | ------------------------------------------------------------------------------ |
| knowledge_base_id / version / processing_rule_id | UUID / int / UUID  | 否             | 无        | 同库正整数发布序号与不可变规则                                                 |
| status                                           | enum               | 否             | building  | building/ready/failed/archived；ready 仅表示候选可用，显式发布后才成为当前发布 |
| manifest / content_hash                          | JSON object / text | 清单否，摘要是 | {} / NULL | 解析、索引、模型、维度、制品与摘要；ready 时完整非空                           |

UNIQUE(knowledge_base_id, version)、UNIQUE(id, knowledge_base_id)；规则使用同库复合 FK。候选创建后选材和规则不改，改选择新建候选。构建失败可对同一候选显式新建作业；ready 后内容与制品封存，不在原发布重建。

manifest 不维护另一份可变文档 ID 数组；权威选材在 release_documents。full_context 可无向量索引，hybrid 必须具有匹配索引。取消/中断的构建作业保持真实终态，候选非 ready，UI 以作业原因区分，不将其显示为已上线。

### knowledge_release_documents（发布选材关系）

阶段：P3。纯关联，无公共 ID、时间或独立修订。

| 字段                                    | 类型    | 可空 | 默认 | 含义与约束                           |
| --------------------------------------- | ------- | ---- | ---- | ------------------------------------ |
| release_id / document_id                | UUID FK | 否   | 无   | 联合主键；同一发布只选一份该文档内容 |
| knowledge_base_id / document_version_id | UUID FK | 否   | 无   | 固定同库文档版本                     |
| ordinal                                 | int     | 否   | 无   | 发布内唯一的正整数全文顺序           |

FK(release_id, knowledge_base_id) → releases(id, knowledge_base_id)，FK(document_version_id, document_id, knowledge_base_id) → versions 的复合唯一键，UNIQUE(release_id, ordinal)。同候选内容哈希一起封存，不按当前分组重算。

### knowledge_jobs（有界知识后台尝试）

阶段：P3。使用公共 ID、created_at、updated_at。

| 字段                                                    | 类型                  | 可空 | 默认       | 含义与约束                                                                           |
| ------------------------------------------------------- | --------------------- | ---- | ---------- | ------------------------------------------------------------------------------------ |
| knowledge_base_id / kind                                | UUID FK / enum        | 否   | 无         | kind 仅 import/build/retrieval_test，不是通用多态任务                                |
| source_id / processing_rule_id                          | UUID FK               | 是   | NULL       | 仅 import 必填；与知识库同库，其余类型为空                                           |
| release_id                                              | UUID FK               | 是   | NULL       | build/retrieval_test 必填，import 必须为空                                           |
| initiated_by_user_id / client_request_id / request_hash | UUID FK / UUID / text | 否   | 无         | 用户、请求 ID 唯一；摘要固定 kind、目标、文件与输入                                  |
| retry_of_job_id                                         | UUID FK               | 是   | NULL       | 显式重试新建尝试；同库同类型                                                         |
| status / revision                                       | enum / int            | 否   | queued / 1 | queued/running/cancelling/succeeded/partially_succeeded/failed/cancelled/interrupted |
| snapshot / result                                       | JSON object           | 否   | {} / {}    | 固定输入依据和有界实际诊断结果；不存秘密或任意资源目标                               |
| error_code / usage                                      | text / JSON object    | 是   | NULL       | 安全错误与实际用量                                                                   |
| started_at / cancel_requested_at / finished_at          | UTC time              | 是   | NULL       | 运行、取消与终态时间                                                                 |

UNIQUE(initiated_by_user_id, client_request_id)、UNIQUE(id, knowledge_base_id)、UNIQUE(id, knowledge_base_id, kind)。所有资源使用同库复合 FK；重试使用 (retry_of_job_id, knowledge_base_id, kind) 复合 FK，保证同库同类型。CHECK kind 对应的非空字段组合、状态与结束时间；partially_succeeded 仅 import 可用。

按库/status/created_at、用户/status 索引；build 在 active 状态对 release_id 建部分唯一索引。结果中 build 产物只有校验后提交到 release manifest，retrieval_test 保存受限候选/预算，不生成正式回答。全局与用户额度同 runs 在一个准入事务中检查；重启标记 interrupted，不自动重放。

### knowledge_import_items（导入逐项结果）

阶段：P3。不使用公共 ID；仅有列出的复合键与时间。

| 字段                                           | 类型               | 可空     | 默认          | 含义与约束                                           |
| ---------------------------------------------- | ------------------ | -------- | ------------- | ---------------------------------------------------- |
| job_id / item_key / knowledge_base_id          | UUID / text / UUID | 否       | 无            | 联合主键 job_id/item_key；所属 import 作业及同库     |
| operation                                      | enum               | 否       | 无            | create/replace，不按文件名猜覆盖                     |
| original_ref / content_hash / input_kind       | text               | 否       | 无            | 原件已持久化；input_kind 为 file/text/builtin_sample |
| source_item_key                                | text               | 否       | 无            | 来源内稳定条目标识；手工可生成标识，样例由包条目固定 |
| target_document_id / expected_document_version | UUID FK / int      | 是       | NULL          | replace 两者必填；create 为空                        |
| target_group_id / result_version_id            | UUID FK            | 是       | NULL          | 同库目标组及实际导入成功的内容版本                   |
| status / error_code                            | enum / text        | 错误可空 | queued / NULL | queued/running/imported/failed/cancelled/interrupted |
| created_at / updated_at                        | UTC time           | 否       | 当前时间      | 逐项处理时间                                         |

FK(job_id, knowledge_base_id) → jobs(id, knowledge_base_id)，作业 kind 在应用强制为 import；目标文档、组与结果版本使用同库 FK。CHECK create/replace 的目标组合；成功结果不得空。按 job/status 查询。

结果版本自身持有文档 ID，创建项不再重复存可编辑的结果文档身份。替换只在当前版本仍匹配时保存；重试只复制明确失败项，不覆盖已成功或更新后的内容。

### knowledge_answers（实际回答证据）

阶段：P3；评测归属 E 扩展。使用公共 ID、created_at；完成后不可变，无 updated_at。

| 字段                                    | 类型                                          | 可空 | 默认              | 含义与约束                                   |
| --------------------------------------- | --------------------------------------------- | ---- | ----------------- | -------------------------------------------- |
| run_id                                  | UUID FK                                       | 否   | 无                | 核心阶段唯一关联一个聊天 run，不额外保存正文 |
| knowledge_base_id / release_id          | UUID FK                                       | 否   | 无                | 与本轮获准知识上下文相同                     |
| strategy / snapshot / trace / citations | enum / JSON object / JSON object / JSON array | 否   | 无 / 无 / {} / [] | 实际策略、送模证据区间、检索依据和校验后引用 |

UNIQUE(run_id)；FK(run_id, knowledge_base_id, release_id) → run_knowledge_contexts 的复合唯一键，发布另有同库 FK。证据在使用时通过 run_steps 保存，正式回答行只在校验通过且成功终态事务中写入。实际检索无命中属于正常知识边界，trace 记录无命中、citations 可为空；未实际读取不建回答行。正文仍在对应 Message，失败诊断不冒充成功回答。

引用块必须属于真实送模区间与发布选材，JSON 内区间由应用验证。E 阶段建立评测三表后，显式将 run_id 改可空、新增唯一 evaluation_result_id FK，并 CHECK 二者恰好一个非空；评测正文由 EvaluationResult 保存。当前 P3 不创建指向未建表的占位 FK。

### answer_feedback（回答判断与说明）

阶段：P3。使用公共 ID、created_at、updated_at。

| 字段                       | 类型              | 可空 | 默认              | 含义与约束                               |
| -------------------------- | ----------------- | ---- | ----------------- | ---------------------------------------- |
| answer_id / user_id        | UUID FK           | 否   | 无                | 同用户同回答唯一；读取先校验回答内容范围 |
| decision / note / revision | enum / text / int | 否   | 无 / 空字符串 / 1 | useful/needs_improvement；说明与条件更新 |

UNIQUE(answer_id, user_id)。反馈只用于聊天知识回答，评测评分仍由评测结果管理。反馈不改 Run 成功状态、不自动改知识和发布。用户/回答删除 RESTRICT，历史按对话范围保留。

## 运行允许目录、实际动作与回答

本版运行技能目录放 config_snapshot；知识许可单独关系化，因其有固定发布与内容范围。步骤记录真实动作，不由快照存在推断发生过调用。

### users（保留账号）

阶段：原有。保留现有公共 ID 与时间。

字段与约束保持[认证设计](../../reference/auth.md)及[GitHub 登录契约](../../reference/github-signin.md)和[当前模型](../../../backend/app/auth/models.py)，本版不新增租户或资源所有权通用字段。

### external_identities（保留登录身份）

阶段：当前基线。字段、默认与约束不变。

沿用[当前认证模型](../../../backend/app/auth/models.py)与[GitHub 登录设计](../../reference/github-signin.md)：user_id 引用 users 并 CASCADE，provider/provider_user_id 唯一，user_id/provider 唯一。它只绑定登录身份，不保存工具访问凭证，不作为 agent_tool_grants 的授权来源。

### auth_sessions（保留会话）

阶段：原有。字段、默认及约束不变。

沿用[当前模型](../../../backend/app/auth/models.py)的会话身份、过期、撤销与用户级联规则。运行会话 FK 仍为 SET NULL，用户审计引用保留。

### organization_rules（保留全局规则）

阶段：原有。不使用公共 UUID，保持单例整型主键。

沿用[当前模型](../../../backend/app/organization_rules/models.py)的 id=1、正文与 revision。它不是知识文档，不增加员工关联。

### conversations（收紧私有知识内容范围）

阶段：P3。使用公共 ID、created_at、updated_at。

| 字段          | 类型    | 可空 | 默认       | 含义与约束                          |
| ------------- | ------- | ---- | ---------- | ----------------------------------- |
| visibility    | enum    | 否   | platform   | platform/owner；旧记录保持 platform |
| owner_user_id | UUID FK | 否   | 沿用创建者 | owner 范围不能被 resources:all 绕过 |

其余当前字段与索引不变。接受私有知识上下文时，要求 actor=库拥有者=对话拥有者，同事务切为 owner。只能收紧，不因解绑重开共享。列表、消息、run、步骤、SSE、引用、导出与缓存一致检查。

### messages（SDK 消息的公开投影）

完整消息和图状态继续由 SDK checkpoint 保存，不新增业务消息表。Run 的输入/输出消息 ID 与序号构成公开读取索引；知识回答证据关联 Run 与公开消息 ID，权限沿用对话范围，不为构建/评测作业制造聊天消息。

### runs（保留聊天尝试与固定依据）

阶段：P1；知识字段通过引用扩展 P3。使用公共 ID、created_at、updated_at。

| 字段                    | 类型        | 可空 | 默认 | 含义与约束                                                                                                                 |
| ----------------------- | ----------- | ---- | ---- | -------------------------------------------------------------------------------------------------------------------------- |
| config_snapshot         | JSON object | 否   | 无   | 当前 schema 固定正文、展示与执行预算；标准包/MCP 切换时升级 schema，固定制品及平台配置、工具摘要、许可和连接修订；不存秘密 |
| request_hash            | text        | 否   | 无   | 幂等摘要加入显式 selected_skill_ids；沿用结构化 work                                                                       |
| usage                   | JSON object | 是   | NULL | 累计全部模型 token 用量；未知字段保持未知，工具次数由步骤统计                                                              |
| ci_result / ci_feedback | JSON object | 是   | NULL | 保留 CI 领域报告与原一次反馈语义，本版不强拆                                                                               |

其余既有字段、状态、消息 ID 关联、重试、用户/请求唯一和活跃对话唯一索引不变。当前执行 schema 1；标准包/MCP 执行器采用升级后的 schema，已接受的快照不回写、不补造步骤；普通聊天重启从 checkpoint 恢复原运行，显式重试重新捕获配置。快照体积与候选数量设限，超限明确拒绝，不隐式漏技能。

快照不外键引用可修改的关系或虚构发布；每轮固定当时全文与授权摘要，运行前及每次操作复查当前许可。历史 FK 删除行为沿用现状；快照不是可变步骤仓库。

### run_knowledge_contexts（本轮获准资料）

阶段：P3。不使用公共 ID/updated_at；固定上下文不可改。

| 字段                           | 类型               | 可空 | 默认     | 含义与约束                                          |
| ------------------------------ | ------------------ | ---- | -------- | --------------------------------------------------- |
| run_id                         | UUID FK            | 否   | 无       | 主键；每轮最多一份                                  |
| knowledge_base_id / release_id | UUID FK            | 否   | 无       | 固定同库 ready 发布                                 |
| strategy / snapshot            | enum / JSON object | 否   | 无       | full_context/hybrid；固定预算、处理、模型和索引依据 |
| created_at                     | UTC time           | 否   | 当前时间 | 接受时捕获，不代表已经读取                          |

PK(run_id)、UNIQUE(run_id, knowledge_base_id, release_id)；发布使用同库复合 FK。资料许可与 owner 可见性在接受事务中完成。快照不保存全部原文；实际读取和答案证据在步骤/知识回答中记录。

### run_steps（可观察的真实动作）

阶段：P1 已实现；tool_connection_id 在 P2 建立连接表时再增加。使用公共 ID、created_at、updated_at。

| 字段                                     | 类型                      | 可空           | 默认             | 含义与约束                                                                                                 |
| ---------------------------------------- | ------------------------- | -------------- | ---------------- | ---------------------------------------------------------------------------------------------------------- |
| run_id / sequence / step_key             | UUID FK / int / text      | 否             | 无               | 运行内顺序与去重键各自唯一                                                                                 |
| kind / status                            | enum                      | 否             | 无 / running     | skill_activation/model_call/tool_call/knowledge/validation；running/succeeded/failed/cancelled/interrupted |
| skill_id（P1）/ tool_connection_id（P2） | UUID FK                   | 是             | NULL             | 当前目录引用可 SET NULL；历史非秘密来源保存在 safe_details                                                 |
| safe_details / result_ref / error_code   | JSON object / text / text | 仅明细非空     | {} / NULL / NULL | 捕获的技能/关系修订、契约、范围摘要与结果引用；不记录秘密/私有推理                                         |
| started_at / finished_at                 | UTC time                  | 开始否，结束是 | 当前时间 / NULL  | 真实区间；结束状态必须有结束时间                                                                           |

UNIQUE(run_id, sequence)、UNIQUE(run_id, step_key)；run 引用 RESTRICT，目录/连接删除 SET NULL。当前按 run/sequence 查询，恢复从活跃 run 关闭其 running 步骤；未增加独立状态清扫索引，后续按规模评估。

CHECK 保证 sequence > 0、状态合法和结束时间匹配；序号由持久化事务分配。技能/资源步骤匹配本轮内容制品；工具步骤匹配本轮独立许可、连接和工具摘要，skill_id 可空，只有宿主具有真实关联依据时才记录。不能要求独立工具调用具有 Skill 或旧需求槽位；这些是应用校验。执行进度先保存再向前端发布；崩溃将未终结步骤标 interrupted。去重键防重复记账，不承诺外部副作用恰好一次。

## 完整性、事务与版本解析

1. **配置事务**：员工及关系/授权一起校验和保存，携带预期修订；技能配置变化递增关系与员工修订；独立许可变化递增许可自身与员工修订，不强制修改无关技能关系。技能内容指针、参数规范和附加配置一起保存并递增技能修订；员工工具许可独立于技能关系。密钥更新不嵌入员工保存事务。
2. **运行接受事务**：身份、资源范围、幂等、容量、固定方法、输入/输出占位及 queued Run 一起提交；私有知识上下文与 owner 可见性同事务。外部调用在事务外。
3. **知识写入事务**：父行可空指针 → 不可变子行 → 回填当前指针。组合外键防跨库；业务事务保证建库默认规则和成功文档头完整。并发序号在写锁事务中分配，不用客户端条数生成。
4. **发布事务**：候选选材先封存，事务外生成产物；构建成功只将候选置 ready；显式发布请求在短事务检查产物摘要、同库 ready 及预期库 revision 后切指针。失败保留旧发布。发布依赖规则、模型和解析版本，不跟随最新配置。
5. **调用前复查**：身份、员工/技能/关系启用、关系/许可修订、获准工具摘要与受信策略、连接配置/凭证/目录修订、库/发布可用状态；参数不能覆盖授权范围。已发出的上游请求不承诺撤回。
6. **终态事务**：知识证据校验后的 knowledge_answers、最终消息、用量和 Run 成功一起保存；CI 继续原报告原子保存。持久化失败不宣告成功，取消/迟到结果不得覆盖终态。
7. **作业一致性**：knowledge_jobs 与 runs 共用 SQLite 短事务准入和有界执行资源；导入逐项结果独立保存，整体可部分成功；不把作业伪造成聊天 Run，也不自动重放。

## 生命周期与索引

| 数据                        | 当前配置退出/删除                                  | 历史保留                                                  |
| --------------------------- | -------------------------------------------------- | --------------------------------------------------------- |
| 员工与共享技能              | 员工有对话禁止硬删；技能被关系引用禁止删，优先停用 | 已固定方法与步骤快照保留，解除关系不删历史                |
| 技能内容制品                | 首批不提供永久删除，当前指针可切换                 | 原始资源、清单和摘要保留，不能只留不可恢复的哈希          |
| 模型/工具连接               | 当前配置和活跃引用保护；先停用并解除授权           | 非秘密来源保留，已结束历史 FK 可 SET NULL；密钥不进入历史 |
| 文档、规则、发布和来源块    | 归档库；分组可移出后删除，其他已引用资料不硬删     | 保留旧版本、制品与引用，不因当前指针变化清理              |
| 知识作业与临时文件          | 取消不撤销已完成导入；无引用暂存文件按保留策略清理 | 失败/重试尝试可查询，已引用原件和索引不作为临时文件清理   |
| 对话、消息、Run、步骤与回答 | 无新永久擦除入口，不额外开放跨用户读取             | 继续原访问范围；私有内容范围只收紧                        |

除各实体列出的索引，所有外键引用方向检查反向查询需求。SQLite 复合索引按左前缀服务目标查询，不能仅因有字段就建索引。偏移分页沿用当前 offset/limit 和稳定时间+ID排序；数据量与执行计划验证后再调整。

## 迁移与待验证项

实际阶段、源字段映射、兼容窗口、回填校验、回退及验收只在[迁移与验收](migration.md)维护。正式 Alembic revision 在实现时按实际 head 创建，本次没有迁移脚本。

以下为明确后续边界：技能发布与多实例需新需求和正式变更；E 阶段才扩展回答归属并增加评测表；供应商能力、预算数值、索引性能、正式迁移与权限全链路须实施验收。字典里的字段不是当前接口已经支持的字段。

## 本次设计校验

2026-10-22 在隔离内存 SQLite 验证了 25 项关键外键、唯一与 CHECK 组合：包含无延迟外键的头指针组装、跨库和跨提供者拒绝、发布选材、作业重试类型、活跃构建唯一及历史 SET NULL。该实验不是完整建表/迁移，也未验证应用授权、不可变写入边界、索引性能和供应商行为；完整检查按[迁移验收](migration.md#验收)实施。

2026-10-23：已按标准 Skill/通用 MCP 重新整理技能制品、动态目录与员工独立工具许可。上述新字段尚未建表；2026-10-22 的 25 项实验不覆盖本次调整，须重新进行 schema、迁移、授权与真实协议验收。

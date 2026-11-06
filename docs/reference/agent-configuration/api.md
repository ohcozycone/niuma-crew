# 员工与技能管理接口

配置结构以[正式迁移](../../../backend/migrations/versions/)及当前 ORM 为准。配置接口负责保存，不在保存时调用模型；普通聊天在接受运行后按需加载装配方法。完整字段约束见[数据字典](../data-model.md)，运行、阶段与验收分别见[运行契约](../runtime.md)和P1 历史验收。OpenAPI 是请求与响应类型的机器来源。

## 权限与共同规则

员工和 Skill 配置管理要求管理员会话。写入要求合法 Origin、JSON 内容类型及对应能力；游客只有公开展示权限，member 可使用共享员工创建、读取和取消本人运行，并管理本人 MCP 账号，不能修改员工与 Skill 共享定义。逐项权限见[身份契约](../auth.md)。匿名 401、缺权限 403、资源不存在 404、修订/引用冲突 409、请求或参数无效 422、容量不足 429、数据库繁忙 503。

ID、时间、修订、关系修订和资源数量均由服务器生成。创建不传预期修订；员工/技能 PATCH 必须传正整数 `expected_revision`。模型连接 PATCH 必须同时传 `expected_config_revision` 与 `expected_credential_revision`。缺失或错误类型为 422，过期为 `409 configuration_revision_conflict`，失败不部分保存。无实际变化不递增配置修订；显式提交替换 Key 算凭证变更。

不保留旧 `model_id`、`skill_ids` 写字段或旧单关系增删接口。技术资源名统一为 Agent，管理与公开 API 使用 agents，权限使用 agents:*，对话使用 agent_id / agent_name，数量摘要使用 agents。页面使用 /agents 与 agent 查询参数，草稿直接使用新资源键；旧命名不设置路由别名、参数或草稿转换，前后端同批部署。界面继续称“数字员工”。既有数据库与历史快照的保留规则见[当前结构](data.md#迁移与验证)。

## 员工接口

| 方法与路径                | 成功 | 用途与权限                                                  |
| ------------------------- | ---- | ----------------------------------------------------------- |
| POST `/api/agents`        | 201  | `agents:create`；创建身份和可选装配                         |
| GET `/api/agents`         | 200  | `agents:read`；当前页摘要                                   |
| GET `/api/agents/{id}`    | 200  | `agents:read`；岗位、示例、交付、修订和完整装配配置         |
| PATCH `/api/agents/{id}`  | 200  | `agents:update`；条件更新聚合                               |
| DELETE `/api/agents/{id}` | 204  | `agents:delete`；已有对话拒绝删除，否则级联删关系、保留技能 |

创建只要求 name、avatar_id。员工名称去除首尾空白后在当前部署的整个员工目录内唯一，停用员工也占用名称；按保存值精确比较，英文大小写不同视为不同名称。创建与改名均检查，改名排除自身；重名返回 `409 agent_name_conflict` 和“员工名称已存在，请换个名字。”，表单保留输入并在名称输入框下方显示错误，不在页面顶部占位；修改姓名清除旧提示。数据库唯一索引同时保护直接写入与并发。名称不承担关联职责，UUID 不变；提交自身原名不递增修订。

普通岗位与展示字段沿用现有含义，模型唯一来源为 model_connection_id。显式写模型外键（含 null）要求 `agents:assign_model`；写 skill_assignments 要求 `agents:assign_skills`。非空模型外键必须存在、启用且为 chat；接受对话时再次检查。

员工配置页的系统提示词提供通用静态填写模板，仅在字段为空时填入当前草稿，提示填写岗位目标、职责范围、工作方式和交付要求。模板不预置具体岗位内容、不调用模型；用户替换提示文字后通过正常保存提交。已有员工指令不因模板调整自动改写。

前端三个 tab 为基础配置、指令与知识、能力装配，URL 键不变。名称和大脑同页，工具与技能使用统一列表、筛选、搜索和分页。面板完成与装配移除只更新员工草稿，主保存沿用下述事务和修订检查；移除先确认，取消不修改草稿。知识辅区提供“我的知识库”独立个人装配入口，选库和召回规则通过knowledge接口单独保存，不属于当前共享员工保存契约；普通成员也可从对话页维护自己的装配。

`skill_assignments` 每项由 skill_id、enabled（默认 true）、parameters（默认 {}）组成。PATCH 省略整个集合保持原关系，[] 解除全部，传数组则完整替换；同技能重复 422。保留关系的创建时间不变，只有参数或启停变化递增关系修订。新关系使用当次员工修订，另捕获创建时间，避免删除重建后误认旧许可。

```json
{
  "expected_revision": 3,
  "skill_assignments": [
    {
      "skill_id": "11111111-1111-4111-8111-111111111111",
      "enabled": true,
      "parameters": { "tone": "brief" }
    }
  ]
}
```

装配详情增加 name、revision、updated_at、ready、readiness_reason。ready 只表示此刻技能已启用且有可用方法正文，不表示已实际调用或验证回答质量。空正文可保存草稿，停用或空正文不进入普通候选，显式指定会失败。

parameters 必须为不超过 16 KiB 的非秘密 JSON 对象，并符合技能 configuration_schema；空规范只允许 {}。不合法参数、不存在技能、名称或编号重复导致整次员工/关系修改回滚；编号重复仍返回 `agent_code_conflict`。只有明确的名称、编号唯一冲突转换为对应业务错误；未知完整性异常保持服务端错误，整次事务回滚，不伪装成可刷新解决的 409。

## 技能接口

| 方法与路径                          | 成功 | 用途与权限                                               |
| ----------------------------------- | ---- | -------------------------------------------------------- |
| POST `/api/skills`                  | 201  | `skills:create`；当前共享定义，初始 revision=1           |
| GET `/api/skills`                   | 200  | `skills:read`；当前页摘要、启停及 assignment_count       |
| GET `/api/skills/{id}`              | 200  | `skills:read`；正文、输入/输出说明、示例、参数规范和修订 |
| PATCH `/api/skills/{id}`            | 200  | `skills:update`；带 expected_revision 条件更新           |
| DELETE `/api/skills/{id}`           | 204  | `skills:delete`；被装配时 409 skill_in_use               |
| POST `/api/skills/import/preview`   | 200  | `skills:create`；校验并预览 ZIP，不保存                  |
| POST `/api/skills/import`           | 201  | `skills:create`；重新校验 ZIP 后创建一份标准包           |
| GET `/api/skills/{id}/files?path=…` | 200  | `skills:read`；按包内路径读取文本或二进制                |
| GET `/api/skills/{id}/export`       | 200  | `skills:read`；下载单技能 ZIP                            |

导入请求使用 `archive_base64`，另可传平台展示 name 与 category。详情增加 `skill_md`、`protocol_name` 和 files 清单；旧记录读取时编译完整主文，包含输入、输出和示例。POST/PATCH 可提供 `skill_md` 和 `package_files`；后者为完整文件集合，每项为 `{path,content}` 或 `{path,content_base64}`，二选一，必须包含 SKILL.md；同时提交的主文须一致。文件与平台字段一次保存，不能把部分加载的清单提交为整包替换。

标准包主文是唯一内容来源，更新解析描述和 instructions；旧说明字段保留兼容，标准包不能单独修改旧指令字段。分类、启停和参数规范独立于标准。中文展示名不替代包协议名。二进制文件读取返回 content_base64，文本返回 content；导出保持原字节。Skill JSON 写请求单独限 32 MiB，仍受包展开 20 MiB、128 文件、单文件 10 MiB、ZIP 12 MiB 和主文 128 KiB 的限制；其他普通 JSON 上限不变。存储、校验和生命周期见[技能模块](../../../backend/app/skills/README.md)。

configuration_schema 默认 {}；非空时必须是 `type=object`、`additionalProperties=false` 的有效 JSON Schema。规范不超过 16 KiB、嵌套不超过 20 层，不支持 $ref/$dynamicRef/$id 或远程解析。修改规范时预检所有启用关系；不兼容先停用、迁移参数再启用，不静默删除参数。

共享正文修改只影响新接受的运行。旧运行读取接受时的固定正文；实时停用、解除关系或修改关系参数会阻止后续动作。

## 分页、摘要与公开投影

管理列表响应均为 `{items,total,offset,limit}`，offset≥0，limit=1…100，默认 20。按 created_at 倒序、id 排序。员工列表为计数、当前页、批量关系三次查询，不随本页员工数逐项查技能。

| 列表   | 支持筛选                                                                                          | 不返回的详情                                                                  |
| ------ | ------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| agents | q（名称、编号、岗位、职责及技能名）、category、is_active、is_favorite、skill_id、model_configured | system_prompt、示例/交付正文、参数；只返回 skill_summaries 与 resource_counts |
| skills | q（名称、简介）、category                                                                         | instructions、configuration_schema、输入/输出说明与示例                       |

resource_counts.skills 统计启用装配；tools 统计启用许可中的实际工具操作，不统计 MCP 服务或账号连接数量；knowledge_bases 仍为 0。计数表达配置，不证明执行成功，也不可写入。

公开员工/技能端点保持显式白名单，不返回岗位指令、关系参数、模型连接标识或技能正文。公开详情保留示例和交付展示；管理员详情与公开投影不混用。

前端进入目录只取当前页，进入编辑按 ID 取详情；工作台内部返回复用已确认结果，保存后按影响更新记录和核对查询，搜索和筛选由服务端执行。GET `/api/configuration-summary` 返回 agents、skills、favorites 总数，要求员工与技能管理读取；公开同路径加 `/public/` 使用公开读取能力。侧栏收藏读取前 20 项，与相同条件的目录共用查询，并以该查询 total 显示收藏数量；技能使用数由服务端聚合，外壳搜索有界查询。身份改变销毁原状态；摘要不能当成完整配置提交。[共享数据标准](../../../frontend/src/state/README.md)定义前端存储、订阅和同步。

## 聊天选择与真实步骤

POST `/api/conversations/{id}/messages` 可传 selected_skill_ids：省略或 [] 自动发现，null/重复或超过 16 项显式选择为 422；未装配或未就绪为明确 409。同幂等键换选择 409，集合排序后计算摘要；重放返回原运行，不重新捕获配置。

步骤不再有独立 HTTP 接口。AssistantMessageView.steps 随历史、接受响应、回复读取和 SSE 返回同一安全快照；前端本地展开和分页。步骤包含实际 kind、status、技能标识、安全摘要、错误和时间，不返回 SDK 原始事件、凭证或私有推理。动作与 Run 版本同步持久化，刷新只观察。

运行的实际接口、预算、取消与故障规则见[运行契约](../runtime.md)。对应自动化测试：[配置](../../../backend/tests/test_configuration_api.py)、[真实 SDK](../../../backend/tests/test_capability_runtime.py)、[运行与 HTTP](../../../backend/tests/test_conversations.py)。

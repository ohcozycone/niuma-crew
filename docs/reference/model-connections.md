# 大脑配置与员工模型装配

本文维护当前已实现行为。实现与测试入口见正文；未来能力仅作为限制或链接，不构成已实现承诺。

## 目标与范围

管理员先在独立「大脑配置」页建立共享 LLM 连接，再在员工配置中选择大脑。大脑只负责模型接入；员工自己的提示词、技能、对话及任务状态不在连接中共享。本文维护现有配置 CRUD、员工绑定和主动连接检查；[真实对话](conversations.md)已另行实现，P1 普通聊天按需指引已实现，通用工具后置。

聊天预设由后端代码维护，统一使用 `openai-chat-completions` 协议。Model ID 可按账户权限调整，Base URL 固定，避免密钥被误发至任意地址。

| 预设 ID / provider | 名称      | Base URL                               | 默认 Model ID     |
| ------------------ | --------- | -------------------------------------- | ----------------- |
| `kimi-code`        | Kimi Code | `https://api.kimi.com/coding/v1`       | `kimi-for-coding` |
| `zhipu`            | 智谱 GLM  | `https://open.bigmodel.cn/api/paas/v4` | `glm-5.3`         |
| `deepseek`         | DeepSeek  | `https://api.deepseek.com`             | `deepseek-flash`  |

智谱使用开放平台标准 API Key，与 GLM Coding Plan Key 不通用；DeepSeek 使用开放平台 API Key。地址与模型名按 [智谱 OpenAI 兼容说明](https://docs.bigmodel.cn/cn/guide/develop/openai/introduction)及 [DeepSeek 快速开始](https://api-docs.deepseek.com/quick_start/)于 2026-11-05 核对。两者通过局部模型适配保留并回传 `reasoning_content`，支持思考模型的工具调用往返；该字段用于协议续接，当前不转换为界面的思考内容块。

依据 [Kimi Code 官方说明](https://www.kimi.com/code/docs/en/)（2026-10-17 核对），Kimi Code 面向编程场景，订阅 Key 与开放平台 Key 不通用，自有通用产品集成应另评估开放平台。客户端使用真实 NiumaCrew 身份，不伪装其他编程工具。

## P1 与后续阶段

连接保存 enabled、capability、config_revision 和 credential_revision。除上述聊天预设外，当前支持 `siliconflow-embedding`：capability=embedding、协议 openai-embeddings、固定 Base URL `https://api.siliconflow.cn/v1` 和模型 `BAAI/bge-m3`。能力由服务端预设决定，向量连接不能装配为员工聊天模型。配置变化和凭证提交分别递增修订，不再用 updated_at 作为运行版本。

数据库字段与条件见[数据字典](data-model.md)，实际验收见迁移记录。

## 模块职责

- `model_connections`：预设目录、请求与安全响应、配置 CRUD、密钥加解密和连接检查；向未来执行模块提供 `LLMConfig`。
- 员工模块：保存 `model_connection_id` 外键；不复制连接 Key 或模型参数。修改共享连接后，后续解析使用新配置。
- 授权模块：声明 `model_connections:read/create/update/delete/test` 与 `agents:assign_model`；HTTP 入口逐项检查。游客无连接查询权限。
- 前端 `pages/brains` 仅管理对话连接；知识库的“检索设置”弹窗仅管理向量连接。两处复用 `components/configuration/ModelConnections` 的表单、删除确认与检查交互，底层共用加密凭证与修订服务；员工编辑复用对话连接选择器。Key 仅驻留当前表单内存，保存成功清空，不写浏览器存储。

## 数据结构

初始迁移创建 model_connections 及 Agent 的可空连接外键和索引。UUID 与时间使用统一字段类型。

| 字段              | SQLite 类型 | 可空 | 默认值               | 说明                                                                               |
| ----------------- | ----------- | ---- | -------------------- | ---------------------------------------------------------------------------------- |
| id                | TEXT        | 否   | 应用 UUID v4         | 稳定主键                                                                           |
| name              | TEXT        | 否   | 无                   | 去首尾空白、1～100 字符、唯一；数据库非空白 CHECK                                  |
| preset_id         | TEXT        | 否   | 无                   | 后端预设 ID：`kimi-code`、`zhipu`、`deepseek` 或 `siliconflow-embedding`；应用校验 |
| model_id          | TEXT        | 否   | 预设默认值由应用填充 | 1～120 位模型标识；应用限制安全标识字符，数据库非空白 CHECK                        |
| encrypted_api_key | TEXT        | 否   | 无                   | Fernet 认证加密密文，永不进入响应 DTO                                              |
| created_at        | TEXT        | 否   | UTC 当前时间         | 创建时间                                                                           |
| updated_at        | TEXT        | 否   | UTC 当前时间         | 修改时间                                                                           |

`agents.model_connection_id` 为可空 TEXT 外键，引用 `model_connections.id`，删除行为 NO ACTION（立即拒绝存在引用的删除），增加查引用索引。Agent 以连接绑定判断是否完成模型装配，模型标识与密文只属于连接。

每个连接必须有 Key；创建必填。PATCH 中省略 `api_key` 保持原 Key，提供非空值替换；空串、null 拒绝，不能通过编辑清空后留下假就绪状态。更新同时核对 expected_config_revision 和 expected_credential_revision；冲突 409，编辑页保留当前内容并提示共享影响。不保存历史验证成功状态，以免换 Key 后继续展示旧结果。

## 密钥与运行配置

API Key 使用 cryptography 的 Fernet 加密。主密钥优先来自 `MODEL_CONNECTIONS_ENCRYPTION_KEY`；未设置时，本机首次保存连接会在 `MODEL_CONNECTIONS_KEY_FILE` 指定位置创建文件，权限 0600，通过临时文件加原子链接避免并发产生不同密钥。文件路径独立于数据库连接，配置见[后端说明](../guides/backend-operations.md#数据库与本地文件配置)。数据库已有连接时丢失主密钥必须报错，不能自动生成新密钥掩盖数据不可读。

主密钥不存数据库、不返回浏览器、不记录日志；数据库和主密钥应分别备份。部署可通过秘密管理注入稳定主密钥；多进程/多实例必须共享同一主密钥。更换主密钥需要专门解密重加密迁移，本阶段不提供旋转界面。读取、解密失败返回固定提示，不包含上游正文、Key 或密文。

## 接口契约

以下接口沿用 Cookie、Origin、JSON、统一错误和 no-store 策略。

| 方法与路径                                         | 权限                     | 成功                                    | 主要错误                                     |
| -------------------------------------------------- | ------------------------ | --------------------------------------- | -------------------------------------------- |
| GET `/api/model-presets`                           | model_connections:read   | 200 预设列表                            | 401/403                                      |
| GET `/api/model-connections`                       | model_connections:read   | 200 分页列表，offset/limit 沿用现有约定 | 401/403/422                                  |
| POST `/api/model-connections`                      | model_connections:create | 201 安全连接响应                        | 401/403/409 重名/422 输入错误/503 密钥不可用 |
| GET `/api/model-connections/{id}`                  | model_connections:read   | 200 安全连接响应                        | 401/403/404                                  |
| PATCH `/api/model-connections/{id}`                | model_connections:update | 200 安全连接响应                        | 401/403/404/409/422/503                      |
| DELETE `/api/model-connections/{id}`               | model_connections:delete | 204                                     | 401/403/404/409 仍被引用                     |
| POST `/api/model-connections/{id}/test`，JSON `{}` | model_connections:test   | 200 `{ok, message}`                     | 401/403/404/429/503                          |

响应增加 enabled、capability、config_revision、credential_revision，其余安全字段为 id、name、preset_id、provider、protocol、base_url、model_id、has_api_key、agents（id/name）、created_at、updated_at。显式构造白名单，不从包含密文的 ORM 对象自动导出。Key 不返回末尾字符，只有是否已配置。

连接检查读取已保存配置后关闭数据库事务，使用 httpx 请求固定 `/models`，超时 8 秒、禁止重定向、禁用环境代理、响应最多 1 MiB，不发送提示词、不调用生成接口。200 且模型目录包含当前 Model ID 才算检查通过；认证失败、拒绝、限速、超时、目录不支持或模型不可见分别给固定说明。每个账号每分钟最多 5 次检查。它只证明当时凭证可读取模型目录，不证明实际生成、额度或任务执行可用。

向量连接的检查调用 `POST /embeddings`，发送固定非业务短文本并验证有效 1024 维向量，代表一次真实向量调用成功；不以模型目录代替向量测试。超时、限流、认证或无效响应返回脱敏错误。共享连接可由有知识库使用权限的用户显式用于本人库，选择器只投影 ID、名称、模型；完整规则见[知识库契约](knowledge.md#硅基流动向量接入)。仍有知识库索引引用时，删除连接返回 409。

员工 POST/PATCH 增加 `model_connection_id`：省略维持现状，null 解除，非空 UUID 必须存在且为启用的聊天连接；显式提交此字段还需 `agents:assign_model`。不存在返回 404，关联和删除冲突返回 409。游客 DTO 不暴露连接 ID、模型参数和凭证，仅保留 `model_configured` 布尔值。

## 前端流程

侧栏新增「大脑配置」，独立地址 `/brains`，刷新保留入口，游客访问显示无权管理。列表显示名称、预设、Model ID、Key 状态及使用员工；提供搜索、新建、编辑、检查和删除。

新建大脑时选择 Kimi Code、智谱 GLM 或 DeepSeek 聊天预设；知识库检索设置中选择硅基流动向量预设。表单自动填充 Base URL 与默认模型，Key 提示跟随所选预设；名称和 Key 必填。编辑时 Key 留空保持，填写表示替换，展示受影响员工。保存后刷新列表；检查结果只展示在当前列表状态。被引用时删除按钮禁用，后端仍检查引用。未保存表单关闭、导航及退出有离开确认；重载有浏览器提示。

员工「工作指令」中选择大脑，可选择暂不装配。未绑定时允许保存草稿但不能进入演示对话。没有连接时提供在新标签页打开大脑配置的入口和刷新列表按钮，保留员工当前草稿。旧模型标识以迁移提示显示，不冒充已装配连接。

## 迁移与验收

新库通过初始迁移建立连接表，配置由管理员重新创建。模型密钥和业务库分开保管；初始化、备份与恢复见[后端操作](../guides/backend-operations.md#数据库与本地文件配置)。

验证覆盖：旧库升级与 schema check；管理员 CRUD；匿名及游客拒绝；密钥加密、缺失/错误主密钥、错误不回显秘密；换 Key 与重启读取；员工复用、解绑、删除约束；固定地址、拒绝重定向、上游失败与请求限速；前端 DTO、代理白名单、页面交互和构建。

## 历史验证入口

历史检查的日期、范围和限制见实施与验证记录，不作为本次重新验收。

新增供应商的实际验证见智谱与 DeepSeek 预设验收。

# 配置与身份模块独立审查

本轮于 2026-10-29 发起、跨日到 2026-10-30 完成取证，审查 auth、agents、skills、model_connections、organization_rules 五个模块的工作区源码。33 个 Python 文件、3794 行均全文读取；README、HTTP 入口、调用方和相关测试另行交叉核对。逐文件范围见 [configuration-coverage.json](configuration-coverage.json)。这是审查记录，不改变现行契约或业务代码。

## 一、先记录代码事实

### 1. 这五块分别拥有什么

| 模块               | 实际所有权                                             | 输入、输出与关键依赖                                                                                                                   | 源码依据                                                                                                                                               |
| ------------------ | ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| auth               | 账号、外部身份、会话、操作主体与固定权限               | 本地密码或经过服务端验证的 GitHub 身份进入；输出 Actor 和提交后的随机 token。业务方只需要 Actor；纯权限规则不查询 ORM。                | `backend/app/auth/models.py:18-77`、`backend/app/auth/service.py:88-177`、`backend/app/auth/permissions.py:50-61`                                      |
| agents             | 共享员工定义、员工选择的技能和工具、使用者个人工具绑定 | 配置 DTO 进入；返回管理详情、目录摘要、公开投影。读取 Skill/ModelConnection 校验引用，删除时直接查询 Conversation；不调用模型。        | `backend/app/agents/models.py:23-142`、`backend/app/agents/service.py:157-181`、`:311-367`                                                             |
| skills             | 共享方法、包文件、当前修订、可编辑源目录与不可变字节   | 旧表单、SKILL.md、文件集合或 ZIP 进入；输出安全清单、管理 DTO、导出包。技能定义不拥有员工关系，但修改参数规范与删除时查询 AgentSkill。 | `backend/app/skills/service.py:105-140`、`:284-322`、`:466-529`                                                                                        |
| model_connections  | 模型供应商预设、共享模型配置、加密凭证与两类修订       | 写请求接受 Key；响应只暴露 has_api_key。运行出口生成 LLMConfig；主动检查仅 GET 模型目录。删除保护读取 Agent 和活跃 Run。               | `backend/app/model_connections/schemas.py:48-85`、`backend/app/model_connections/service.py:147-210`、`:212-265`                                       |
| organization_rules | 部署内唯一一份全员规则正文及修订                       | 管理员整体替换正文，并提供预期修订；输出当前正文、修订和时间。规则组合与冻结发生在 conversations，而非本模块。                         | `backend/app/organization_rules/models.py:12-25`、`backend/app/organization_rules/service.py:28-47`、`backend/app/conversations/preparation.py:75-112` |

这是一组同库协作的业务模块。员工装配归员工、Skill 内容归技能、Key 归模型连接，划分有真实的数据所有权依据。员工配置与运行状态也没有混成一张“Agent 总表”：员工服务的运行入口只捕获与复核依据，实际执行输入由 ConversationPreparation 组合（`backend/app/agents/service.py:370-456`；`backend/app/conversations/preparation.py:59-153`）。

### 2. 真实依赖方向

1. HTTP 路由调用模块服务，认证依赖先解析 Cookie 为 Actor，再查固定能力集合；模型、技能、规则的管理服务自身没有 Actor 参数。新增后台或 CLI 调用时必须自行考虑授权，不能仅因函数位于 service.py 就认为它有权限保护。当前 HTTP 接线可见 `backend/app/api/dependencies.py:27-37`、`backend/app/api/routes/skills.py:122-138`、`backend/app/api/routes/model_connections.py:71-103`、`backend/app/api/routes/organization_rules.py:15-32`。
2. 员工自身的编辑归属由路由先查 `edit_agent`，随后另开保存事务。它允许创建者编辑，管理员只额外维护 created_by_user_id 为空的历史员工；管理员并非自动能编辑任何他人创建的员工。当前没有修改 created_by_user_id 的服务路径，因此没有从这两个事务直接推出归属竞争漏洞（`backend/app/agents/access.py:6-10`；`backend/app/api/routes/agents.py:85-113`；`backend/app/agents/schemas.py:61-76`）。
3. agents→skills.models 表示装配引用，skills.service→agents.models 表示参数兼容和删除保护；agents.service↔model_connections.service 也通过对方模型形成包级双向关联，但未见模块导入时循环初始化。它们没有相互调用独立提交的服务来完成同一次装配；保存使用同一个 Session（`backend/app/agents/service.py:12-34`、`:157-176`；`backend/app/skills/service.py:16`、`:474-480`；`backend/app/model_connections/service.py:9-18`）。
4. conversations 在接受执行时读取员工、模型、规则、技能与工具；后续动作复核当前会话、员工启停、装配修订、连接修订。冻结的是当次方法内容，实时检查的是当前使用许可（`backend/app/conversations/preparation.py:68-153`；`backend/app/conversations/authorization.py:17-44`；`backend/app/agents/service.py:423-445`）。
5. 工具许可属于员工模块；工具定义、连接及参数范围检查由 tools 提供。`tool_grants.py` 同时负责 HTTP 输入模型、配置替换、快照捕获和动作授权；`schemas.py` 导入其中的 GrantInput，ToolGrantService 又通过函数内导入 require_agent 连接回 service（`backend/app/agents/tool_grants.py:19-35`、`:87-114`、`:187-347`；`backend/app/agents/schemas.py:16`）。这是可读性和类型化的重点位置，不能直接等同于错误的权限边界。

### 3. auth 内部

`actor.py` 的不可变数据对象只有身份、会话和到期时间；`permissions.py` 负责角色能力及归属；`models.py` 定义账号、外部身份和服务端会话；`service.py` 管理生命周期；`github.py` 独立处理上游与 OAuth 暂存；`config.py` 校验来源和 Cookie；`cli.py` 是本机账号维护入口。这些文件名与实际职责基本一致（`backend/app/auth/actor.py:7-14`；`backend/app/auth/permissions.py:6-61`；`backend/app/auth/cli.py:20-51`）。

本地登录先读账号、在写事务外做 Argon2 校验，再用带旧密码摘要和启用条件的 UPDATE 复核；旧会话撤销、新会话建立在同一写事务，token 在事务退出后返回。数据库只存 token 的 SHA-256 摘要。账号禁用、重置密码和撤销会话先更新账号，随后统一撤销会话（`backend/app/auth/service.py:23-24`、`:63-128`）。

请求解析可以按间隔更新用户 last_seen；后台 validate_session/resolve_session 仅读取，因此后台持续运行不会自行延长闲置期限。guest 只捕获 AuthenticationError，存储故障不能变成游客回退（`backend/app/auth/service.py:179-197`、`:210-256`）。

GitHub state 与 PKCE verifier 封入经认证加密的十分钟 Cookie；回调限定跳转路径；上游请求不跟随跳转、不读环境代理、有限时和响应体上限。GitHub 用户 ID 用于关联，用户名变化不创建新站内身份；上游 token 没有写入数据库（`backend/app/auth/github.py:29-42`、`:56-106`、`:109-168`；`backend/app/auth/service.py:130-177`）。

测试读取：会话轮换/撤销/闲置、Origin 和脱敏在 `backend/tests/test_authentication.py:61-328`；OAuth 错误、最小授权、并发首次登录与同名不合并在 `backend/tests/test_github_signin.py:93-245`、`:261-420`。这些测试使用真实迁移后的临时 SQLite 和 MockTransport；不能证明当前真实 GitHub 配置可登录。

### 4. agents 内部

`models.py` 同时放员工和三种装配关系，体现这些关系随员工维护；`access.py` 是纯创建者编辑规则；`personal_tools.py` 只处理使用者连接绑定；`service.py` 负责员工 CRUD、技能装配、目录投影和执行许可；`tool_grants.py` 负责工具装配与执行依据。配置服务不解密模型 Key，也不生成回答（`backend/app/agents/models.py:23-142`；`backend/app/agents/personal_tools.py:15-91`；`backend/app/agents/service.py:157-456`）。

员工创建/修改先取得 SQLite 写入资格，再检查名字、修订及引用，员工字段和关系一次提交。技能参数根据共享技能规范校验；未改变的关系保留创建时间，移除重建后的关系结合 revision 和 created_at 检查，阻止旧 Run 继续使用旧许可（`backend/app/agents/service.py:124-176`、`:311-358`、`:423-445`）。

目录采用计数、当前页、批量技能摘要三次查询；正文按需读取。详情读取仍逐关系查询 Skill；工具计数也有单独查询，适用于详情而非批量目录（`backend/app/agents/service.py:78-121`、`:233-309`）。目录公开响应有独立白名单；model_configured 当前表达“外键非空”，不能保证连接仍启用（`backend/app/agents/schemas.py:103-127`；`backend/app/agents/service.py:295-307`）。

个人工具绑定只能指向自己拥有且同服务、已启用、已批准的连接，并比较工具描述摘要。运行捕获账号与连接多种修订；每次动作检查 grant、个人 binding 身份和连接定义，历史结果读取也保留原工具的实时授权（`backend/app/agents/personal_tools.py:47-91`；`backend/app/agents/tool_grants.py:249-347`；`backend/app/tools/service.py:73-90`）。

测试读取：`backend/tests/test_configuration_api.py:37-340` 覆盖名称、并发修订、参数、集合替换和回滚；`:438-465` 明确断言目录三次 SELECT；`backend/tests/test_agent_skill_storage.py:133-312` 覆盖真实数据库约束；`backend/tests/test_mcp_accounts.py:50-212`、`:366-415` 覆盖个人连接、共享账号、工具描述变更和跨创建者编辑拒绝。

### 5. skills 内部

本模块有三种不同状态：可编辑目录供人或安装器维护；数据库正文/manifest 表达已发布版本；按 SHA-256 寻址的 blob 保存不可变字节，旧 Run 仍可读取。`library.py` 负责可编辑目录锁及替换回滚，`packages.py` 负责包校验和 blob，`parameters.py` 负责非秘密 JSON 参数，`service.py` 组合导入、同步、发布与修订，命名能对应实际边界（`backend/app/skills/library.py:40-157`；`backend/app/skills/packages.py:264-306`；`backend/app/skills/service.py:46-140`、`:150-252`）。

ZIP 导入验证相对路径、重复/大小写路径、父子路径冲突、链接、文件数、展开字节和压缩比；YAML 使用 SafeLoader 并拒绝重复键、循环和过深元数据。上传声明的 allowed-tools 不会自动授予工具。预览只有解析，导入重新解析再创建（`backend/app/skills/packages.py:39-134`、`:168-245`；`backend/app/skills/service.py:284-307`）。

发布先保存不可变字节，再拿目录锁、暂存整目录并在数据库失败时恢复旧目录。数据库事务与目录替换不能提供跨存储断电原子性；源码仅对 Python 异常回滚，有 fsync 文件但目录替换阶段没有事务日志和启动恢复。README 已明确此限制；不能把它写成“完全原子”（`backend/app/skills/library.py:116-157`；`backend/app/skills/service.py:421-464`；`backend/app/skills/README.md:43`）。

修改参数规范会校验所有启用的员工关系；技能被装配时禁止删除。标准包的描述和指令由 SKILL.md 解析，旧表单内容保留兼容，但标准包不能单独编辑旧说明字段（`backend/app/skills/service.py:466-529`）。

测试读取：`backend/tests/test_skill_packages.py:64-155` 覆盖惰性预览和恶意包，`:157-208` 验证旧 Run 仍读旧字节，`:259-315` 覆盖越权资源和存储故障；`backend/tests/test_skill_library.py:44-174` 覆盖同步保留关系、外部改动冲突、缺源保留和数据库拒绝回滚。真实 OpenSandbox 与外部安装器并发替换目录未在本次验证。

### 6. model_connections 内部

`presets.py` 只提供 Kimi Code 固定端点；schema 不接受任意 Base URL。`credentials.py` 管理 Fernet 主密钥与加解密；首次生成使用临时文件加硬链接，避免并发创建半个 Key；已有密文时保存新 Key 会先尝试解密一条旧记录，失败不创建替代密钥（`backend/app/model_connections/presets.py:17-27`；`backend/app/model_connections/schemas.py:48-62`；`backend/app/model_connections/credentials.py:22-51`；`backend/app/model_connections/service.py:66-71`）。

配置修订与凭证修订分开：普通真实字段变化增加前者，显式提交 Key 增加后者；运行解析可要求两者与接受时相同。数据库事务退出后才解密生成 LLMConfig，HTTP 模型目录检查也在事务外。删除先持写锁，再检查活跃 Run 与员工引用（`backend/app/model_connections/service.py:114-164`、`:178-265`）。

主动检查只证明模型目录接受 Key 并包含指定模型，不证明内容生成或 Agent 工具成功。Key 不在 ConnectionRead 里，LLMConfig 只在服务器内部返回（`backend/app/model_connections/schemas.py:70-85`；`backend/app/model_connections/service.py:195-210`、`:247-256`）。

测试读取：`backend/tests/test_model_connections.py:29-112`、`:187-239` 覆盖加密、重启、引用保护、主密钥缺失和并发首次写；`:245-346` 是受控 httpx 假响应和修订检查。本次未调用真实 Kimi。

### 7. organization_rules 内部

仅 models、schemas、service 与包说明，规模与职责匹配，无需为了形式再建 repository。id=1 和正文长度同时受数据库约束保护；PUT 的 revision 名字虽与其他模块 expected_revision 不同，但执行的是预期修订语义。服务先条件 UPDATE 再读取，避免先读后写的 SQLite 快照升级；相同正文与相同修订不递增，旧修订即便正文相同仍冲突（`backend/app/organization_rules/models.py:14-25`；`backend/app/organization_rules/schemas.py:11-18`；`backend/app/organization_rules/service.py:28-47`）。

`backend/tests/test_organization_rules.py:15-113` 覆盖重启、清空、无变化、权限、并发只允许一个胜出和直接 SQL 约束。规则只在接受时由 conversations 冻结，修改规则不会重写已经接受的执行输入（`backend/app/conversations/preparation.py:75-112`）。

## 二、在上述事实基础上的评审

### 已确认问题

| 编号   | 优先级 | 问题与影响                                                                                                                                                             | 调用链与证据                                                                                                                                                                                                                                                                                                                                                                                                                              | 建议                                                                                                        |
| ------ | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| CFG-01 | P2     | “未配置大脑”筛选会遗漏真正没有绑定连接的员工。当可用连接子查询非空时，NULL NOT IN (...) 结果不是 true，未绑定员工因此被过滤；空连接库反而看不出问题。                  | HTTP `backend/app/api/routes/agents.py:57-67` → `backend/app/agents/service.py:216-222`。真实迁移+API 复现：全部为“未绑定、可用绑定、后来停用”，false 只返回“后来停用”，true 正确返回“可用绑定”；原始记录见 [configuration-reproduction.log](configuration-reproduction.log)。                                                                                                                                                            | 使用明确包含 `model_connection_id IS NULL` 的反向条件，或相关 EXISTS/NOT EXISTS；加三种状态同时存在的回归。 |
| CFG-02 | P2     | 损坏 ZIP 的 DEFLATE 数据触发原始 zlib.error，没有转换为“包无效”。预览入口实测 HTTP 500 / Internal Server Error，而非管理端可理解的 422。影响限已有技能创建权限的输入。 | `backend/app/api/routes/skills.py:51-67` → `backend/app/skills/service.py:284-307` → `backend/app/skills/packages.py:227-228`；`:244-245` 捕获集合缺少 zlib.error。本次破坏压缩体、保留 ZIP 目录，直接复现 `zlib.error: Error -3 ... invalid block type`，见 [configuration-corrupt-zip.log](configuration-corrupt-zip.log)；完整 API 状态见 [configuration-reproduction.log](configuration-reproduction.log)。                           | 捕获确定的解压异常并转 package_error；加损坏压缩流回归，仍保留未知编程错误。                                |
| CFG-03 | P3     | 原样提交工具许可会增加员工修订，即使空集合替换空集合。使无实际变化的保存导致别的编辑器出现过期冲突；不代表已证实旧 Run 因此撤权，运行工具主要核对 grant revision。     | PATCH `backend/app/agents/service.py:329-343` 只检查字段出现；PUT `backend/app/agents/tool_grants.py:103-107` 无条件 +1；与 `docs/reference/agent-configuration/api.md:9` 契约冲突。实测 revision 1→PATCH 空 tool_grants 得2→PUT空grants得3。                                                                                                                                                                                             | 先比较规范化后的实际工具许可变化，再更新员工修订；保留真实变化的冲突保护。                                  |
| CFG-04 | P3     | 部分现行说明滞后，容易让维护者按错误的权限或职责开展修改。                                                                                                             | `backend/app/auth/README.md:47` 说 member 只有公开展示能力，而 `backend/app/auth/permissions.py:36-45` 允许本人对话/运行/工具；`backend/app/organization_rules/README.md:7` 把 prompt 组合归到 agents，真实实现为 `backend/app/conversations/preparation.py:15-31`、`:75-112`。`docs/reference/agent-configuration/api.md:3` 仍写迁移 head 0009，真实本次迁移跑到0011；`:79` 的工具数只写 CI，而 agents/service.py:112-118 已计通用工具。 | 核对现行文档中的权威事实并收敛重复说明。本次仅记录，不擅自改写当前契约。                                    |

CFG-01 的公开 API 实验必须单独解释：`/api/public/agents` 的签名没有 model_configured，传此查询会被忽略（`backend/app/api/routes/public.py:23-42`），所以公开列表的实验不能拿来证明同一筛选缺陷。公开 model_configured 本来就按外键有无输出；停用连接仍为 true，当前代码可直接证明，是否改成“可运行”需要产品确认。

### 架构与文件组织判断

1. **保留当前按业务能力组织的模块化单体。** 这五块已经按账号、员工、方法、凭证、规则分开；同一 SQLite 中有必要的引用校验和一次性保存。当前没有证据支持为了套 Clean Architecture 全面增设实体映射、repository 接口和 use-case 类。项目手册也明确简单 CRUD 可直接用 ORM（`docs/engineering/backend.md:61-81`）。
2. **优先整理工具装配的入口和类型。** 不是因为347行超过阈值，而是 `schemas.py → tool_grants.py → service.py → schemas.py` 确实存在文件职责环：schemas导入GrantInput，tool_grants的get/replace局部导入require_agent，service反过来导入schemas。局部导入缓解模块初始化顺序，没有消除这组职责相互依赖。输入模型、管理写入和运行时校验有不同变化原因；可先把 GrantInput/GrantsInput 迁到明确契约文件，把require_agent/authorize_execution等读取与访问检查入口按实际所有权放到轻量文件，补 capture_tools/assert_binding/resolve_account 的输入输出类型，再按变更频率决定是否分离管理与运行规则（`backend/app/agents/schemas.py:16`；`backend/app/agents/tool_grants.py:19-35`、`:87-105`、`:249-253`；`backend/app/agents/service.py:13-23`）。
3. **技能服务的长文件源自真实跨存储流程，拆文件应保留原子边界。** 包解析/字节存储、可编辑目录操作已经分开，service 负责顺序是合理的；下一步可抽独立的“目录同步”编排以减少 create/update/delete 同 sync_library 的干扰，不能把一次保存改成多个各自提交的服务（`backend/app/skills/service.py:150-252`、`:389-529`）。
4. **目录读取还有可以省掉的数据搬运。** skills.list 虽延迟 instructions/configuration_schema，却仍选中 Skill.skill_md 和 package_manifest；summary/public DTO 最后丢掉它们。最大页100条、单 SKILL.md 可128 KiB，理论上仅主文就可能额外加载约12.5 MiB。这里是从查询与明确上限得到的容量推算，没有做生产性能压测。可将这两列一并 defer 并给 SQL 查询回归补断言（`backend/app/skills/service.py:343-382`；`backend/app/skills/models.py:36-45`；`backend/app/skills/packages.py:30`；`backend/app/api/routes/skills.py:85-90`）。
5. **命名总体能表达内容，跨模块数据契约比批量改名更值得优先。** model_connections 和 personal_tools 分清共享与个人；Actor 与 Agent 没有混用。薄弱处是 grant/binding/snapshot 大量 dict，db、data、id 一类形参无类型，真实必要字段藏在消费端。当前 mypy 的 files 列表不含这五个模块，静态检查通过不能证明这些契约已被检查（`backend/app/agents/tool_grants.py:187-347`；`backend/app/agents/personal_tools.py:19-91`；`backend/pyproject.toml:52-59`）。不要求所有内部函数写冗长 docstring，先补跨模块函数与返回结构。

### 保留的取舍与未知项

- 配置 CRUD 授权在 HTTP，公开服务函数可被内部直接调用，这是当前明确设计；本次未找到无授权暴露的独立入口。若新增非 HTTP 入口，需要重新核对，不能依赖 README 的一句约定。
- Skill 库文件锁只约束平台进程；外部安装器不共享锁。当前 fingerprint 检测能发现已完成的外部修改，但本次没有模拟外部写入恰好穿过目录替换的竞争，不能承诺覆盖所有此类情形（`backend/app/skills/library.py:3-5`、`:116-149`）。
- blob 刻意不自动删除，保证旧 Run 可恢复；垃圾回收、磁盘容量长期增长与备份恢复未做生产演练。put 有剩余空间下限，但没有总配额（`backend/app/skills/packages.py:268-293`）。
- CredentialVault 检查一条旧密文是当前防错机制，不是完整的主密钥轮换协议；真实 Key 轮换、供应商和 GitHub 网络可用性未调用或验证。
- 全局规章制度是冻结给模型的自然语言输入，不替代后端工具和资源权限。接受后修改规则是否应撤销旧 Run，属于尚需明确的产品语义，当前代码选择继续冻结依据。

## 三、实际验证与可复查材料

本子审查没有重复运行根审查的全量测试，也没有修改业务代码、访问开发数据库、读取真实凭证或调用外部供应商。逐文件扫描及测试内容阅读已完成；全量测试和静态检查的实际结果由主报告统一记录，不能把这里的“测试读取”当作测试已经执行。

定向实验使用 `backend/tests/conftest.py:19-45` 的临时 AppConfig 构造和正式 Alembic migration 到0011，所有数据库、技能目录与假主密钥都在 /tmp；真实 TestClient/lifespan 跑管理员登录、配置创建和查询。脚本与输出：

- [configuration-reproduction.py](configuration-reproduction.py)、[configuration-reproduction.log](configuration-reproduction.log)：复现 NULL 筛选、反例、无变化修订与损坏压缩包预览 HTTP 500。仓库根执行 `PYTHONPATH=backend:backend/tests backend/.venv/bin/python docs/records/backend-deep-review-2026-10-29/evidence/configuration-reproduction.py`，只创建新的 /tmp 数据。
- [configuration-corrupt-zip.py](configuration-corrupt-zip.py)、[configuration-corrupt-zip.log](configuration-corrupt-zip.log)：最小损坏压缩流实验，未访问数据库或网络。
- [configuration-coverage.json](configuration-coverage.json)：33个源码文件的全文范围、散列与职责；另外列出已读测试与调用边界，不声称整仓库都由本子审查覆盖。
- `../context/functions/configuration-*.md`：关键函数的先验假设、分支与跨函数约束，建立事实后才在本报告给出问题判断。

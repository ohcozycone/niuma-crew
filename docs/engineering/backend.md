# 后端工程手册

定义后端统一工程标准，适用于业务 API、后台执行、身份权限、持久化、模型与工具适配及后端维护脚本。工程约定基于当前 Python 模块化单体。

## 技术栈与依赖

Python 最低版本、FastAPI、SQLAlchemy、Alembic、模型 SDK 与开发工具以 [pyproject.toml](../../backend/pyproject.toml)、[uv.lock](../../backend/uv.lock) 为准。使用 uv 管理环境和依赖；增加依赖同步声明用途与锁文件，不把临时实验安装当作工程已采用。

现有数据库是文件型 SQLite，SQLAlchemy 使用同步 Session；后台为同一应用生命周期中的异步 RunWorker。当前模型接入由 LangChain 工厂及按需指引中间件构成，技能和 MCP 按员工装配接入，基础文件工具直接复用 Deep Agents，沙箱由环境服务提供。SDK 提供能力不等于平台已授权，具体边界见[运行契约](../reference/runtime.md)。

## 目录与命名

目录树表达职责，不是必须经过的调用层数。模块按实际操作选择 service、queries 或具体职责文件，不要求每个模块具备同构层级。模块按业务能力就近维护；项目级说明位于 docs，不在后端重新维护一套文档目录。

| 对象                              | 约定                                                                                                |
| --------------------------------- | --------------------------------------------------------------------------------------------------- |
| Python 包、模块、函数、方法、变量 | snake_case，名称表达职责，例如 model_connections、reserve_writer                                    |
| 类、异常与输入输出模型            | PascalCase；错误使用 Error 或既有 Failure 后缀，避免同名不同语义                                    |
| 常量                              | UPPER_SNAKE_CASE；实际值只在代码或配置源定义                                                        |
| 测试                              | tests/test_<topic>.py，函数 test_<observable_behavior>；跨测试复用放 conftest 或有明确职责的 helper |
| 文档                              | 小写短横线；模块入口为 README.md                                                                    |

绝对导入统一使用 app 前缀。普通业务从模型所属模块导入，不从数据库模型注册聚合文件取得业务模型。`__init__.py` 只在确有公共入口时导出，避免为每个目录建聚合层。迁移名称和框架约定沿用工具格式。

新增或实质修改的公共入口、DTO 和跨模块返回值优先补明确类型；内部辅助函数按实际复杂度处理。当前用 mypy 检查执行契约、准入、查询、对话读写和输入准备、普通运行契约、知识资源与执行证据、请求服务及发布；具体范围以 pyproject.toml 为准，导入的其他代码不自动视为已严格检查。新增受影响接口应补类型，逐步扩展覆盖。make typecheck-backend 已纳入 lint-backend。迁移职责时同步迁移 mypy 检查范围，不能只检查原文件留下的包装入口。

## 文件职责与依赖

| 文件或模块                                               | 负责内容与边界                                                                   |
| -------------------------------------------------------- | -------------------------------------------------------------------------------- |
| main.py                                                  | ASGI 导出入口，调用 bootstrap；不归属 HTTP 适配模块                              |
| api/routes                                               | 参数、响应、Cookie、入口权限和 SSE；把业务决策交给所属服务                       |
| schemas.py                                               | 输入校验、响应投影与协议类型，不承担数据库事务                                   |
| models.py                                                | 所属模块的 ORM 结构、约束及关系，不集中所有业务模型                              |
| service.py                                               | 一次业务操作的校验、协作、查询及事务；简单 CRUD 可直接使用 ORM                   |
| store.py / queries.py                                    | 有实际后台存取或安全读取边界时拆分，不强制每表一个 repository                    |
| applications/conversations/writes.py                     | 对话消息、绑定及接纳所需的发布写入；使用调用方 Session，不决定接纳时机或自行提交 |
| applications/conversations/commands.py                   | 创建、接受、停止和重试事务；不启动模型或持有后台任务                             |
| resources/capability_catalog/queries.py                  | 统一目录的可见范围、搜索、计数、排序与分页                                       |
| runtime/execution/snapshot.py、preparation.py、runner.py | 分别捕获配置、准备资源和协调单次执行；授权组合由 RunService 负责                 |
| applications/conversations/acceptance.py                 | 复核对话接纳资格并组织正式回复发布；失败只重试接纳                               |
| rules、prompt 等职责文件                                 | 有独立价值的纯规则或组合逻辑；没有需要时不预建层级                               |
| runtime/execution                                        | 队列、领取、看护、取消、预算及终态；与单次 HTTP 观察分开                         |
| runtime/agent、infrastructure/llm                        | 前者运行 Agent 和解释 SDK，后者适配模型；两者均不查询身份或业务库                |
| infrastructure/database                                  | 共用存储机制，不拥有员工、对话等业务规则                                         |
| bootstrap                                                | 组合具体服务并管理生命周期，可以同时认识多类实现                                 |

api 不导入 main 或 bootstrap；装配层组合 HTTP 适配与具体服务，配置和跨模块引用检查回调由 bootstrap 固定注入。路由通过 dependencies 取得服务，不在请求中重新构造带默认配置的实例。服务不接收 FastAPI Request，不在模块导入时连接数据库或启动后台任务。不同业务模块确需协作时写清所有者和调用入口；同库引用计数、兼容性验证和删除保护由状态所有者提供具名只读查询，使用调用方 Session；跨模块 ORM 仅允许架构契约逐文件声明的只读投影；对话服务和共享回复流程可以组合所需模块的公开操作，同库原子操作不拆成独立 commit。`runtime/execution` 不导入业务应用或 HTTP 实现；`runtime/agent` 不读取业务 ORM，通过普通输入和 AgentContext 协议请求受控操作。装配入口组合具体实现。完整依赖与具名例外由[test_architecture_contract.py](../../backend/tests/test_architecture_contract.py)检查，运行和失败路径继续由既有边界测试覆盖。

工作台配置摘要的响应与只读投影归 `applications/configuration_summary.py`，路由只处理 HTTP 协议。完整文件归属、允许依赖、状态所有权与执行顺序以[后端架构](../architecture/backend.md)和[可执行架构契约](../../backend/tests/architecture_contract.json)为准。

RunWorker 与 RunService 共同读取 ExecutionStatus；Worker 管队列、在途任务和服务生命周期，Task 管单次执行、看护、受限操作与资源释放，完成后唤醒独立接纳。DatabaseConfig 定义在基础设施，app.config 负责配置组合。业务模型仅由 `bootstrap/model_registry.py` 聚合注册，数据库机制不反向导入业务模型。Agent 只接收普通 AgentRequest，通过 AgentContext 协议报告内容和请求受控操作；该协议不暴露 store 或数据库。

技能格式由 `resources/skills/definitions.py` 解释，员工捕获关系由 `resources/employees/assembly.py` 维护。员工固定连接和知识关系由 `resources/employees/` 维护；MCP 连接、清单和调用分别归 `resources/mcp/` 下的 `connections.py`、`catalogs.py`、`invocation.py`。共享主密钥机制归 infrastructure/credentials，业务负责转换故障；目录查询可以读约定概要字段，不重新解析技能原文。

## 运行管理组织约定

可靠执行、SDK循环与实际资源按所有权分开：执行层维护持久状态、预算、当前授权、看护和资源释放；Agent层解释SDK与模型协议，不直接读取业务数据库。平台不为每个内部步骤建立可装配对象或只转发的层级；详细文件职责和正常流程见[执行说明](../../backend/app/runtime/execution/README.md)。

单用户容量、队列、同一对话占用、动作预算和时限分别约束自己的范围；调度去重和单宿主锁不能被新增并发代码绕过。外部行为由[运行契约](../reference/runtime.md)维护，部署参数由[运维](../guides/backend-operations.md)维护。

## HTTP、校验与授权

输入优先复用 [RequestModel、分页和 PATCH 约定](../../backend/app/common/schemas.py)，字段结构由 schema 与运行 OpenAPI 维护。新增接口按现有规则声明请求、响应、状态和特殊错误；业务语义、权限、幂等及兼容在对应 reference 维护。

应用操作按失败含义抛出 app.common.errors 的具体类型；已登记分类的子类沿 MRO 使用最近分类的 HTTP 状态，未分类的 ServiceError 仍是服务器错误；code 表达细分原因，message 必须可公开，retry_after 是可选等待建议。HTTP 状态由 API 统一映射，不传入业务异常，也不通过公共父类吞掉所有故障。认证回退只处理认证失败，持续授权复核只将认证或权限失效解释为撤权；其他故障保留原有含义。类型、响应与传输例外见[应用错误约定](../reference/failures.md)。

PATCH 用 exclude_unset 区分未提供与显式清空，不能把字段默认 None 当作客户端请求清空。非空字段显式 null 必须拒绝；可空字段的清空语义由各契约定义。配置变更核对对应预期修订，冲突保留客户端输入，服务不能静默采用最新版本覆盖。

身份由 auth.service 解析为 auth.actor.Actor，操作能力和资源归属通过 auth.permissions 分别检查。权限策略不读取 Cookie、数据库或业务模型。HTTP 路由声明操作能力；所属模块的用户操作也显式接收可信 Actor 并检查权限，不能依赖 HTTP 才安全。员工编辑权、资源归属、修订和写入使用同一事务。固定技能定义、全员规则、模型修订及运行连接解析等内部协作按已授权运行读取，使用调用方 Session，不套用管理员配置权限。本机账号初始化与环境核对是受信运维入口，不伪造用户会话。列表与单条访问遵守同一资源范围。公开 DTO 使用独立字段白名单；public 不表示匿名免会话。

同步数据库路径使用同步路由；异步 SSE 或任务中的同步 I/O 显式转入工作线程，不能把同步查询放进 async 函数便当作异步。Session 不随 Request 或异步任务共享。接口实现位于 [API 模块](../../backend/app/api)。

## 事务与迁移

业务操作通过 Database.transaction 创建短事务，成功提交、异常回滚和释放由该入口负责。嵌套协作需要同一 Session 时传入当前 Session，辅助操作不擅自新建事务或提交。模型、工具、文件解析和昂贵密码计算置于写事务之外，必要时返回后在新短事务中复核状态。

对于先检查再写的竞争路径，依据业务约束在读取前取得写入资格，并由数据库唯一、外键和 CHECK 兜底。reserve_writer 的零匹配 UPDATE 原因由[代码注释](../../backend/app/infrastructure/database/transactions.py)及[竞争测试](../../backend/tests/test_database.py)维护；不要在 docs 复制其 SQL。

数字标识、UUID、UTC 时间、文本和 JSON 编码复用[字段类型](../../backend/app/infrastructure/database/fields.py)；应用校验与数据库约束分别核对，不能因 ORM 通过就宣称直接数据库写入也被保护。

新增 ORM 同时更新模型注册与正式迁移，审核自动生成的重命名、回填和 SQLite 重建。应用启动不自动建业务表或迁移；测试迁移使用真实 Alembic 流程。备份、升级和恢复遵循[操作指南](../guides/backend-operations.md#数据库迁移)，不在手册复制脚本或生产参数表。

## 执行、外部调用与资源

应用 lifespan 拥有连接池、RunWorker 和需关闭的服务；创建后立即登记最终释放，异步服务在启动尝试前登记停止。启动部分失败或任一关闭异常时仍尝试其余清理，先停止生产任务，再停止文件/沙箱维护，最后关闭 MCP 与数据库；异常链保留失败信息。每次请求或后台步骤拥有自己的 Session。共享数据库只允许一个持锁 RunWorker，当前不支持多 worker 或跨主机租约。

接受输入命令、配置依据、消息 ID/序号与 queued run 原子保存，模型执行发生在事务外。checkpoint 专门保存恢复状态；接受时已建立助手 Message，执行成果与 Run 终态原子提交，对话在另一个接纳事务写正文、附件和关联释放，SSE 只观察已提交的过程或结果。配置快照固定本轮方法，当前启停、会话、关系及模型修订仍逐动作复核。SDK 解释留在 agent；宿主接收普通内容和真实动作。模型动作的当前授权、预算扣减与开始记录使用同一事务。断开订阅不取消运行，取消通过显式操作表达。

外部调用定义时限、预算、凭证来源、错误与关闭责任。普通聊天允许重启后从 checkpoint 继续，未落盘模型请求可能重发，必须保留尝试计数及未知用量；其他外部操作仍须单独定义重放和副作用。取消优先于迟到成功，存储失败停止后续操作；未知协议快照不自动重放。新增工具、知识和执行方式须明确其授权与生命周期，不能直接开放 SDK 默认工具。

## 注释与说明语言

注释服务于维护者理解和安全修改代码：补充实现原因、调用约束及容易误改的边界。名称、类型和实现已经清楚表达的内容不再复述，不要求每个文件、类或函数都有说明。

| 情况                           | 应写的内容                                                 |
| ------------------------------ | ---------------------------------------------------------- |
| 事务、并发、取消或资源释放顺序 | 为什么必须按此顺序；交换或省略步骤会破坏什么               |
| 输入输出存在隐含约束           | 单位、范围、所有权、是否提交事务，以及调用方必须满足的条件 |
| 兼容处理或不直观的实现         | 对应限制及保留该实现的原因；已失效时随代码删除             |
| 名称不足以说明的接口           | 简短说明调用契约；参数及返回类型由类型声明表达             |
| 模块协作、产品规则或操作指南   | 写在现有文档，代码只保留定位当前实现所需的原因             |

先改进命名和结构，再考虑解释性注释。删除逐行翻译代码、重复类型、目录口号及改动流水；保留能防止误改的原因，通常一两句即可，并放在对应逻辑附近。参数很多不等于需要逐项复述，单位或副作用不明显时才说明。

自有维护的注释和 Python 说明字符串使用中文；代码标识、协议名称、引用及工具指令保留原文。`noqa`、`type: ignore`、shebang、编码声明等不能翻译。第三方原文、生成文件和历史迁移按来源维护。模型提示词、工具描述、测试样本及错误消息是运行数据，不按注释批量处理。

## 配置、错误与诊断信息

配置经 load_config 显式解析并校验，环境与本地文件优先级由[配置指南](../guides/backend-operations.md)和代码维护。业务不散落读取进程环境，测试使用注入配置和临时路径，不读取开发数据库或密钥。

已知业务错误沿用 [ServiceError 及子类](../../backend/app/common/errors.py)，HTTP 状态与响应由 [API 转换入口](../../backend/app/api/errors.py)维护。422 当前是经过脱敏的校验条目数组，不能假定所有错误都有同一 code 包络。SQLite busy/locked 与业务冲突分别处理。数据库驱动错误码、唯一约束文本由[数据库错误识别](../../backend/app/infrastructure/database/errors.py)封装；业务只转换能够确认含义的冲突，其他完整性异常原样抛出，删除保护检查实际关联。

Agent 与 Execution 只表达稳定 code、技术类型及执行处理规则，不维护用户提示。两者的异常继承 `CodedFailure`，应用业务拒绝继续保留具体 `ServiceError` 类型；执行入口可以省略其 message，由应用出口映射。公开文案在 `app/common/public_errors.py` 维护，HTTP、对话或考核按使用场景选择展示；程序不得依赖文案表识别错误。模型工具反馈仍是运行数据，不等同于用户错误说明。契约见[失败事实与展示](../reference/failures.md#执行失败事实与应用文案)。

不得将密码、Cookie、API Key、密文、完整配置快照或上游原始异常放入响应、日志和步骤。诊断信息优先记录非秘密标识、错误类别及已确认阶段；记录输入正文须有实际用途与边界，不能默认打印全部请求。HTTP 已提供 X-Request-ID 和安全失败日志，后台通过 Run 标识定位；核心执行事件另以相同 Run/动作键输出有界结构化文件日志；不是所有后端日志落库，详见[执行证据契约](../reference/runtime.md)。

## 检查与交付

| 内容                                 | 当前工具或评审方式                                                                                                                                                                  |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 基础 Python 错误、未使用项、导入排序 | Ruff 已启用 E4/E7/E9/F/I；具体规则见 pyproject.toml                                                                                                                                 |
| Python 格式                          | Ruff format，包含 backend 与根 scripts                                                                                                                                              |
| 业务与迁移行为                       | pytest 隔离数据库、假上游及真实迁移；重点覆盖失败、拒绝、并发和恢复                                                                                                                 |
| 类型、依赖方向及职责                 | mypy 检查数据库错误识别及已列入的执行边界；导入约束由 test_runtime_boundaries.py 与 test_execution_boundaries.py 强制；完整目录、无环依赖、普通契约隔离和具名例外由架构契约测试检查 |
| 文档入口、文件和章节链接             | make check-docs；不判断业务内容是否正确                                                                                                                                             |

公共入口为 `make lint-backend`、`make test-backend`；修改启动器执行 `make test-dev`。后端测试的[共享夹具](../../backend/tests/conftest.py)使用 tmp_path、隔离迁移、注入配置与 TestClient lifespan；运行器测试按需显式启用并使用假执行器及真实 SDK 的假模型。外部响应格式变化应在适配边界测试，不仅 mock 最外层服务结果。

按[共享验证矩阵](shared.md#变更与验证选择)选择检查。表结构、接口、权限和生命周期变化同步当前契约与模块说明；局部实现原因留注释，可执行规则留工具。交付如实记录执行过的检查与剩余范围。

执行公开操作统一使用 submit、cancel、complete。是否参与调用方事务由 Session 参数和方法契约表达，不以 `_in` 后缀建立另一套操作词汇。submit、cancel 使用调用方 Session；complete 使用独立短事务。

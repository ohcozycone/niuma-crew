# 后端工程手册

定义后端统一工程标准，适用于业务 API、后台执行、身份权限、持久化、模型与工具适配及后端维护脚本。

## 职责与入口

| 入口                                            | 维护内容                                                                 |
| ----------------------------------------------- | ------------------------------------------------------------------------ |
| [后端 README](../../backend/README.md)          | 项目、模块和验证入口                                                     |
| [后端操作指南](../guides/backend-operations.md) | 配置、账号、迁移、运行限制与静态交付                                     |
| 本手册、[共享约定](shared.md)                   | 代码归属、命名、依赖、事务和验证标准                                     |
| [当前后端架构](../architecture/backend.md)      | 当前协作、应用生命周期和限制                                             |
| [现行契约](../README.md#现行契约)               | 业务、API、数据、权限和前端消费语义                                      |
| 源码旁模块 README                               | 先说明业务作用与正常流程，再解释设计、文件分工、依赖、局部约束与测试入口 |

## 技术栈与依赖

Python 最低版本、FastAPI、SQLAlchemy、Alembic、模型 SDK 与开发工具以 [pyproject.toml](../../backend/pyproject.toml)、[uv.lock](../../backend/uv.lock) 为准。使用 uv 管理环境和依赖；增加依赖同步声明用途与锁文件，不把临时实验安装当作工程已采用。

现有数据库是文件型 SQLite，SQLAlchemy 使用同步 Session；后台为同一应用生命周期中的异步 RunWorker。当前模型接入由 LangChain 工厂及按需指引中间件构成，技能、原生工作区和 MCP 通过受控入口接入。SDK 提供能力不等于平台已授权，具体边界见[运行契约](../reference/runtime.md)。

## 目录与命名

主要目录与完整职责以[当前后端架构](../architecture/backend.md)和[执行模块](../../backend/app/execution/README.md)为准，工程手册不维护第二份目录树。

目录树表达职责，不是必须经过的调用层数。模块按实际操作选择 service、queries 或具体职责文件，不要求每个模块具备同构层级。模块按业务能力就近维护；项目级说明位于 docs，不在后端重新维护一套文档目录。

| 对象                              | 约定                                                                                                |
| --------------------------------- | --------------------------------------------------------------------------------------------------- |
| Python 包、模块、函数、方法、变量 | snake_case，名称表达职责，例如 model_connections、reserve_writer                                    |
| 类、异常与输入输出模型            | PascalCase；错误使用 Error 或既有 Failure 后缀，避免同名不同语义                                    |
| 常量                              | UPPER_SNAKE_CASE；实际值只在代码或配置源定义                                                        |
| 测试                              | tests/test_<topic>.py，函数 test_<observable_behavior>；跨测试复用放 conftest 或有明确职责的 helper |
| 文档                              | 小写短横线；模块入口为 README.md                                                                    |

绝对导入统一使用 app 前缀。普通业务从模型所属模块导入，不从数据库模型注册聚合文件取得业务模型。`__init__.py` 只在确有公共入口时导出，避免为每个目录建聚合层。迁移名称和框架约定沿用工具格式。

新增或实质修改的公共入口、DTO 和跨模块返回值优先补明确类型；内部辅助函数按实际复杂度处理。当前用 mypy 检查执行契约、准入、查询、对话读写和输入准备、Agent 契约、请求服务及发布；具体范围以 pyproject.toml 为准，导入的其他代码不自动视为已严格检查。新增受影响接口应补类型，逐步扩展覆盖。make typecheck-backend 已纳入 lint-backend。

## 文件职责与依赖

| 文件或模块                                                                    | 负责内容与边界                                                    |
| ----------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| main.py                                                                       | ASGI 导出入口，调用 bootstrap；不归属 HTTP 适配模块               |
| api/routes                                                                    | 参数、响应、Cookie、入口权限和 SSE；把业务决策交给所属服务        |
| schemas.py                                                                    | 输入校验、响应投影与协议类型，不承担数据库事务                    |
| models.py                                                                     | 所属模块的 ORM 结构、约束及关系，不集中所有业务模型               |
| service.py                                                                    | 一次业务操作的校验、协作、查询及事务；简单 CRUD 可直接使用 ORM    |
| store.py / queries.py                                                         | 有实际后台存取或安全读取边界时拆分，不强制每表一个 repository     |
| conversations/writes.py                                                       | 对话业务写入与发布规则；使用调用方 Session，不自行提交            |
| conversations/service.py                                                      | 创建、接受、停止和重试事务；不启动模型或持有后台任务              |
| capability_catalog/queries.py                                                 | 统一目录的可见范围、搜索、计数、排序与分页                        |
| execution/snapshot.py、execution/runtime/task.py、conversations/acceptance.py | 配置、单次准备和独立应用接纳；授权组合由 RunService 负责          |
| rules、prompt 等职责文件                                                      | 有独立价值的纯规则或组合逻辑；没有需要时不预建层级                |
| execution                                                                     | 队列、领取、看护、取消、预算及终态；与单次 HTTP 观察分开          |
| execution/runtime（SDK 文件）/ llm                                            | 前者运行 Agent 和解释 SDK，后者适配模型；两者均不查询身份或业务库 |
| infrastructure/database                                                       | 共用存储机制，不拥有员工、对话等业务规则                          |
| bootstrap                                                                     | 组合具体服务并管理生命周期，可以同时认识多类实现                  |

api 不导入 main 或 bootstrap；装配层组合 HTTP 适配与具体服务，配置和跨模块引用检查回调由 bootstrap 固定注入。路由通过 dependencies 取得服务，不在请求中重新构造带默认配置的实例。服务不接收 FastAPI Request，不在模块导入时连接数据库或启动后台任务。不同业务模块确需协作时写清所有者和调用入口；同库引用计数、兼容性验证和删除保护可使用所属模型或公开查询，是否注入回调取决于既有依赖边界，不要求统一所有查询形式；对话服务和共享回复流程可以组合所需模块的公开操作，同库原子操作不拆成独立 commit。execution 不导入 conversations 或 HTTP 实现；execution/models.py、store.py 不导入 snapshot/prompts/runtime，snapshot 不导入 SDK/runtime，prompts 不导入业务模块、数据库或 SDK，runtime 的 SDK 文件不读取业务 ORM，Worker/Task 允许按职责访问执行模型和平台服务；执行内部由 execution/assembly.py 装配；bootstrap 只传共享服务及管理跨模块生命周期，对话接纳独立扫描已完成关联；snapshot 负责捕获冻结依据，runtime 可依赖共享 prompts，工具结果保存和读取核验统一由 runtime/tool_results.py 处理；该边界及 llm 不读取业务库、api 不反向导入装配层等方向由 test_runtime_boundaries.py 的表驱动检查和 test_execution_boundaries.py 执行，检查解析绝对、相对及包成员导入。

RunWorker 与 RunService 共同读取 ExecutionStatus；Worker 管队列、在途任务和服务生命周期，Task 管单次执行、看护、受限操作与资源释放，完成后唤醒独立接纳。DatabaseConfig 定义在基础设施，app.config 负责配置组合。数据库 models.py 反向导入业务模型仅用于元数据注册，是窄用途装配入口。Agent 只接收普通 AgentRequest，通过 AgentContext 协议报告内容和请求受控操作；该协议不暴露 store 或数据库。

技能格式由 skills/definitions 解释，员工捕获关系由 employees/assembly 维护。账号选择由 employees/tool_account_bindings 维护；连接、清单和调用分别归 mcp/connections、catalogs、invocation。共享主密钥机制归 infrastructure/credentials，业务负责转换故障；目录查询可以读约定概要字段，不重新解析技能原文。

## 运行管理组织约定

运行管理采用执行任务职责与目录收敛的 Service、Worker、Task 责任：RunService 受理、取消和提交成果；RunWorker 统一队列、在途任务、服务生命周期与持久化故障重试；RunTask 统一单次加载、领取、最终请求、恢复、执行、看护、受限操作、进度、资源释放与成果提交。models.py、store.py 直接归 execution；Worker、Task、线程等待和工具调用控制统一归 runtime，与 SDK 文件并列，原 bindings 包删除，快照捕获归 snapshot.py，固定指令归 prompts.py，当前授权组合由 RunService.authorize 负责。

Store 保留授权、预算、动作等原子事务，runtime 统一后台控制与 SDK 实现；其中 SDK 文件保留框架算法和状态解释；bootstrap 经 build_execution 构建子系统。不能为每个内部步骤再建立可装配对象或只转发的层级。完整文件职责见[执行说明](../../backend/app/execution/README.md)。

RunWorker 已取消全平台 Run 执行数量上限；单用户未结束容量、队列容量、同一对话占用及各 Run 的资源预算继续按各自规则检查。调度仍使用在途任务表去重，停服等待所有任务结束并释放单宿主锁。完整参数及行为只维护在[操作指南](../guides/backend-operations.md#运行)和[运行契约](../reference/runtime.md#调度与并发计数)。

## HTTP、校验与授权

输入优先复用 [RequestModel、分页和 PATCH 约定](../../backend/app/schemas.py)，字段结构由 schema 与运行 OpenAPI 维护。新增接口按现有规则声明请求、响应、状态和特殊错误；业务语义、权限、幂等及兼容在对应 reference 维护。

应用操作按失败含义抛出 app.errors 的具体类型；已登记分类的子类沿 MRO 使用最近分类的 HTTP 状态，未分类的 ServiceError 仍是服务器错误；code 表达细分原因，message 必须可公开，retry_after 是可选等待建议。HTTP 状态由 API 统一映射，不传入业务异常，也不通过公共父类吞掉所有故障。认证回退只处理认证失败，持续授权复核只将认证或权限失效解释为撤权；其他故障保留原有含义。类型、响应与传输例外见[应用错误约定](../../backend/app/api/README.md#应用错误分类与-http-转换)。

PATCH 用 exclude_unset 区分未提供与显式清空，不能把字段默认 None 当作客户端请求清空。非空字段显式 null 必须拒绝；可空字段的清空语义由各契约定义。配置变更核对对应预期修订，冲突保留客户端输入，服务不能静默采用最新版本覆盖。

身份由 auth.service 解析为 auth.actor.Actor，操作能力和资源归属通过 auth.permissions 分别检查。权限策略不读取 Cookie、数据库或业务模型。HTTP 路由声明操作能力；所属模块的用户操作也显式接收可信 Actor 并检查权限，不能依赖 HTTP 才安全。员工编辑权、资源归属、修订和写入使用同一事务。固定技能定义、全员规则、模型修订及运行连接解析等内部协作按已授权运行读取，使用调用方 Session，不套用管理员配置权限。本机账号初始化与环境核对是受信运维入口，不伪造用户会话。列表与单条访问遵守同一资源范围。公开 DTO 使用独立字段白名单；public 不表示匿名免会话。

同步数据库路径使用同步路由；异步 SSE 或任务中的同步 I/O 显式转入工作线程，不能把同步查询放进 async 函数便当作异步。Session 不随 Request 或异步任务共享。完整行为见 [API 模块](../../backend/app/api/README.md)。

## 事务与迁移

业务操作通过 Database.transaction 创建短事务，成功提交、异常回滚和释放由该入口负责。嵌套协作需要同一 Session 时传入当前 Session，辅助操作不擅自新建事务或提交。模型、工具、文件解析和昂贵密码计算置于写事务之外，必要时返回后在新短事务中复核状态。

对于先检查再写的竞争路径，依据业务约束在读取前取得写入资格，并由数据库唯一、外键和 CHECK 兜底。reserve_writer 的零匹配 UPDATE 原因由[代码注释](../../backend/app/infrastructure/database/transactions.py)及[竞争测试](../../backend/tests/test_database.py)维护；不要在 docs 复制其 SQL。

数字标识、UUID、UTC 时间、文本和 JSON 编码复用[字段类型](../../backend/app/infrastructure/database/fields.py)；应用校验与数据库约束分别核对，不能因 ORM 通过就宣称直接数据库写入也被保护。详情见[现行数据模型](../reference/data-model.md)。

新增 ORM 同时更新模型注册与正式迁移，审核自动生成的重命名、回填和 SQLite 重建。应用启动不自动建业务表或迁移；测试迁移使用真实 Alembic 流程。备份、升级和恢复遵循[操作指南](../guides/backend-operations.md#数据库与本地文件配置)，不在手册复制脚本或生产参数表。

## 执行、外部调用与资源

应用 lifespan 拥有连接池、RunWorker 和需关闭的服务；创建后立即登记最终释放，异步服务在启动尝试前登记停止。启动部分失败或任一关闭异常时仍尝试其余清理，先停止生产任务，再停止文件/沙箱维护，最后关闭 MCP 与数据库；异常链保留失败信息。每次请求或后台步骤拥有自己的 Session。共享数据库只允许一个持锁 RunWorker，当前不支持多 worker 或跨主机租约。

接受输入命令、配置依据、消息 ID/序号与 queued run 原子保存，模型执行发生在事务外。checkpoint 专门保存恢复状态；接受时已建立助手 Message，执行成果与 Run 终态原子提交，对话在另一个接纳事务写正文、附件和关联释放，SSE 只观察已提交的过程或结果。配置快照固定本轮方法，当前启停、会话、关系及模型修订仍逐动作复核。SDK 解释留在 execution/runtime；宿主接收普通内容和真实动作。模型动作的当前授权、预算扣减与开始记录使用同一事务。断开订阅不取消运行，取消通过显式操作表达。

外部调用定义时限、预算、凭证来源、错误与关闭责任。普通聊天允许重启后从 checkpoint 继续，未落盘模型请求可能重发，必须保留尝试计数及未知用量；其他外部操作仍须单独定义重放和副作用。取消优先于迟到成功，存储失败停止后续操作；未知协议快照不自动重放。新增工具、知识和执行方式须明确其授权与生命周期，不能直接开放 SDK 默认工具。

## 配置、错误与诊断信息

配置经 load_config 显式解析并校验，环境与本地文件优先级由[配置指南](../guides/database-configuration.md)和代码维护。业务不散落读取进程环境，测试使用注入配置和临时路径，不读取开发数据库或密钥。

已知业务错误沿用 [ServiceError 及子类](../../backend/app/errors.py)，HTTP 状态与响应由 [API 转换入口](../../backend/app/api/errors.py)维护。422 当前是经过脱敏的校验条目数组，不能假定所有错误都有同一 code 包络。SQLite busy/locked 与业务冲突分别处理。数据库驱动错误码、唯一约束文本由[数据库错误识别](../../backend/app/infrastructure/database/errors.py)封装；业务只转换能够确认含义的冲突，其他完整性异常原样抛出，删除保护检查实际关联。

不得将密码、Cookie、API Key、密文、完整配置快照或上游原始异常放入响应、日志和步骤。诊断信息优先记录非秘密标识、错误类别及已确认阶段；记录输入正文须有实际用途与边界，不能默认打印全部请求。HTTP 已提供 X-Request-ID 和安全失败日志，后台通过 Run 标识定位；核心执行事件另以相同 Run/动作键输出有界结构化文件日志；不是所有后端日志落库，详见[执行证据契约](../reference/execution-evidence.md)。

## 检查与交付

| 内容                                 | 当前工具或评审方式                                                                                                                          |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- |
| 基础 Python 错误、未使用项、导入排序 | Ruff 已启用 E4/E7/E9/F/I；具体规则见 pyproject.toml                                                                                         |
| Python 格式                          | Ruff format，包含 backend 与根 scripts                                                                                                      |
| 业务与迁移行为                       | pytest 隔离数据库、假上游及真实迁移；重点覆盖失败、拒绝、并发和恢复                                                                         |
| 类型、依赖方向及职责                 | mypy 检查数据库错误识别及已列入的执行边界；导入约束由 test_runtime_boundaries.py 与 test_execution_boundaries.py 强制；其余未列方向仍需评审 |
| 文档入口、文件和章节链接             | make check-docs；不判断业务内容是否正确                                                                                                     |

公共入口为 `make lint-backend`、`make test-backend`；修改启动器执行 `make test-dev`。后端测试的[共享夹具](../../backend/tests/conftest.py)使用 tmp_path、隔离迁移、注入配置与 TestClient lifespan；运行器测试按需显式启用并使用假执行器及真实 SDK 的假模型。外部响应格式变化应在适配边界测试，不仅 mock 最外层服务结果。

按[共享验证矩阵](shared.md#变更与验证选择)选择检查。表结构、接口、权限和生命周期变化同步当前契约与模块说明；局部实现原因留注释，可执行规则留工具。交付如实记录执行过的检查与剩余范围。

执行公开操作统一使用 submit、cancel、complete。是否参与调用方事务由 Session 参数和方法契约表达，不以 `_in` 后缀建立另一套操作词汇。submit、cancel 使用调用方 Session；complete 使用独立短事务。

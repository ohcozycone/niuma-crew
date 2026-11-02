# 完整目标工程树与文档树

API 归属已由 [2026-10-30 整理方案](../api-responsibilities.md) 接替；当前结构以 [API 模块](../../../backend/app/api/README.md)为准，本文保留上一轮设计依据。

本文为[已采纳方案](README.md)的实施结构附录，由[生成器](build-target-tree.py)根据当前实际文件扫描，并与[重构前基线](inventory.json)核对生成。基线 567 个工程文件均在[逐文件去向](file-map.md)中有记录；本次实际工程共 593 个文件。

每个目录和文件都有中文职责与设计原因，不用省略号代替节点。完整工程树包含后端、前端、测试、迁移、构建、教学资料、品牌、头像和文档；文档树另行完整展开，便于阅读。源代码旁 README、AGENTS 和设计系统文档同样在工程树中逐项列出。

本树是 P1—P4 当前实施范围的实际源码快照；execution/sdk 已迁入 agent_runtime。服务归属与依赖详见[请求与共享流程](service-boundaries.md)。没有为未来 Task、Goal、Plan、通用工具或知识能力预建文件树；接入条件见[后续能力](extensions.md)。依赖环境、缓存、被忽略构建产物、本地 .env、数据库、密钥和外部归档不属于此工程文件清单。

## 完整目标工程树

```text
niuma-crew/  # 实际工程根目录；模块化单体与前端独立构建，按职责协作
├── backend/  # 后端应用、迁移、测试与示例；部署代码与验证材料分开
│   ├── app/  # 正式应用包；模块按规则和生命周期所有权组织
│   │   ├── agent_runtime/  # Agent 内部运行模块；按业务与运行所有权聚合
│   │   │   ├── README.md  # Agent 输入、控制、输出与恢复边界；独立测试无需业务服务
│   │   │   ├── __init__.py  # Agent 运行包声明；导入不创建模型或后台任务
│   │   │   ├── checkpoints.py  # SDK 存档、可信完成和兼容读取；具体资源独立注入
│   │   │   ├── contracts.py  # 普通请求、受限控制、动作内容及候选输出；阻止 ORM 与 SDK 类型跨界
│   │   │   ├── langchain.py  # 现有 Agent 构造、模型工具循环与恢复判断；当前单一实现直接归组
│   │   │   ├── middleware.py  # SDK 动作前后接入控制；不解析业务身份或操作 ORM
│   │   │   ├── skill_loading.py  # 获准方法的虚拟资源与读取检查；方法文字不授予新权限
│   │   │   └── streaming.py  # SDK 片段和工具请求识别；宿主与前端只接收普通可见内容
│   │   ├── agents/  # 员工定义与装配模块；按业务与运行所有权聚合
│   │   │   ├── README.md  # 员工定义与装配的职责、协作与测试入口；不复制完整字段定义
│   │   │   ├── __init__.py  # 所属 Python 包声明；只保留必要入口，不在导入时运行服务
│   │   │   ├── models.py  # 员工定义与装配的 ORM 与约束；由本模块拥有而不集中业务模型
│   │   │   ├── schemas.py  # 员工定义与装配的请求和安全投影；传输校验与事务规则分开
│   │   │   └── service.py  # 员工配置装配与就绪规则；管理公开读取、共享准备和授权共同复用
│   │   ├── api/  # HTTP 接入与请求编排模块；按业务与运行所有权聚合
│   │   │   ├── routes/  # 按对外能力分组路由；传输职责不侵入执行器
│   │   │   │   ├── conversations/  # 对话请求与只读观察；只拆有真实复杂度的 API 分组
│   │   │   │   │   ├── __init__.py  # 所属 Python 包声明；只保留必要入口，不在导入时运行服务
│   │   │   │   │   ├── router.py  # 对话命令、读取与观察的 HTTP 接入；参数状态码和响应由本层转换
│   │   │   │   │   ├── service.py  # ConversationRequestService 的请求目标、幂等及接受停止反馈事务；共享流程只调用一份
│   │   │   │   │   └── streaming.py  # SSE 限额、重验身份、心跳及连接释放；只观察已保存结果，断线不取消工作
│   │   │   │   ├── __init__.py  # 所属 Python 包声明；只保留必要入口，不在导入时运行服务
│   │   │   │   ├── agents.py  # 员工配置 HTTP 入口；参数和响应交给传输层、业务规则交给所属服务
│   │   │   │   ├── auth.py  # 身份与登录 HTTP 入口；参数和响应交给传输层、业务规则交给所属服务
│   │   │   │   ├── ci_diagnosis.py  # 专业配置与安装 HTTP 入口；报告和反馈通过准确的对话回复路径接入
│   │   │   │   ├── configuration_summary.py  # 全局配置计数 HTTP 读取；一条汇总查询，不另建计数领域服务
│   │   │   │   ├── health.py  # 存活与就绪 HTTP 入口；参数和响应交给传输层、业务规则交给所属服务
│   │   │   │   ├── model_connections.py  # 模型连接 HTTP 入口；参数和响应交给传输层、业务规则交给所属服务
│   │   │   │   ├── organization_rules.py  # 全员规则 HTTP 入口；参数和响应交给传输层、业务规则交给所属服务
│   │   │   │   ├── public.py  # 公开字段白名单 HTTP 入口；参数和响应交给传输层、业务规则交给所属服务
│   │   │   │   └── skills.py  # 共享方法 HTTP 入口；参数和响应交给传输层、业务规则交给所属服务
│   │   │   ├── README.md  # HTTP 接入与请求编排的职责、协作与测试入口；不复制完整字段定义
│   │   │   ├── __init__.py  # 所属 Python 包声明；只保留必要入口，不在导入时运行服务
│   │   │   ├── dependencies.py  # 解析身份并取得服务；后台不持有 Request Session
│   │   │   ├── errors.py  # 应用及已知数据库错误转公开响应；隐藏内部细节
│   │   │   ├── frontend_delivery.py  # 静态成品、压缩缓存与深链交付；目录由应用装配显式传入
│   │   │   ├── rate_limit.py  # 共享请求频率限制；不把模型检查限流归入账号模型
│   │   │   ├── router.py  # 注册 HTTP 能力入口；显式导入对话分组 router，不让共享业务导入 API
│   │   │   └── security.py  # 浏览器来源、格式及体积保护；业务授权继续单独校验
│   │   ├── auth/  # 账号、登录与访问策略模块；按业务与运行所有权聚合
│   │   │   ├── README.md  # 账号、登录与访问策略的职责、协作与测试入口；不复制完整字段定义
│   │   │   ├── __init__.py  # 所属 Python 包声明；只保留必要入口，不在导入时运行服务
│   │   │   ├── actor.py  # 可信当前主体；被多个业务入口共用且不含 HTTP 依赖
│   │   │   ├── cli.py  # 管理员本地维护命令；复用认证服务而不绕过生命周期
│   │   │   ├── config.py  # 账号、登录与访问策略的部署设置；经统一配置入口解析和校验
│   │   │   ├── github.py  # OAuth 身份适配与返回地址检查；上游令牌使用后丢弃
│   │   │   ├── models.py  # 账号、登录与访问策略的 ORM 与约束；由本模块拥有而不集中业务模型
│   │   │   ├── permissions.py  # 操作及资源范围纯策略；不与账号会话生命周期混合
│   │   │   └── service.py  # 认证、签发、解析与撤销会话；对外返回 Actor
│   │   ├── ci_diagnosis/  # CI 证据、报告与反馈模块；按业务与运行所有权聚合
│   │   │   ├── README.md  # CI 证据、报告与反馈的职责、协作与测试入口；不复制完整字段定义
│   │   │   ├── __init__.py  # 所属 Python 包声明；只保留必要入口，不在导入时运行服务
│   │   │   ├── contracts.py  # CI 目标、证据、报告、反馈和工具声明；专业规则不进入通用 Run
│   │   │   ├── executor.py  # 现有受控 CI 取证与分析；共用运行控制但保留专业约束
│   │   │   ├── mcp.py  # 现有受限 MCP 客户端；保留范围和关闭语义而不预建通用工具框架
│   │   │   ├── models.py  # CiDiagnosis 过程、报告、专业版本及一次反馈；专业数据不塞进 Run
│   │   │   ├── report.py  # 来源、覆盖和引用校验及确定性正文；业务含义不进入通用执行
│   │   │   └── service.py  # CiDiagnosisService 的配置安装、范围、查询和反馈；专业记录名不与服务混用
│   │   ├── conversations/  # 交流内容、查询与共享回复流程；同时服务请求和后台，禁止反向导入 API
│   │   │   ├── README.md  # 对话与轻量交流内容的职责、协作与测试入口；不复制完整字段定义
│   │   │   ├── __init__.py  # 所属 Python 包声明；只保留必要入口，不在导入时运行服务
│   │   │   ├── authorization.py  # 身份、装配、连接和专业范围组合授权；API 与后台各时点共用
│   │   │   ├── models.py  # 对话、轻量内容与处理关联；正文直存且活动唯一约束保留
│   │   │   ├── preparation.py  # 接受时捕获与启动恢复时准备；原冻结依据不被当前配置覆盖
│   │   │   ├── publication.py  # 回复、专业报告、Run 终态与占用原子交付；完成恢复和排队停止共用
│   │   │   ├── queries.py  # 历史、问题目录、上下文和统一回复读取；页面不解释 SDK
│   │   │   ├── schemas.py  # 对话提交、用户消息、助手视图和公开步骤；前端无需理解执行内部类型
│   │   │   └── writes.py  # 建立输入与回复、绑定及填充终态正文；使用传入事务保持原子
│   │   ├── execution/  # Run 生命周期与实际动作模块；按业务与运行所有权聚合
│   │   │   ├── README.md  # Run 生命周期与实际动作的职责、协作与测试入口；不复制完整字段定义
│   │   │   ├── __init__.py  # 所属 Python 包声明；只保留必要入口，不在导入时运行服务
│   │   │   ├── admission.py  # 幂等、容量与登记 Run；归属与配置由调用用例组织
│   │   │   ├── config.py  # Run 生命周期与实际动作的部署设置；经统一配置入口解析和校验
│   │   │   ├── contracts.py  # 执行依据、准备函数与终态意图；不保存业务正文与专业结果
│   │   │   ├── control.py  # 受限运行控制及私有普通进度缓冲；调用状态操作但不解析 SDK
│   │   │   ├── coordinator.py  # 单 Run 看护与执行函数；通过注入回调准备授权发布，不反向导入对话或 API
│   │   │   ├── errors.py  # 运行故障到终态和公开提示；应用错误与 HTTP 转换另有边界
│   │   │   ├── models.py  # Run 与实际动作约束；移除通用结果和 CI 专业内容
│   │   │   ├── queries.py  # 执行记录、动作与安全事实查询；不反向依赖对话响应类型
│   │   │   ├── scheduler.py  # 多 Run 队列、进程锁、并发与启动恢复；不组织模型内部步骤
│   │   │   └── store.py  # Run 持久操作与状态规则、动作预算和恢复；不调用跨模块发布器
│   │   ├── infrastructure/  # 共享技术机制；不拥有业务规则
│   │   │   ├── database/  # 连接、事务、错误与元数据；所属模型留在业务模块
│   │   │   │   ├── README.md  # 技术机制的职责、协作与测试入口；不复制完整字段定义
│   │   │   │   ├── __init__.py  # 所属 Python 包声明；只保留必要入口，不在导入时运行服务
│   │   │   │   ├── base.py  # 声明式 ORM 基类及元数据；不包含业务规则
│   │   │   │   ├── errors.py  # 底层数据库错误识别；业务只转换确认的冲突
│   │   │   │   ├── fields.py  # UUID、UTC 与 JSON 字段约定；所有 ORM 共用存储语义
│   │   │   │   ├── models.py  # 集中注册所属模块 ORM；仅作迁移装配例外
│   │   │   │   ├── session.py  # DatabaseConfig 与数据库连接生命周期；不导入应用配置聚合层
│   │   │   │   └── transactions.py  # 写入资格与事务协作机制；处理先读后写竞争
│   │   │   └── __init__.py  # 所属 Python 包声明；只保留必要入口，不在导入时运行服务
│   │   ├── llm/  # 模型技术适配模块；按业务与运行所有权聚合
│   │   │   ├── README.md  # 模型技术适配的职责、协作与测试入口；不复制完整字段定义
│   │   │   ├── __init__.py  # 所属 Python 包声明；只保留必要入口，不在导入时运行服务
│   │   │   ├── config.py  # 显式单次模型配置；不在模型层查询业务绑定
│   │   │   ├── errors.py  # 已知上游错误分类；不吞数据库或程序故障
│   │   │   ├── factory.py  # 模型工厂及网络会话；调用结束和取消时关闭资源
│   │   │   └── usage.py  # 普通用量结构与保守累计；仅接收普通映射，SDK 类型留在运行实现
│   │   ├── model_connections/  # 模型连接与凭证模块；按业务与运行所有权聚合
│   │   │   ├── README.md  # 模型连接与凭证的职责、协作与测试入口；不复制完整字段定义
│   │   │   ├── __init__.py  # 所属 Python 包声明；只保留必要入口，不在导入时运行服务
│   │   │   ├── credentials.py  # 模型密文与主密钥操作；凭证生命周期留在连接模块
│   │   │   ├── models.py  # 模型连接与凭证的 ORM 与约束；由本模块拥有而不集中业务模型
│   │   │   ├── presets.py  # 受信模型协议及端点元数据；不让表单任意扩大连接能力
│   │   │   ├── schemas.py  # 模型连接与凭证的请求和安全投影；传输校验与事务规则分开
│   │   │   └── service.py  # 模型连接与凭证的业务操作；短事务内校验并明确回滚
│   │   ├── organization_rules/  # 全员规章制度模块；按业务与运行所有权聚合
│   │   │   ├── README.md  # 全员规章制度的职责、协作与测试入口；不复制完整字段定义
│   │   │   ├── __init__.py  # 所属 Python 包声明；只保留必要入口，不在导入时运行服务
│   │   │   ├── models.py  # 全员规章制度的 ORM 与约束；由本模块拥有而不集中业务模型
│   │   │   ├── schemas.py  # 全员规章制度的请求和安全投影；传输校验与事务规则分开
│   │   │   └── service.py  # 全员规章制度的业务操作；短事务内校验并明确回滚
│   │   ├── skills/  # 共享方法资产模块；按业务与运行所有权聚合
│   │   │   ├── README.md  # 共享方法资产的职责、协作与测试入口；不复制完整字段定义
│   │   │   ├── __init__.py  # 所属 Python 包声明；只保留必要入口，不在导入时运行服务
│   │   │   ├── models.py  # 共享方法资产的 ORM 与约束；由本模块拥有而不集中业务模型
│   │   │   ├── parameters.py  # 有界参数规范与装配参数校验；编辑、保存和运行准备共用
│   │   │   ├── schemas.py  # 共享方法资产的请求和安全投影；传输校验与事务规则分开
│   │   │   └── service.py  # 共享方法资产的业务操作；短事务内校验并明确回滚
│   │   ├── __init__.py  # 所属 Python 包声明；只保留必要入口，不在导入时运行服务
│   │   ├── bootstrap.py  # 装配共享准备授权发布回调、执行器与 HTTP 请求服务；后台不依赖 API 实现
│   │   ├── config.py  # 聚合并校验部署配置；避免业务散读环境变量
│   │   ├── errors.py  # 应用失败语义；由 HTTP 层决定响应状态
│   │   ├── main.py  # ASGI 导出入口；与 HTTP 适配和业务规则分开
│   │   └── schemas.py  # 公共请求与分页校验；避免 PATCH 和文本约束各自实现
│   ├── datasets/  # 教学与评测示例；不默认进入运行上下文
│   │   └── travel-expense/  # 虚构差旅数据包；资料与评分依据分开
│   │       ├── documents/  # 可用于知识实验的正文；保留来源与生效范围
│   │       │   ├── 01-scope-and-transport.md  # 差旅教学的 01-scope-and-transport.md；保留资料、题目及审核依据的来源和用途隔离
│   │       │   ├── 02-accommodation-policy.md  # 差旅教学的 02-accommodation-policy.md；保留资料、题目及审核依据的来源和用途隔离
│   │       │   ├── 03-accommodation-update.md  # 差旅教学的 03-accommodation-update.md；保留资料、题目及审核依据的来源和用途隔离
│   │       │   ├── 04-expense-process.md  # 差旅教学的 04-expense-process.md；保留资料、题目及审核依据的来源和用途隔离
│   │       │   └── 05-knowledge-boundaries.md  # 差旅教学的 05-knowledge-boundaries.md；保留资料、题目及审核依据的来源和用途隔离
│   │       ├── evaluation/  # 审核、题目与参考答案；不泄漏到回答输入
│   │       │   ├── REVIEW.md  # 差旅教学的 REVIEW.md；保留资料、题目及审核依据的来源和用途隔离
│   │       │   ├── questions.jsonl  # 差旅教学的 questions.jsonl；保留资料、题目及审核依据的来源和用途隔离
│   │       │   ├── reference_answers.jsonl  # 差旅教学的 reference_answers.jsonl；保留资料、题目及审核依据的来源和用途隔离
│   │       │   ├── review-results.jsonl  # 差旅教学的 review-results.jsonl；保留资料、题目及审核依据的来源和用途隔离
│   │       │   └── rules.json  # 差旅教学的 rules.json；保留资料、题目及审核依据的来源和用途隔离
│   │       ├── README.md  # 差旅教学的 README.md；保留资料、题目及审核依据的来源和用途隔离
│   │       └── manifest.json  # 差旅教学的 manifest.json；保留资料、题目及审核依据的来源和用途隔离
│   ├── experiments/  # 独立技术验证；不作为正式应用隐式依赖
│   │   └── sqlite_checkpoint_chat.py  # 隔离 SDK 实验；不装配正式业务应用
│   ├── migrations/  # 正式结构与数据升级；与应用启动分开执行
│   │   ├── versions/  # 冻结历史和增量迁移；不改写已存在升级链
│   │   │   ├── 0001_initial_schema.py  # 冻结的历史结构及数据升级；保留原名和行为防止旧库迁移失真
│   │   │   ├── 0002_remove_run_base_checkpoint.py  # 冻结的历史结构及数据升级；保留原名和行为防止旧库迁移失真
│   │   │   ├── 0003_unique_agent_name.py  # 冻结的历史结构及数据升级；保留原名和行为防止旧库迁移失真
│   │   │   ├── 0004_execution_and_messages.py  # 冻结的历史结构及数据升级；保留原名和行为防止旧库迁移失真
│   │   │   └── 0005_message_delivery.py  # P2 的正文、关联、专业数据与版本迁移；保留历史 ID 并逐项校验
│   │   ├── env.py  # 正式迁移环境及连接；不依赖应用自动建表
│   │   └── script.py.mako  # 新迁移模板；沿用工具标准格式
│   ├── tests/  # 隔离行为、竞争与边界验证；不访问开发业务库或真实上游
│   │   ├── checkpoint_helpers.py  # 测试存档构造与断言；正式 SDK 恢复不携带测试图 API
│   │   ├── checkpoint_worker.py  # 隔离 HTTP 子进程及故障注入；验证真实重启窗口
│   │   ├── configuration_helpers.py  # 配置测试共享装配；减少重复而不掩盖业务断言
│   │   ├── conftest.py  # 临时数据库、身份和服务 fixture；测试不读开发数据
│   │   ├── legacy_execution_helpers.py  # 冻结旧库和旧存档的构造；保留真实迁移回归能力
│   │   ├── runtime_helpers.py  # 内存运行控制与假执行器；分别验证隔离边界两侧
│   │   ├── scenario_client.py  # 既有场景的测试适配；生产不保留旧 Run HTTP 入口
│   │   ├── test_agent_identity.py  # 员工姓名、身份提示和历史快照的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_agent_skill_storage.py  # 员工装配约束及整体修改回滚的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_api_errors.py  # 应用错误分类、响应脱敏和捕获边界的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_authentication.py  # 账号认证、游客、会话失效和撤销的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_bootstrap.py  # 应用资源装配、启动失败和关闭的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_capability_runtime.py  # 真实 SDK 方法加载、预算与授权的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_checkpoint_runtime.py  # 真实子进程重启、预算与完成补发布的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_ci_diagnosis.py  # 专业取证、引用、报告、反馈及取消竞争的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_config.py  # 配置来源、路径、范围和预算合法性的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_configuration_api.py  # 配置接口、修订冲突、参数及公开投影的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_conversation_message_state.py  # 消息回复、状态、历史和观察一致性的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_conversation_submission.py  # 原子接受、幂等与回滚的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_conversations.py  # 对话、上下文、权限、停止及重试的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_database.py  # 底层约束、事务和写入竞争的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_database_error_boundaries.py  # 已知业务冲突、未知异常和删除保护的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_database_errors.py  # 数据库错误码与约束识别的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_execution_boundaries.py  # 原子发布、不可变历史、故障和依赖方向的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_frontend.py  # 静态资源、压缩缓存、深链与缺失资源的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_github_signin.py  # OAuth state、PKCE、身份及安全返回地址的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_llm.py  # 模型工厂、流关闭、错误和未知用量累计的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_message_delivery_migration.py  # 0005 历史保留与损坏输入拒绝；正式迁移不能凭空补答案
│   │   ├── test_migrations.py  # 新旧库升级、数据保留、离线 SQL 和失败回滚的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_model_connections.py  # 连接配置、密文、修订和显式连接检查的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_organization_rules.py  # 共享规则、权限与并发版本替换的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_response_contract.py  # 实际公开协议及一致读取测试；不经过旧场景适配器
│   │   ├── test_runtime_boundaries.py  # Agent 与宿主依赖、受限接口和普通内容回归；防止存储逃逸
│   │   ├── test_runtime_streaming.py  # 流式片段、工具轮次和取消关闭的隔离回归；保留拒绝、故障与竞争断言
│   │   └── test_sqlite_checkpoints.py  # 独立实验的存档隔离与跨进程恢复的隔离回归；保留拒绝、故障与竞争断言
│   ├── .env.example  # 部署参数示例；只提供占位值而不保存真实秘密
│   ├── .python-version  # Python 工具链版本；开发与隔离测试使用一致解释器
│   ├── AGENTS.md  # 端内协作导航；规则正文集中在工程与契约文档
│   ├── README.md  # 所属模块入口、职责与验证导航；详细规则只维护一份
│   ├── alembic.ini  # 数据库迁移入口及路径配置；升级不依赖启动时自动建表
│   ├── pyproject.toml  # 依赖、命令与检查清单；与锁文件同步维护
│   └── uv.lock  # 依赖精确锁定；使环境与构建可复现
├── docs/  # 项目级文档；现行规则、目标方案与历史证据分开
│   ├── architecture/  # 实施后的系统协作；目标方案未落地前不改成当前事实
│   │   ├── diagrams/  # 当前架构图和源；实现时与正文同步更新
│   │   │   ├── backend-current.svg  # 静态或图示资源 backend-current.svg；保留来源并按对应构建或文档流程维护
│   │   │   ├── build-backend-views.py  # 对应文档图示的可编辑生成源；改变设计后同步再生成
│   │   │   └── diagram_paths.py  # 对应文档图示的可编辑生成源；改变设计后同步再生成
│   │   ├── agent-runtime.md  # 实施后解释 SDK 与宿主协作；取舍与控制边界有稳定维护位置
│   │   ├── backend.md  # 后端架构；按现行规则或导航维护，防止目标与当前实现混淆
│   │   ├── domain-glossary.md  # 当前领域术语；按现行规则或导航维护，防止目标与当前实现混淆
│   │   ├── frontend.md  # 前端架构；按现行规则或导航维护，防止目标与当前实现混淆
│   │   └── overview.md  # 平台架构；按现行规则或导航维护，防止目标与当前实现混淆
│   ├── engineering/  # 各端可执行工程标准；不累计实施流水账
│   │   ├── backend.md  # 后端工程手册；按现行规则或导航维护，防止目标与当前实现混淆
│   │   ├── frontend.md  # 前端工程手册；按现行规则或导航维护，防止目标与当前实现混淆
│   │   └── shared.md  # 共享工程约定；按现行规则或导航维护，防止目标与当前实现混淆
│   ├── guides/  # 开发、配置、迁移和资源操作；明确前提与恢复
│   │   ├── assets.md  # 应用资源与历史素材维护；按现行规则或导航维护，防止目标与当前实现混淆
│   │   ├── backend-operations.md  # 后端运行、配置与维护；按现行规则或导航维护，防止目标与当前实现混淆
│   │   ├── database-configuration.md  # 数据库连接与本地文件配置；按现行规则或导航维护，防止目标与当前实现混淆
│   │   └── local-development.md  # 本地开发与统一命令入口；按现行规则或导航维护，防止目标与当前实现混淆
│   ├── learning/  # 学习路线和代码阅读；不替代正式行为契约
│   │   ├── observing-runtime.md  # 从页面到后台和数据的渐进观测；用具体操作理解机制
│   │   ├── reading-code.md  # 按运行链路阅读代码；按现行规则或导航维护，防止目标与当前实现混淆
│   │   └── roadmap.md  # 智能应用开发学习路线；按现行规则或导航维护，防止目标与当前实现混淆
│   ├── proposals/  # 尚未实施的增量与已实现方案来源；状态以正文为准
│   │   ├── agent-capabilities/  # 所属专题增量及图示；状态以方案正文为准，实施后回写现行契约
│   │   │   ├── diagrams/  # 所属专题增量及图示；状态以方案正文为准，实施后回写现行契约
│   │   │   │   ├── agent-capability-model.svg  # 静态或图示资源 agent-capability-model.svg；保留来源并按对应构建或文档流程维护
│   │   │   │   └── agent-capability-model@2x.png  # 静态或图示资源 agent-capability-model@2x.png；保留来源并按对应构建或文档流程维护
│   │   │   ├── README.md  # 数字员工目标数据模型；按增量方案维护，防止目标与当前实现混淆
│   │   │   ├── data.md  # 能力资源目标字段与约束草案；按增量方案维护，防止目标与当前实现混淆
│   │   │   ├── migration.md  # 能力后续阶段迁移与验收计划；按增量方案维护，防止目标与当前实现混淆
│   │   │   └── runtime.md  # 数字员工运行与读取契约；按增量方案维护，防止目标与当前实现混淆
│   │   ├── agent-workspace/  # 所属专题增量及图示；状态以方案正文为准，实施后回写现行契约
│   │   │   ├── README.md  # 员工工作页与任务执行的分阶段改造；按增量方案维护，防止目标与当前实现混淆
│   │   │   ├── runtime.md  # 执行内核、持久等待与自动交办；按增量方案维护，防止目标与当前实现混淆
│   │   │   └── tasks.md  # 任务、成果与接口增量；按增量方案维护，防止目标与当前实现混淆
│   │   ├── backend-architecture/  # 所属专题增量及图示；状态以方案正文为准，实施后回写现行契约
│   │   │   ├── diagrams/  # 所属专题增量及图示；状态以方案正文为准，实施后回写现行契约
│   │   │   │   └── backend-modules.svg  # 静态或图示资源 backend-modules.svg；保留来源并按对应构建或文档流程维护
│   │   │   ├── README.md  # 后端领域与执行架构重设计；按增量方案维护，防止目标与当前实现混淆
│   │   │   └── execution.md  # 执行对象、事务与生命周期；按增量方案维护，防止目标与当前实现混淆
│   │   ├── knowledge-assistant/  # 所属专题增量及图示；状态以方案正文为准，实施后回写现行契约
│   │   │   ├── README.md  # 项目知识助手最小闭环；按增量方案维护，防止目标与当前实现混淆
│   │   │   ├── access.md  # P1 与后续阶段；按增量方案维护，防止目标与当前实现混淆
│   │   │   └── plan.md  # 知识助手首个学习迭代与开发任务；按增量方案维护，防止目标与当前实现混淆
│   │   ├── platform-refactor/  # 本次统一目标设计；替代旧方案的后续边界和命名
│   │   │   ├── diagrams/  # 本次目标图与源；明确未实施而不覆盖当前图
│   │   │   │   ├── build-diagrams.py  # 新版目标图的可编辑源；图与正文同步
│   │   │   │   ├── build-layered-diagrams.py  # 并行整理的分层图源，本轮保留；与专题共同核对职责和含义
│   │   │   │   ├── layered-01-overview.svg  # 并行整理的总体图，本轮未重画；与新版专题共同核对职责
│   │   │   │   ├── layered-02-frontend.svg  # 并行整理的前端图，本轮未重画；与新版 Hook 边界分别核对
│   │   │   │   ├── layered-03-backend.svg  # 并行整理的后端图，本轮未重画；不由生成树推断已经实施
│   │   │   │   ├── layered-04-execution.svg  # 并行整理的执行图，本轮未重画；与新版运行协议分别核对
│   │   │   │   ├── request-lifecycle.svg  # 新版发送到发布时序；区分事务和外部等待
│   │   │   │   └── target-boundaries.svg  # 新版模块与数据归属图；帮助区分模块和实体
│   │   │   ├── README.md  # 总方案结论、实例和导航；先建立整体再进入细节
│   │   │   ├── api.md  # 面向用户操作的接口；公开路径不镜像内部模块
│   │   │   ├── build-target-tree.py  # 生成树和完整映射；从同一来源核对结构
│   │   │   ├── decisions.md  # 逐项追问与替代方案；说明抽象的真实必要性
│   │   │   ├── domain.md  # 内容、处理、关联与专业数据；从事实区分身份和状态
│   │   │   ├── extensions.md  # 未来能力的接入条件；不提前预建完整空文件树
│   │   │   ├── file-map.md  # 每个重写前文件去向；避免只规划主链遗漏外围
│   │   │   ├── flows.md  # 端到端正常与异常流程；明确写入者、顺序和提交
│   │   │   ├── frontend.md  # 页面、Hook和状态生命周期；按交互组织而非后端实体
│   │   │   ├── inventory.json  # 重写前工程清单；使覆盖与新增文件可核对
│   │   │   ├── layered-architecture.md  # 配套四张职责分层图解读；具体数据和接口由对应专题确定
│   │   │   ├── migration.md  # 实施、数据搬迁与验收；保留正确行为并可核对回退
│   │   │   ├── modules.md  # 全部后端模块职责与依赖；区分业务组织与执行管理
│   │   │   ├── responsibility-review.md  # 全工程职责与引用复核；给出证据、目标归属、保留和不采纳项
│   │   │   ├── runtime.md  # Agent 输入控制输出与恢复；防止 SDK 和存储互相渗透
│   │   │   ├── service-boundaries.md  # API 请求服务、业务模块与共享回复流程；给出逐项归属、调用和事务依据
│   │   │   └── target-tree.md  # 完整目标工程及文档树；每节点解释职责与原因
│   │   ├── skills-and-mcp/  # 所属专题增量及图示；状态以方案正文为准，实施后回写现行契约
│   │   │   ├── README.md  # 标准 Agent Skills 与通用 MCP 接入；按增量方案维护，防止目标与当前实现混淆
│   │   │   └── ci-connection-migration.md  # CI 凭证迁移到工具连接；按增量方案维护，防止目标与当前实现混淆
│   │   ├── README.md  # 待实施方案索引；按增量方案维护，防止目标与当前实现混淆
│   │   ├── agent-model-rebuild.md  # Agent 模型与持久化基线重建；按增量方案维护，防止目标与当前实现混淆
│   │   ├── agent-name-identity.md  # 员工名称唯一与运行身份；按增量方案维护，防止目标与当前实现混淆
│   │   ├── conversation-execution-display.md  # 对话执行过程展示；按增量方案维护，防止目标与当前实现混淆
│   │   ├── conversation-hooks.md  # 会话与消息访问边界；按增量方案维护，防止目标与当前实现混淆
│   │   ├── conversation-layout.md  # 对话布局与历史读取增量；按增量方案维护，防止目标与当前实现混淆
│   │   ├── conversation-message-state.md  # 对话消息与执行步骤统一读取；按增量方案维护，防止目标与当前实现混淆
│   │   ├── conversation-state-management.md  # 对话状态与执行过程展示；按增量方案维护，防止目标与当前实现混淆
│   │   ├── frontend-simplification.md  # 前端精简的待核对增量；按增量方案维护，防止目标与当前实现混淆
│   │   ├── member-model-access.md  # 免费模型的后续方向（未实现）；按增量方案维护，防止目标与当前实现混淆
│   │   ├── organization-rules.md  # 多份规则建议（待确认，未实现）；按增量方案维护，防止目标与当前实现混淆
│   │   ├── platform-evolution.md  # 平台后续能力的接入边界；按增量方案维护，防止目标与当前实现混淆
│   │   ├── product-validation.md  # 产品定位、差异化与企业收益验证；按增量方案维护，防止目标与当前实现混淆
│   │   ├── research-assistant.md  # 研发研究员最小闭环；按增量方案维护，防止目标与当前实现混淆
│   │   ├── runtime-configuration.md  # 运行配置集中管理；按增量方案维护，防止目标与当前实现混淆
│   │   ├── runtime-refactoring.md  # runtime 重构与执行过程展示；按增量方案维护，防止目标与当前实现混淆
│   │   ├── service-errors.md  # 应用错误分类整理；按增量方案维护，防止目标与当前实现混淆
│   │   └── sqlite-checkpoint-chat.md  # SQLite checkpoint 聊天接入方案；按增量方案维护，防止目标与当前实现混淆
│   ├── records/  # 限定时点的评审与验收；原始名称和通过数量保持历史含义
│   │   ├── diagrams/  # 历史评审图；不作为当前架构前置
│   │   │   └── dependency-review/  # 一次依赖研究的图与源；保留其证据时点
│   │   │       ├── build-diagrams.py  # 对应文档图示的可编辑生成源；改变设计后同步再生成
│   │   │       ├── current-dependencies.svg  # 静态或图示资源 current-dependencies.svg；保留来源并按对应构建或文档流程维护
│   │   │       ├── proposed-boundaries.svg  # 静态或图示资源 proposed-boundaries.svg；保留来源并按对应构建或文档流程维护
│   │   │       └── runtime-scheduling.svg  # 静态或图示资源 runtime-scheduling.svg；保留来源并按对应构建或文档流程维护
│   │   ├── README.md  # 评审与验收记录索引；按历史证据维护，防止目标与当前实现混淆
│   │   ├── agent-editor-validation.md  # 员工编辑与删除确认验收；按历史证据维护，防止目标与当前实现混淆
│   │   ├── agent-model-rebuild.md  # Agent 模型基线重建验收；按历史证据维护，防止目标与当前实现混淆
│   │   ├── agent-name-identity.md  # 员工名称唯一与运行身份验收；按历史证据维护，防止目标与当前实现混淆
│   │   ├── agent-resource-summary.md  # 员工资源配置摘要：历史实施与验证；按历史证据维护，防止目标与当前实现混淆
│   │   ├── agent-runtime-sdk-assessment.md  # Agent运行层SDK接入评估；按历史证据维护，防止目标与当前实现混淆
│   │   ├── api-service-boundaries.md  # 本轮服务归属修订及文档检查；保留未实施状态和业务文件哈希证据
│   │   ├── asset-isolation.md  # 应用与历史素材隔离；按历史证据维护，防止目标与当前实现混淆
│   │   ├── auth-consolidation.md  # 身份与访问控制模块合并验收；按历史证据维护，防止目标与当前实现混淆
│   │   ├── avatar-validation.md  # 静态头像历史验证；按历史证据维护，防止目标与当前实现混淆
│   │   ├── backend-dependency-review.md  # 后端依赖与调度关系深度评审；按历史证据维护，防止目标与当前实现混淆
│   │   ├── backend-file-responsibilities.md  # 后端文件职责第一轮整理验收；按历史证据维护，防止目标与当前实现混淆
│   │   ├── brand-development.md  # 品牌候选、命名迁移与验收记录；按历史证据维护，防止目标与当前实现混淆
│   │   ├── ci-diagnosis-review.md  # GitHub CI 诊断方案质询与价值评审；按历史证据维护，防止目标与当前实现混淆
│   │   ├── client-routing.md  # 客户端路由迁移与专项复查；按历史证据维护，防止目标与当前实现混淆
│   │   ├── component-visual-validation.md  # 组件视觉与状态：历史验收；按历史证据维护，防止目标与当前实现混淆
│   │   ├── conversation-hooks.md  # 会话与消息双入口验收；按历史证据维护，防止目标与当前实现混淆
│   │   ├── conversation-layout.md  # 对话布局与历史读取验收；按历史证据维护，防止目标与当前实现混淆
│   │   ├── conversation-message-state.md  # 对话正文与步骤统一读取验收；按历史证据维护，防止目标与当前实现混淆
│   │   ├── conversation-state-management.md  # 会话 SDK 与执行过程展示验收；按历史证据维护，防止目标与当前实现混淆
│   │   ├── database-error-boundaries.md  # 数据库错误识别与业务冲突边界验收；按历史证据维护，防止目标与当前实现混淆
│   │   ├── design-system.md  # 设计系统目录、令牌与第三方主题整理记录；按历史证据维护，防止目标与当前实现混淆
│   │   ├── directory-responsibility-review.md  # 本轮目录审查范围与实际文档检查；不冒称业务改动已经实施
│   │   ├── documentation-reorganization.md  # 文档分类、后端工程手册与引用整理验收；按历史证据维护，防止目标与当前实现混淆
│   │   ├── execution-refactor.md  # 执行重设计第一阶段验收；按历史证据维护，防止目标与当前实现混淆
│   │   ├── frontend-engineering.md  # 前端工程标准实施与验收；按历史证据维护，防止目标与当前实现混淆
│   │   ├── light-theme.md  # 全站微暖中性浅色体系；按历史证据维护，防止目标与当前实现混淆
│   │   ├── local-development.md  # 本地开发：历史迁移与验证；按历史证据维护，防止目标与当前实现混淆
│   │   ├── openagents-collaboration-research.md  # OpenAgents 工作空间与协作机制调研；按历史证据维护，防止目标与当前实现混淆
│   │   ├── platform-product-and-execution-assessment.md  # 数字员工平台的产品重心与执行架构评估；按历史证据维护，防止目标与当前实现混淆
│   │   ├── platform-refactor-implementation.md  # 实施、迁移、检查、启动和限制；区分当前规则与一次验证
│   │   ├── platform-refactor-plan.md  # 平台重构计划编制与检查记录；按历史证据维护，防止目标与当前实现混淆
│   │   ├── platform-refactor-redesign.md  # 本次重写、独立复核与实际检查记录；不冒称业务已经重构
│   │   ├── run-checkpoint-start.md  # 执行起点精简验收；按历史证据维护，防止目标与当前实现混淆
│   │   ├── runtime-configuration.md  # 运行配置集中管理验收；按历史证据维护，防止目标与当前实现混淆
│   │   ├── runtime-middleware-refactor.md  # 运行中间件职责整理与验证；按历史证据维护，防止目标与当前实现混淆
│   │   ├── service-errors.md  # 应用错误分类整理验收；按历史证据维护，防止目标与当前实现混淆
│   │   └── sqlite-checkpoint-chat.md  # SQLite checkpoint 聊天隔离验证；按历史证据维护，防止目标与当前实现混淆
│   ├── reference/  # 实施后生效的契约；字段事实仍链接代码与迁移
│   │   ├── agent-configuration/  # 员工配置的数据及 API；装配与公开投影一处维护
│   │   │   ├── api.md  # 员工与技能管理接口；按现行规则或导航维护，防止目标与当前实现混淆
│   │   │   └── data.md  # 员工与技能当前数据结构；按现行规则或导航维护，防止目标与当前实现混淆
│   │   ├── ci-diagnosis/  # 专业结果与反馈契约；与通用执行规则分开
│   │   │   ├── README.md  # 运维马 GitHub CI 故障诊断；按现行规则或导航维护，防止目标与当前实现混淆
│   │   │   ├── api.md  # GitHub CI 诊断接口契约；按现行规则或导航维护，防止目标与当前实现混淆
│   │   │   └── data.md  # GitHub CI 诊断数据契约；按现行规则或导航维护，防止目标与当前实现混淆
│   │   ├── diagram/  # 现行运行时序图；与对应契约一起更新
│   │   │   └── runtime-sequence.svg  # 静态或图示资源 runtime-sequence.svg；保留来源并按对应构建或文档流程维护
│   │   ├── agent-resource-summary.md  # 员工资源配置摘要；按现行规则或导航维护，防止目标与当前实现混淆
│   │   ├── auth.md  # 管理员登录与游客访问契约；按现行规则或导航维护，防止目标与当前实现混淆
│   │   ├── avatar-assets.md  # 角色 SVG 母版与静态组件；按现行规则或导航维护，防止目标与当前实现混淆
│   │   ├── brand.md  # 产品品牌与工程标识；按现行规则或导航维护，防止目标与当前实现混淆
│   │   ├── conversations.md  # 对话与历史契约；按现行规则或导航维护，防止目标与当前实现混淆
│   │   ├── data-model.md  # 当前数据模型与约束入口；按现行规则或导航维护，防止目标与当前实现混淆
│   │   ├── design-system.md  # 设计系统展示与第三方主题接入；按现行规则或导航维护，防止目标与当前实现混淆
│   │   ├── github-signin.md  # GitHub 登录与普通用户；按现行规则或导航维护，防止目标与当前实现混淆
│   │   ├── model-connections.md  # 大脑配置与员工模型装配；按现行规则或导航维护，防止目标与当前实现混淆
│   │   ├── organization-rules.md  # 规章制度与员工自动继承；按现行规则或导航维护，防止目标与当前实现混淆
│   │   ├── runtime.md  # 当前运行、步骤与读取；按现行规则或导航维护，防止目标与当前实现混淆
│   │   ├── signin.md  # Signin 登录页面；按现行规则或导航维护，防止目标与当前实现混淆
│   │   └── theme.md  # 日间、夜间与跟随系统；按现行规则或导航维护，防止目标与当前实现混淆
│   ├── templates/  # 按需裁剪的文档模板；不强制重复无关章节
│   │   └── design.md  # 增量名称与设计；按现行规则或导航维护，防止目标与当前实现混淆
│   ├── README.md  # NiumaCrew 文档索引；按现行规则或导航维护，防止目标与当前实现混淆
│   └── documentation.md  # 文档组织与维护规范；按现行规则或导航维护，防止目标与当前实现混淆
├── frontend/  # 浏览器应用和构建配置；与后端通过明确 DTO 协作
│   ├── public/  # 浏览器直接消费的静态成品；不放制作工程与秘密
│   │   ├── avatars/  # 正式角色资源；与生成清单同源
│   │   │   ├── svg/  # 对应角色的同源静态成品；与选择器及生成清单保持一致
│   │   │   │   ├── admin-bull.svg  # 角色成品或生成组件 admin-bull.svg；与头像清单同源，不在架构重构中重做素材
│   │   │   │   ├── backend-horse.svg  # 角色成品或生成组件 backend-horse.svg；与头像清单同源，不在架构重构中重做素材
│   │   │   │   ├── catalog.json  # SVG 角色资源元数据；文件变化可被构建校验发现
│   │   │   │   ├── designer-bull.svg  # 角色成品或生成组件 designer-bull.svg；与头像清单同源，不在架构重构中重做素材
│   │   │   │   ├── finance-bull.svg  # 角色成品或生成组件 finance-bull.svg；与头像清单同源，不在架构重构中重做素材
│   │   │   │   ├── frontend-bull.svg  # 角色成品或生成组件 frontend-bull.svg；与头像清单同源，不在架构重构中重做素材
│   │   │   │   ├── intern-bull.svg  # 角色成品或生成组件 intern-bull.svg；与头像清单同源，不在架构重构中重做素材
│   │   │   │   ├── knowledge-bull.svg  # 角色成品或生成组件 knowledge-bull.svg；与头像清单同源，不在架构重构中重做素材
│   │   │   │   ├── operations-bull.svg  # 角色成品或生成组件 operations-bull.svg；与头像清单同源，不在架构重构中重做素材
│   │   │   │   ├── product-horse.svg  # 角色成品或生成组件 product-horse.svg；与头像清单同源，不在架构重构中重做素材
│   │   │   │   ├── programmer-horse.svg  # 角色成品或生成组件 programmer-horse.svg；与头像清单同源，不在架构重构中重做素材
│   │   │   │   ├── research-horse.svg  # 角色成品或生成组件 research-horse.svg；与头像清单同源，不在架构重构中重做素材
│   │   │   │   ├── support-horse.svg  # 角色成品或生成组件 support-horse.svg；与头像清单同源，不在架构重构中重做素材
│   │   │   │   └── sysadmin-horse.svg  # 角色成品或生成组件 sysadmin-horse.svg；与头像清单同源，不在架构重构中重做素材
│   │   │   └── catalog.json  # 头像标识与成品目录；选择器和构建清单有同一来源
│   │   └── brand/  # 品牌静态成品；由构建脚本生成和校验
│   │       ├── apple-touch-icon.png  # 静态或图示资源 apple-touch-icon.png；保留来源并按对应构建或文档流程维护
│   │       ├── icon-192.png  # 静态或图示资源 icon-192.png；保留来源并按对应构建或文档流程维护
│   │       ├── icon-32.png  # 静态或图示资源 icon-32.png；保留来源并按对应构建或文档流程维护
│   │       ├── mark.svg  # 静态或图示资源 mark.svg；保留来源并按对应构建或文档流程维护
│   │       ├── wordmark-dark.svg  # 静态或图示资源 wordmark-dark.svg；保留来源并按对应构建或文档流程维护
│   │       └── wordmark.svg  # 静态或图示资源 wordmark.svg；保留来源并按对应构建或文档流程维护
│   ├── scripts/  # 前端资源构建与压缩；生成步骤集中可重复
│   │   ├── README.md  # README 资源构建；从来源再生成并保持交付可重复
│   │   ├── build-avatar-manifest.mjs  # build-avatar-manifest 资源构建；从来源再生成并保持交付可重复
│   │   ├── build-brand.mjs  # 从品牌源稿生成派生图形；构建不再反向读取登录页私有文件
│   │   ├── build-frontend-compression.mjs  # build-frontend-compression 资源构建；从来源再生成并保持交付可重复
│   │   └── build-theme.mjs  # build-theme 资源构建；从来源再生成并保持交付可重复
│   ├── src/  # 人工维护的前端逻辑；生成资源有单独来源
│   │   ├── components/  # 可复用展示能力；不访问页面私有 Store
│   │   │   ├── auth/  # 身份入口与页面保护；服务端仍执行真实权限
│   │   │   │   ├── AccountMenu.tsx  # 当前身份和账号操作菜单；认证仍由服务端确认
│   │   │   │   ├── AuthBoundary.test.tsx  # AuthBoundary 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   └── AuthBoundary.tsx  # 页面身份与访问分支；不替代服务端权限检查
│   │   │   ├── avatars/  # 稳定头像选择与加载；后端只引用标识
│   │   │   │   ├── svg/  # 生成的角色组件；从同源成品再生成
│   │   │   │   │   ├── admin-bull.tsx  # 角色成品或生成组件 admin-bull.tsx；与头像清单同源，不在架构重构中重做素材
│   │   │   │   │   ├── backend-horse.tsx  # 角色成品或生成组件 backend-horse.tsx；与头像清单同源，不在架构重构中重做素材
│   │   │   │   │   ├── designer-bull.tsx  # 角色成品或生成组件 designer-bull.tsx；与头像清单同源，不在架构重构中重做素材
│   │   │   │   │   ├── finance-bull.tsx  # 角色成品或生成组件 finance-bull.tsx；与头像清单同源，不在架构重构中重做素材
│   │   │   │   │   ├── frame.tsx  # SVG 实例标识与外框适配；多个头像并存时避免内部 ID 冲突
│   │   │   │   │   ├── frontend-bull.tsx  # 角色成品或生成组件 frontend-bull.tsx；与头像清单同源，不在架构重构中重做素材
│   │   │   │   │   ├── index.tsx  # 各角色生成组件的导出清单；与资源 catalog 和懒加载入口一致
│   │   │   │   │   ├── intern-bull.tsx  # 角色成品或生成组件 intern-bull.tsx；与头像清单同源，不在架构重构中重做素材
│   │   │   │   │   ├── knowledge-bull.tsx  # 角色成品或生成组件 knowledge-bull.tsx；与头像清单同源，不在架构重构中重做素材
│   │   │   │   │   ├── operations-bull.tsx  # 角色成品或生成组件 operations-bull.tsx；与头像清单同源，不在架构重构中重做素材
│   │   │   │   │   ├── package.json  # 生成组件的工具及类型配置；遵循资源生成边界
│   │   │   │   │   ├── product-horse.tsx  # 角色成品或生成组件 product-horse.tsx；与头像清单同源，不在架构重构中重做素材
│   │   │   │   │   ├── programmer-horse.tsx  # 角色成品或生成组件 programmer-horse.tsx；与头像清单同源，不在架构重构中重做素材
│   │   │   │   │   ├── research-horse.tsx  # 角色成品或生成组件 research-horse.tsx；与头像清单同源，不在架构重构中重做素材
│   │   │   │   │   ├── support-horse.tsx  # 角色成品或生成组件 support-horse.tsx；与头像清单同源，不在架构重构中重做素材
│   │   │   │   │   └── sysadmin-horse.tsx  # 角色成品或生成组件 sysadmin-horse.tsx；与头像清单同源，不在架构重构中重做素材
│   │   │   │   ├── AgentAvatar.tsx  # 员工头像统一展示；不把角色外观当作能力证明
│   │   │   │   ├── AvatarBadge.tsx  # 小尺寸头像和状态展示；样式不拥有业务状态
│   │   │   │   ├── AvatarPicker.tsx  # 头像选择表单；只保存稳定 avatar_id
│   │   │   │   ├── CHARACTERS.md  # 角色设定与形象依据；将制作语义与运行时选择分开
│   │   │   │   ├── LazySvgAvatar.tsx  # 头像资源延迟加载；避免首屏加载全部角色
│   │   │   │   ├── README.md  # 头像公共接口、生成来源与维护入口；消费者不依赖角色私有实现
│   │   │   │   ├── assets.test.ts  # assets 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   ├── index.ts  # 头像能力公共导出；业务与样板从稳定入口使用
│   │   │   │   ├── svgAvatar.test.ts  # svgAvatar 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   └── svgAvatar.ts  # 头像类型和资源选择约定；页面不直接依赖生成文件细节
│   │   │   ├── brand/  # 品牌展示与源资源；不承担登录业务状态
│   │   │   │   ├── BrandLogo.tsx  # 品牌标志展示；统一读取生成成品
│   │   │   │   ├── brandLogoStyles.ts  # 所属页面或组件的样式与令牌；视觉职责就近维护而不侵入业务状态
│   │   │   │   ├── mark.svg  # 静态或图示资源 mark.svg；保留来源并按对应构建或文档流程维护
│   │   │   │   └── wordmarkSource.ts  # 品牌 SVG 原始字符串及固定 ID；登录动画与构建脚本共用同一来源
│   │   │   ├── common/  # 跨业务展示与布局；专用组件仍留页面
│   │   │   │   ├── EmptyState.tsx  # 空数据和无结果展示；不掩盖加载或错误状态
│   │   │   │   ├── Markdown.tsx  # 安全 Markdown 正文展示；不解析 SDK 或执行文本指令
│   │   │   │   ├── PageBreadcrumb.tsx  # 来源与位置导航；不决定后台执行目标
│   │   │   │   ├── PageHeading.tsx  # 页面标题和说明；展示与业务命令分开
│   │   │   │   ├── PageToolbar.tsx  # 共享页头插槽与操作布局；各页注入自己的交互
│   │   │   │   ├── ResourcePagination.tsx  # URL 列表分页与刷新交互；不限定为配置编辑
│   │   │   │   ├── SearchInput.tsx  # 共享搜索输入交互；由调用页决定实际查询
│   │   │   │   └── pageHeadingStyles.ts  # 所属页面或组件的样式与令牌；视觉职责就近维护而不侵入业务状态
│   │   │   ├── configuration/  # 实际复用的加载、冲突与草稿提示；具体资源读取由页面提供
│   │   │   │   ├── ConfigurationConflict.tsx  # 版本冲突查看和采用最新修订交互；资源读取与字段展示由页面提供
│   │   │   │   ├── ResourceStatus.tsx  # 由 ready、error、onReload 驱动的加载反馈；不依赖全局配置 Context
│   │   │   │   └── StaleDraftNotice.tsx  # 过期草稿提示；避免用旧表单覆盖新修订
│   │   │   ├── navigation/  # 外壳导航、搜索与收藏；专用网络和状态不进入通用控件
│   │   │   │   ├── FavoriteAgentLink.tsx  # 收藏员工导航链接；外壳与设计样板共用，不属于员工配置
│   │   │   │   ├── GlobalSearch.tsx  # 全局搜索弹窗、输入和跨资源结果；从外壳收回完整搜索交互
│   │   │   │   ├── navigationFlow.test.tsx  # 导航摘要刷新与搜索迟到结果隔离；不依赖全局资源仓库
│   │   │   │   └── useNavigationSummary.ts  # 外壳计数与有界收藏读取；写入或身份变化后刷新，忽略旧结果
│   │   │   ├── organization-rules/  # 规则管理和继承展示；正文由后端统一维护
│   │   │   │   ├── InheritedRules.tsx  # 员工继承规则展示；不创建一份独立规则副本
│   │   │   │   └── useOrganizationRules.ts  # 规则读取、编辑和冲突反馈；复用配置生命周期
│   │   │   ├── skills/  # 方法卡片和当前CI接入展示；通用工具管理未实现
│   │   │   │   ├── GithubCiSetup.tsx  # CI 方法安装及连接配置展示；技能库和员工装配实际共用
│   │   │   │   ├── SkillCard.tsx  # 方法摘要卡片；展示资产与员工装配分开
│   │   │   │   ├── SkillCollection.tsx  # 方法集合展示与入口；不隐式激活运行能力
│   │   │   │   ├── githubCiSetupStyles.ts  # CI 安装配置展示样式；随组件职责改名，保持现有视觉
│   │   │   │   ├── skillCardStyles.ts  # 所属页面或组件的样式与令牌；视觉职责就近维护而不侵入业务状态
│   │   │   │   └── skillCollectionStyles.ts  # 所属页面或组件的样式与令牌；视觉职责就近维护而不侵入业务状态
│   │   │   ├── theme/  # 主题切换及图案；不依赖工作会话数据
│   │   │   │   ├── ThemeArtwork.tsx  # 主题相关装饰资源；与业务数据和身份无关
│   │   │   │   ├── ThemeSwitcher.test.tsx  # ThemeSwitcher 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   └── ThemeSwitcher.tsx  # 主题切换入口；复用统一偏好和首屏约定
│   │   │   └── ui/  # 基础 UI 控件；不包含业务授权或调度
│   │   │       ├── Badge.tsx  # 徽标基础能力；通过统一控件复用且不绑定业务状态
│   │   │       ├── Bubble.tsx  # 气泡基础能力；通过统一控件复用且不绑定业务状态
│   │   │       ├── Button.tsx  # 按钮基础能力；通过统一控件复用且不绑定业务状态
│   │   │       ├── Collapsible.tsx  # 折叠基础能力；通过统一控件复用且不绑定业务状态
│   │   │       ├── Dialog.tsx  # 对话框基础能力；通过统一控件复用且不绑定业务状态
│   │   │       ├── DropdownMenu.tsx  # 菜单基础能力；通过统一控件复用且不绑定业务状态
│   │   │       ├── Field.tsx  # 字段基础能力；通过统一控件复用且不绑定业务状态
│   │   │       ├── Form.tsx  # 表单基础能力；通过统一控件复用且不绑定业务状态
│   │   │       ├── Input.tsx  # 输入基础能力；通过统一控件复用且不绑定业务状态
│   │   │       ├── InputGroup.tsx  # 输入组基础能力；通过统一控件复用且不绑定业务状态
│   │   │       ├── LICENSE  # 复用 UI 的第三方许可；保留版权与使用依据
│   │   │       ├── Message.tsx  # 消息展示基础能力；通过统一控件复用且不绑定业务状态
│   │   │       ├── MessageScroller.tsx  # 消息滚动基础能力；通过统一控件复用且不绑定业务状态
│   │   │       ├── Select.tsx  # 选择基础能力；通过统一控件复用且不绑定业务状态
│   │   │       ├── Switch.tsx  # 开关基础能力；通过统一控件复用且不绑定业务状态
│   │   │       ├── Tabs.tsx  # 页签基础能力；通过统一控件复用且不绑定业务状态
│   │   │       ├── Textarea.tsx  # 多行输入基础能力；通过统一控件复用且不绑定业务状态
│   │   │       ├── Tooltip.tsx  # 提示基础能力；通过统一控件复用且不绑定业务状态
│   │   │       ├── Trace.tsx  # 执行过程展示基础能力；通过统一控件复用且不绑定业务状态
│   │   │       └── styledProps.ts  # 共享样式属性约定；过滤展示属性而不污染DOM
│   │   ├── design-system/  # 视觉令牌与组件规范；本重构保持现有视觉契约
│   │   │   ├── README.md  # 主题、组件与视觉工程入口；正式业务引用统一设计规则
│   │   │   ├── colors.md  # 颜色语义与使用规范；数值由主题令牌维护
│   │   │   ├── components.md  # 组件尺寸、状态与组合约定；与真实组件和样板核对
│   │   │   ├── spec.ts  # 可由工具检查的视觉规格；与组件和样板共享依据
│   │   │   ├── theme.css  # 主题颜色、字号和间距令牌；首屏、组件与生成品牌同源
│   │   │   ├── themeValues.test.ts  # themeValues 的行为回归；随职责改名并保持边界覆盖
│   │   │   ├── themeValues.ts  # 读取和转换主题令牌；不重复硬编码 CSS 数值
│   │   │   └── tokenContract.test.ts  # tokenContract 的行为回归；随职责改名并保持边界覆盖
│   │   ├── hooks/  # 真实跨业务 Hook；页面专用 Hook 留在页面模块
│   │   │   ├── useDraft.ts  # 非秘密表单草稿生命周期；不同业务使用自己的存储结构
│   │   │   └── useQueryState.ts  # URL 参数读写与显式重置选项；具体查询联动由调用页面声明
│   │   ├── lib/  # 接口、共享数据和普通函数；不反向导入页面或 Context
│   │   │   ├── api/  # 面向用户操作的公开HTTP契约；不按后端实体强制拆分
│   │   │   │   ├── agents.test.ts  # agents 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   ├── agents.ts  # 员工摘要、详情、编辑与公开读取 DTO；列表不伪造完整配置
│   │   │   │   ├── ciDiagnosis.ts  # 专业阶段、报告与反馈 HTTP 契约；按回复和专业版本读取
│   │   │   │   ├── conversationTransport.ts  # 可注入的对话网络能力；控制器可隔离测试且不读取路由
│   │   │   │   ├── conversations.test.ts  # conversations 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   ├── conversations.ts  # 对话、消息和回复用户操作契约；不镜像内部 Run 与 SDK 结构
│   │   │   │   ├── http.ts  # Cookie、响应及错误的共用传输；不包含业务状态机
│   │   │   │   ├── modelConnections.test.ts  # modelConnections 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   ├── modelConnections.ts  # 连接配置与显式检查；全量读取分页循环仅供本文件使用
│   │   │   │   ├── navigation.ts  # 导航计数、收藏和跨资源搜索请求；按前端使用场景组合现有端点
│   │   │   │   ├── organizationRules.test.ts  # organizationRules 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   ├── organizationRules.ts  # 公司规章制度 HTTP 契约；正文和修订统一读取
│   │   │   │   ├── skills.test.ts  # 方法客户端白名单、详情和写入回归；从混合配置测试归位
│   │   │   │   └── skills.ts  # 方法管理及公开读取 DTO 与映射；不从员工客户端借类型
│   │   │   ├── avatars/  # 头像清单和注册；生成来源与消费关系可追踪
│   │   │   │   ├── manifest.generated.ts  # 构建生成的头像元数据；从同源资源再生成而不手改
│   │   │   │   └── registry.ts  # 头像注册及加载关系；业务只保存稳定 avatar_id
│   │   │   ├── models/  # 共享员工及技能展示模型；不从页面私有类型导出
│   │   │   │   ├── agent.ts  # 员工摘要、完整详情和编辑输入类型；在同文件区分，避免假空正文
│   │   │   │   ├── agentAvailability.ts  # 员工展示可用性计算；服务端仍决定实际执行资格
│   │   │   │   └── skill.ts  # 共享方法展示模型；资产信息与运行激活分开
│   │   │   ├── brand.ts  # 品牌成品与尺寸约定；消费端不重复拼装资源路径
│   │   │   ├── draft.test.ts  # draft 的行为回归；随职责改名并保持边界覆盖
│   │   │   ├── draft.ts  # 通用非秘密草稿保存；配置与输入各有自己的 schema
│   │   │   ├── identity.test.ts  # identity 的行为回归；随职责改名并保持边界覆盖
│   │   │   ├── identity.ts  # 当前身份、隔离键和变更通知；返回位置统一归导航
│   │   │   ├── navigation.test.ts  # 来源、安全返回和规则定位回归；导航规则只维护一处
│   │   │   ├── navigation.ts  # 来源、安全返回与规则位置；不猜测编辑器草稿键
│   │   │   ├── utils.test.ts  # utils 的行为回归；随职责改名并保持边界覆盖
│   │   │   └── utils.ts  # 通用类名等纯工具；不包含业务状态或网络
│   │   ├── pages/  # 按页面业务组织；专用逻辑就近维护
│   │   │   ├── agents/  # 员工目录、配置与工作入口；草稿和服务器修订分开
│   │   │   │   ├── AgentCard.tsx  # 员工身份、能力摘要与工作入口；卡片不组织后台执行
│   │   │   │   ├── AgentConfiguration.tsx  # 员工配置表单与保存协作；修订冲突和草稿留在配置交互
│   │   │   │   ├── AgentDeletionDialog.tsx  # 员工删除确认与依赖反馈；真实删除规则仍在后端
│   │   │   │   ├── AgentDirectory.tsx  # 员工目录筛选与分页；不等待对话运行状态
│   │   │   │   ├── AgentModelConnectionField.tsx  # 员工模型装配选择；展示可用连接而不接触凭证
│   │   │   │   ├── AgentsPage.tsx  # 员工页面和导航组合；配置与对话入口各自保留生命周期
│   │   │   │   ├── README.md  # 员工目录、配置和装配的维护入口；链接共享契约而不复制字段
│   │   │   │   ├── SkillAssignmentConfiguration.tsx  # 员工方法装配参数；整体保存与服务端校验一致
│   │   │   │   ├── agentCardStyles.ts  # 所属页面或组件的样式与令牌；视觉职责就近维护而不侵入业务状态
│   │   │   │   ├── agentPresentation.test.ts  # agentPresentation 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   ├── agentPresentation.ts  # 员工展示字段整理；不把缺失配置伪装成可执行
│   │   │   │   ├── agentSearch.test.ts  # agentSearch 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   ├── agentSearch.ts  # 员工目录的搜索匹配；页面筛选规则集中维护
│   │   │   │   ├── availability.test.ts  # availability 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   ├── configurationFlow.test.tsx  # 目录和详情切换、过期读取与完整配置保存；防止摘要覆盖正文
│   │   │   │   ├── index.ts  # 员工卡片与展示转换的公共入口；设计样板不导入页面私有状态
│   │   │   │   ├── publicAgentPresentation.test.ts  # publicAgentPresentation 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   ├── types.ts  # 所属模块共享展示类型；避免从组件内部反向导出
│   │   │   │   ├── useAgentDirectory.ts  # 员工目录条件、分页、启停收藏与局部错误；不加载编辑全文
│   │   │   │   └── useAgentEditor.ts  # 单个员工详情、保存删除和方法选择读取；只接受完整编辑数据
│   │   │   ├── avatars/  # 所属专题或资源的内部组织；就近维护并避免跨模块私有依赖
│   │   │   │   ├── AvatarGalleryPage.tsx  # 正式角色图鉴与选择展示；复用同一头像清单和加载能力
│   │   │   │   └── svgGalleryStyles.ts  # 所属页面或组件的样式与令牌；视觉职责就近维护而不侵入业务状态
│   │   │   ├── brains/  # 模型连接管理；秘密不保存在浏览器草稿
│   │   │   │   ├── BrainWorkspace.tsx  # 连接目录、检查与编辑表单；密钥仅留表单内存，使用统一离开保护
│   │   │   │   └── BrainsPage.tsx  # 模型连接页入口与权限反馈；页面不代替后端检查
│   │   │   ├── conversations/  # 输入、回复与历史页面；按用户交互和对话作用域组织
│   │   │   │   ├── CiReport.tsx  # 专业阶段、来源、报告和反馈；按 CI 版本读取而非每次文字更新
│   │   │   │   ├── ConversationComposer.tsx  # 输入、方法选择和提交交互；网络由对话控制器管理
│   │   │   │   ├── ConversationControls.tsx  # 当前回复停止重试等控件；操作绑定准确回复ID
│   │   │   │   ├── ConversationHistory.test.tsx  # ConversationHistory 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   ├── ConversationHistory.tsx  # 历史入口和阅读状态展示；不自行重复建立订阅
│   │   │   │   ├── ConversationMessage.tsx  # 用户内容或助手回复行；组合状态过程与专业报告
│   │   │   │   ├── ConversationOutline.test.tsx  # ConversationOutline 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   ├── ConversationOutline.tsx  # 问题目录接入与正文定位；展示组件不绑定网络实现
│   │   │   │   ├── ConversationPanel.test.tsx  # ConversationPanel 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   ├── ConversationPanel.tsx  # 对话页面组合与滚动协作；不复制一套执行生命周期
│   │   │   │   ├── ConversationProvider.tsx  # 身份和对话作用域；切换销毁读取观察而不停止后台
│   │   │   │   ├── ConversationQuestionPreview.test.tsx  # ConversationQuestionPreview 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   ├── ConversationQuestionPreview.tsx  # 提问短预览展示；来源是专用预览接口
│   │   │   │   ├── ConversationRuler.test.tsx  # ConversationRuler 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   ├── ConversationRuler.tsx  # 问题刻度、触摸键盘和定位反馈；编号来自真实用户提问
│   │   │   │   ├── ConversationsPage.test.tsx  # ConversationsPage 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   ├── ConversationsPage.tsx  # 对话列表与路由入口；新对话先保留本地草稿
│   │   │   │   ├── README.md  # 工作会话的局部交互；专用职责留在本模块，不制造全局状态
│   │   │   │   ├── RunActions.test.tsx  # RunActions 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   ├── RunActions.tsx  # 回复的真实过程展示与本地分页；不负责执行调度
│   │   │   │   ├── actionPagination.ts  # 已加载过程的本地分页；展开步骤不额外发请求
│   │   │   │   ├── conversationContext.ts  # 稳定实例上下文；共享作用域而不广播每次正文变化
│   │   │   │   ├── conversationDraft.ts  # 未提交输入草稿与匹配清理；不能覆盖已发出待确认命令
│   │   │   │   ├── conversationScope.test.ts  # 对话和回复各自版本合并；迟到接受或读取不能回退当前活动目标
│   │   │   │   ├── conversationState.ts  # 纯状态合并及操作资格；不再解释模型轮和工具请求
│   │   │   │   ├── conversationStore.ts  # 按作用域版本和回复版本合并并提供稳定快照；避免串写与重复渲染
│   │   │   │   ├── conversationTestHelpers.ts  # 对话接口与组件测试替身；只表达公开交互事实
│   │   │   │   ├── pendingSubmissionStorage.ts  # 未知提交的固定键、输入和停止意图；区别于未发送草稿
│   │   │   │   ├── questionNavigation.ts  # 目录数据源和浏览状态类型；目录与正文窗口分开
│   │   │   │   ├── useConversation.ts  # 对话级输入、摘要与历史入口；保留真实用户交互边界
│   │   │   │   ├── useConversationController.test.tsx  # useConversationController 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   ├── useConversationController.ts  # 对话命令、确认、观察与作用域副作用；一实例一控制器
│   │   │   │   ├── useConversationHistory.test.tsx  # useConversationHistory 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   ├── useConversationHistory.ts  # 最新与历史连续窗口；保留阅读锚点并拒绝迟到请求
│   │   │   │   ├── useMessage.test.tsx  # useMessage 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   ├── useMessage.ts  # 按行读取正文、状态、过程与操作；不强制对齐后端实体字段
│   │   │   │   ├── useQuestionNavigation.ts  # 目录分页锚点与有界缓存；不下载完整对话
│   │   │   │   ├── useQuestionPreview.ts  # 预览加载与目标隔离；迟到结果不能覆盖新问题
│   │   │   │   └── useResponseSubscription.ts  # 观察指定回复并只读恢复；消息组件不各自建连接
│   │   │   ├── design-system/  # 真实组件展示；正式业务不依赖演示数据
│   │   │   │   ├── fixtures/  # 设计展示示例数据；不冒充业务记录
│   │   │   │   │   └── agents.ts  # 员工设计样板数据；明确为展示 fixture，不进入业务保存
│   │   │   │   ├── ColorCatalog.tsx  # 主题颜色与语义色示例；直接核对设计令牌
│   │   │   │   ├── ComponentExamples.tsx  # 基础控件真实交互样例；复用正式 UI 入口
│   │   │   │   ├── DesignSystemPage.tsx  # 设计展示页签与样例组合；与生产业务状态隔离
│   │   │   │   ├── PatternExamples.tsx  # 员工和对话等组合样板；通过允许的公共组件入口展示
│   │   │   │   ├── TypographyCatalog.tsx  # 字号、行高与文字层级示例；遵守统一排版令牌
│   │   │   │   ├── previewStyles.ts  # 所属页面或组件的样式与令牌；视觉职责就近维护而不侵入业务状态
│   │   │   │   └── useThemeValues.ts  # 设计展示读取当前 CSS 变量；不再维护一套主题值
│   │   │   ├── help/  # 用户操作帮助；功能与新路由命名同步
│   │   │   │   ├── HelpPage.tsx  # 帮助导航与指南组合；按已生效用户操作提供说明
│   │   │   │   ├── guideStyles.ts  # 所属页面或组件的样式与令牌；视觉职责就近维护而不侵入业务状态
│   │   │   │   └── guides.ts  # 各能力帮助内容；实施行为变化后同步，目标建议不写成当前功能
│   │   │   ├── knowledge/  # 当前教学资料和规则入口；真实检索另按业务增量接入
│   │   │   │   ├── KnowledgeLibrary.tsx  # 教学资料筛选、查看和下载；不伪装成已接入在线知识检索
│   │   │   │   ├── KnowledgePage.tsx  # 资料与规则页签组合；规则编辑按自身区域注册离开保护
│   │   │   │   ├── OrganizationRulesEditor.tsx  # 知识页面专用规则编辑；共享继承展示仍在公共组件
│   │   │   │   ├── README.md  # 知识页面、教学资料和规则编辑入口；区分当前展示与后续检索
│   │   │   │   └── teachingDocuments.ts  # 教学资料目录与元数据；来自明确示例而非隐式模型上下文
│   │   │   ├── signin/  # 登录表单与视觉；不依赖工作会话状态
│   │   │   │   ├── motion/  # 登录场景动画模型与控制；视觉运行与认证请求分开
│   │   │   │   │   ├── controller.ts  # 登录动画时钟、场景 DOM 和关闭清理；认证操作不依赖动画结束
│   │   │   │   │   └── model.ts  # 品牌字形状态、接触计算与 SVG 绑定；统一控制完整场景而不按字母拆文件
│   │   │   │   ├── SigninPage.tsx  # 身份入口、登录表单和品牌场景组合；品牌源稿从共享品牌能力读取
│   │   │   │   ├── formState.test.ts  # formState 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   ├── formState.ts  # 凭证必填检查和登录失败反馈；错误信息不暴露服务端内部细节
│   │   │   │   ├── geometry.ts  # 登录场景响应尺寸计算；只处理几何，不读取主题或认证状态
│   │   │   │   ├── layoutConfig.ts  # 登录场景尺寸约束；与主题令牌分开，避免视觉参数散落
│   │   │   │   ├── signinStyles.ts  # 所属页面或组件的样式与令牌；视觉职责就近维护而不侵入业务状态
│   │   │   │   ├── useSigninForm.test.ts  # useSigninForm 的行为回归；随职责改名并保持边界覆盖
│   │   │   │   ├── useSigninForm.ts  # 凭证、游客与 GitHub 登录交互；完成后刷新真实身份
│   │   │   │   └── useSigninScene.ts  # 登录场景尺寸与动态加载生命周期；处理减少动态效果和页面隐藏
│   │   │   └── skills/  # 方法管理页面；工具许可不伪装为方法正文
│   │   │       ├── SkillEditor.tsx  # 方法正文、参数规范和修订编辑；具体草稿清理注册给外壳
│   │   │       ├── SkillsPage.tsx  # 方法目录与编辑路由组合；各视图调用自己的读取 Hook
│   │   │       ├── configurationFlow.test.tsx  # 目录展开、安装刷新、编辑保存与身份切换；验证页面状态归位
│   │   │       ├── useSkillDirectory.ts  # 方法列表、展开、安装刷新及删除；状态随目录查询变化
│   │   │       └── useSkillEditor.ts  # 指定方法详情、保存和冲突；与目录加载分别取消
│   │   ├── state/  # 身份、编辑保护、主题和轻量更新通知；资源内容保留页面所有权
│   │   │   ├── auth/  # 当前身份及变更；销毁旧用户作用域
│   │   │   │   ├── IdentityProvider.tsx  # 当前身份实例与变化通知；切换后销毁旧业务作用域
│   │   │   │   ├── identityContext.ts  # 稳定身份上下文；认证网络操作集中组织
│   │   │   │   └── useIdentity.ts  # 身份共享读取入口；不由客户端推断登录成功
│   │   │   ├── configuration/  # 配置写入失效通知；不建立资源总仓库或路由解析器
│   │   │   │   └── useConfigurationInvalidation.ts  # 配置写入后的版本通知与小 Context；不保存资源列表、路由和编辑状态
│   │   │   ├── editing/  # 未保存修改与导航保护；不与服务端执行状态混合
│   │   │   │   ├── useEditing.test.tsx  # 编辑注册撤销、放弃回调和同步保存门闩；防止离开误清草稿
│   │   │   │   └── useEditing.ts  # 编辑区注册、脏状态、同步保存门闩和放弃回调；不识别员工或技能键
│   │   │   └── theme/  # 主题持久偏好与控制；首屏和 React 共用约定
│   │   │       ├── themeAssets.test.ts  # themeAssets 的行为回归；随职责改名并保持边界覆盖
│   │   │       ├── themeController.test.ts  # themeController 的行为回归；随职责改名并保持边界覆盖
│   │   │       ├── themeController.ts  # 主题偏好与系统变化协调；首屏与 React 保持一致
│   │   │       └── useTheme.ts  # 组件读取和切换主题；不重复保存主题状态
│   │   ├── Layout.tsx  # 工作台路由导航与唯一离开保护；不保存页面资源或拼接草稿键
│   │   ├── globals.css  # 共享基础样式入口；业务样式遵循既有设计令牌
│   │   ├── main.tsx  # 浏览器与 React 启动；只装配路由和全局能力
│   │   └── router.tsx  # 显式页面路由、权限与懒加载；命名切换与深链一处维护
│   ├── .env.example  # 部署参数示例；只提供占位值而不保存真实秘密
│   ├── .prettierignore  # 生成物与格式检查范围；保留来源检查而不手改构建产物
│   ├── AGENTS.md  # 端内协作导航；规则正文集中在工程与契约文档
│   ├── README.md  # 所属模块入口、职责与验证导航；详细规则只维护一份
│   ├── THIRD_PARTY_NOTICES.md  # 第三方来源和许可说明；保留合法使用与维护依据
│   ├── eslint.config.mjs  # 命名、导入和 React 静态规则；可判定约束交给工具
│   ├── eslint.config.test.ts  # 静态规则本身的回归；防止边界检查配置悄悄失效
│   ├── index.html  # 浏览器 HTML 与首屏主题入口；主题不等待 React 才初始化
│   ├── package.json  # 依赖、命令与检查清单；与锁文件同步维护
│   ├── pnpm-lock.yaml  # 依赖精确锁定；使环境与构建可复现
│   ├── pnpm-workspace.yaml  # 依赖、命令与检查清单；与锁文件同步维护
│   ├── themeBootstrap.test.ts  # 首屏主题及内联脚本验证；防止业务重构引入主题闪动
│   ├── tsconfig.json  # TypeScript 类型和路径约定；前端契约在构建前检查
│   ├── vite.config.ts  # 开发 API/SSE 代理和生产构建；保留来源及流式传输语义
│   └── vitest.config.ts  # 前端测试环境与运行配置；组件和状态可隔离验证
├── scripts/  # 跨端开发和文档工具；由根 Makefile 统一调用
│   ├── tests/  # 工具行为回归；验证端口、退出和文档错误
│   │   ├── fake_services.py  # fake_services的隔离回归；保留拒绝、故障与竞争断言
│   │   ├── test_check_docs.py  # 本地文档链接、锚点与索引错误的隔离回归；保留拒绝、故障与竞争断言
│   │   └── test_dev.py  # 端口协同、代理和子进程退出的隔离回归；保留拒绝、故障与竞争断言
│   ├── README.md  # 所属模块入口、职责与验证导航；详细规则只维护一份
│   ├── check_docs.py  # 本地链接、锚点与索引检查；现行文档与方案可可靠导航
│   └── dev.py  # 前后端端口协同与子进程清理；业务重命名不改变开发生命周期
├── .gitignore  # 依赖、缓存和运行数据排除；防止环境及秘密进入工程
├── AGENTS.md  # 项目协作入口；只导航现行约束而不复制所有规则
├── Makefile  # 统一开发、检查、构建和维护命令；避免各端操作漂移
└── README.md  # 项目定位与启动入口；通过文档索引进入详细契约
```

## 完整目标文档树

本树包含全部现有 docs，生效规则已合入现行正文。历史 records 保留当时名称和检查数量，不把旧建议改成新事实。分层图及图源与本轮职责调整同步维护，具体数据与接口约束仍以专题正文为准。

```text
niuma-crew/  # 实际工程根目录；模块化单体与前端独立构建，按职责协作
└── docs/  # 项目级文档；现行规则、目标方案与历史证据分开
    ├── architecture/  # 实施后的系统协作；目标方案未落地前不改成当前事实
    │   ├── diagrams/  # 当前架构图和源；实现时与正文同步更新
    │   │   ├── backend-current.svg  # 静态或图示资源 backend-current.svg；保留来源并按对应构建或文档流程维护
    │   │   ├── build-backend-views.py  # 对应文档图示的可编辑生成源；改变设计后同步再生成
    │   │   └── diagram_paths.py  # 对应文档图示的可编辑生成源；改变设计后同步再生成
    │   ├── agent-runtime.md  # 实施后解释 SDK 与宿主协作；取舍与控制边界有稳定维护位置
    │   ├── backend.md  # 后端架构；按现行规则或导航维护，防止目标与当前实现混淆
    │   ├── domain-glossary.md  # 当前领域术语；按现行规则或导航维护，防止目标与当前实现混淆
    │   ├── frontend.md  # 前端架构；按现行规则或导航维护，防止目标与当前实现混淆
    │   └── overview.md  # 平台架构；按现行规则或导航维护，防止目标与当前实现混淆
    ├── engineering/  # 各端可执行工程标准；不累计实施流水账
    │   ├── backend.md  # 后端工程手册；按现行规则或导航维护，防止目标与当前实现混淆
    │   ├── frontend.md  # 前端工程手册；按现行规则或导航维护，防止目标与当前实现混淆
    │   └── shared.md  # 共享工程约定；按现行规则或导航维护，防止目标与当前实现混淆
    ├── guides/  # 开发、配置、迁移和资源操作；明确前提与恢复
    │   ├── assets.md  # 应用资源与历史素材维护；按现行规则或导航维护，防止目标与当前实现混淆
    │   ├── backend-operations.md  # 后端运行、配置与维护；按现行规则或导航维护，防止目标与当前实现混淆
    │   ├── database-configuration.md  # 数据库连接与本地文件配置；按现行规则或导航维护，防止目标与当前实现混淆
    │   └── local-development.md  # 本地开发与统一命令入口；按现行规则或导航维护，防止目标与当前实现混淆
    ├── learning/  # 学习路线和代码阅读；不替代正式行为契约
    │   ├── observing-runtime.md  # 从页面到后台和数据的渐进观测；用具体操作理解机制
    │   ├── reading-code.md  # 按运行链路阅读代码；按现行规则或导航维护，防止目标与当前实现混淆
    │   └── roadmap.md  # 智能应用开发学习路线；按现行规则或导航维护，防止目标与当前实现混淆
    ├── proposals/  # 尚未实施的增量与已实现方案来源；状态以正文为准
    │   ├── agent-capabilities/  # 所属专题增量及图示；状态以方案正文为准，实施后回写现行契约
    │   │   ├── diagrams/  # 所属专题增量及图示；状态以方案正文为准，实施后回写现行契约
    │   │   │   ├── agent-capability-model.svg  # 静态或图示资源 agent-capability-model.svg；保留来源并按对应构建或文档流程维护
    │   │   │   └── agent-capability-model@2x.png  # 静态或图示资源 agent-capability-model@2x.png；保留来源并按对应构建或文档流程维护
    │   │   ├── README.md  # 数字员工目标数据模型；按增量方案维护，防止目标与当前实现混淆
    │   │   ├── data.md  # 能力资源目标字段与约束草案；按增量方案维护，防止目标与当前实现混淆
    │   │   ├── migration.md  # 能力后续阶段迁移与验收计划；按增量方案维护，防止目标与当前实现混淆
    │   │   └── runtime.md  # 数字员工运行与读取契约；按增量方案维护，防止目标与当前实现混淆
    │   ├── agent-workspace/  # 所属专题增量及图示；状态以方案正文为准，实施后回写现行契约
    │   │   ├── README.md  # 员工工作页与任务执行的分阶段改造；按增量方案维护，防止目标与当前实现混淆
    │   │   ├── runtime.md  # 执行内核、持久等待与自动交办；按增量方案维护，防止目标与当前实现混淆
    │   │   └── tasks.md  # 任务、成果与接口增量；按增量方案维护，防止目标与当前实现混淆
    │   ├── backend-architecture/  # 所属专题增量及图示；状态以方案正文为准，实施后回写现行契约
    │   │   ├── diagrams/  # 所属专题增量及图示；状态以方案正文为准，实施后回写现行契约
    │   │   │   └── backend-modules.svg  # 静态或图示资源 backend-modules.svg；保留来源并按对应构建或文档流程维护
    │   │   ├── README.md  # 后端领域与执行架构重设计；按增量方案维护，防止目标与当前实现混淆
    │   │   └── execution.md  # 执行对象、事务与生命周期；按增量方案维护，防止目标与当前实现混淆
    │   ├── knowledge-assistant/  # 所属专题增量及图示；状态以方案正文为准，实施后回写现行契约
    │   │   ├── README.md  # 项目知识助手最小闭环；按增量方案维护，防止目标与当前实现混淆
    │   │   ├── access.md  # P1 与后续阶段；按增量方案维护，防止目标与当前实现混淆
    │   │   └── plan.md  # 知识助手首个学习迭代与开发任务；按增量方案维护，防止目标与当前实现混淆
    │   ├── platform-refactor/  # 本次统一目标设计；替代旧方案的后续边界和命名
    │   │   ├── diagrams/  # 本次目标图与源；明确未实施而不覆盖当前图
    │   │   │   ├── build-diagrams.py  # 新版目标图的可编辑源；图与正文同步
    │   │   │   ├── build-layered-diagrams.py  # 并行整理的分层图源，本轮保留；与专题共同核对职责和含义
    │   │   │   ├── layered-01-overview.svg  # 并行整理的总体图，本轮未重画；与新版专题共同核对职责
    │   │   │   ├── layered-02-frontend.svg  # 并行整理的前端图，本轮未重画；与新版 Hook 边界分别核对
    │   │   │   ├── layered-03-backend.svg  # 并行整理的后端图，本轮未重画；不由生成树推断已经实施
    │   │   │   ├── layered-04-execution.svg  # 并行整理的执行图，本轮未重画；与新版运行协议分别核对
    │   │   │   ├── request-lifecycle.svg  # 新版发送到发布时序；区分事务和外部等待
    │   │   │   └── target-boundaries.svg  # 新版模块与数据归属图；帮助区分模块和实体
    │   │   ├── README.md  # 总方案结论、实例和导航；先建立整体再进入细节
    │   │   ├── api.md  # 面向用户操作的接口；公开路径不镜像内部模块
    │   │   ├── build-target-tree.py  # 生成树和完整映射；从同一来源核对结构
    │   │   ├── decisions.md  # 逐项追问与替代方案；说明抽象的真实必要性
    │   │   ├── domain.md  # 内容、处理、关联与专业数据；从事实区分身份和状态
    │   │   ├── extensions.md  # 未来能力的接入条件；不提前预建完整空文件树
    │   │   ├── file-map.md  # 每个重写前文件去向；避免只规划主链遗漏外围
    │   │   ├── flows.md  # 端到端正常与异常流程；明确写入者、顺序和提交
    │   │   ├── frontend.md  # 页面、Hook和状态生命周期；按交互组织而非后端实体
    │   │   ├── inventory.json  # 重写前工程清单；使覆盖与新增文件可核对
    │   │   ├── layered-architecture.md  # 配套四张职责分层图解读；具体数据和接口由对应专题确定
    │   │   ├── migration.md  # 实施、数据搬迁与验收；保留正确行为并可核对回退
    │   │   ├── modules.md  # 全部后端模块职责与依赖；区分业务组织与执行管理
    │   │   ├── responsibility-review.md  # 全工程职责与引用复核；给出证据、目标归属、保留和不采纳项
    │   │   ├── runtime.md  # Agent 输入控制输出与恢复；防止 SDK 和存储互相渗透
    │   │   ├── service-boundaries.md  # API 请求服务、业务模块与共享回复流程；给出逐项归属、调用和事务依据
    │   │   └── target-tree.md  # 完整目标工程及文档树；每节点解释职责与原因
    │   ├── skills-and-mcp/  # 所属专题增量及图示；状态以方案正文为准，实施后回写现行契约
    │   │   ├── README.md  # 标准 Agent Skills 与通用 MCP 接入；按增量方案维护，防止目标与当前实现混淆
    │   │   └── ci-connection-migration.md  # CI 凭证迁移到工具连接；按增量方案维护，防止目标与当前实现混淆
    │   ├── README.md  # 待实施方案索引；按增量方案维护，防止目标与当前实现混淆
    │   ├── agent-model-rebuild.md  # Agent 模型与持久化基线重建；按增量方案维护，防止目标与当前实现混淆
    │   ├── agent-name-identity.md  # 员工名称唯一与运行身份；按增量方案维护，防止目标与当前实现混淆
    │   ├── conversation-execution-display.md  # 对话执行过程展示；按增量方案维护，防止目标与当前实现混淆
    │   ├── conversation-hooks.md  # 会话与消息访问边界；按增量方案维护，防止目标与当前实现混淆
    │   ├── conversation-layout.md  # 对话布局与历史读取增量；按增量方案维护，防止目标与当前实现混淆
    │   ├── conversation-message-state.md  # 对话消息与执行步骤统一读取；按增量方案维护，防止目标与当前实现混淆
    │   ├── conversation-state-management.md  # 对话状态与执行过程展示；按增量方案维护，防止目标与当前实现混淆
    │   ├── frontend-simplification.md  # 前端精简的待核对增量；按增量方案维护，防止目标与当前实现混淆
    │   ├── member-model-access.md  # 免费模型的后续方向（未实现）；按增量方案维护，防止目标与当前实现混淆
    │   ├── organization-rules.md  # 多份规则建议（待确认，未实现）；按增量方案维护，防止目标与当前实现混淆
    │   ├── platform-evolution.md  # 平台后续能力的接入边界；按增量方案维护，防止目标与当前实现混淆
    │   ├── product-validation.md  # 产品定位、差异化与企业收益验证；按增量方案维护，防止目标与当前实现混淆
    │   ├── research-assistant.md  # 研发研究员最小闭环；按增量方案维护，防止目标与当前实现混淆
    │   ├── runtime-configuration.md  # 运行配置集中管理；按增量方案维护，防止目标与当前实现混淆
    │   ├── runtime-refactoring.md  # runtime 重构与执行过程展示；按增量方案维护，防止目标与当前实现混淆
    │   ├── service-errors.md  # 应用错误分类整理；按增量方案维护，防止目标与当前实现混淆
    │   └── sqlite-checkpoint-chat.md  # SQLite checkpoint 聊天接入方案；按增量方案维护，防止目标与当前实现混淆
    ├── records/  # 限定时点的评审与验收；原始名称和通过数量保持历史含义
    │   ├── diagrams/  # 历史评审图；不作为当前架构前置
    │   │   └── dependency-review/  # 一次依赖研究的图与源；保留其证据时点
    │   │       ├── build-diagrams.py  # 对应文档图示的可编辑生成源；改变设计后同步再生成
    │   │       ├── current-dependencies.svg  # 静态或图示资源 current-dependencies.svg；保留来源并按对应构建或文档流程维护
    │   │       ├── proposed-boundaries.svg  # 静态或图示资源 proposed-boundaries.svg；保留来源并按对应构建或文档流程维护
    │   │       └── runtime-scheduling.svg  # 静态或图示资源 runtime-scheduling.svg；保留来源并按对应构建或文档流程维护
    │   ├── README.md  # 评审与验收记录索引；按历史证据维护，防止目标与当前实现混淆
    │   ├── agent-editor-validation.md  # 员工编辑与删除确认验收；按历史证据维护，防止目标与当前实现混淆
    │   ├── agent-model-rebuild.md  # Agent 模型基线重建验收；按历史证据维护，防止目标与当前实现混淆
    │   ├── agent-name-identity.md  # 员工名称唯一与运行身份验收；按历史证据维护，防止目标与当前实现混淆
    │   ├── agent-resource-summary.md  # 员工资源配置摘要：历史实施与验证；按历史证据维护，防止目标与当前实现混淆
    │   ├── agent-runtime-sdk-assessment.md  # Agent运行层SDK接入评估；按历史证据维护，防止目标与当前实现混淆
    │   ├── api-service-boundaries.md  # 本轮服务归属修订及文档检查；保留未实施状态和业务文件哈希证据
    │   ├── asset-isolation.md  # 应用与历史素材隔离；按历史证据维护，防止目标与当前实现混淆
    │   ├── auth-consolidation.md  # 身份与访问控制模块合并验收；按历史证据维护，防止目标与当前实现混淆
    │   ├── avatar-validation.md  # 静态头像历史验证；按历史证据维护，防止目标与当前实现混淆
    │   ├── backend-dependency-review.md  # 后端依赖与调度关系深度评审；按历史证据维护，防止目标与当前实现混淆
    │   ├── backend-file-responsibilities.md  # 后端文件职责第一轮整理验收；按历史证据维护，防止目标与当前实现混淆
    │   ├── brand-development.md  # 品牌候选、命名迁移与验收记录；按历史证据维护，防止目标与当前实现混淆
    │   ├── ci-diagnosis-review.md  # GitHub CI 诊断方案质询与价值评审；按历史证据维护，防止目标与当前实现混淆
    │   ├── client-routing.md  # 客户端路由迁移与专项复查；按历史证据维护，防止目标与当前实现混淆
    │   ├── component-visual-validation.md  # 组件视觉与状态：历史验收；按历史证据维护，防止目标与当前实现混淆
    │   ├── conversation-hooks.md  # 会话与消息双入口验收；按历史证据维护，防止目标与当前实现混淆
    │   ├── conversation-layout.md  # 对话布局与历史读取验收；按历史证据维护，防止目标与当前实现混淆
    │   ├── conversation-message-state.md  # 对话正文与步骤统一读取验收；按历史证据维护，防止目标与当前实现混淆
    │   ├── conversation-state-management.md  # 会话 SDK 与执行过程展示验收；按历史证据维护，防止目标与当前实现混淆
    │   ├── database-error-boundaries.md  # 数据库错误识别与业务冲突边界验收；按历史证据维护，防止目标与当前实现混淆
    │   ├── design-system.md  # 设计系统目录、令牌与第三方主题整理记录；按历史证据维护，防止目标与当前实现混淆
    │   ├── directory-responsibility-review.md  # 本轮目录审查范围与实际文档检查；不冒称业务改动已经实施
    │   ├── documentation-reorganization.md  # 文档分类、后端工程手册与引用整理验收；按历史证据维护，防止目标与当前实现混淆
    │   ├── execution-refactor.md  # 执行重设计第一阶段验收；按历史证据维护，防止目标与当前实现混淆
    │   ├── frontend-engineering.md  # 前端工程标准实施与验收；按历史证据维护，防止目标与当前实现混淆
    │   ├── light-theme.md  # 全站微暖中性浅色体系；按历史证据维护，防止目标与当前实现混淆
    │   ├── local-development.md  # 本地开发：历史迁移与验证；按历史证据维护，防止目标与当前实现混淆
    │   ├── openagents-collaboration-research.md  # OpenAgents 工作空间与协作机制调研；按历史证据维护，防止目标与当前实现混淆
    │   ├── platform-product-and-execution-assessment.md  # 数字员工平台的产品重心与执行架构评估；按历史证据维护，防止目标与当前实现混淆
    │   ├── platform-refactor-implementation.md  # 实施、迁移、检查、启动和限制；区分当前规则与一次验证
    │   ├── platform-refactor-plan.md  # 平台重构计划编制与检查记录；按历史证据维护，防止目标与当前实现混淆
    │   ├── platform-refactor-redesign.md  # 本次重写、独立复核与实际检查记录；不冒称业务已经重构
    │   ├── run-checkpoint-start.md  # 执行起点精简验收；按历史证据维护，防止目标与当前实现混淆
    │   ├── runtime-configuration.md  # 运行配置集中管理验收；按历史证据维护，防止目标与当前实现混淆
    │   ├── runtime-middleware-refactor.md  # 运行中间件职责整理与验证；按历史证据维护，防止目标与当前实现混淆
    │   ├── service-errors.md  # 应用错误分类整理验收；按历史证据维护，防止目标与当前实现混淆
    │   └── sqlite-checkpoint-chat.md  # SQLite checkpoint 聊天隔离验证；按历史证据维护，防止目标与当前实现混淆
    ├── reference/  # 实施后生效的契约；字段事实仍链接代码与迁移
    │   ├── agent-configuration/  # 员工配置的数据及 API；装配与公开投影一处维护
    │   │   ├── api.md  # 员工与技能管理接口；按现行规则或导航维护，防止目标与当前实现混淆
    │   │   └── data.md  # 员工与技能当前数据结构；按现行规则或导航维护，防止目标与当前实现混淆
    │   ├── ci-diagnosis/  # 专业结果与反馈契约；与通用执行规则分开
    │   │   ├── README.md  # 运维马 GitHub CI 故障诊断；按现行规则或导航维护，防止目标与当前实现混淆
    │   │   ├── api.md  # GitHub CI 诊断接口契约；按现行规则或导航维护，防止目标与当前实现混淆
    │   │   └── data.md  # GitHub CI 诊断数据契约；按现行规则或导航维护，防止目标与当前实现混淆
    │   ├── diagram/  # 现行运行时序图；与对应契约一起更新
    │   │   └── runtime-sequence.svg  # 静态或图示资源 runtime-sequence.svg；保留来源并按对应构建或文档流程维护
    │   ├── agent-resource-summary.md  # 员工资源配置摘要；按现行规则或导航维护，防止目标与当前实现混淆
    │   ├── auth.md  # 管理员登录与游客访问契约；按现行规则或导航维护，防止目标与当前实现混淆
    │   ├── avatar-assets.md  # 角色 SVG 母版与静态组件；按现行规则或导航维护，防止目标与当前实现混淆
    │   ├── brand.md  # 产品品牌与工程标识；按现行规则或导航维护，防止目标与当前实现混淆
    │   ├── conversations.md  # 对话与历史契约；按现行规则或导航维护，防止目标与当前实现混淆
    │   ├── data-model.md  # 当前数据模型与约束入口；按现行规则或导航维护，防止目标与当前实现混淆
    │   ├── design-system.md  # 设计系统展示与第三方主题接入；按现行规则或导航维护，防止目标与当前实现混淆
    │   ├── github-signin.md  # GitHub 登录与普通用户；按现行规则或导航维护，防止目标与当前实现混淆
    │   ├── model-connections.md  # 大脑配置与员工模型装配；按现行规则或导航维护，防止目标与当前实现混淆
    │   ├── organization-rules.md  # 规章制度与员工自动继承；按现行规则或导航维护，防止目标与当前实现混淆
    │   ├── runtime.md  # 当前运行、步骤与读取；按现行规则或导航维护，防止目标与当前实现混淆
    │   ├── signin.md  # Signin 登录页面；按现行规则或导航维护，防止目标与当前实现混淆
    │   └── theme.md  # 日间、夜间与跟随系统；按现行规则或导航维护，防止目标与当前实现混淆
    ├── templates/  # 按需裁剪的文档模板；不强制重复无关章节
    │   └── design.md  # 增量名称与设计；按现行规则或导航维护，防止目标与当前实现混淆
    ├── README.md  # NiumaCrew 文档索引；按现行规则或导航维护，防止目标与当前实现混淆
    └── documentation.md  # 文档组织与维护规范；按现行规则或导航维护，防止目标与当前实现混淆
```

每个目标均核对实际存在。具体来源、删除和新增原因见[file-map](file-map.md)与[实施计划](migration.md)。文档与图的生成检查不能替代业务测试。

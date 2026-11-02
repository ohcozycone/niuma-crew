"""Generate the implemented annotated tree and account for every baseline source file."""

import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASELINE = json.loads((HERE / "inventory.json").read_text())["files"]

MOVES = {
    "backend/app/agents/execution.py": "backend/app/agents/service.py",
    "backend/app/execution/driver.py": "backend/app/execution/scheduler.py",
    "backend/app/execution/hooks.py": "backend/app/execution/control.py",
    "backend/app/execution/sdk/agent_loop.py": "backend/app/agent_runtime/langchain.py",
    "frontend/src/pages/conversations/conversationController.ts": "frontend/src/pages/conversations/useConversationController.ts",
    "frontend/src/pages/conversations/conversationController.test.tsx": "frontend/src/pages/conversations/useConversationController.test.tsx",
    "frontend/src/pages/conversations/conversationSession.ts": "frontend/src/pages/conversations/pendingSubmissionStorage.ts",
    "frontend/src/pages/conversations/useRunSubscription.ts": "frontend/src/pages/conversations/useResponseSubscription.ts",
    "backend/app/execution/progress.py": "backend/app/execution/control.py",
    "backend/app/execution/sdk/__init__.py": "backend/app/agent_runtime/__init__.py",
    "backend/app/api/frontend.py": "backend/app/api/frontend_delivery.py",
    "backend/app/api/routes/configuration.py": "backend/app/api/routes/configuration_summary.py",
    "frontend/src/lib/session.ts": "frontend/src/lib/identity.ts",
    "frontend/src/lib/session.test.ts": "frontend/src/lib/identity.test.ts",
    "frontend/src/lib/knowledgeNavigation.ts": "frontend/src/lib/navigation.ts",
    "frontend/src/lib/knowledgeNavigation.test.ts": "frontend/src/lib/navigation.test.ts",
    "frontend/src/lib/api/configuration.ts": "frontend/src/lib/api/agents.ts",
    "frontend/src/lib/api/configuration.test.ts": "frontend/src/lib/api/agents.test.ts",
    "frontend/src/lib/api/public.ts": "frontend/src/lib/api/agents.ts",
    "frontend/src/components/configuration/ResourceSearchResults.tsx": "frontend/src/components/navigation/GlobalSearch.tsx",
    "frontend/src/components/agents/FavoriteAgentLink.tsx": "frontend/src/components/navigation/FavoriteAgentLink.tsx",
    "frontend/src/components/configuration/ConfigurationStatus.tsx": "frontend/src/components/configuration/ResourceStatus.tsx",
    "frontend/src/components/configuration/ResourcePagination.tsx": "frontend/src/components/common/ResourcePagination.tsx",
    "frontend/src/components/organization-rules/RulesWorkspace.tsx": "frontend/src/pages/knowledge/OrganizationRulesEditor.tsx",
    "frontend/src/components/skills/GithubCiMcp.tsx": "frontend/src/components/skills/GithubCiSetup.tsx",
    "frontend/src/components/skills/githubCiMcpStyles.ts": "frontend/src/components/skills/githubCiSetupStyles.ts",
    "frontend/src/pages/signin/logo.ts": "frontend/src/components/brand/wordmarkSource.ts",
    "frontend/src/state/configuration/ConfigurationProvider.tsx": "frontend/src/state/configuration/useConfigurationInvalidation.ts",
    "frontend/src/state/configuration/configurationContext.ts": "frontend/src/state/configuration/useConfigurationInvalidation.ts",
    "frontend/src/state/configuration/useConfiguration.ts": "frontend/src/state/configuration/useConfigurationInvalidation.ts",
    "frontend/src/state/configuration/useConfigurationState.ts": "frontend/src/state/configuration/useConfigurationInvalidation.ts",
    "backend/app/use_cases/__init__.py": "backend/app/api/routes/conversations/__init__.py",
    "backend/app/use_cases/conversation_commands.py": "backend/app/api/routes/conversations/service.py",
    "backend/app/use_cases/publish_run.py": "backend/app/conversations/publication.py",
    "backend/app/api/routes/conversations.py": "backend/app/api/routes/conversations/router.py",
}

SPLITS = {
    "backend/app/agents/execution.py": [
        "backend/app/conversations/preparation.py",
        "backend/app/conversations/authorization.py",
    ],
    "backend/app/execution/contracts.py": ["backend/app/agent_runtime/contracts.py"],
    "backend/app/execution/progress.py": ["backend/app/agent_runtime/streaming.py"],
    "backend/app/execution/sdk/checkpoints.py": ["backend/tests/checkpoint_helpers.py"],
    "backend/app/execution/store.py": [
        "backend/app/conversations/writes.py",
        "backend/app/ci_diagnosis/service.py",
    ],
    "backend/app/bootstrap.py": [
        "backend/app/conversations/authorization.py",
        "backend/app/conversations/preparation.py",
    ],
    "backend/app/execution/coordinator.py": ["backend/app/conversations/authorization.py"],
    "backend/app/ci_diagnosis/service.py": [
        "backend/app/ci_diagnosis/executor.py",
        "backend/app/ci_diagnosis/report.py",
        "backend/app/api/routes/conversations/service.py",
    ],
    "backend/app/execution/models.py": [
        "backend/app/conversations/models.py",
        "backend/app/ci_diagnosis/models.py",
    ],
    "backend/app/api/routes/ci_diagnosis.py": ["backend/app/ci_diagnosis/service.py"],
    "backend/app/agents/schemas.py": ["backend/app/agents/service.py"],
    "backend/app/config.py": ["backend/app/infrastructure/database/session.py"],
    "frontend/src/Layout.tsx": [
        "frontend/src/components/navigation/GlobalSearch.tsx",
        "frontend/src/components/navigation/useNavigationSummary.ts",
    ],
    "frontend/src/state/configuration/ConfigurationProvider.tsx": [
        "frontend/src/components/navigation/useNavigationSummary.ts",
        "frontend/src/pages/agents/useAgentDirectory.ts",
        "frontend/src/pages/agents/useAgentEditor.ts",
        "frontend/src/pages/skills/useSkillDirectory.ts",
        "frontend/src/pages/skills/useSkillEditor.ts",
    ],
    "frontend/src/state/configuration/useConfigurationState.ts": [
        "frontend/src/pages/agents/useAgentDirectory.ts",
        "frontend/src/pages/agents/useAgentEditor.ts",
        "frontend/src/pages/skills/useSkillDirectory.ts",
        "frontend/src/pages/skills/useSkillEditor.ts",
    ],
    "frontend/src/lib/api/configuration.ts": [
        "frontend/src/lib/api/skills.ts",
        "frontend/src/lib/api/modelConnections.ts",
    ],
    "frontend/src/lib/api/configuration.test.ts": ["frontend/src/lib/api/skills.test.ts"],
    "frontend/src/lib/api/public.ts": ["frontend/src/lib/api/skills.ts"],
    "frontend/src/lib/session.ts": ["frontend/src/lib/navigation.ts"],
    "frontend/src/lib/session.test.ts": ["frontend/src/lib/navigation.test.ts"],
    "frontend/src/lib/knowledgeNavigation.ts": ["frontend/src/state/editing/useEditing.ts"],
    "frontend/src/lib/knowledgeNavigation.test.ts": [
        "frontend/src/state/editing/useEditing.test.tsx"
    ],
    "backend/app/api/routes/conversations.py": [
        "backend/app/api/routes/conversations/streaming.py",
        "backend/app/api/routes/conversations/service.py",
    ],
}

NEW_FILES = {
    "backend/tests/scenario_client.py": "既有场景的测试适配；生产不保留旧 Run HTTP 入口",
    "backend/tests/test_message_delivery_migration.py": "0005 历史保留与损坏输入拒绝；正式迁移不能凭空补答案",
    "backend/tests/test_response_contract.py": "实际公开协议及一致读取测试；不经过旧场景适配器",
    "frontend/src/pages/conversations/conversationScope.test.ts": "对话和回复各自版本合并；迟到接受或读取不能回退当前活动目标",
    "docs/learning/observing-runtime.md": "从页面到后台和数据的渐进观测；用具体操作理解机制",
    "docs/records/platform-refactor-implementation.md": "实施、迁移、检查、启动和限制；区分当前规则与一次验证",
    "backend/migrations/versions/0005_message_delivery.py": "P2 的正文、关联、专业数据与版本迁移；保留历史 ID 并逐项校验",
    "backend/app/agent_runtime/README.md": "Agent 输入、控制、输出与恢复边界；独立测试无需业务服务",
    "backend/app/agent_runtime/__init__.py": "Agent 运行包声明；导入不创建模型或后台任务",
    "backend/app/agent_runtime/contracts.py": "普通请求、受限控制、动作内容及候选输出；阻止 ORM 与 SDK 类型跨界",
    "backend/app/agent_runtime/streaming.py": "SDK 片段和工具请求识别；宿主与前端只接收普通可见内容",
    "backend/app/conversations/preparation.py": "接受时捕获与启动恢复时准备；原冻结依据不被当前配置覆盖",
    "backend/app/conversations/authorization.py": "身份、装配、连接和专业范围组合授权；API 与后台各时点共用",
    "backend/app/ci_diagnosis/executor.py": "现有受控 CI 取证与分析；共用运行控制但保留专业约束",
    "backend/app/ci_diagnosis/report.py": "来源、覆盖和引用校验及确定性正文；业务含义不进入通用执行",
    "backend/tests/checkpoint_helpers.py": "测试存档构造与断言；正式 SDK 恢复不携带测试图 API",
    "backend/tests/runtime_helpers.py": "内存运行控制与假执行器；分别验证隔离边界两侧",
    "backend/tests/test_runtime_boundaries.py": "Agent 与宿主依赖、受限接口和普通内容回归；防止存储逃逸",
    "docs/architecture/agent-runtime.md": "实施后解释 SDK 与宿主协作；取舍与控制边界有稳定维护位置",
    "docs/records/platform-refactor-redesign.md": "本次重写、独立复核与实际检查记录；不冒称业务已经重构",
    "docs/proposals/platform-refactor/README.md": "总方案结论、实例和导航；先建立整体再进入细节",
    "docs/proposals/platform-refactor/decisions.md": "逐项追问与替代方案；说明抽象的真实必要性",
    "docs/proposals/platform-refactor/domain.md": "内容、处理、关联与专业数据；从事实区分身份和状态",
    "docs/proposals/platform-refactor/modules.md": "全部后端模块职责与依赖；区分业务组织与执行管理",
    "docs/proposals/platform-refactor/runtime.md": "Agent 输入控制输出与恢复；防止 SDK 和存储互相渗透",
    "docs/proposals/platform-refactor/api.md": "面向用户操作的接口；公开路径不镜像内部模块",
    "docs/proposals/platform-refactor/frontend.md": "页面、Hook和状态生命周期；按交互组织而非后端实体",
    "docs/proposals/platform-refactor/flows.md": "端到端正常与异常流程；明确写入者、顺序和提交",
    "docs/proposals/platform-refactor/migration.md": "实施、数据搬迁与验收；保留正确行为并可核对回退",
    "docs/proposals/platform-refactor/extensions.md": "未来能力的接入条件；不提前预建完整空文件树",
    "docs/proposals/platform-refactor/target-tree.md": "完整目标工程及文档树；每节点解释职责与原因",
    "docs/proposals/platform-refactor/file-map.md": "每个重写前文件去向；避免只规划主链遗漏外围",
    "docs/proposals/platform-refactor/inventory.json": "重写前工程清单；使覆盖与新增文件可核对",
    "docs/proposals/platform-refactor/build-target-tree.py": "生成树和完整映射；从同一来源核对结构",
    "docs/proposals/platform-refactor/diagrams/build-diagrams.py": "新版目标图的可编辑源；图与正文同步",
    "docs/proposals/platform-refactor/diagrams/target-boundaries.svg": "新版模块与数据归属图；帮助区分模块和实体",
    "docs/proposals/platform-refactor/diagrams/request-lifecycle.svg": "新版发送到发布时序；区分事务和外部等待",
    "docs/proposals/platform-refactor/layered-architecture.md": "配套四张职责分层图解读；具体数据和接口由对应专题确定",
    "frontend/src/state/configuration/useConfigurationInvalidation.ts": "配置写入后的版本通知与小 "
    "Context；不保存资源列表、路由和编辑状态",
    "frontend/src/components/navigation/useNavigationSummary.ts": "外壳计数与有界收藏读取；写入或身份变化后刷新，忽略旧结果",
    "frontend/src/pages/agents/useAgentDirectory.ts": "员工目录条件、分页、启停收藏与局部错误；不加载编辑全文",
    "frontend/src/pages/agents/useAgentEditor.ts": "单个员工详情、保存删除和方法选择读取；只接受完整编辑数据",
    "frontend/src/pages/skills/useSkillDirectory.ts": "方法列表、展开、安装刷新及删除；状态随目录查询变化",
    "frontend/src/pages/skills/useSkillEditor.ts": "指定方法详情、保存和冲突；与目录加载分别取消",
    "frontend/src/lib/api/skills.ts": "方法管理及公开读取 DTO 与映射；不从员工客户端借类型",
    "frontend/src/lib/api/navigation.ts": "导航计数、收藏和跨资源搜索请求；按前端使用场景组合现有端点",
    "frontend/src/lib/api/skills.test.ts": "方法客户端白名单、详情和写入回归；从混合配置测试归位",
    "frontend/src/lib/navigation.test.ts": "来源、安全返回和规则定位回归；导航规则只维护一处",
    "frontend/src/state/editing/useEditing.test.tsx": "编辑注册撤销、放弃回调和同步保存门闩；防止离开误清草稿",
    "frontend/src/components/navigation/navigationFlow.test.tsx": "导航摘要刷新与搜索迟到结果隔离；不依赖全局资源仓库",
    "frontend/src/pages/agents/configurationFlow.test.tsx": "目录和详情切换、过期读取与完整配置保存；防止摘要覆盖正文",
    "frontend/src/pages/skills/configurationFlow.test.tsx": "目录展开、安装刷新、编辑保存与身份切换；验证页面状态归位",
    "docs/proposals/platform-refactor/responsibility-review.md": "全工程职责与引用复核；给出证据、目标归属、保留和不采纳项",
    "docs/records/directory-responsibility-review.md": "本轮目录审查范围与实际文档检查；不冒称业务改动已经实施",
    "backend/app/api/routes/conversations/streaming.py": "SSE 限额、重验身份、心跳及连接释放；只观察已保存结果，断线不取消工作",
    "docs/proposals/platform-refactor/service-boundaries.md": "API 请求服务、业务模块与共享回复流程；给出逐项归属、调用和事务依据",
    "docs/records/api-service-boundaries.md": "本轮服务归属修订及文档检查；保留未实施状态和业务文件哈希证据",
}

FILE_NOTES = {
    "backend/alembic.ini": "数据库迁移入口及路径配置；升级不依赖启动时自动建表",
    "backend/.python-version": "Python 工具链版本；开发与隔离测试使用一致解释器",
    "frontend/index.html": "浏览器 HTML 与首屏主题入口；主题不等待 React 才初始化",
    "frontend/tsconfig.json": "TypeScript 类型和路径约定；前端契约在构建前检查",
    "frontend/vite.config.ts": "开发 API/SSE 代理和生产构建；保留来源及流式传输语义",
    "frontend/vitest.config.ts": "前端测试环境与运行配置；组件和状态可隔离验证",
    "frontend/eslint.config.mjs": "命名、导入和 React 静态规则；可判定约束交给工具",
    "frontend/eslint.config.test.ts": "静态规则本身的回归；防止边界检查配置悄悄失效",
    "frontend/themeBootstrap.test.ts": "首屏主题及内联脚本验证；防止业务重构引入主题闪动",
    "frontend/.prettierignore": "生成物与格式检查范围；保留来源检查而不手改构建产物",
    "frontend/src/components/avatars/CHARACTERS.md": "角色设定与形象依据；将制作语义与运行时选择分开",
    "frontend/src/components/ui/LICENSE": "复用 UI 的第三方许可；保留版权与使用依据",
    "frontend/src/components/avatars/svg/package.json": "生成组件的工具及类型配置；遵循资源生成边界",
    "frontend/public/avatars/catalog.json": "头像标识与成品目录；选择器和构建清单有同一来源",
    "frontend/public/avatars/svg/catalog.json": "SVG 角色资源元数据；文件变化可被构建校验发现",
    "AGENTS.md": "项目协作入口；只导航现行约束而不复制所有规则",
    "README.md": "项目定位与启动入口；通过文档索引进入详细契约",
    "Makefile": "统一开发、检查、构建和维护命令；避免各端操作漂移",
    ".gitignore": "依赖、缓存和运行数据排除；防止环境及秘密进入工程",
    "backend/app/main.py": "ASGI 导出入口；与 HTTP 适配和业务规则分开",
    "backend/app/bootstrap.py": "装配共享准备授权发布回调、执行器与 HTTP 请求服务；后台不依赖 API 实现",
    "backend/app/config.py": "聚合并校验部署配置；避免业务散读环境变量",
    "backend/app/errors.py": "应用失败语义；由 HTTP 层决定响应状态",
    "backend/app/schemas.py": "公共请求与分页校验；避免 PATCH 和文本约束各自实现",
    "backend/app/auth/actor.py": "可信当前主体；被多个业务入口共用且不含 HTTP 依赖",
    "backend/app/auth/permissions.py": "操作及资源范围纯策略；不与账号会话生命周期混合",
    "backend/app/auth/service.py": "认证、签发、解析与撤销会话；对外返回 Actor",
    "backend/app/auth/github.py": "OAuth 身份适配与返回地址检查；上游令牌使用后丢弃",
    "backend/app/auth/cli.py": "管理员本地维护命令；复用认证服务而不绕过生命周期",
    "backend/app/agents/service.py": "员工配置装配与就绪规则；管理公开读取、共享准备和授权共同复用",
    "backend/app/skills/parameters.py": "有界参数规范与装配参数校验；编辑、保存和运行准备共用",
    "backend/app/model_connections/credentials.py": "模型密文与主密钥操作；凭证生命周期留在连接模块",
    "backend/app/model_connections/presets.py": "受信模型协议及端点元数据；不让表单任意扩大连接能力",
    "backend/app/llm/config.py": "显式单次模型配置；不在模型层查询业务绑定",
    "backend/app/llm/factory.py": "模型工厂及网络会话；调用结束和取消时关闭资源",
    "backend/app/llm/usage.py": "普通用量结构与保守累计；仅接收普通映射，SDK 类型留在运行实现",
    "backend/app/llm/errors.py": "已知上游错误分类；不吞数据库或程序故障",
    "backend/app/execution/admission.py": "幂等、容量与登记 Run；归属与配置由调用用例组织",
    "backend/app/execution/scheduler.py": "多 Run 队列、进程锁、并发与启动恢复；不组织模型内部步骤",
    "backend/app/execution/coordinator.py": "单 Run 看护与执行函数；通过注入回调准备授权发布，不反向导入对话或 API",
    "backend/app/execution/store.py": "Run 持久操作与状态规则、动作预算和恢复；不调用跨模块发布器",
    "backend/app/execution/contracts.py": "执行依据、准备函数与终态意图；不保存业务正文与专业结果",
    "backend/app/execution/errors.py": "运行故障到终态和公开提示；应用错误与 HTTP 转换另有边界",
    "backend/app/execution/queries.py": "执行记录、动作与安全事实查询；不反向依赖对话响应类型",
    "backend/app/agent_runtime/langchain.py": "现有 Agent 构造、模型工具循环与恢复判断；当前单一实现直接归组",
    "backend/app/agent_runtime/middleware.py": "SDK 动作前后接入控制；不解析业务身份或操作 ORM",
    "backend/app/agent_runtime/skill_loading.py": "获准方法的虚拟资源与读取检查；方法文字不授予新权限",
    "backend/app/agent_runtime/checkpoints.py": "SDK 存档、可信完成和兼容读取；具体资源独立注入",
    "backend/app/ci_diagnosis/service.py": "CiDiagnosisService 的配置安装、范围、查询和反馈；专业记录名不与服务混用",
    "backend/app/ci_diagnosis/contracts.py": "CI 目标、证据、报告、反馈和工具声明；专业规则不进入通用 Run",
    "backend/app/ci_diagnosis/mcp.py": "现有受限 MCP 客户端；保留范围和关闭语义而不预建通用工具框架",
    "backend/app/api/router.py": "注册 HTTP 能力入口；显式导入对话分组 router，不让共享业务导入 API",
    "backend/app/api/dependencies.py": "解析身份并取得服务；后台不持有 Request Session",
    "backend/app/api/security.py": "浏览器来源、格式及体积保护；业务授权继续单独校验",
    "backend/app/api/rate_limit.py": "共享请求频率限制；不把模型检查限流归入账号模型",
    "backend/app/api/errors.py": "应用及已知数据库错误转公开响应；隐藏内部细节",
    "backend/app/api/frontend.py": "压缩、缓存与静态深链；未知 API 和缺资源保持错误",
    "backend/app/infrastructure/database/session.py": "DatabaseConfig 与数据库连接生命周期；不导入应用配置聚合层",
    "backend/app/infrastructure/database/transactions.py": "写入资格与事务协作机制；处理先读后写竞争",
    "backend/app/infrastructure/database/errors.py": "底层数据库错误识别；业务只转换确认的冲突",
    "backend/app/infrastructure/database/fields.py": "UUID、UTC 与 JSON 字段约定；所有 ORM 共用存储语义",
    "backend/app/infrastructure/database/base.py": "声明式 ORM 基类及元数据；不包含业务规则",
    "backend/app/infrastructure/database/models.py": "集中注册所属模块 ORM；仅作迁移装配例外",
    "backend/migrations/env.py": "正式迁移环境及连接；不依赖应用自动建表",
    "backend/migrations/script.py.mako": "新迁移模板；沿用工具标准格式",
    "backend/tests/conftest.py": "临时数据库、身份和服务 fixture；测试不读开发数据",
    "backend/tests/legacy_execution_helpers.py": "冻结旧库和旧存档的构造；保留真实迁移回归能力",
    "backend/tests/checkpoint_worker.py": "隔离 HTTP 子进程及故障注入；验证真实重启窗口",
    "backend/tests/configuration_helpers.py": "配置测试共享装配；减少重复而不掩盖业务断言",
    "backend/experiments/sqlite_checkpoint_chat.py": "隔离 SDK 实验；不装配正式业务应用",
    "frontend/src/main.tsx": "浏览器与 React 启动；只装配路由和全局能力",
    "frontend/src/router.tsx": "显式页面路由、权限与懒加载；命名切换与深链一处维护",
    "frontend/src/Layout.tsx": "工作台路由导航与唯一离开保护；不保存页面资源或拼接草稿键",
    "frontend/src/globals.css": "共享基础样式入口；业务样式遵循既有设计令牌",
    "frontend/src/lib/api/http.ts": "Cookie、响应及错误的共用传输；不包含业务状态机",
    "frontend/src/lib/navigation.ts": "来源、安全返回与规则位置；不猜测编辑器草稿键",
    "frontend/src/lib/draft.ts": "通用非秘密草稿保存；配置与输入各有自己的 schema",
    "frontend/src/lib/avatars/manifest.generated.ts": "构建生成的头像元数据；从同源资源再生成而不手改",
    "frontend/src/lib/avatars/registry.ts": "头像注册及加载关系；业务只保存稳定 avatar_id",
    "scripts/dev.py": "前后端端口协同与子进程清理；业务重命名不改变开发生命周期",
    "scripts/check_docs.py": "本地链接、锚点与索引检查；现行文档与方案可可靠导航",
    "backend/app/conversations/models.py": "对话、轻量内容与处理关联；正文直存且活动唯一约束保留",
    "backend/app/conversations/queries.py": "历史、问题目录、上下文和统一回复读取；页面不解释 SDK",
    "backend/app/conversations/writes.py": "建立输入与回复、绑定及填充终态正文；使用传入事务保持原子",
    "backend/app/execution/models.py": "Run 与实际动作约束；移除通用结果和 CI 专业内容",
    "backend/app/execution/control.py": "受限运行控制及私有普通进度缓冲；调用状态操作但不解析 SDK",
    "backend/app/api/routes/conversations/service.py": "ConversationRequestService "
    "的请求目标、幂等及接受停止反馈事务；共享流程只调用一份",
    "backend/app/conversations/publication.py": "回复、专业报告、Run 终态与占用原子交付；完成恢复和排队停止共用",
    "backend/app/ci_diagnosis/models.py": "CiDiagnosis 过程、报告、专业版本及一次反馈；专业数据不塞进 Run",
    "backend/app/api/routes/ci_diagnosis.py": "专业配置与安装 HTTP 入口；报告和反馈通过准确的对话回复路径接入",
    "frontend/src/lib/api/conversations.ts": "对话、消息和回复用户操作契约；不镜像内部 Run 与 SDK 结构",
    "frontend/src/lib/api/conversationTransport.ts": "可注入的对话网络能力；控制器可隔离测试且不读取路由",
    "frontend/src/lib/api/ciDiagnosis.ts": "专业阶段、报告与反馈 HTTP 契约；按回复和专业版本读取",
    "frontend/src/pages/conversations/useConversationController.ts": "对话命令、确认、观察与作用域副作用；一实例一控制器",
    "frontend/src/pages/conversations/pendingSubmissionStorage.ts": "未知提交的固定键、输入和停止意图；区别于未发送草稿",
    "frontend/src/pages/conversations/useResponseSubscription.ts": "观察指定回复并只读恢复；消息组件不各自建连接",
    "frontend/src/pages/conversations/useMessage.ts": "按行读取正文、状态、过程与操作；不强制对齐后端实体字段",
    "frontend/src/pages/conversations/useConversation.ts": "对话级输入、摘要与历史入口；保留真实用户交互边界",
    "frontend/src/pages/conversations/conversationStore.ts": "按作用域版本和回复版本合并并提供稳定快照；避免串写与重复渲染",
    "frontend/src/pages/conversations/conversationState.ts": "纯状态合并及操作资格；不再解释模型轮和工具请求",
    "frontend/src/pages/conversations/conversationDraft.ts": "未提交输入草稿与匹配清理；不能覆盖已发出待确认命令",
    "frontend/src/pages/conversations/conversationContext.ts": "稳定实例上下文；共享作用域而不广播每次正文变化",
    "frontend/src/pages/conversations/ConversationProvider.tsx": "身份和对话作用域；切换销毁读取观察而不停止后台",
    "frontend/src/pages/conversations/CiReport.tsx": "专业阶段、来源、报告和反馈；按 CI 版本读取而非每次文字更新",
    "frontend/src/pages/conversations/RunActions.tsx": "回复的真实过程展示与本地分页；不负责执行调度",
    "docs/proposals/platform-refactor/diagrams/build-layered-diagrams.py": "并行整理的分层图源，本轮保留；与专题共同核对职责和含义",
    "docs/proposals/platform-refactor/diagrams/layered-01-overview.svg": "并行整理的总体图，本轮未重画；与新版专题共同核对职责",
    "docs/proposals/platform-refactor/diagrams/layered-02-frontend.svg": "并行整理的前端图，本轮未重画；与新版 Hook 边界分别核对",
    "docs/proposals/platform-refactor/diagrams/layered-03-backend.svg": "并行整理的后端图，本轮未重画；不由生成树推断已经实施",
    "docs/proposals/platform-refactor/diagrams/layered-04-execution.svg": "并行整理的执行图，本轮未重画；与新版运行协议分别核对",
    "frontend/src/components/agents/FavoriteAgentLink.tsx": "收藏或常用员工的导航展示；只传稳定员工标识",
    "frontend/src/components/auth/AccountMenu.tsx": "当前身份和账号操作菜单；认证仍由服务端确认",
    "frontend/src/components/auth/AuthBoundary.tsx": "页面身份与访问分支；不替代服务端权限检查",
    "frontend/src/components/avatars/AgentAvatar.tsx": "员工头像统一展示；不把角色外观当作能力证明",
    "frontend/src/components/avatars/AvatarBadge.tsx": "小尺寸头像和状态展示；样式不拥有业务状态",
    "frontend/src/components/avatars/AvatarPicker.tsx": "头像选择表单；只保存稳定 avatar_id",
    "frontend/src/components/avatars/LazySvgAvatar.tsx": "头像资源延迟加载；避免首屏加载全部角色",
    "frontend/src/components/avatars/svgAvatar.ts": "头像类型和资源选择约定；页面不直接依赖生成文件细节",
    "frontend/src/components/brand/BrandLogo.tsx": "品牌标志展示；统一读取生成成品",
    "frontend/src/components/common/EmptyState.tsx": "空数据和无结果展示；不掩盖加载或错误状态",
    "frontend/src/components/common/Markdown.tsx": "安全 Markdown 正文展示；不解析 SDK 或执行文本指令",
    "frontend/src/components/common/PageBreadcrumb.tsx": "来源与位置导航；不决定后台执行目标",
    "frontend/src/components/common/PageHeading.tsx": "页面标题和说明；展示与业务命令分开",
    "frontend/src/components/common/PageToolbar.tsx": "共享页头插槽与操作布局；各页注入自己的交互",
    "frontend/src/components/common/SearchInput.tsx": "共享搜索输入交互；由调用页决定实际查询",
    "frontend/src/components/configuration/ConfigurationConflict.tsx": "版本冲突查看和采用最新修订交互；资源读取与字段展示由页面提供",
    "frontend/src/components/configuration/ConfigurationStatus.tsx": "配置加载和保存状态反馈；各页面共用一致提示",
    "frontend/src/components/configuration/ResourcePagination.tsx": "资源列表分页控件；页码交互与业务数据读取分开",
    "frontend/src/components/configuration/ResourceSearchResults.tsx": "搜索结果数量与空态；列表读取仍由所属页面组织",
    "frontend/src/components/configuration/StaleDraftNotice.tsx": "过期草稿提示；避免用旧表单覆盖新修订",
    "frontend/src/components/organization-rules/InheritedRules.tsx": "员工继承规则展示；不创建一份独立规则副本",
    "frontend/src/components/organization-rules/RulesWorkspace.tsx": "公司规章制度编辑工作区；正文及修订由后端管理",
    "frontend/src/components/organization-rules/useOrganizationRules.ts": "规则读取、编辑和冲突反馈；复用配置生命周期",
    "frontend/src/components/skills/GithubCiMcp.tsx": "当前 CI 专业接入配置界面；不伪装成任意通用工具管理",
    "frontend/src/components/skills/SkillCard.tsx": "方法摘要卡片；展示资产与员工装配分开",
    "frontend/src/components/skills/SkillCollection.tsx": "方法集合展示与入口；不隐式激活运行能力",
    "frontend/src/components/theme/ThemeArtwork.tsx": "主题相关装饰资源；与业务数据和身份无关",
    "frontend/src/components/theme/ThemeSwitcher.tsx": "主题切换入口；复用统一偏好和首屏约定",
    "frontend/src/components/ui/styledProps.ts": "共享样式属性约定；过滤展示属性而不污染DOM",
    "frontend/src/hooks/useDraft.ts": "非秘密表单草稿生命周期；不同业务使用自己的存储结构",
    "frontend/src/hooks/useQueryState.ts": "URL 参数读写与显式重置选项；具体查询联动由调用页面声明",
    "frontend/src/lib/api/modelConnections.ts": "连接配置与显式检查；全量读取分页循环仅供本文件使用",
    "frontend/src/lib/api/organizationRules.ts": "公司规章制度 HTTP 契约；正文和修订统一读取",
    "frontend/src/lib/brand.ts": "品牌成品与尺寸约定；消费端不重复拼装资源路径",
    "frontend/src/lib/knowledgeNavigation.ts": "知识资料与员工来源链接；当前静态资料和未来检索分开",
    "frontend/src/lib/models/agent.ts": "员工摘要、完整详情和编辑输入类型；在同文件区分，避免假空正文",
    "frontend/src/lib/models/agentAvailability.ts": "员工展示可用性计算；服务端仍决定实际执行资格",
    "frontend/src/lib/models/skill.ts": "共享方法展示模型；资产信息与运行激活分开",
    "frontend/src/lib/utils.ts": "通用类名等纯工具；不包含业务状态或网络",
    "frontend/src/pages/agents/AgentCard.tsx": "员工身份、能力摘要与工作入口；卡片不组织后台执行",
    "frontend/src/pages/agents/AgentConfiguration.tsx": "员工配置表单与保存协作；修订冲突和草稿留在配置交互",
    "frontend/src/pages/agents/AgentDeletionDialog.tsx": "员工删除确认与依赖反馈；真实删除规则仍在后端",
    "frontend/src/pages/agents/AgentDirectory.tsx": "员工目录筛选与分页；不等待对话运行状态",
    "frontend/src/pages/agents/AgentModelConnectionField.tsx": "员工模型装配选择；展示可用连接而不接触凭证",
    "frontend/src/pages/agents/AgentsPage.tsx": "员工页面和导航组合；配置与对话入口各自保留生命周期",
    "frontend/src/pages/agents/SkillAssignmentConfiguration.tsx": "员工方法装配参数；整体保存与服务端校验一致",
    "frontend/src/pages/agents/agentPresentation.ts": "员工展示字段整理；不把缺失配置伪装成可执行",
    "frontend/src/pages/agents/agentSearch.ts": "员工目录的搜索匹配；页面筛选规则集中维护",
    "frontend/src/pages/agents/types.ts": "所属模块共享展示类型；避免从组件内部反向导出",
    "frontend/src/pages/conversations/ConversationComposer.tsx": "输入、方法选择和提交交互；网络由对话控制器管理",
    "frontend/src/pages/conversations/ConversationControls.tsx": "当前回复停止重试等控件；操作绑定准确回复ID",
    "frontend/src/pages/conversations/ConversationHistory.tsx": "历史入口和阅读状态展示；不自行重复建立订阅",
    "frontend/src/pages/conversations/ConversationMessage.tsx": "用户内容或助手回复行；组合状态过程与专业报告",
    "frontend/src/pages/conversations/ConversationOutline.tsx": "问题目录接入与正文定位；展示组件不绑定网络实现",
    "frontend/src/pages/conversations/ConversationPanel.tsx": "对话页面组合与滚动协作；不复制一套执行生命周期",
    "frontend/src/pages/conversations/ConversationQuestionPreview.tsx": "提问短预览展示；来源是专用预览接口",
    "frontend/src/pages/conversations/ConversationRuler.tsx": "问题刻度、触摸键盘和定位反馈；编号来自真实用户提问",
    "frontend/src/pages/conversations/ConversationsPage.tsx": "对话列表与路由入口；新对话先保留本地草稿",
    "frontend/src/pages/conversations/actionPagination.ts": "已加载过程的本地分页；展开步骤不额外发请求",
    "frontend/src/pages/conversations/conversationTestHelpers.ts": "对话接口与组件测试替身；只表达公开交互事实",
    "frontend/src/pages/conversations/questionNavigation.ts": "目录数据源和浏览状态类型；目录与正文窗口分开",
    "frontend/src/pages/conversations/useConversationHistory.ts": "最新与历史连续窗口；保留阅读锚点并拒绝迟到请求",
    "frontend/src/pages/conversations/useQuestionNavigation.ts": "目录分页锚点与有界缓存；不下载完整对话",
    "frontend/src/pages/conversations/useQuestionPreview.ts": "预览加载与目标隔离；迟到结果不能覆盖新问题",
    "frontend/src/state/auth/IdentityProvider.tsx": "当前身份实例与变化通知；切换后销毁旧业务作用域",
    "frontend/src/state/auth/identityContext.ts": "稳定身份上下文；认证网络操作集中组织",
    "frontend/src/state/auth/useIdentity.ts": "身份共享读取入口；不由客户端推断登录成功",
    "frontend/src/state/editing/useEditing.ts": "编辑区注册、脏状态、同步保存门闩和放弃回调；不识别员工或技能键",
    "frontend/src/state/theme/themeController.ts": "主题偏好与系统变化协调；首屏与 React 保持一致",
    "frontend/src/state/theme/useTheme.ts": "组件读取和切换主题；不重复保存主题状态",
    "backend/app/api/frontend_delivery.py": "静态成品、压缩缓存与深链交付；目录由应用装配显式传入",
    "backend/app/api/routes/configuration_summary.py": "全局配置计数 HTTP 读取；一条汇总查询，不另建计数领域服务",
    "frontend/src/lib/identity.ts": "当前身份、隔离键和变更通知；返回位置统一归导航",
    "frontend/src/lib/api/agents.ts": "员工摘要、详情、编辑与公开读取 DTO；列表不伪造完整配置",
    "frontend/src/components/navigation/GlobalSearch.tsx": "全局搜索弹窗、输入和跨资源结果；从外壳收回完整搜索交互",
    "frontend/src/components/navigation/FavoriteAgentLink.tsx": "收藏员工导航链接；外壳与设计样板共用，不属于员工配置",
    "frontend/src/components/configuration/ResourceStatus.tsx": "由 ready、error、onReload 驱动的加载反馈；不依赖全局配置 "
    "Context",
    "frontend/src/components/common/ResourcePagination.tsx": "URL 列表分页与刷新交互；不限定为配置编辑",
    "frontend/src/pages/knowledge/OrganizationRulesEditor.tsx": "知识页面专用规则编辑；共享继承展示仍在公共组件",
    "frontend/src/components/skills/GithubCiSetup.tsx": "CI 方法安装及连接配置展示；技能库和员工装配实际共用",
    "frontend/src/components/skills/githubCiSetupStyles.ts": "CI 安装配置展示样式；随组件职责改名，保持现有视觉",
    "frontend/src/components/brand/wordmarkSource.ts": "品牌 SVG 原始字符串及固定 ID；登录动画与构建脚本共用同一来源",
    "frontend/scripts/build-brand.mjs": "从品牌源稿生成派生图形；构建不再反向读取登录页私有文件",
    "backend/app/conversations/schemas.py": "对话提交、用户消息、助手视图和公开步骤；前端无需理解执行内部类型",
    "frontend/src/components/avatars/README.md": "头像公共接口、生成来源与维护入口；消费者不依赖角色私有实现",
    "frontend/src/components/avatars/index.ts": "头像能力公共导出；业务与样板从稳定入口使用",
    "frontend/src/components/avatars/svg/frame.tsx": "SVG 实例标识与外框适配；多个头像并存时避免内部 ID 冲突",
    "frontend/src/components/avatars/svg/index.tsx": "各角色生成组件的导出清单；与资源 catalog 和懒加载入口一致",
    "frontend/src/pages/agents/README.md": "员工目录、配置和装配的维护入口；链接共享契约而不复制字段",
    "frontend/src/pages/agents/index.ts": "员工卡片与展示转换的公共入口；设计样板不导入页面私有状态",
    "frontend/src/pages/avatars/AvatarGalleryPage.tsx": "正式角色图鉴与选择展示；复用同一头像清单和加载能力",
    "frontend/src/pages/brains/BrainsPage.tsx": "模型连接页入口与权限反馈；页面不代替后端检查",
    "frontend/src/pages/brains/BrainWorkspace.tsx": "连接目录、检查与编辑表单；密钥仅留表单内存，使用统一离开保护",
    "frontend/src/pages/design-system/fixtures/agents.ts": "员工设计样板数据；明确为展示 fixture，不进入业务保存",
    "frontend/src/pages/design-system/ColorCatalog.tsx": "主题颜色与语义色示例；直接核对设计令牌",
    "frontend/src/pages/design-system/ComponentExamples.tsx": "基础控件真实交互样例；复用正式 UI 入口",
    "frontend/src/pages/design-system/DesignSystemPage.tsx": "设计展示页签与样例组合；与生产业务状态隔离",
    "frontend/src/pages/design-system/PatternExamples.tsx": "员工和对话等组合样板；通过允许的公共组件入口展示",
    "frontend/src/pages/design-system/TypographyCatalog.tsx": "字号、行高与文字层级示例；遵守统一排版令牌",
    "frontend/src/pages/design-system/useThemeValues.ts": "设计展示读取当前 CSS 变量；不再维护一套主题值",
    "frontend/src/pages/help/HelpPage.tsx": "帮助导航与指南组合；按已生效用户操作提供说明",
    "frontend/src/pages/help/guides.ts": "各能力帮助内容；实施行为变化后同步，目标建议不写成当前功能",
    "frontend/src/pages/knowledge/KnowledgePage.tsx": "资料与规则页签组合；规则编辑按自身区域注册离开保护",
    "frontend/src/pages/knowledge/KnowledgeLibrary.tsx": "教学资料筛选、查看和下载；不伪装成已接入在线知识检索",
    "frontend/src/pages/knowledge/teachingDocuments.ts": "教学资料目录与元数据；来自明确示例而非隐式模型上下文",
    "frontend/src/pages/knowledge/README.md": "知识页面、教学资料和规则编辑入口；区分当前展示与后续检索",
    "frontend/src/pages/signin/SigninPage.tsx": "身份入口、登录表单和品牌场景组合；品牌源稿从共享品牌能力读取",
    "frontend/src/pages/signin/formState.ts": "凭证必填检查和登录失败反馈；错误信息不暴露服务端内部细节",
    "frontend/src/pages/signin/geometry.ts": "登录场景响应尺寸计算；只处理几何，不读取主题或认证状态",
    "frontend/src/pages/signin/layoutConfig.ts": "登录场景尺寸约束；与主题令牌分开，避免视觉参数散落",
    "frontend/src/pages/signin/useSigninForm.ts": "凭证、游客与 GitHub 登录交互；完成后刷新真实身份",
    "frontend/src/pages/signin/useSigninScene.ts": "登录场景尺寸与动态加载生命周期；处理减少动态效果和页面隐藏",
    "frontend/src/pages/signin/motion/controller.ts": "登录动画时钟、场景 DOM 和关闭清理；认证操作不依赖动画结束",
    "frontend/src/pages/signin/motion/model.ts": "品牌字形状态、接触计算与 SVG 绑定；统一控制完整场景而不按字母拆文件",
    "frontend/src/pages/skills/SkillsPage.tsx": "方法目录与编辑路由组合；各视图调用自己的读取 Hook",
    "frontend/src/pages/skills/SkillEditor.tsx": "方法正文、参数规范和修订编辑；具体草稿清理注册给外壳",
    "frontend/src/design-system/README.md": "主题、组件与视觉工程入口；正式业务引用统一设计规则",
    "frontend/src/design-system/colors.md": "颜色语义与使用规范；数值由主题令牌维护",
    "frontend/src/design-system/components.md": "组件尺寸、状态与组合约定；与真实组件和样板核对",
    "frontend/src/design-system/spec.ts": "可由工具检查的视觉规格；与组件和样板共享依据",
    "frontend/src/design-system/themeValues.ts": "读取和转换主题令牌；不重复硬编码 CSS 数值",
    "frontend/src/design-system/theme.css": "主题颜色、字号和间距令牌；首屏、组件与生成品牌同源",
    "backend/app/api/routes/conversations/router.py": "对话命令、读取与观察的 HTTP 接入；参数状态码和响应由本层转换",
    "backend/app/conversations/preparation.py": "接受时捕获与启动恢复时准备；原冻结依据不被当前配置覆盖",
    "backend/app/conversations/authorization.py": "身份、装配、连接和专业范围组合授权；API 与后台各时点共用",
}

MODULES = {
    "auth": "账号、登录与访问策略",
    "agents": "员工定义与装配",
    "skills": "共享方法资产",
    "organization_rules": "全员规章制度",
    "model_connections": "模型连接与凭证",
    "conversations": "对话与轻量交流内容",
    "execution": "Run 生命周期与实际动作",
    "ci_diagnosis": "CI 证据、报告与反馈",
    "api": "HTTP 接入与请求编排",
    "agent_runtime": "Agent 内部运行",
    "llm": "模型技术适配",
}

DIRECTORIES = {
    "backend": "后端应用、迁移、测试与示例；部署代码与验证材料分开",
    "backend/app": "正式应用包；模块按规则和生命周期所有权组织",
    "backend/app/api/routes": "按对外能力分组路由；传输职责不侵入执行器",
    "backend/app/infrastructure": "共享技术机制；不拥有业务规则",
    "backend/app/infrastructure/database": "连接、事务、错误与元数据；所属模型留在业务模块",
    "backend/migrations": "正式结构与数据升级；与应用启动分开执行",
    "backend/migrations/versions": "冻结历史和增量迁移；不改写已存在升级链",
    "backend/tests": "隔离行为、竞争与边界验证；不访问开发业务库或真实上游",
    "backend/experiments": "独立技术验证；不作为正式应用隐式依赖",
    "backend/datasets": "教学与评测示例；不默认进入运行上下文",
    "backend/datasets/travel-expense": "虚构差旅数据包；资料与评分依据分开",
    "backend/datasets/travel-expense/documents": "可用于知识实验的正文；保留来源与生效范围",
    "backend/datasets/travel-expense/evaluation": "审核、题目与参考答案；不泄漏到回答输入",
    "frontend": "浏览器应用和构建配置；与后端通过明确 DTO 协作",
    "frontend/src": "人工维护的前端逻辑；生成资源有单独来源",
    "frontend/src/pages": "按页面业务组织；专用逻辑就近维护",
    "frontend/src/pages/agents": "员工目录、配置与工作入口；草稿和服务器修订分开",
    "frontend/src/pages/brains": "模型连接管理；秘密不保存在浏览器草稿",
    "frontend/src/pages/skills": "方法管理页面；工具许可不伪装为方法正文",
    "frontend/src/pages/knowledge": "当前教学资料和规则入口；真实检索另按业务增量接入",
    "frontend/src/pages/signin": "登录表单与视觉；不依赖工作会话状态",
    "frontend/src/pages/signin/motion": "登录场景动画模型与控制；视觉运行与认证请求分开",
    "frontend/src/pages/design-system": "真实组件展示；正式业务不依赖演示数据",
    "frontend/src/pages/design-system/fixtures": "设计展示示例数据；不冒充业务记录",
    "frontend/src/pages/help": "用户操作帮助；功能与新路由命名同步",
    "frontend/src/components": "可复用展示能力；不访问页面私有 Store",
    "frontend/src/components/ui": "基础 UI 控件；不包含业务授权或调度",
    "frontend/src/components/common": "跨业务展示与布局；专用组件仍留页面",
    "frontend/src/components/avatars": "稳定头像选择与加载；后端只引用标识",
    "frontend/src/components/avatars/svg": "生成的角色组件；从同源成品再生成",
    "frontend/src/components/brand": "品牌展示与源资源；不承担登录业务状态",
    "frontend/src/components/configuration": "实际复用的加载、冲突与草稿提示；具体资源读取由页面提供",
    "frontend/src/components/auth": "身份入口与页面保护；服务端仍执行真实权限",
    "frontend/src/components/organization-rules": "规则管理和继承展示；正文由后端统一维护",
    "frontend/src/components/skills": "方法卡片和当前CI接入展示；通用工具管理未实现",
    "frontend/src/components/theme": "主题切换及图案；不依赖工作会话数据",
    "frontend/src/components/agents": "跨页面员工展示；收藏导航已归导航，配置仍在员工页面",
    "frontend/src/state": "身份、编辑保护、主题和轻量更新通知；资源内容保留页面所有权",
    "frontend/src/state/auth": "当前身份及变更；销毁旧用户作用域",
    "frontend/src/state/configuration": "配置写入失效通知；不建立资源总仓库或路由解析器",
    "frontend/src/state/editing": "未保存修改与导航保护；不与服务端执行状态混合",
    "frontend/src/state/theme": "主题持久偏好与控制；首屏和 React 共用约定",
    "frontend/src/hooks": "真实跨业务 Hook；页面专用 Hook 留在页面模块",
    "frontend/src/lib": "接口、共享数据和普通函数；不反向导入页面或 Context",
    "frontend/src/lib/api": "面向用户操作的公开HTTP契约；不按后端实体强制拆分",
    "frontend/src/lib/models": "共享员工及技能展示模型；不从页面私有类型导出",
    "frontend/src/lib/avatars": "头像清单和注册；生成来源与消费关系可追踪",
    "frontend/src/design-system": "视觉令牌与组件规范；本重构保持现有视觉契约",
    "frontend/public": "浏览器直接消费的静态成品；不放制作工程与秘密",
    "frontend/public/avatars": "正式角色资源；与生成清单同源",
    "frontend/public/brand": "品牌静态成品；由构建脚本生成和校验",
    "frontend/scripts": "前端资源构建与压缩；生成步骤集中可重复",
    "scripts": "跨端开发和文档工具；由根 Makefile 统一调用",
    "scripts/tests": "工具行为回归；验证端口、退出和文档错误",
    "docs": "项目级文档；现行规则、目标方案与历史证据分开",
    "docs/architecture": "实施后的系统协作；目标方案未落地前不改成当前事实",
    "docs/architecture/diagrams": "当前架构图和源；实现时与正文同步更新",
    "docs/engineering": "各端可执行工程标准；不累计实施流水账",
    "docs/reference": "实施后生效的契约；字段事实仍链接代码与迁移",
    "docs/reference/agent-configuration": "员工配置的数据及 API；装配与公开投影一处维护",
    "docs/reference/ci-diagnosis": "专业结果与反馈契约；与通用执行规则分开",
    "docs/reference/diagram": "现行运行时序图；与对应契约一起更新",
    "docs/guides": "开发、配置、迁移和资源操作；明确前提与恢复",
    "docs/learning": "学习路线和代码阅读；不替代正式行为契约",
    "docs/templates": "按需裁剪的文档模板；不强制重复无关章节",
    "docs/proposals": "尚未实施的增量与已实现方案来源；状态以正文为准",
    "docs/proposals/platform-refactor": "本次统一目标设计；替代旧方案的后续边界和命名",
    "docs/proposals/platform-refactor/diagrams": "本次目标图与源；明确未实施而不覆盖当前图",
    "docs/records": "限定时点的评审与验收；原始名称和通过数量保持历史含义",
    "docs/records/diagrams": "历史评审图；不作为当前架构前置",
    "docs/records/diagrams/dependency-review": "一次依赖研究的图与源；保留其证据时点",
    "frontend/src/pages/conversations": "输入、回复与历史页面；按用户交互和对话作用域组织",
    "frontend/src/components/navigation": "外壳导航、搜索与收藏；专用网络和状态不进入通用控件",
    "backend/app/api/routes/conversations": "对话请求与只读观察；只拆有真实复杂度的 API 分组",
    "backend/app/conversations": "交流内容、查询与共享回复流程；同时服务请求和后台，禁止反向导入 API",
}

UI_NAMES = {
    "Badge": "徽标",
    "Bubble": "气泡",
    "Button": "按钮",
    "Collapsible": "折叠",
    "Dialog": "对话框",
    "DropdownMenu": "菜单",
    "Field": "字段",
    "Form": "表单",
    "Input": "输入",
    "InputGroup": "输入组",
    "Message": "消息展示",
    "MessageScroller": "消息滚动",
    "Popover": "浮层",
    "Select": "选择",
    "Switch": "开关",
    "Tabs": "页签",
    "Textarea": "多行输入",
    "Tooltip": "提示",
    "Trace": "执行过程展示",
}

TEST_TOPICS = {
    "test_conversations": "对话、上下文、权限、停止及重试",
    "test_conversation_submission": "原子接受、幂等与回滚",
    "test_conversation_message_state": "消息回复、状态、历史和观察一致性",
    "test_capability_runtime": "真实 SDK 方法加载、预算与授权",
    "test_runtime_streaming": "流式片段、工具轮次和取消关闭",
    "test_agent_identity": "员工姓名、身份提示和历史快照",
    "test_agent_skill_storage": "员工装配约束及整体修改回滚",
    "test_authentication": "账号认证、游客、会话失效和撤销",
    "test_github_signin": "OAuth state、PKCE、身份及安全返回地址",
    "test_api_errors": "应用错误分类、响应脱敏和捕获边界",
    "test_bootstrap": "应用资源装配、启动失败和关闭",
    "test_config": "配置来源、路径、范围和预算合法性",
    "test_configuration_api": "配置接口、修订冲突、参数及公开投影",
    "test_database": "底层约束、事务和写入竞争",
    "test_database_errors": "数据库错误码与约束识别",
    "test_database_error_boundaries": "已知业务冲突、未知异常和删除保护",
    "test_execution_boundaries": "原子发布、不可变历史、故障和依赖方向",
    "test_frontend": "静态资源、压缩缓存、深链与缺失资源",
    "test_llm": "模型工厂、流关闭、错误和未知用量累计",
    "test_migrations": "新旧库升级、数据保留、离线 SQL 和失败回滚",
    "test_model_connections": "连接配置、密文、修订和显式连接检查",
    "test_organization_rules": "共享规则、权限与并发版本替换",
    "test_threads": "工作会话、上下文、权限、停止及重试",
    "test_thread_submission": "首条原子创建、幂等和接受回滚",
    "test_thread_items": "消息、执行联合读取及历史/SSE一致性",
    "test_agent_capabilities": "真实 SDK 的方法加载、预算和授权",
    "test_agent_streaming": "流式内容、工具轮次、迟到片段及取消关闭",
    "test_checkpoint_runtime": "真实子进程重启、预算与完成补发布",
    "test_sqlite_checkpoints": "独立实验的存档隔离与跨进程恢复",
    "test_ci_diagnosis": "专业取证、引用、报告、反馈及取消竞争",
    "test_dev": "端口协同、代理和子进程退出",
    "test_check_docs": "本地文档链接、锚点与索引错误",
}


def moved(source):
    if source in MOVES:
        return MOVES[source]
    if source.startswith("backend/app/execution/sdk/"):
        return source.replace("execution/sdk/", "agent_runtime/")
    return source


def description(path):
    if path in NEW_FILES:
        return NEW_FILES[path]
    if path in FILE_NOTES:
        return FILE_NOTES[path]
    p = Path(path)
    name = p.name
    if name == "__init__.py":
        return "所属 Python 包声明；只保留必要入口，不在导入时运行服务"
    if path.startswith("backend/migrations/versions/"):
        return "冻结的历史结构及数据升级；保留原名和行为防止旧库迁移失真"
    if path.startswith("backend/app/"):
        module = MODULES.get(p.parts[2], "技术机制")
        roles = {
            "models.py": f"{module}的 ORM 与约束；由本模块拥有而不集中业务模型",
            "schemas.py": f"{module}的请求和安全投影；传输校验与事务规则分开",
            "service.py": f"{module}的业务操作；短事务内校验并明确回滚",
            "config.py": f"{module}的部署设置；经统一配置入口解析和校验",
            "README.md": f"{module}的职责、协作与测试入口；不复制完整字段定义",
        }
        if name in roles:
            return roles[name]
        if "/api/routes/" in path:
            topic = {
                "conversations": "对话、回复和问题目录",
                "health": "存活与就绪",
                "auth": "身份与登录",
                "configuration": "配置摘要",
                "public": "公开字段白名单",
                "ci_diagnosis": "CI 专业配置、报告与反馈",
                "agents": "员工配置",
                "skills": "共享方法",
                "model_connections": "模型连接",
                "organization_rules": "全员规则",
            }.get(p.stem, p.stem)
            return f"{topic} HTTP 入口；参数和响应交给传输层、业务规则交给所属服务"
    if path.startswith(("backend/tests/", "scripts/tests/")):
        return f"{TEST_TOPICS.get(p.stem, p.stem)}的隔离回归；保留拒绝、故障与竞争断言"
    if path.startswith("docs/") and p.suffix == ".md":
        source = ROOT / path
        title = p.stem
        if not source.exists():
            old = next((s for s in BASELINE if moved(s) == path), None)
            source = ROOT / old if old else source
        if source.exists():
            title = next(
                (
                    x.removeprefix("# ").strip()
                    for x in source.read_text().splitlines()
                    if x.startswith("# ")
                ),
                title,
            )
        kind = (
            "历史证据"
            if "/records/" in path
            else "增量方案"
            if "/proposals/" in path
            else "现行规则或导航"
        )
        return f"{title}；按{kind}维护，防止目标与当前实现混淆"
    if path.startswith("backend/datasets/"):
        return f"差旅教学的 {name}；保留资料、题目及审核依据的来源和用途隔离"
    if path.startswith("frontend/src/components/ui/"):
        topic = UI_NAMES.get(p.stem, "控件类型与样式约定")
        return f"{topic}基础能力；通过统一控件复用且不绑定业务状态"
    if name.endswith((".test.ts", ".test.tsx")):
        return f"{name.split('.test.')[0]} 的行为回归；随职责改名并保持边界覆盖"
    if "/public/avatars/" in path or "/components/avatars/svg/" in path:
        return f"角色成品或生成组件 {name}；与头像清单同源，不在架构重构中重做素材"
    if "/public/brand/" in path or p.suffix in (".svg", ".png"):
        return f"静态或图示资源 {name}；保留来源并按对应构建或文档流程维护"
    if path.startswith("frontend/scripts/"):
        return f"{p.stem} 资源构建；从来源再生成并保持交付可重复"
    if name.endswith(("Styles.ts", "styles.css")) or p.suffix == ".css":
        return "所属页面或组件的样式与令牌；视觉职责就近维护而不侵入业务状态"
    if path.startswith("frontend/src/pages/conversations/"):
        topics = {
            "ConversationComposer": "输入及可用方法选择",
            "ConversationControls": "指定 回复的操作控件",
            "ConversationHistory": "会话历史入口",
            "ConversationMessage": "对话内容和回复状态",
            "ConversationOutline": "问题目录与正文定位接入",
            "ConversationPanel": "工作会话页面组合",
            "ConversationQuestionPreview": "问题短预览",
            "ConversationRuler": "刻度浏览与键盘触摸交互",
            "ConversationsPage": "工作会话列表与路由入口",
            "RunActions": "真实动作折叠与本地分页",
            "conversationTestHelpers": "工作会话测试数据与替身",
        }
        return f"{topics.get(p.stem, '工作会话的局部交互')}；专用职责留在本模块，不制造全局状态"
    if path.startswith("frontend/src/pages/"):
        area = p.parts[3]
        return f"{area} 页面中的 {p.stem}；页面专用实现就近维护并复用共享契约"
    if path.startswith("frontend/src/state/"):
        area = p.parts[3]
        return f"{area} 共享状态中的 {p.stem}；按身份、配置或主题生命周期隔离"
    if path.startswith("frontend/src/components/"):
        area = p.parts[3]
        return f"{area} 复用能力中的 {p.stem}；展示与所属业务服务分开"
    if path.startswith("frontend/src/hooks/"):
        return f"{p.stem} 通用交互；仅跨业务真实复用时留在共享层"
    if path.startswith("frontend/src/lib/"):
        return f"{p.stem} 共享类型或普通能力；不反向依赖页面和 React Context"
    if path.startswith("frontend/src/design-system/"):
        return f"{name} 视觉规范或令牌；保持主题和组件一致且不随业务改名漂移"
    if name == "AGENTS.md":
        return "端内协作导航；规则正文集中在工程与契约文档"
    if name == "README.md":
        return "所属模块入口、职责与验证导航；详细规则只维护一份"
    if name == ".env.example":
        return "部署参数示例；只提供占位值而不保存真实秘密"
    if name in ("uv.lock", "pnpm-lock.yaml"):
        return "依赖精确锁定；使环境与构建可复现"
    if name in ("pyproject.toml", "package.json", "pnpm-workspace.yaml"):
        return "依赖、命令与检查清单；与锁文件同步维护"
    if name in ("THIRD_PARTY_NOTICES.md", "LICENSE"):
        return "第三方来源和许可说明；保留合法使用与维护依据"
    if path.startswith("docs/") and p.suffix == ".py":
        return "对应文档图示的可编辑生成源；改变设计后同步再生成"
    return f"{name} 工具或构建配置；沿用所属工具约定并集中检查"


def dir_description(path):
    if path in DIRECTORIES:
        return DIRECTORIES[path]
    if path.startswith("backend/app/") and path.count("/") == 2:
        return f"{MODULES.get(Path(path).name, '所属能力')}模块；按业务与运行所有权聚合"
    if path.startswith("docs/proposals/"):
        return "所属专题增量及图示；状态以方案正文为准，实施后回写现行契约"
    if path.startswith("frontend/public/avatars/"):
        return "对应角色的同源静态成品；与选择器及生成清单保持一致"
    return "所属专题或资源的内部组织；就近维护并避免跨模块私有依赖"


def render_tree(paths):
    tree = {}
    for path in sorted(paths):
        node = tree
        for part in path.split("/"):
            node = node.setdefault(part, {})
    lines = ["niuma-crew/  # 实际工程根目录；模块化单体与前端独立构建，按职责协作"]

    def walk(node, prefix="", parent=""):
        entries = sorted(node.items(), key=lambda item: (not bool(item[1]), item[0]))
        for index, (name, children) in enumerate(entries):
            last = index == len(entries) - 1
            path = f"{parent}/{name}" if parent else name
            note = dir_description(path) if children else description(path)
            assert ";" in note or "；" in note, (path, note)
            assert any("\u4e00" <= c <= "\u9fff" for c in note), path
            label = name + ("/" if children else "")
            lines.append(f"{prefix}{'└──' if last else '├──'} {label}  # {note}")
            if children:
                walk(children, prefix + ("    " if last else "│   "), path)

    walk(tree)
    return "\n".join(lines)


REMOVED = {
    "backend/app/execution/schemas.py": "已删除旧 Run API 响应类型；助手及公开步骤归 conversations/schemas.py，确有宿主复用的数据才归 "
    "execution/contracts.py",
    "frontend/src/components/ui/Popover.tsx": "当前没有调用、示例或测试；已删除未使用控件，不为未来需求预存封装",
}


def main():
    assert len(BASELINE) == len(set(BASELINE)), "duplicate baseline file"
    assert set(REMOVED) <= set(BASELINE), "removed path is not in baseline"
    assert set(MOVES) <= set(BASELINE), "move source is not in baseline"
    assert set(SPLITS) <= set(BASELINE), "split source is not in baseline"
    assert not (set(REMOVED) & set(MOVES)), "removed source also moved"
    targets = set(
        subprocess.check_output(
            ["rg", "--files", "--hidden", "-g", "!.git", "-g", "!*.tsbuildinfo"],
            cwd=ROOT,
            text=True,
        ).splitlines()
    )
    for source in BASELINE:
        if source not in REMOVED:
            assert moved(source) in targets, (source, moved(source))
            for dest in SPLITS.get(source, []):
                assert dest in targets, (source, dest)
    assert set(NEW_FILES) <= targets, "planned file is not implemented"
    tree = render_tree(targets)
    docs_tree = render_tree({p for p in targets if p.startswith("docs/")})
    tree_doc = f"""# 完整目标工程树与文档树

本文为[已采纳方案](README.md)的实施结构附录，由[生成器](build-target-tree.py)根据当前实际文件扫描，并与[重构前基线](inventory.json)核对生成。基线 {len(BASELINE)} 个工程文件均在[逐文件去向](file-map.md)中有记录；本次实际工程共 {len(targets)} 个文件。

每个目录和文件都有中文职责与设计原因，不用省略号代替节点。完整工程树包含后端、前端、测试、迁移、构建、教学资料、品牌、头像和文档；文档树另行完整展开，便于阅读。源代码旁 README、AGENTS 和设计系统文档同样在工程树中逐项列出。

本树是 P1—P4 当前实施范围的实际源码快照；execution/sdk 已迁入 agent_runtime。服务归属与依赖详见[请求与共享流程](service-boundaries.md)。没有为未来 Task、Goal、Plan、通用工具或知识能力预建文件树；接入条件见[后续能力](extensions.md)。依赖环境、缓存、被忽略构建产物、本地 .env、数据库、密钥和外部归档不属于此工程文件清单。

## 完整目标工程树

§§§text
{tree}
§§§

## 完整目标文档树

本树包含全部现有 docs，生效规则已合入现行正文。历史 records 保留当时名称和检查数量，不把旧建议改成新事实。分层图及图源与本轮职责调整同步维护，具体数据与接口约束仍以专题正文为准。

§§§text
{docs_tree}
§§§

每个目标均核对实际存在。具体来源、删除和新增原因见[file-map](file-map.md)与[实施计划](migration.md)。文档与图的生成检查不能替代业务测试。
""".replace("§", chr(96))
    (HERE / "target-tree.md").write_text(tree_doc)
    rows = []
    for source in BASELINE:
        if source in REMOVED:
            rows.append(
                f"| §{source}§ | 移除旧文件，职责按右栏归位 | 删除/归位 | {REMOVED[source]} |"
            )
            continue
        dest = moved(source)
        destinations = list(dict.fromkeys([dest, *SPLITS.get(source, [])]))
        state = (
            "拆分/归位"
            if source in SPLITS
            else "按职责改名/移动"
            if dest != source
            else "保留职责与路径"
        )
        if source.startswith(("backend/migrations/versions/", "docs/records/")):
            state = "历史冻结，必要时补适用说明与链接"
        destination_cell = "、".join(f"§{path}§" for path in destinations)
        rows.append(f"| §{source}§ | {destination_cell} | {state} | {description(dest)} |")
    mapping = """# 重构前工程文件的完整去向

本文与[目标树](target-tree.md)共同核对[总方案](README.md)。本轮复核前每个基线文件恰好一行；拆分行可以有多个目标，同一目标接收多个来源表示有意归位，不复制另一套权威状态。

“保留职责与路径”表示没有移动，不代表该文件一定修改过。只有依赖、契约或行为实际受影响时才改对应引用与测试。历史迁移冻结，当前规则已回写现行契约；实际检查见实施记录。

Conversation、Run、对外 conversations 与公开 useConversation/useMessage 保留。改名、合并与拆分均有实际职责依据，不做全栈词语替换。对话请求服务放在 API 分组，共享准备、授权和发布回 conversations；其他业务 service 保留所属模块，不保留全局 use_cases/application。配置页面、导航和品牌按实际调用归位，不为每个路由新建服务。未来能力按真实增量再确定结构。

| 当前文件 | 目标去向 | 处理 | 职责与原因 |
| --- | --- | --- | --- |
""" + "\n".join(rows)
    mapping += f"\n\n覆盖检查：基线 {len(BASELINE)} 个文件，映射 {len(rows)} 行，无遗漏；目标共 {len(targets)} 个文件。每个新增文件也有中文职责与原因，不含假想未来模块。\n"
    (HERE / "file-map.md").write_text(mapping.replace("§", chr(96)))
    print(
        f"Baseline={len(BASELINE)}; mapped={len(rows)}; target={len(targets)}; removed={len(REMOVED)}"
    )


if __name__ == "__main__":
    main()

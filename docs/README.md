# NiumaCrew 文档索引

- [NiumaCrew 与 StaffDeck 产品及技术对比](records/niuma-staffdeck-comparison-2026-11-01.md)：2026-11-01 源码调查，覆盖功能差异、具体实现、发展优先级及验收方法；属于研究建议，未改变现行契约。

- [对话页右侧辅助栏](proposals/conversation-sidebar.md)：正文与默认展开的历史/能力侧栏，复用真实会话和个人知识库；[验收记录](records/conversation-sidebar.md)。

- [柔和工作台与紧凑卡片试版](proposals/soft-workspace-preview.md)：可恢复的外壳与视觉密度调整，待用户反馈。

- [员工目录顶部分页](proposals/agent-directory-pagination.md)：搜索与岗位筛选靠左、分页靠右，沿用服务端分页；[验收记录](records/agent-directory-pagination.md)。

开发者与 AI 共用本索引。先按当前任务读取，再沿正文进入代码、测试或模块说明。现行文档描述已实现行为；方案定义增量，记录保留限定版本的证据。文档与代码的分工见[组织与维护规范](documentation.md)。

## 按任务开始

| 任务               | 阅读入口                                                                                                                                                                                                                                                                                    |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 第一次理解平台     | [项目 README](../README.md) → [平台与功能](product/README.md) → [使用流程与执行链路](product/workflows.md)；无需先读代码或历史方案                                                                                                                                                          |
| 首次运行           | [项目 README](../README.md) → [本地开发](guides/local-development.md) → [后端配置与维护](guides/backend-operations.md)                                                                                                                                                                      |
| 理解系统           | [系统架构与选型](architecture/overview.md) → [前端业务与工程架构](architecture/frontend.md) / [后端业务与工程架构](architecture/backend.md) → 模块 README → [代码链路阅读](learning/reading-code.md)                                                                                        |
| 核对实际源码架构   | [源码调查](codebase/ARCHITECTURE.md) → [技术栈](codebase/STACK.md)、[目录与入口](codebase/STRUCTURE.md)、[工程约定](codebase/CONVENTIONS.md)、[外部集成](codebase/INTEGRATIONS.md)、[测试与验证](codebase/TESTING.md)、[风险与差异](codebase/CONCERNS.md)；含 2026-10-31 调查证据与未覆盖项 |
| 修改已有功能       | [共享约定](engineering/shared.md) → 适用[前端手册](engineering/frontend.md) / [后端手册](engineering/backend.md) → 下方现行契约 → 模块与测试                                                                                                                                                |
| 修改视觉与组件     | [设计系统](../frontend/src/design-system/README.md) → [对象、动作与确认](../frontend/src/design-system/resource-language.md)、[类型与空间](../frontend/src/design-system/component-catalog.md) / [布局](../frontend/src/design-system/layout.md) → 现行组件、颜色与真实样板                 |
| 新增能力或变更边界 | 当前契约与代码 → [方案索引](proposals/README.md) → 受影响模块；生效后回写现行文档                                                                                                                                                                                                           |
| 排查运行与数据问题 | [后端操作](guides/backend-operations.md)、[数据库配置](guides/database-configuration.md) → 当前日志、模块与测试 → 按需查看[历史记录](records/README.md)                                                                                                                                     |
| 学习项目           | [学习路线](learning/roadmap.md) → [代码阅读](learning/reading-code.md) → [教学数据](../backend/datasets/travel-expense/README.md)                                                                                                                                                           |
| 新建或整理文档     | [文档规范](documentation.md)、[增量方案模板](templates/design.md)；检查命令 make check-docs                                                                                                                                                                                                 |

## 当前架构与工程标准

产品层从[平台说明](product/README.md)理解功能及对象关系，从[使用流程](product/workflows.md)理解操作、结果和执行链路。架构层解释当前模块、依赖与选型；模块 README 先讲产品作用，再讲设计、文件和局部约束。字段和完整接口继续由现行契约维护，方案与记录不作为新人阅读的前置。

| 入口                                                                                                                                  | 范围                                           |
| ------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| [总体架构](architecture/overview.md)、[领域术语](architecture/domain-glossary.md)                                                     | 当前能力、模块、运行与概念                     |
| [前端架构](architecture/frontend.md)、[后端架构](architecture/backend.md)、[Agent 边界](architecture/agent-runtime.md)                | 当前代码协作与生命周期，目标演进另见方案       |
| [共享约定](engineering/shared.md)                                                                                                     | 代码、数据来源、运行命令、按风险选择验证与交付 |
| [前端工程手册](engineering/frontend.md)、[后端工程手册](engineering/backend.md)                                                       | 目录、命名、依赖、类型、状态与事务边界         |
| [前端 README](../frontend/README.md)、[后端启动入口](../backend/app/main.py)、[后端模块入口](../backend/README.md#模块架构与阅读入口) | 端内模块与实际维护入口                         |
| [前端共享数据标准](../frontend/src/state/README.md)                                                                                   | Provider、按记录订阅、请求与写入同步及后续接入 |
| [运行脚本](../scripts/README.md)、[前端构建脚本](../frontend/scripts/README.md)                                                       | 进程启动与资源生成职责                         |

## 现行契约

| 主题           | 权威入口                                                                                                                                                                                                                                                                                           |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 身份与权限     | [身份、会话与访问控制](reference/auth.md)、[GitHub 登录](reference/github-signin.md)                                                                                                                                                                                                               |
| 应用错误       | [访问异常与恢复接入](reference/failures.md)：统一事实、策略、页面/局部反馈及接入示例；[错误分类与 HTTP 转换](../backend/app/api/README.md#应用错误分类与-http-转换)：后端公开协议和 OAuth/SSE 例外                                                                                                 |
| 员工与共享技能 | [API 与公开投影](reference/agent-configuration/api.md)、[当前配置数据](reference/agent-configuration/data.md)、[资源数量摘要](reference/agent-resource-summary.md)                                                                                                                                 |
| 当前持久化     | [数据模型与约束入口](reference/data-model.md)，字段事实链接 ORM 和正式迁移；Message 保存输入与最终正文，Run 记录处理，专业报告独立保存，checkpoint 只负责按 Run 恢复 SDK 状态；[数据库错误边界](../backend/app/infrastructure/database/README.md#数据库错误与业务错误)说明技术识别与业务冲突的分工 |
| 模型连接       | [大脑与凭证契约](reference/model-connections.md)                                                                                                                                                                                                                                                   |
| 知识库         | [原件暂存、后台处理与三种检索](reference/knowledge.md)                                                                                                                                                                                                                                             |
| 规章制度       | [单份规则与全员继承](reference/organization-rules.md)                                                                                                                                                                                                                                              |
| 对话与执行     | [对话与历史](reference/conversations.md)、[当前运行、步骤与读取](reference/runtime.md)、[会话 Hook 与消息关系](../frontend/src/pages/conversations/README.md#领域关系与-hook-命名)、[正文与问答导航接入](../frontend/src/pages/conversations/README.md#导航数据流)                                 |
| 登录与主题     | [登录页](reference/signin.md)、[主题模式](reference/theme.md)、[品牌](reference/brand.md)                                                                                                                                                                                                          |
| 设计与资源     | [设计系统展示与适配](reference/design-system.md)、[头像资源](reference/avatar-assets.md)、[头像组件](../frontend/src/components/avatars/README.md)、[角色设定](../frontend/src/components/avatars/CHARACTERS.md)                                                                                   |
| 前端模块       | [员工配置](../frontend/src/pages/agents/README.md)、[知识页与规章制度入口](../frontend/src/pages/knowledge/README.md)                                                                                                                                                                              |

## 操作与学习

- [工具、文件与沙箱契约](reference/agent-tools.md)、[接入与部署](guides/agent-tools.md)、[本轮实施与验证](records/agent-foundations.md)：通用 MCP、原生文件与代码执行。

- [从页面逐步观测运行机制](learning/observing-runtime.md)：按用户操作追踪接口、后台、数据与异常；[本次实施记录](records/platform-refactor-implementation.md)列明实际验证与启动结果。

- [本地开发与统一命令](guides/local-development.md)：端口、代理、进程清理。
- [后端运行、配置与维护](guides/backend-operations.md)：配置表、账号、迁移、模型、运行器及静态交付。
- [数据库与本地文件配置](guides/database-configuration.md)：路径解析、配置边界和维护约束。
- [应用资源与历史素材维护](guides/assets.md)：正式资源、生成器、临时与长期证据。
- [学习路线](learning/roadmap.md)、[代码阅读](learning/reading-code.md)：学习掌握标准与当前实现分开。

## 方案与历史

- [员工配置布局与操作调整](proposals/agent-editor-layout.md)：基础配置、指令与知识主辅布局及按草稿状态显示的页头操作已实施，见[本轮验收](records/agent-editor-layout.md)。

- [焦点轮廓与滚动裁切](proposals/focus-visibility.md)：滚动区域统一预留焦点空间，Tab 与贴边交互采用内侧轮廓；实际覆盖见对应验收记录。

- [下拉选择统一入口](proposals/unified-select.md)：SelectField 完整配置接入与重复拼装迁移，实际结果见[验收记录](records/unified-select.md)。

- [表单控件与主题焦点统一](proposals/unified-form-controls.md)：统一 Field 组合、输入/选择/搜索和输入组的中性灰焦点；当前规范见设计系统。

- [搜索输入防抖](proposals/input-debounce.md)：自动远程搜索与本地筛选、手动提交的边界，实际盘点与验证见[验收记录](records/input-debounce.md)。

- [官方基础能力包与可靠交付](proposals/skills-and-mcp/foundation-capability-packages.md)：可执行草案，未实施；以八产品交叉核验为依据，给出信息获取、文件成果与按环境开放计算的产品范围、模块/契约增量、六个交付单元、质量成本门槛及回退路径。

- [后端模块职责与稳定边界设计](proposals/backend-module-boundaries.md)：已采纳并完成源码改造；包含 CI 退役、全部应用文件去向与用途、账号绑定和业务/执行边界；[本轮记录](records/backend-module-boundaries.md)区分隔离检查与[当前本机升级及真实链路验收](records/backend-module-boundaries.md#本机环境升级与真实链路验收)，其他环境升级按操作指南执行。

- [知识库建设方案导航](proposals/knowledge-assistant/implementation.md)：方案正文在 Notion 分层维护；独立 POC 及[多库文本入库增量](proposals/knowledge-assistant/library-upload.md)已实施，实际结果见[页面与迁移记录](records/knowledge-library.md)。[硅基流动向量接入](proposals/knowledge-assistant/siliconflow-embedding.md)已实施，验证见[向量接入记录](records/siliconflow-embedding.md)；本轮[资料建设闭环](proposals/knowledge-assistant/document-processing.md)已实施，见[验收记录](records/knowledge-document-processing.md)；另已实施[短章节合并与处理预览](proposals/knowledge-assistant/chunk-preview.md)，见[实测记录](records/knowledge-chunk-preview.md)；[员工个人多库装配与问答](proposals/knowledge-assistant/employee-knowledge.md)已完成方案评审及实施，见[验收记录](records/employee-knowledge.md)；完整增量向量仍待实施。

- [工作台组件与布局规范迁移](proposals/workspace-layout.md)：组件分类、容器预算与响应式已接入正式页面；设计系统提供规范、示例与验收入口。

- [API 职责与业务入口整理](proposals/api-responsibilities.md)：统一 HTTP、业务事务、目录查询和装配，实际结果见[验收记录](records/api-responsibilities.md)。

- [工作台共享数据 Provider](proposals/workspace-shared-data.md)：已实现统一的按记录订阅、共享查询与领域操作；替换旧局部失效方案，实际检查见[验收记录](records/workspace-shared-data.md)。
- [员工收藏与目录更新](proposals/agent-directory-updates.md)：局部方案的历史设计，现已由共享数据层替换。

- [平台工作流与执行边界重构方案](proposals/platform-refactor/README.md)：已实施当前范围；保留 Conversation/Run，正文与专业数据归位、隔开宿主与 Agent，分别设计 API 和前端；附[服务归属与调用](proposals/platform-refactor/service-boundaries.md)、完整中文注释树及分期验收。
- [待实施方案](proposals/README.md)：知识助手、标准技能与通用 MCP、能力数据与运行演进及其他未定增量。[后端领域与执行重设计](proposals/backend-architecture/README.md)已实现第一阶段执行与稳定消息边界，以及 auth 合并和首轮文件职责整理；后续任务/计划/目标仍为方案。员工工作入口、任务成果及执行阶段见[分阶段改造方案](proposals/agent-workspace/README.md)。
- [Agent 基础能力接入](proposals/skills-and-mcp/official-agent-tools.md)：通用工具、搜索与网页、文件、Sandbox 和代码执行的详细方案及 T0–T4 验收；[架构边界](proposals/skills-and-mcp/foundation-boundaries.md)明确模块所有权、跨边界契约和资源生命周期；部署细节与开源分工见[OpenSandbox 附录](proposals/skills-and-mcp/opensandbox-self-hosted.md)。当前本机模型、HTTP MCP 与虚拟文件已[补验](records/backend-module-boundaries.md#本机环境升级与真实链路验收)，沙箱及其他环境仍需单独验收。
- [技能库统一展示与连接装配改造](proposals/skills-and-mcp/unified-capability-library.md)：Token MCP 与联合列表部分已实施，完整规则见当前 MCP 契约；后续继续复用官方 MCPConfig/MCPAdapter、标准 Skill 与按需工具，保留统一目录、内置展示、共享/专用 Key 和原子装配；含模块图和 C01–C32 改动清单。
- [MCP 接入与员工装配](reference/mcp.md)：当前 HTTP/可信 stdio、Token/env、统一能力库、账号目录和个人/共用装配；OAuth 后置。
- [标准目录与快捷接入验收](records/portable-capability-onboarding.md)：MCP 统一表单/描述导入，以及可配置 `.agents/skills` 同步、别名与员工关联保留。
- [能力接入与装配最终实施计划](proposals/skills-and-mcp/execution-plan.md)：本轮实施基线，含独立评审结果、可信 stdio、标准包、前端交互和执行核验边界。
- [能力库与员工装配界面改造](proposals/skills-and-mcp/capability-library-and-assembly-ui.md)：已由最终实施计划落地，保留实施前分析与布局依据。
- [标准 Skill 包与执行可靠性增量](proposals/skills-and-mcp/skill-package-and-runtime-integration.md)：已由最终实施计划落地，保留字段、存储与协议取舍；[只读核查](records/skill-mcp-integration-review.md)记录实施前缺口。
- [可复用工作流程草案](proposals/configurable-workflows.md)：PR 审批引出的模板、员工绑定、事件触发、人工确认与外部提交边界；讨论草案，未采纳、未实施。
- [独立沙箱服务详细设计](proposals/skills-and-mcp/sandbox-service.md)：待实施；Mac/Linux 配置、容量与队列、API/状态/数据、文件与技能执行、回收、工程拆分及验收矩阵。
- [评审与验收记录](records/README.md)：原始时点、方法、实际结果和限制；退出默认开发阅读路径。

新增、移动或改变职责时更新相应入口。同一规则详细定义只保留一处，索引不复制正文。

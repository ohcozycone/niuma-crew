# 待实施方案索引

- [工程评审后的可靠性与验证增量](engineering-review-reliability.md)：已完成验证基线、生命周期清理、执行准备类型、错误子类与边界守卫；[实际验收](../records/engineering-review-reliability.md)。

- [对话页右侧辅助栏](conversation-sidebar.md)：默认展开、可收起，承载员工历史与能力；不加入任务入口。

- [柔和工作台与紧凑卡片试版](soft-workspace-preview.md)：可恢复的外壳与视觉密度调整，待用户反馈。

- [员工目录顶部分页](agent-directory-pagination.md)：已实施查询工具栏重排、shadcn/ui 纯箭头分页与现有分页接口接入。

- [员工配置布局与操作调整](agent-editor-layout.md)：基础配置、指令与知识主辅布局及按草稿状态显示的页头操作已实施。

- [焦点轮廓与滚动裁切](focus-visibility.md)：统一处理表单、Tab、搜索和能力列表的焦点裁切，保留必要滚动与动画。

- [下拉选择统一入口](unified-select.md)：已将页面重复拼装收拢到 SelectField，统一选项、图标、禁用及弹层配置，并以 ESLint 约束后续接入。

[表单控件与主题焦点统一](unified-form-controls.md)：沿用 shadcn Field 与现有 Base UI 适配，统一字段组合、中性灰焦点与输入组边界。

- [搜索输入防抖](input-debounce.md)：已实施统一远程搜索的输入提交、中文组词与清空/回车行为；本地筛选和显式提交不延迟。

- [全站设计语言统一与员工配置打磨](site-design-language.md)：已采纳并接入正式前端；盘点、规范依据与迁移说明，知识库绑定仍为独立功能增量；现行规则与验证从正文进入。

- [员工知识库装配与问答](knowledge-assistant/employee-knowledge.md)：经独立sub评审后实施，个人装配、多库召回、受管工具及正式引用；验证见验收记录。
- [短章节合并与处理预览](knowledge-assistant/chunk-preview.md)：已实施同父短章节合并、规则临时调整及只读分页预览，实际样例比较见验收记录。
- [知识库资料建设闭环](knowledge-assistant/document-processing.md)：已实施原件暂存、手动持久任务、逐文件关键词发布、库级规则和全局上传浮层；员工挂载及完整增量向量后续推进。
- [知识库检索测试与配置入口](knowledge-assistant/retrieval-testing.md)：已实施；大脑与向量入口分开，配置弹窗、检索优先布局和 RRF 混合检索。

- [共享样式组件完整封装](component-encapsulation.md)：已实施完整组合封装；知识卡片经用户确认，复用员工同源卡片、共享内容容器与通用知识图标；实际结果见[记录](../records/component-encapsulation.md)。

- [官方基础能力包与可靠交付](skills-and-mcp/foundation-capability-packages.md)：可执行草案，未实施；在现有 MCP、Skill、文件和执行边界上增加官方配方、信息结果适配、预算内最终回答、员工装配与任务评测，分六个交付单元推进。

- [知识库列表与文档入库增量](knowledge-assistant/library-upload.md)：已实施；多知识库页面、受控文本上传、切片和 BM25，当前范围不含员工绑定或正式聊天，实施状态见正文。
- [知识库页面密度调整](knowledge-assistant/page-density.md)：已实施多列资源网格及文档优先布局，上传与用途说明按需展开，保留重试和离开保护；现行卡片沿用共享组件规范。

- [后端模块职责与稳定边界设计](backend-module-boundaries.md)：已采纳，源码改造已落地；完整应用文件树、CI 退役、账号绑定与业务/执行分工，独立 worker 仍为有条件的后续增量。

- [工作台组件与布局规范迁移](workspace-layout.md)：已实现；完整类型、空间预算、容器推导与同源样例在设计系统维护，实际结果见实施验收。
- [工作台共享数据 Provider](workspace-shared-data.md)：已实现固定 Context 实例、按记录订阅、共享查询和领域写操作。
- [员工收藏与目录更新](agent-directory-updates.md)：历史局部方案，已被共享数据 Provider 取代。

基础工具与 Token MCP 已实现，规则见[MCP 契约](../reference/mcp.md)。员工共用一份定义，使用者绑定本人连接或使用明确共用账号；旧的私人员工、广场与发布复制方案已撤回，OAuth 暂缓。本轮[最终实施计划](skills-and-mcp/execution-plan.md)经三方独立评审并落地，覆盖能力库/装配 UI、可信 stdio、标准 Skill 包和结果核验；证据见[实施验收](../records/capability-integration-implementation.md)。[可复用工作流程草案](configurable-workflows.md)讨论模板、员工绑定、触发与人工确认，未采纳、未实施。

新增[独立沙箱服务详细设计](skills-and-mcp/sandbox-service.md)：Mac/Linux 共用接入，独立进程、总容量、等待队列、接口与数据、回收及验收；仅设计，尚未实施。

[API 职责与业务入口整理](api-responsibilities.md)：已完成 HTTP 与业务事务归位、联合目录、依赖装配、读取模型及 API README 治理，见[验收记录](../records/api-responsibilities.md)。

方案描述有效需求与目标增量，采纳不等于实现。现行功能见[主索引](../README.md#现行契约)，实施后将生效细则合入现行正文；历史方法与结果由[记录](../records/README.md)保存。

[知识库建设方案导航](knowledge-assistant/implementation.md)：独立 POC 与多库文本入库已实施，真实向量及员工聊天未接入；方案正文已在 Notion 按路线判断、LangChain 选型、入库/召回两条主线及模块子页拆分。D01—D08 集中记录建议与代价；已补最小实现契约、暂定实验配置和 C 端组织建议，参数仍待验证；仓库只保留导航与工程契约入口。

[SQLite checkpoint 聊天接入](sqlite-checkpoint-chat.md)：隔离实验及正式 Conversation/Runner 已接入；执行起点直接读取会话引用，历史从存档读取，普通聊天重启自动恢复。

| 方案                                                                             | 范围与状态                                                                                                        |
| -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| [平台工作流与执行边界重构方案](platform-refactor/README.md)                      | 当前范围已实施；保留 Conversation/Run，正文和专业数据归位、隔离宿主与 Agent；现行契约及实际验收见方案导航         |
| [应用错误分类整理](service-errors.md)                                            | 已实现；七类应用错误、统一 HTTP 转换与捕获边界                                                                    |
| [访问异常页面与恢复链路](error-pages.md)                                         | 保留44项分类与交互；404配图及弹性排版已认可，当前正式接线见统一接入方案                                           |
| [访问异常统一接入](error-handling-integration.md)                                | 当前工程错误事实、中央策略/组件、状态适配和静态兜底；独立评审后直接实施，实际进度见正文                           |
| [Agent 模型与初始基线重建](agent-model-rebuild.md)                               | 已实现；单份初始迁移，实际业务库与 checkpoint 已重建并验证                                                        |
| [员工名称唯一与运行身份](agent-name-identity.md)                                 | 已实现；名称唯一约束、创建与改名校验及姓名提示词                                                                  |
| [对话布局与历史读取](conversation-layout.md)                                     | 已实现；正文与导航边界收拢、可见问答组高亮、提问定位与预览，以及历史位置保持                                      |
| [会话状态管理](conversation-state-management.md)                                 | 已实现；局部 hook、首条原子提交、同键重试、停止确认与只读重连                                                     |
| [对话消息与执行步骤统一读取](conversation-message-state.md)                      | 已实现；history 与 SSE 携带同一 Run，步骤读取不再请求接口                                                         |
| [会话与消息访问边界](conversation-hooks.md)                                      | 已实现；useConversation/useMessage，共享读取与按消息绑定操作                                                      |
| [CI 凭证迁移到工具连接](skills-and-mcp/ci-connection-migration.md)               | 已撤回；CI 试验整体移除，不再实施专用凭证迁移，删除范围见后端稳定边界方案                                         |
| [对话执行过程的组件组合与数据映射](conversation-execution-display.md)            | 已实现；官方 shadcn/ui、可折叠执行过程与最终回答、按需读取步骤                                                    |
| [后端领域与执行架构重设计](backend-architecture/README.md)                       | 阶段 A、auth 合并及首轮职责整理已实现；后续目标由平台重构总计划接替                                               |
| [数字员工目标数据模型](agent-capabilities/README.md)                             | 待实施增量；具体阶段以正文为准                                                                                    |
| [能力资源目标字段与约束草案](agent-capabilities/data.md)                         | 待实施增量；具体阶段以正文为准                                                                                    |
| [能力后续阶段迁移与验收计划](agent-capabilities/migration.md)                    | 待实施增量；具体阶段以正文为准                                                                                    |
| [数字员工运行与读取契约](agent-capabilities/runtime.md)                          | 待实施增量；具体阶段以正文为准                                                                                    |
| [runtime 重构与执行过程展示](runtime-refactoring.md)                             | 已实现；技能职责收拢、流式回答、技能/工具步骤与思考展示                                                           |
| [运行配置集中管理](runtime-configuration.md)                                     | 已实现；执行预算统一配置、快照冻结与中文注释                                                                      |
| [前端精简的待核对增量](frontend-simplification.md)                               | 待实施增量；具体阶段以正文为准                                                                                    |
| [项目知识助手最小闭环](knowledge-assistant/README.md)                            | 多库文本入库已实施；员工问答及后续计划待实施                                                                      |
| [P1 与后续阶段](knowledge-assistant/access.md)                                   | 多库文本入库已实施；员工问答及后续计划待实施                                                                      |
| [知识助手首个学习迭代与开发任务](knowledge-assistant/plan.md)                    | 多库文本入库已实施；员工问答及后续计划待实施                                                                      |
| [免费模型的后续方向（未实现）](member-model-access.md)                           | 待实施增量；具体阶段以正文为准                                                                                    |
| [多份规则建议（待确认，未实现）](organization-rules.md)                          | 待实施增量；具体阶段以正文为准                                                                                    |
| [平台后续能力的接入边界](platform-evolution.md)                                  | 待实施增量；具体阶段以正文为准                                                                                    |
| [员工工作页与任务执行的分阶段改造](agent-workspace/README.md)                    | 草案；W1 工作入口、W2 任务成果、W3 等待恢复、W4 自动交办，均未实施                                                |
| [产品定位、差异化与企业收益验证](product-validation.md)                          | 待实施增量；具体阶段以正文为准                                                                                    |
| [研发研究员最小闭环](research-assistant.md)                                      | 待实施增量；具体阶段以正文为准                                                                                    |
| [标准 Agent Skills 与通用 MCP 接入](skills-and-mcp/README.md)                    | 待实施增量；具体阶段以正文为准                                                                                    |
| [Agent 基础能力接入方案](skills-and-mcp/official-agent-tools.md)                 | 自托管选型已采纳；通用工具、联网、文件、Sandbox 与代码执行的通俗说明及 T0–T4 验收，接线已实现，真实上游待环境验收 |
| [基础能力与现有架构的边界](skills-and-mcp/foundation-boundaries.md)              | 已复审；模块归属、跨边界契约、数据/资源生命周期、恢复范围与实施检查点，接线已实现，真实上游待环境验收             |
| [技能库统一展示与连接装配](skills-and-mcp/unified-capability-library.md)         | Token MCP 与联合列表部分已实施；标准包等剩余增量待实施，已撤回的私有/复制方向不作依据                             |
| [MCP 平台接入与能力装配](skills-and-mcp/mcp-platform-integration.md)             | 原探索方案；Token 范围由实施增量与当前契约接替，OAuth 暂缓                                                        |
| [私人员工、员工广场与个人授权](skills-and-mcp/private-agents-and-gallery.md)     | 已被 Token 实施增量取代；不实施广场、独立发布或复制员工                                                           |
| [能力库与员工装配界面改造](skills-and-mcp/capability-library-and-assembly-ui.md) | 已由最终实施计划落地；保留实施前分析和布局依据                                                                    |

- [MCP Token 实施增量](skills-and-mcp/mcp-token-implementation.md)：共享员工定义、个人/共用账号、统一能力库；不实施 OAuth 和员工复制。
- [标准 Skill 包、受管理 stdio 与执行可靠性](skills-and-mcp/skill-package-and-runtime-integration.md)：已由最终实施计划落地；保留标准、存储与协议取舍。

- [能力接入与装配最终实施计划](skills-and-mcp/execution-plan.md)：汇总有效需求、模块边界、三方评审修订与实施验收；OAuth、员工复制和独立沙箱重建不在本轮范围。

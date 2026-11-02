# 全工程职责与引用复核

本文补充[总方案](README.md)，作为本次统一修订的依据。2026-10-27，推荐草案，尚未实施。检查对象是实际文件、导入、调用、数据读写、路由入口和构建来源；不是只按目录名称判断。

## 1. 结论先行

**保留现有业务模块，收回越界的操作，合并迁移后只剩薄包装的文件；前端资源状态回到页面，外壳只管理导航和离开保护。**

本轮不再增加新的一级业务模块。主要调整如下：

| 方向           | 当前或上一版的问题                                        | 本轮统一结论                                                      |
| -------------- | --------------------------------------------------------- | ----------------------------------------------------------------- |
| 员工运行准备   | agents/execution.py 同时检查员工、拼快照和组织其他模块    | 员工规则合入 service；完整准备和组合授权归 conversations 共享流程 |
| Run 状态       | 上版计划新增 lifecycle，但 store 已有领取、完成和恢复入口 | 不新增 lifecycle；请求停止也收回 store，同一处维护状态操作        |
| 运行进度       | SDK 解析迁走后，独立 progress 只剩控制对象内部缓冲        | 并入 control；SDK 拼接留在 agent_runtime/streaming                |
| Agent 目录     | 单一实现又套 langchain_adapter 子目录                     | 压平到 agent_runtime；保留公开 contracts 与实现之间的依赖约束     |
| 旧执行响应类型 | 容易保留一套与新助手视图重复的 DTO                        | 旧入口退出后删 execution/schemas；类型按真实用途定义一次          |
| 配置读取       | 全局 Provider 解析员工/技能路由，包办列表、详情和保存     | 页面持有自己的读取；全局只传写入后的更新通知                      |
| 编辑保护       | Layout 猜资源草稿键，多个组件重复注册离开保护             | 编辑器注册 dirty、saving、discard；Layout 统一处理离开            |
| API 与展示类型 | 员工/技能客户端混合，列表摘要伪装完整编辑数据             | 客户端按实际能力拆分；同一模型文件区分摘要、详情和编辑输入        |
| 导航与共享组件 | 全局搜索属于 configuration，规则编辑器挂在共享组件        | 搜索归 navigation；规则编辑归 knowledge 页面；实际复用组件保留    |
| 技术依赖       | 数据库机制反向导入 AppConfig，用量类型依赖 SDK            | 配置类型回到技术模块，用量采用普通映射，环境由配置入口解析        |
| 路由和装配     | CI 安装业务写在路由，bootstrap 定义组合业务规则           | 安装回专业服务，跨模块准备/授权回用例，入口负责调用和装配         |
| 资源构建       | 品牌生成脚本读取登录页私有源稿                            | 源稿归 brand，登录动画和构建共用，固定 SVG ID 保持不变            |

不是每个问题都需要拆文件。此次明确撤销 lifecycle、独立 progress、独立内部 Run schemas 和 SDK 子目录；也不把四个配置 Context 文件换成四种资源 Provider。

## 2. 检查覆盖与证据如何理解

复核前清单包含 **567 个工程文件**：后端 162、前端 260、docs 135、scripts 6、根目录 4。包括测试、配置、迁移、资源和文档，不包含忽略的依赖、缓存、构建产物、数据库或秘密。

建立了 292 个源码节点的静态引用索引：102 个 Python 实现/工具文件、190 个手写前端 TS/TSX 文件（含测试）。另外核对包导出、路由懒加载、ORM 注册、CLI、脚本读取、头像生成与静态资源引用。测试和文档按相关职责复核，不声称逐行深审全部资源、全部测试或每份历史记录。

引用索引只是线索。动态导入、`from package import module`、Alembic 元数据注册和构建期 readFile 可能不表现为普通导入；不能用“没有入边”直接宣布死代码。本文关于删除的结论另做全文引用核对。

[逐文件去向](file-map.md)覆盖每个基线文件；[完整目标树](target-tree.md)列出全部目标文件和中文原因。两者说明去向完整，不代表每个保留文件都要改动。基线在本轮开始时冻结，新增的本报告和审查记录单列为新增目标。

### 统一判断方法

1. 谁实际调用？是多个消费者，还是一个对象内部状态？
2. 它维护哪条规则？这条规则是否在别处重复？
3. 它改哪些数据？是否应该参与调用方的共同事务？
4. 依赖是否越过了自己应知的范围？
5. 合并后是否更容易理解，拆开是否真能隔离一种变化？

短文件不是问题；没有独立规则、只转发同一操作的结构才值得合并。大文件也不一定混杂；同一业务的相关查询可以放在一起。

## 3. 后端配置模块：规则留在所有者，组合放到用例

### 3.1 auth：保留内部划分，统一重复的会话判断

[Actor](../../../backend/app/auth/actor.py)被身份入口、权限判断和多处业务操作引用，仍单独保留。permissions 管操作与范围，service 管登录会话，github 管 OAuth，cli 管本地账号维护；它们有不同调用入口和变化原因，不再合成一个大文件。

[service](../../../backend/app/auth/service.py)的前台解析与后台解析重复了部分有效性判断。目标是在原文件共用一组判断，保留两种操作差异：

- 前台认证可以按原规则维护会话活动信息。
- 后台看护不刷新会话寿命。
- 发布授权使用调用方 Session，读取与发布相同事务中的当前事实；不自行开启另一份认证事务。

这不是新增认证抽象层，也不改变会话延长规则。

### 3.2 agents：员工规则、读取结果和运行准备各有归属

[agents/execution.py](../../../backend/app/agents/service.py)撤销后的分工见[后端模块](modules.md)。存在/启用/模型绑定/装配修订是员工规则；快照形状、正文哈希、大小限制、公司指令合成与具体执行函数绑定是整次运行准备。

还需一起修正两处重复：

| 实际问题                                                          | 调整                                                              | 保持的行为                                     |
| ----------------------------------------------------------------- | ----------------------------------------------------------------- | ---------------------------------------------- |
| service 与 execution 分别检查员工就绪                             | 在 service 共用员工就绪判断，展示理由和运行准备使用同一规则       | require_agent 仍只检查存在，未就绪员工仍能编辑 |
| schemas 与 service 各计算 resource_counts，CI 工具数重复写 3      | service 生成摘要，schemas 只表达字段；CI 数量由其真实工具声明计算 | 数量含义、装配启停、游客白名单保持一致         |
| 带 summary 布尔参数的读取改变返回形状，公开路由再从完整配置裁字段 | 现有 service 提供明确摘要/详情/公开读取入口，复用内部查询         | 对外字段不因整理扩大，列表不加载不需要的正文   |

不新建 availability.py、counts.py、public_queries.py。轻量的 CI 工具声明可在其现有 contracts 中统一供 MCP 声明和统计使用；员工计数不能为取一个数量而创建 MCP 客户端或导入执行循环。

### 3.3 skills、model_connections、organization_rules：大体保留

- [skills/parameters.py](../../../backend/app/skills/parameters.py)被规范编辑、装配保存与运行准备实际共用，继续独立。SkillService 的公开/管理读取改为明确入口，不让路由先取完整内部配置再裁剪。
- 模型 credentials 维护密文、主密钥与轮换；presets 维护受信协议与地址；二者继续独立。[连接 service](../../../backend/app/model_connections/service.py)的版本复核提供调用方 Session 形式，让最终授权与发布一致；解析后的解密仍在短事务之外。
- 连接检查访问 `/models` 是现有“检查连接”的组成部分，目前只有一个调用点。本轮留在 service，不为约几十行请求单独建 catalog 适配器；多个真实复用者出现时再提取。
- organization_rules 的 models、schemas、service 分别拥有存储约束、输入结构和修订更新，保持。全员规则不迁入员工目录，也不并入系统提示词工具。

## 4. 对话、运行与专业处理：减少文件，收紧真实边界

### 4.1 conversations：保留四种实际职责，修正上下文函数

models、writes、queries、schemas 继续存在。queries 中归属、历史、目录、预览与上下文都服务同一对话读取，不再按查询类型拆许多小文件。

当前 [select_context](../../../backend/app/conversations/queries.py)接收并修改 RunSpec，还识别 CI 快照。目标改成明确输入“配对数量、剩余字节等限制”，返回消息和截断信息。是否给 CI 带聊天上下文、结果如何填进 RunSpec，由 preparation 决定。

函数不再理解另一模块的完整对象，比把它搬到 context.py 更能消除耦合。

### 4.2 execution：保留状态操作的一个入口

| 文件                     | 目标职责                                                   | 合并或迁出什么                                           |
| ------------------------ | ---------------------------------------------------------- | -------------------------------------------------------- |
| models.py                | Run/RunAction 字段与数据库约束                             | Message、专业 CI 内容迁出                                |
| store.py                 | 领取、停止、预算、动作、结束与启动恢复的数据操作及状态规则 | 接收API 请求服务中直接修改取消字段的操作；不再调用发布器 |
| control.py               | 授权检查、动作控制、普通内容缓冲、限制、恢复               | hooks 改名；progress 的普通缓冲并入                      |
| coordinator.py           | 看护单次处理、总时限、停止任务、执行函数与故障收束         | 业务授权组合移至用例，SDK 判断移至运行实现               |
| scheduler.py             | 队列、并发、进程锁、后台生命周期、启动恢复调度             | driver 改名                                              |
| admission.py             | 同键重放、容量与登记                                       | 继续参与调用方事务                                       |
| queries.py               | 执行记录、动作与安全事实读取                               | 不再构造公开旧 Run CRUD 结构                             |
| contracts.py / errors.py | 宿主的执行依据、准备函数、终态意图与错误                   | 不复制 Agent 控制协议或对话响应                          |

[RunStore](../../../backend/app/execution/store.py)已经拥有 claim、finish、预算和动作操作。新增 lifecycle 会把规则分到三个地方；本轮取消该目标文件。停止请求服务调用 store 的 Session 入口，仍由请求服务提交，不改变停止与成功竞争的事务顺序。

仅转调发布器的 Store.complete 包装也撤销。协调器调用注入的发布能力；恢复读取返回需要收束的事项，由调度/协调入口发起发布。Store 不同时承担数据操作和跨模块业务提交。

旧 Run API 退出后删除 execution/schemas.py。助手与公开步骤类型归 conversations/schemas；Agent 协议归 agent_runtime/contracts；宿主确有复用的数据归 execution/contracts。不为了替代 RunRead 又造一套几乎相同的 RunFacts。

### 4.3 agent_runtime：一个模块足以容纳当前实现

```text
agent_runtime/         # Agent 内部运行；通过受限协议与宿主协作
├── __init__.py        # 包声明；不自动加载整个 SDK
├── README.md          # 输入、控制、输出和恢复边界；供维护与测试
├── contracts.py       # 普通输入、控制、动作/内容和输出；唯一公开边界类型
├── langchain.py       # 当前 Agent 构造、模型工具循环和恢复判断；直接表达实际实现
├── streaming.py       # SDK 片段与完整响应转普通内容；宿主不识别 SDK 消息
├── middleware.py      # 实际动作前后接控制和记账；不保存业务记录
├── skill_loading.py   # 方法虚拟资源、读取与激活；文字不会扩大执行许可
└── checkpoints.py     # SDK 存档和兼容读取；存储资源由装配入口注入
```

当前只有一个实现，取消 langchain_adapter 子目录。压平目录不取消边界：宿主只使用 contracts，不导入 langchain、streaming 或 checkpoints；具体实现只在 bootstrap 装配。不要再为了压平给所有文件都加 langchain_ 前缀。

### 4.4 ci_diagnosis：拆开真实的网络循环，保留专业整体

当前 [原service（已退役）](../../reference/ci-diagnosis/README.md)把配置事务、长时间受控取证、报告校验与反馈放在一起。executor/report 拆分有实际内容与多个调用点，继续采用；不再新增 feedback、progress、queries 或 configuration 文件。

- service 保留配置、安装、仓库范围、专业授权、读取和反馈。
- executor 保留实际取证/分析循环与外部来源复查。
- report 维护来源规范化、覆盖和引用核验、确定性正文；来源入库前的简单脱敏也可留 executor 私有辅助，不能误称成普通格式化。
- contracts 在请求、员工配置、执行器与报告校验中实际复用；mcp 负责协议与资源关闭，均保留。
- 服务类改名 **CiDiagnosisService**，专业 ORM 继续叫 **CiDiagnosis**，避免同名。

[原CI 路由（已退役）](../../reference/ci-diagnosis/README.md)中的内置方法安装、默认参数、写库和装配数量逻辑归 service。路由只确认 HTTP 权限、传参和返回结果。

### 4.5 请求编排与三个共享流程

ConversationRequestService 放在 API 对话分组；preparation、authorization、publication 放在 conversations，分别处理准备、组合授权和最终提交。撤销全局 use_cases，不建立 application。具体调用与保留其他模块 service 的理由见[服务归属](service-boundaries.md)。

preparation 内区分“捕获当前配置”和“从冻结依据准备执行”两个函数。恢复只走后者，不能重新抓取提示词覆盖原快照。CI 过程保存回调也在这里绑定；实际专业修改仍调用 CI service，公开运行版本调用 store，在同一短事务提交，不为一个回调新增 save_ci_progress.py。

## 5. 技术模块、入口与工程

| 位置                               | 发现与处理                                                                                          | 为什么这样处理                                                                 |
| ---------------------------------- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| llm/usage.py                       | 去除顶层 LangChain UsageMetadata 依赖，接收普通映射；SDK 特有字段识别在 streaming/middleware 内完成 | TokenUsage 被运行读取和对外结构使用，不应借此加载 SDK                          |
| infrastructure/database/session.py | DatabaseConfig 放在本文件，与 Database 相邻；config.py 导入它并解析环境                             | 避免数据库技术层反向依赖聚合 auth/execution 的 AppConfig；不为一类配置再建文件 |
| infrastructure/database/models.py  | 保留 ORM 集中注册，仅供迁移/装配使用                                                                | 这是显式装配例外；业务测试从所属模块导入模型                                   |
| api/frontend.py                    | 改 frontend_delivery.py；静态目录由 AppConfig 解析后传入                                            | 它负责静态交付；不再自行散读环境，保留现有相对路径解释                         |
| api/routes/configuration.py        | 改 configuration_summary.py，外部 URL 不变                                                          | 实际只汇总导航计数；一条 SQL 的只读汇总允许留在这个入口，不再加计数服务        |
| api/errors / security / rate_limit | 保留                                                                                                | HTTP 转换、请求保护和共享限流是不同机制                                        |
| bootstrap / main / config          | 装配 / ASGI 导出 / 配置解析分别保留；组合业务闭包移至用例                                           | 不按文件短小合并，也不让装配入口定义授权或 CI 规则                             |
| migrations                         | 0001—0004 冻结，新增正式升级                                                                        | 历史迁移不作为目录整理对象；避免已存在数据库失去升级路径                       |
| tests / experiments / datasets     | 保留独立用途；checkpoint 测试图构造移到测试 helper                                                  | 正式恢复仍留运行实现，测试便利函数不进入正式包                                 |
| scripts/dev.py、Makefile           | 保留进程与命令组织                                                                                  | 端口、启动检查和退出清理是一种完整职责，不与业务配置混合                       |
| 前端资源构建脚本                   | 各自保留头像、品牌、主题、压缩职责                                                                  | 来源和执行时机不同，不合成 build-utils 或塞进 Vite                             |
| docs                               | 保留 architecture/reference/proposals/records 分工                                                  | 本轮仅改方案、图源和审查记录；现行契约在业务实施后更新                         |

## 6. 前端：页面持有资源，外壳持有导航

### 6.1 拆掉按路径工作的全局配置总仓库

历史 ConfigurationProvider（此处记录改造前实现；现行数据层见[共享数据模块](../../../frontend/src/state/README.md)）读取路由和多套搜索参数，同时持有员工、方法、详情、收藏、计数、保存锁和错误。它的三个生产消费者是 Layout、AgentsPage、SkillsPage；共用一个 Context 并不说明这些状态有同一生命周期。

目标分工：

| 位置                                             | 拥有的内容                                | 不再拥有                       |
| ------------------------------------------------ | ----------------------------------------- | ------------------------------ |
| useAgentDirectory                                | 员工筛选、分页、收藏/启停、目录错误       | 编辑全文和别的页面列表         |
| useAgentEditor                                   | 指定员工详情、保存删除、装配选择读取      | 员工目录全局缓存               |
| useSkillDirectory                                | 方法目录、展开、安装刷新与删除            | 编辑详情                       |
| useSkillEditor                                   | 指定方法详情、保存和冲突                  | 员工装配页的选择状态           |
| navigation/useNavigationSummary                  | 外壳全局计数和最多 20 个收藏              | 资源编辑状态                   |
| state/configuration/useConfigurationInvalidation | 小 Context、当前更新版本、invalidate 入口 | 列表、路由、请求、草稿或保存锁 |

版本由 Layout 持有。页面写入成功后发更新通知；导航重新读取自己的摘要。其他已挂载的相关读取可据此失效刷新。身份切换必须销毁旧读取，结果以身份、目标 ID 和完整查询条件核对，不能只比较 pathname。

四个页面 Hook 分别对应已有目录/编辑生命周期，可以由现有 AgentsPage、SkillsPage 中相应组件调用；本轮不再为每条路由增加 EditorPage 文件，也不额外拆表单字段组件。

员工编辑需要一页技能选择数据，由员工编辑生命周期读取，这不是建立全局技能仓库的理由。现有四个 configuration 状态文件删除，大 Context 与总入口不保留兼容壳。

### 6.2 编辑区注册自己的清理动作

[Layout](../../../frontend/src/Layout.tsx)当前按路径拼草稿键，brains 会落入 skill:undefined 分支；它与多个编辑器还重复注册 beforeunload。

目标由 useEditing 维护当前编辑区注册：dirty、saving、可同步检查的提交门闩和 discard。页面负责具体草稿键、验证与清理。Layout 统一处理浏览器关闭、路由阻止和“放弃并离开”，只调用注册回调。

编辑区域边界也由编辑器声明，例如知识页从规则页签切到资料页应离开编辑；外壳不硬编码规则页特例。组件内部弹窗关闭确认仍留本地。注册撤销要核对当前实例，旧编辑器 cleanup 不能抹掉新注册。

合并两套保存门闩时保留同步检查：点击保存后立即导航，不能等下一次 React 渲染才知道正在保存。API Key 继续只在连接表单内存中。

### 6.3 API 和展示类型按实际用途命名

[configuration.ts](../../../frontend/src/lib/api/agents.ts)的员工和方法请求分别归 agents.ts、skills.ts；public.ts 的两类公开 DTO 与映射也归这两处。请求函数依旧采用各自后端端点，不为目录对齐改 URL。

- all() 只有模型连接全量读取使用，移回 modelConnections.ts 私有，不造通用分页层。
- 导航计数、收藏与搜索请求归 api/navigation.ts；这是前端使用场景组合，不要求后端新建 navigation 领域或服务。
- useQueryState 只读写 URL，接收页面传入的重置键；删除内部 /agents、skill_q 等业务判断。
- [agent 模型](../../../frontend/src/lib/models/agent.ts)在原文件区分摘要、完整详情与编辑输入。摘要没有 systemPrompt 就不填假的空正文；编辑器只接受完整类型。
- 类型切换完成前保留 configurationLoaded 保存保护，不能先删标志。未展示的 icon 传递字段在确认所有映射、fixture 和兼容要求后清理，不把它当作本轮重构前提。

### 6.4 共享组件按消费者归属

| 当前                                                  | 目标                                    | 依据                                                 |
| ----------------------------------------------------- | --------------------------------------- | ---------------------------------------------------- |
| configuration/ResourceSearchResults + Layout 搜索弹窗 | navigation/GlobalSearch                 | 完整全局搜索交互，外壳只管打开                       |
| agents/FavoriteAgentLink                              | navigation/FavoriteAgentLink            | 实际是导航，外壳和设计样板复用                       |
| configuration/ConfigurationStatus                     | configuration/ResourceStatus            | 由 ready/error/onReload 驱动，不再读取资源 Context   |
| configuration/ResourcePagination                      | common/ResourcePagination               | 通用 URL 分页，不属于编辑                            |
| organization-rules/RulesWorkspace                     | pages/knowledge/OrganizationRulesEditor | 只有知识页面使用的具体编辑功能                       |
| skills/GithubCiMcp                                    | skills/GithubCiSetup                    | 做安装和配置展示，不执行 MCP；两处真实复用所以仍共享 |
| signin/logo.ts                                        | brand/wordmarkSource.ts                 | 构建与登录共用的品牌源稿                             |
| lib/session.ts                                        | lib/identity.ts + 现有 navigation.ts    | 身份与返回路径是不同职责                             |
| lib/knowledgeNavigation.ts                            | 现有 navigation.ts / editing            | 规则定位归导航，离开编辑判定归编辑注册               |

ConfigurationConflict、StaleDraftNotice、InheritedRules、useOrganizationRules、SkillCard、SkillCollection 继续保留真实复用。冲突组件不再内置员工/技能字段名和资源读取；页面提供读取与展示，组件管理查看并采用新修订的交互，不新增配置框架。

## 7. 有意不做的拆合与清理

| 对象                                                  | 结论及原因                                                                   |
| ----------------------------------------------------- | ---------------------------------------------------------------------------- |
| useConversation/useMessage                            | 现有对话和消息交互入口保留；不新增 useRun/useTurn                            |
| Provider/controller/store/state                       | 分别是作用域、副作用、稳定快照和纯转换，不能因名字多就合并                   |
| auth 的 Actor、权限、会话文件                         | 实际多方引用且规则不同，保留                                                 |
| skills parameters、模型 credentials/presets、llm 文件 | 有独立规则或生命周期，保留                                                   |
| pages/agents/index、avatars/index                     | 真实公共入口，设计样板与业务消费者使用，保留                                 |
| Field/Form/styledProps                                | 短但提供统一 UI 适配，多处使用，保留                                         |
| ThemeArtwork、themeController/useTheme                | 图形复用、首屏与运行同源、React 适配分别有依据，保留                         |
| useDraft/lib/draft                                    | React 保存时机与普通存储校验分开，保留                                       |
| PageToolbar/Markdown                                  | 外壳插槽和统一富文本入口有实际作用，保留                                     |
| 头像组件、registry、catalog、生成物                   | 业务 ID 回退、懒加载、资源查询和生成各有职责，保持同源与视觉                 |
| 单消费者样式字典                                      | 本轮保留，不用行数决定合并；没有证据表明其造成领域混杂                       |
| BrainWorkspace、登录动画内部文件                      | 有可选收紧空间，但当前能解释其视图/表单和动画职责；不扩大为本轮必需路径改造  |
| svgAvatar 额外导出层                                  | 可选后续合并，本轮保留测试和公开入口，避免把所有薄导出都当成错误             |
| Popover                                               | 全前端未发现使用、示例或测试，列入 P4 删除；若实施前出现实际消费者则重新核对 |

“保留”不是宣布永久完美，只是这次没有充分理由变动。可选整理不进入目标树，避免读者误以为本轮必须顺带完成。

## 8. 对实施和验收的影响

本轮调整纳入[实施计划](migration.md)的 P1 基础整理，前端配置/导航可用现有 API 独立完成；不用等待 Message 数据迁移。P2/P3 的内容、运行关联、回复 API 结论保持，P4 删除旧 DTO 和无消费者控件。

验证围绕真实风险：

1. 未就绪员工仍可读可编辑；资源数量、公开字段和装配修订判断一致。
2. 发布授权使用当前事务；后台认证不延长会话；秘密解析和网络不进入长写事务。
3. 停止/领取/恢复/完成仍由同一组状态操作保护；保存失败后不发出外部调用。
4. 配置目录与详情切换忽略旧请求；摘要不能当作完整配置保存；写入后导航及时刷新。
5. 编辑器注册/撤销、离开回调和同步保存门闩正确；规则页签、模型连接和弹窗均覆盖。
6. 品牌固定 ID、动画和构建来源不变；权限、草稿、主题、静态深链与压缩交付保持。
7. 类型、ESLint 导入边界、文档、生成清单随路径更新；不为纯搬文件写镜像测试。

实际本轮只验证文档和生成工具，见[审查记录](../../records/directory-responsibility-review.md)。这里的验收条目是实施要求，不是已完成结果。

服务归属的后续统一修订见[请求与共享流程](service-boundaries.md)：本轮不把所有服务集中进 application，也不批量迁入 API；仅增加有实际内容的对话请求服务，其余服务与三个共享流程有明确所有者。此项以该专题为准，历史审查记录保留当时数量与名称。

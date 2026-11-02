# 前端：按对话交互组织状态和操作

本文描述[目标方案](README.md)中的浏览器设计。前端按用户正在完成的事情组织，不复制后端模块树；同时保留已经有实际作用的作用域、命令协调和稳定渲染机制。

## 1. 保留用户认识的页面

| 页面或共享区域     | 负责什么                                   | 本轮如何处理                                 |
| ------------------ | ------------------------------------------ | -------------------------------------------- |
| 对话 conversations | 输入、回复、过程、停止重试、历史与问题目录 | 继续此命名，切换对话 API 与读取结构          |
| 员工 agents        | 员工目录、配置和工作入口                   | 保留草稿、修订冲突、来源导航和公开摘要       |
| 方法 skills        | 当前方法资产及专业能力配置入口             | 不因运行重构提前建设通用工具页               |
| 大脑 brains        | 模型连接、凭证输入和显式连接检查           | 不把凭证写入草稿，不将保存成功当作可调用证明 |
| 知识 knowledge     | 现有教学资料与规章制度                     | 保留静态能力说明，真实检索仍是后续专题       |
| 登录 signin        | 管理员、游客、GitHub 身份与界面反馈        | 不依赖对话运行状态                           |
| 帮助与设计系统     | 用户帮助和组件样例                         | 随生效行为更新帮助，不重做视觉系统           |
| Layout/router      | 共享外壳、导航、权限入口与懒加载           | 不持有对话订阅和后台运行                     |

前端页面可以组合多个后端模块提供的数据。员工、身份和运行状态出现在同一页面，不代表它们必须变成同一个后端领域。

## 2. 共享入口与内部 Hook 分开

| 入口                                               | 组件从中得到什么                                   | 为什么保留                           |
| -------------------------------------------------- | -------------------------------------------------- | ------------------------------------ |
| useConversation                                    | 当前对话、输入提交、待确认操作、历史入口与末次消息 | 整段对话有共同作用域和命令生命周期   |
| useMessage(messageId)                              | 这一行的内容、状态、过程、复制、停止与重试操作     | 回复组件实际同时需要这些能力         |
| useConversationHistory（内部）                     | 连续历史窗口、定位和回到最新                       | 阅读位置与最新接收内容有不同生命周期 |
| useQuestionNavigation / useQuestionPreview（内部） | 提问目录浏览与短预览                               | 不应为看目录下载整段历史             |

对话模块的共享消费者入口只有 useConversation、useMessage。历史、目录和预览 Hook 是页面内部按交互生命周期拆分的实现，可由对应接入组件使用，不要求普通消息消费者理解。

不新增 useTurn、useRun 或 useReply 与现有公开入口并列。useMessage 是页面交互读取接口，不要求严格等于后端 Message 表字段。

内部 useRunSubscription 改为 useResponseSubscription，是因为网络目标变成对话中的回复。它由对话控制器使用，不让每个消息行自己订阅。

## 3. 页面内部为什么仍有几种文件

| 位置                           | 职责                                   | 生命周期                          |
| ------------------------------ | -------------------------------------- | --------------------------------- |
| ConversationProvider / context | 为当前身份和对话建立并传递稳定实例     | 身份或对话变化时销毁旧作用域      |
| useConversationController      | 组织网络、命令确认、重连与输入目标     | 一次对话实例只有一个控制器        |
| conversationStore              | 保存已接受读取状态，提供稳定的逐行快照 | 正文更新只通知变化的行            |
| conversationState              | 纯状态转换、合并和交互资格计算         | 无网络副作用                      |
| conversationDraft              | 尚未提交的输入                         | 与已发出的待确认命令分开          |
| pendingSubmissionStorage       | 固定请求键、输入和停止意图             | 提交未知时跨刷新核对              |
| useResponseSubscription        | 单条当前回复的读取观察与重连           | 切换目标或离开作用域关闭          |
| 组件及样式                     | 输入、正文、过程、历史、诊断与导航展示 | 不直接取得底层网络或后端 ORM 规则 |

当前 conversationController.ts 实际导出 Hook，改为 useConversationController.ts；conversationSession.ts 改为 pendingSubmissionStorage.ts，名称表达它保存的是待核对命令，不是第二种业务会话。

Provider、controller、store 并非三个重复服务：它们分别管理共享生命周期、副作用和局部渲染。保留这些已经有行为依据的职责，不再增加 facade、manager 或另一套全局状态框架。

## 4. API 客户端怎样组织

lib/api/conversations.ts 保存对话用户操作的请求、响应和函数；不按 Run/Message 每个实体分文件。conversationTransport.ts 保留可注入的网络能力集合，便于控制器测试，不再暴露后端 current_model 等运行对象。

http.ts 继续处理 Cookie、HTTP 错误和普通请求；页面不重复实现它。API 客户端不能反向导入页面 Context、React Hook 或当前员工选择。

可以共享明确的公开类型，但不生成一套与全部后端 Python 类同名的前端领域模型。

## 5. 一份回复如何更新

1. snapshot、历史、提交确认或 SSE 得到相同 AssistantMessageView。
2. 控制器验证对话与身份作用域，再交给 store；对话摘要按 scope_version 合并，单回复按自身 version 合并。
3. store 按消息 ID 和 version 合并；旧版本不能覆盖新版本。
4. 助手视图任一实际字段变化才产生该行新快照，包括状态、步骤、用量、错误和 CI 版本；未变化的列表、其他行及步骤保留引用。
5. useMessage(id) 通知对应组件重新渲染；终态通知和停止响应同时合入新版本对话摘要，不能仅本地清空活动目标而保留旧 scope_version。
6. 复制、停止、重试由这一行的操作入口提供，控制器把准确 response_id 交给服务器。

删除前端 answerContent 对 has_tool_calls、result.content、current_model 的选择逻辑。服务器直接返回当前可见 content 和 content_state。

完整内容、草稿与失败片段在界面有明确状态；空正文的失败回复仍可展示错误与重试，不制造“看起来成功”的占位内容。

## 6. 发送结果未知时如何处理

发送前固定一次请求键和目标，不在请求失败后自动换键：

- 确认接受：保存返回的准确回复与带版本当前摘要，清理匹配的草稿和待确认记录；迟到确认不强行改活动目标。
- 明确拒绝：保留输入和错误，允许用户修改或重新操作。
- 结果未知：保留原命令，用只读接口核对；必要重发继续使用原键和原输入。
- 未确认时要求停止：记录停止意图，找到准确回复后再发送停止。
- 切换身份或对话：旧命令回调不能写入新 store，也不能停止新对话的处理。

网络层中止读取不代表后端取消了已接受工作。客户端不能把一次 AbortError 自动当作“没有发出去”。

## 7. 历史与最新内容

保留最新窗口和一个正在阅读的连续历史窗口，不把不相邻的两段数组直接拼接。

- 新快照更新最新缓存。
- 历史窗口中同 ID 的回复可以更新，不能因为新回复到达而强行跳到底部。
- around_message_id 直接定位目标窗口，不逐页下载中间正文。
- 快速切换目标取消旧读取并忽略迟到结果。
- 问题编号来自用户消息顺序，重试和模型调用不增加提问数。
- 目录、预览和正文窗口分别按需读取；预览不订阅整条执行。
- 回到最新只读恢复，不重新提交工作。

保留现有滚动、键盘触摸、减少动态效果、定位高亮及主题行为。本次没有重新设计视觉的需求。

## 8. CI 报告的读取

回复只带 CI 是否存在和专业版本。CiReport 按 conversation_id、response_id 和 CI version 读取专业状态，而不是按每次普通正文 version 重读来源。

- 执行中的阶段和证据仍可查。
- 终态只在 report 已成功提交后展示完整报告。
- 反馈只在成功且报告存在时开放。
- 报告组件不依赖 Run ID；后台解析关联。
- GET 与反馈响应都有专业版本；切换目标时取消旧读取，旧版本不能覆盖新内容，成功反馈立即合入新专业视图和同响应返回的助手视图。
- 不新增通用附件系统或独立全局报告状态仓库。

## 9. 前端与后端必须一致的内容

必须一致：ID 指向、状态含义、失败与停止语义、重试资格、数据版本、错误和权限范围。

可以不同：页面目录、组件拆分、Hook 名称、API URL 与 Python 文件名。按钮可叫“停止回复”，服务器实际取消 Run；这些名字分别表达各自使用场景。

API 也不按每个组件设计。稳定用户操作留在契约里，纯布局和展开状态留在前端，避免移动一个按钮就修改后端。

## 10. 配置读取回到页面

不再通过全局 ConfigurationProvider 解析路由并同时加载员工和方法。目标只保留：

| 位置                                             | 状态与操作                                    |
| ------------------------------------------------ | --------------------------------------------- |
| pages/agents/useAgentDirectory                   | 当前员工查询、分页、启停收藏及局部错误        |
| pages/agents/useAgentEditor                      | 单个员工详情、保存删除和装配选择列表          |
| pages/skills/useSkillDirectory                   | 方法目录、展开、安装刷新及删除                |
| pages/skills/useSkillEditor                      | 单个方法详情、保存与修订冲突                  |
| components/navigation/useNavigationSummary       | Layout 的全局数量与有界收藏                   |
| state/configuration/useConfigurationInvalidation | Layout 持有的更新版本和写入后 invalidate 通知 |

删除原四个配置状态文件和大 Context。四个 Hook 是已有目录/编辑生命周期的实现，仍由现有页面文件中的相应组件使用；不再为每条路由增加页面文件或 Provider。

具体读取身份包括当前身份、资源 ID、完整查询条件和更新版本。切换时中止旧请求并拒绝迟到结果；不能继续只按 loadedPath 判断 ready。列表、编辑详情和技能选择列表分别加载，不互相伪装完整数据。

员工编辑需要方法选择数据，可以直接调用 api/skills，不借用技能目录页的状态。页面保存成功后更新本地结果并发失效通知，导航刷新自己的摘要；不建立资源注册表、查询总线或全局缓存。

## 11. 导航、API 和展示类型

全局搜索的弹窗、输入、结果与错误统一归 components/navigation/GlobalSearch；Layout 只控制打开及快捷键。FavoriteAgentLink 同归 navigation。导航网络由 api/navigation 维护，调用现有摘要、收藏和搜索端点，不要求后端新建同名模块。

混合 configuration 客户端拆为 api/agents 与 api/skills，public 中两类公开结构和映射合入对应客户端。modelConnections 全量读取的分页循环移回本文件私有；不用一个只有一个消费者的公共 all 工具。

lib/models/agent 在原文件中区分摘要、完整详情和编辑输入。摘要不填假的 systemPrompt 等空配置；编辑器只接受完整类型。类型切换前保留 configurationLoaded 保存保护，不能先删标志。卡片继续消费 AgentPresentation，不依赖完整编辑数据。

useQueryState 只管理 URL 参数；查询变化需要重置哪些分页键由页面显式传入。它不再识别 /agents、skill_q 或具体资源。

lib/session 的身份类型、隔离键和通知改放 lib/identity；safeReturnPath 合入 lib/navigation。knowledgeNavigation 的规则定位合入 navigation，编辑离开判断改由编辑区注册，测试随职责归位。

## 12. 一份编辑保护，具体清理由编辑器提供

useEditing 保存当前编辑区注册、dirty、saving、同步提交门闩与 discard 回调。页面拥有自己的草稿键、清理和校验；Layout 统一处理 beforeunload、路由阻止与离开确认，不再按路径猜 agent/skill 草稿。

“放弃并离开”先调用当前编辑器提供的 discard，再离开。编辑器定义自己的区域边界，包含规则页签等场景；旧实例 cleanup 不可撤销新编辑器注册。组件内部弹窗关闭确认仍在本地。

合并重复保存状态时必须保留同步门闩，保存后立即点导航也应被拦住。模型连接密钥只留表单内存，不进入全局上下文或持久草稿。

## 13. 共享 UI 和品牌来源

| 调整                                               | 目标职责                                 |
| -------------------------------------------------- | ---------------------------------------- |
| ConfigurationStatus → ResourceStatus               | 由 ready/error/onReload 驱动的纯加载反馈 |
| ResourcePagination → components/common             | 通用 URL 分页                            |
| RulesWorkspace → knowledge/OrganizationRulesEditor | 知识页面专用编辑器                       |
| GithubCiMcp → GithubCiSetup                        | 两处共用的 CI 安装和配置展示             |
| signin/logo → brand/wordmarkSource                 | 登录动画与品牌构建共享 SVG 原稿          |

ConfigurationConflict 保留通用查看/采用最新修订交互；具体资源读取、字段名与展示由页面提供。StaleDraftNotice、InheritedRules、useOrganizationRules、头像入口、基础 UI 适配和样式文件有真实用途，继续保留。

品牌源稿移动后更新 build-brand 与登录页引用，不留旧转发壳，不改 SVG 固定 ID、动画或视觉。头像、主题和压缩构建继续各自维护，不合并成构建杂物文件。

## 14. 验收重点

继续覆盖单订阅、StrictMode、旧闭包、身份切换、未知提交、未确认停止、乱序版本、历史连续窗口和局部渲染。新增验证包括首屏一致快照、没有原始 SDK 字段也能展示完整流程、CI 不随普通 token 重复加载。

配置与外壳调整还需覆盖：写入后摘要刷新、目录/详情查询隔离、摘要不能保存成全文、编辑注册撤销、正确放弃草稿、规则页签离开，以及保存期间同步保护。具体证据和不采纳的可选整理见[全工程复核](responsibility-review.md)。

这些是迁移需要保持的行为；历史通过结果不代表本次重构已经验证。

后端请求服务和共享流程的目录调整不要求前端再改 Hook 或接口文件名。前端 service/client 是网络接入，后端 service 是业务操作，不按同名强制对应；边界见[服务归属](service-boundaries.md)。

# 对话与历史契约

本页描述当前交流、读取与操作规则；运行管理见[运行契约](runtime.md)。API 围绕用户操作设计，内部目录无需与前端 Hook 或 URL 同名。

## 目标与范围

用户与一位员工持续交流。页面只保存本地草稿，首条通过 POST /api/conversations 发送，不传 conversation_id；后端在受理事务生成 ID，前端先保存返回的 conversation.id，再进入正式对话路由。

首条发送前可通过独立文件上传接口添加附件，但不读取对话文件列表。本地 `draft:…` 标识只用于草稿和会话存储；文件列表请求必须使用后端返回的正式对话 ID，不能把草稿标识作为 `conversation_id`。

## P1 与后续阶段

当前已实现可靠提交、真实模型/方法循环、稳定消息、取消、失败重试、历史分页、问题目录、恢复及受控工具调用。任务、计划、目标、多引擎仍在各自方案中，不作为本轮已实现能力。

## 复用基础与已完成的改造

使用现有身份、Cookie、Origin、JSON/体积校验、权限、模型连接、员工及方法修订。当前助手正文直接保存到 Message，SDK checkpoint 保存连续线程状态与执行恢复依据，不再有 RunResult 表或前端选取最终模型轮的逻辑。

## 模块职责与关联

Conversation 是交流容器，Message 是用户输入或助手回复记录，Run 是针对输入的一次处理尝试。ConversationRun 把原输入、助手回复和 Run 关联起来，保证它们属于同一对话。

接受请求时，用户和空助手 Message 已经存在。一次失败重试沿用原用户输入，新增 Run 和助手 Message，旧回复及动作不覆盖。response_id、Run.id 与助手 Message.id 使用同一个由执行侧生成的值，不增加 Response 实体。

conversations/service.py 组织命令事务；跨资源配置捕获归 execution/snapshot，执行准备归 RunTask，当前授权由 RunService.authorize 组合，员工只提供自身装配事实，对话接纳只保存业务结果。RunWorker 管调度、在途任务和服务生命周期，RunTask 管单次加载、领取、执行、看护、受限操作、资源释放和成果提交，execution/store 管原子持久事实，execution/runtime 统一后台运行、单次资源和 SDK 内部循环；普通配置服务保留在所属模块。

## 主流程与执行生命周期

1. 首条发送一并保存对话、用户原文、空助手记录、Run、冻结输入与绑定，返回 202；同键重放返回 200 及原记录当前视图。
2. 后台领取 queued，复核授权并从冻结依据准备。模型与工具等待在业务事务外，动作开始记录失败就不发出调用。
3. 生成中保存普通草稿、思考与动作；SSE 读取这些已提交内容。
4. 执行完成后先由运行公开操作保存成果及 Run 终态；对话接纳在另一事务复核适用性、保存正文及文件关联并释放活动占用。
5. 用户停止明确指向某条回复，断线不停止。失败重试需当前对话空闲且目标为末次 failed/cancelled/interrupted 回复。

网络结果未知使用原键核对或重发，不能换键再交办。业务明确失败后的重试才创建新尝试。

## 数据设计

Conversation、用户 Message 和 Run 使用同一持久序列，固定 12 位十进制、范围 100000000000–999999999999；数据库整数、HTTP/前端字符串。助手复用 Run ID。client_request_id 由前端生成 UUID，仅作为请求幂等键；不共享前端业务发号规则。

Message 的 ID、角色、对话和序号固定。用户正文不可覆盖；助手最终正文只由接纳入口写入，终态重复发布和迟到片段不能改写。空正文不等于不存在记录，也不另建一套消息运行状态。

Conversation.revision 在接受和释放占用等变化中同步递增。一个对话最多一个 active 绑定，数据库部分唯一索引兜底。输入与回复使用同对话复合外键，ConversationRun.run_id 同时关联 Run 和助手 Message，不另设 reply_message_id。完整结构见[数据模型](data-model.md)。

## HTTP 接口契约

| 方法与路径                                                 | 用途及返回                                                             |
| ---------------------------------------------------------- | ---------------------------------------------------------------------- |
| GET /api/conversations                                     | 当前可读范围内的分页列表，可按员工过滤                                 |
| GET /api/conversations/stats?agent_id=UUID                 | 员工在当前可见对话范围内的完成问答轮数                                 |
| GET /api/conversations/{id}/snapshot                       | 同事务摘要、员工安全摘要、最新连续消息页和提问摘要                     |
| GET /api/conversations/{id}/messages                       | 历史页；before/after/around 三类游标互斥                               |
| POST /api/conversations                                    | 首次发送，必填 agent_id；服务端发号并原子创建，返回 AcceptedSubmission |
| GET /api/conversations/requests/{key}                      | 未知对话 ID 时核对首次提交；未查到返回 200/null                        |
| POST /api/conversations/{id}/messages                      | 向已有对话发送，返回 AcceptedSubmission                                |
| GET /api/conversations/{id}/requests/{key}                 | 只读核对提交；未查到返回 200/null                                      |
| GET /api/conversations/{id}/responses/{response_id}        | 当前 ResponseSnapshot                                                  |
| POST /api/conversations/{id}/responses/{response_id}/stop  | 精确停止，幂等返回当前 ResponseSnapshot                                |
| POST /api/conversations/{id}/responses/{response_id}/retry | 新键重试末次失败回复，返回 AcceptedSubmission                          |
| GET /api/conversations/{id}/responses/{response_id}/events | 已提交回复快照的 SSE 观察                                              |
| GET /api/conversations/{id}/questions                      | 用户提问目录、搜索、分页与锚点                                         |
| GET /api/conversations/{id}/questions/{message_id}/preview | 该输入最新尝试的有界文字摘要                                           |

对话在首次发送时原子创建，不提供单独创建空对话或读取摘要的 HTTP 入口；摘要随 snapshot、提交和回复读取返回。执行模块没有独立 Run HTTP 路由。没有独立步骤 HTTP 接口；动作随运行或回复投影返回，页面本地折叠和分页。

AcceptedSubmission 包含 client_request_id、当前 conversation、原 input_message 和 response。ResponseSnapshot 包含同一次读取的 conversation 与 response。首屏、历史、接受、核对、GET 和 SSE 的助手部分使用同一 AssistantMessageView。

助手字段 content 已选好可见正文；content_state 为 empty/draft/complete/partial。status 表示处理状态，两者各司其职。steps 为有界实际动作；can_retry 由服务器表示当前是否可重试，前端还需检查末条回复和交互状态。回复不再包含 ci 或 work_kind。完整字段由 [schemas](../../backend/app/conversations/schemas.py) 和运行 OpenAPI 维护，不在本文复制全部 DTO。

SSE 业务事件为 response.snapshot、response.finished、access.revoked；事件 ID 为回复版本，data 为公开快照 JSON，撤权时只发空对象后结束。恢复是读取当前快照，不承诺 token 回放。只有 Run 达到终态且业务接纳不再 pending，才发送 response.finished。

事件编码和空闲约 15 秒一次的 ping 注释由 FastAPI 官方 ServerSentEvent / EventSourceResponse 生成器路由提供。ping 不携带业务版本，也不触发快照更新。响应禁止缓存并关闭代理缓冲。订阅前先校验身份、runs:read、资源范围和名额，保留正常的 401/403/404/429；建流后认证或权限失效发送 access.revoked。streaming 的 request 生命周期依赖持有订阅名额，正常结束、撤权、断线、发送失败和取消均释放；断线不取消后台 Run。

CI 试验接口和员工 ci_repository 字段已移除；发送请求不再接受 work，旧字段返回明确的输入错误。本次重建不保留退役运行和旧格式数据；历史退役背景见说明。

## 历史列表查询与展示

GET /api/conversations 支持 agent_id、offset、limit、标题关键词 q（最多 200 字）及最近回复状态组 status：processing、replied、attention、stopped。关键词按标题字面匹配；筛选、total 和当前页使用同一授权集合，保持 updated_at／id 倒序。非管理员仍限定本人，管理员沿用现有可见范围。

ConversationRead 增加有界 latest_response（id、status、acceptance），列表使用批量投影，不读取正文或执行步骤。状态基于最近一次尝试：排队／执行／停止中及等待接纳属于处理中；成功接纳才算已回复；失败、中断及接纳错误属于需关注；主动停止单列。空话题不算处理中，旧失败不能使后来成功的话题继续匹配失败组。列表、snapshot 和提交返回的摘要使用同一接纳口径。

员工个人页与全局记录页使用同源表格：主题、最近回复、最近活动／创建日期、执行日志／去对话。无轮次列，最近活动使用 updated_at，不冒充最后一条可见消息的时间；创建日期为次要信息。搜索和状态筛选在服务端执行。员工页 URL 使用 history_ 前缀，改变条件回到首页；聊天侧栏保留独立的局部分页和紧凑列表。切换身份／员工取消旧读取，刷新失败保留可用旧页但不冒充新条件已加载。

新对话进入空白草稿，不隐式恢复最近记录。主题下方展示 Conversation ID 与最近 Run ID，搜索同时支持主题关键词及完整 Conversation ID／Run ID；ID 精确匹配仍受所有者、员工和最近回复状态筛选约束。命中 Run 时返回 matched_response_id，执行日志弹窗打开该次尝试；其他入口默认最近一次尝试。关闭日志保留原列表和筛选。小于 800px 的列表将状态并入主题，小于 600px 改为纵向行；两个操作保持文字可见。当前诊断结构见[执行日志](execution-evidence.md)，历史列表首次验收见记录。

## 员工完成轮数

员工个人页通过 `GET /api/conversations/stats?agent_id=UUID` 读取 `completed_rounds`，响应禁止缓存。操作要求 `conversations:read` 与 `runs:read`，资源范围与对话列表相同：管理员可读取全部，普通成员限定本人。不存在的员工返回 404，非法员工 ID 返回 422。

计数要求 Run 成功且 ConversationRun 已完成接纳、没有接纳错误，并按原用户输入 ID 去重。重试仍属于同一轮；运行中、失败、取消、中断、等待接纳及接纳失败不计，考核等没有对话绑定的执行也不计。直接在数据库聚合全部可读历史，不以分页列表条数或助手消息数替代，不新增持久计数字段。字段与实现见[schemas](../../backend/app/conversations/schemas.py)和[queries](../../backend/app/conversations/queries.py)。

## 前端交互

助手回复的执行过程复用 Trace，以细竖线串联步骤，显示动作名称、状态和整轮耗时。标题图标随服务器保存的当前动作切换：模型用大脑、工具用扳手，知识、技能和结果校验使用各自图标；存在在途工具时优先显示工具阶段。运行阶段稳定 120ms 后更新图标及文案，避免短暂闪换；成功使用 MessageCircleCheck，失败、取消、中断、排队及回复保存有各自状态，终态不等待防抖。图标以 280ms 的轻微横移、淡入淡出及模糊过渡，位置固定；初次读历史不播放入场，减少动态效果时直接替换。思考与必要过程信息在原位置折叠展开，不跳转执行详情；不重复展示最终正文。完整输入、工具载荷与技术日志从历史记录的大型弹窗查看，见[执行详情与调用证据](execution-evidence.md)。

对话页左侧为正文与输入，右侧辅助栏在新进入对话时默认展开，可收起或通过顶栏重新展开。辅助栏有「历史对话」「员工能力」两项，不包含任务。历史沿用当前使用者与当前员工的服务端分页列表；新回复被接受后刷新列表摘要，切换历史不停止后台运行，侧栏失败不替换正文。

话题标题位于正文上方，顶栏保留员工层级和对话操作。辅助栏顶部统一显示员工身份，两种标签共用；历史使用轻量行与当前项状态，能力按技能、工具、个人知识库分组。附件操作与发送同处输入框，仍使用原上传和选择逻辑。

能力区显示当前启用技能及其就绪状态；有员工配置查看权限时展示已授权工具操作，账号入口沿用本人连接页。个人知识库按当前身份从共享数据层订阅读取，设置复用现有 EmployeeKnowledge 编辑器，保存后摘要同步更新。当前挂载资源不代表本轮实际调用；本轮来源和过程仍在回复中查看。右栏布局与窄屏规则见[对话布局](../../frontend/src/design-system/layout.md#对话与阅读布局)。

useConversation 处理对话交互，useMessage 提供逐条读取、停止、重试和复制，useResponseSubscription 管单个回复的观察与只读重连。内部控制器接收页面提供的身份隔离作用域。

首屏只读一个 snapshot。摘要 version 与单回复 version 分别合并，旧窗口和旧接受结果不会回退当前活动目标；如收到另一个活动回复的摘要，重新读取首屏。正文直接来自服务端，不再解释 SDK 的工具轮。

消息历史保持连续窗口，支持前后分页和按问题定位；问题目录只数用户输入，重试不增加问题编号。历史阅读与最新回复观察分开，迟到历史不能覆盖已观察的终态或正文。

问题导航从第三次用户提问起显示。高亮表示消息区内可见的问答组，可同时高亮多项：一次提问与通过 reply_to_message_id 关联的回复属于同一组，任一消息部分露出也计入；阅读长回复时，提问离屏仍保留该组高亮，重试回复不增加导航项。点击或键盘激活仍以提问起点为锚点，保留顶部阅读留白、焦点与气泡底色反馈；未加载的提问先读取所属窗口再定位。悬停／聚焦只预览，刻度可独立翻阅，不移动正文。键盘焦点与可见高亮分别表达操作位置和阅读范围。

正文区域统一管理消息节点、可见范围及定位反馈，导航通过问题 ID 和定位控制接入，不依赖正文 DOM 或完整会话状态。目录与预览负责各自的读取失败；定位的加载和错误以历史层 jump 状态为准，不混入前后分页错误，也不在菜单中维护副本。具体接入见[模块导航数据流](../../frontend/src/pages/conversations/README.md#导航数据流)。

待确认命令按身份与页面作用域存入当前标签页，使用新的 v3 存储作用域。首次未收到回执时用原 client_request_id 调用全局核对接口，查不到也不拿本地 draft 标记读取后端；显式重发沿用原键与原文。取得真实 ID 后先保存，再迁移到正式路由。提交期间的停止意图保留到取消成功，网络失败或重载后继续核对并补停。

## 外部依赖、边界与错误

管理员能力与资源范围每次由服务器检查，知道回复 ID 不授予权限。配置错误、容量/频率、内容冲突和依赖不可用继续使用应用错误分类；已接受后的运行失败通过回复 status/error 表达，不能假装 POST 未接受。

公开数据不包含模型凭证、内部 SDK 状态或原始供应商异常。模型请求仍可能失败，连接检查成功不等于生成可用。真实上游与离线替身验证分开记录。

## 初始化与维护

启动前显式迁移至 head，应用不自动建表或升级。修改现有数据前按[后端操作](../guides/backend-operations.md#数据库与本地文件配置)停服并成套备份业务库、checkpoint 和密钥。本次数字标识切换按明确授权清库重建，不转换旧数据，日常启动不得自动清库。

## 验证与验收

[公开协议测试](../../backend/tests/test_response_contract.py) 使用普通 TestClient 验证新协议和真实 SQLite 快照并发；既有运行场景通过测试适配器继续验证执行 ID 下的内部状态。适配器不进入应用，也不证明旧 HTTP 路由仍存在。

## 取舍与后续扩展

保留模块化单体与当前 SQLite 单宿主。不为当前无需求的任务、目标、引擎注册和通用结果容器预建层级。新增来源需先说明自己的接受、授权和交付规则。

## 历史验证入口

本轮结果见实施记录。

回复的 acceptance 与 Run status 分别表达业务接纳和执行事实。pending 时继续观察并可展示已保存成果；暂时保存失败按持久依据重试，明确拒绝为 failed；两种情况都不改写成功 Run，也不触发重新求解。

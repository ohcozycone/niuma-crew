# 对话与历史契约

本页描述当前交流、读取与操作规则；运行管理见[运行契约](runtime.md)。API 围绕用户操作设计，内部目录无需与前端 Hook 或 URL 同名。

## 目标与范围

用户与一位员工持续交流。页面可先生成本地对话 UUID 和草稿，首条发送时才原子创建后端记录；仍保留显式创建空对话接口供需要它的 API 客户端使用。

## P1 与后续阶段

当前已实现可靠提交、真实模型/方法循环、稳定消息、取消、失败重试、历史分页、问题目录、恢复及受控工具调用。任务、计划、目标、多引擎仍在各自方案中，不作为本轮已实现能力。

## 复用基础与已完成的改造

使用现有身份、Cookie、Origin、JSON/体积校验、权限、模型连接、员工及方法修订。当前助手正文直接保存到 Message，SDK checkpoint 只负责恢复，不再有 RunResult 表或前端选取最终模型轮的逻辑。

## 模块职责与关联

Conversation 是交流容器，Message 是用户输入或助手回复记录，Run 是针对输入的一次处理尝试。ConversationRun 把原输入、助手回复和 Run 关联起来，保证它们属于同一对话。

接受请求时，用户和空助手 Message 已经存在。一次失败重试沿用原用户输入，新增 Run 和助手 Message，旧回复及动作不覆盖。response_id 就是助手 Message ID，不增加 Response 实体。

conversations/service.py 组织命令事务；同模块的准备、授权、发布供请求与后台使用。execution 管可靠运行，agent_runtime 管 SDK 内部循环；普通配置服务保留在所属模块。

## 主流程与执行生命周期

1. 首条发送一并保存对话、用户原文、空助手记录、Run、冻结输入与绑定，返回 202；同键重放返回 200 及原记录当前视图。
2. 后台领取 queued，复核授权并从冻结依据准备。模型与工具等待在业务事务外，动作开始记录失败就不发出调用。
3. 生成中保存普通草稿、思考与动作；SSE 读取这些已提交内容。
4. 候选完成后，共享发布流程在同一事务复核当前授权、保存正文及输出文件关联、结束 Run 并释放活动占用。
5. 用户停止明确指向某条回复，断线不停止。失败重试需当前对话空闲且目标为末次 failed/cancelled/interrupted 回复。

网络结果未知使用原键核对或重发，不能换键再交办。业务明确失败后的重试才创建新尝试。

## 数据设计

Message 的 ID、角色、对话和序号固定。用户正文不可覆盖；助手最终正文只由发布入口写入，终态重复发布和迟到片段不能改写。空正文不等于不存在记录，也不另建一套消息运行状态。

Conversation.revision 在接受和释放占用等变化中同步递增。一个对话最多一个 active 绑定，数据库部分唯一索引兜底。输入与回复使用同对话复合外键，reply_message_id 非空且唯一。完整结构见[数据模型](data-model.md)。

## HTTP 接口契约

| 方法与路径                                                 | 用途及返回                                                    |
| ---------------------------------------------------------- | ------------------------------------------------------------- |
| POST /api/conversations                                    | 显式创建空对话，返回摘要                                      |
| GET /api/conversations                                     | 当前可读范围内的分页列表，可按员工过滤                        |
| GET /api/conversations/{id}                                | 当前带版本摘要                                                |
| GET /api/conversations/{id}/snapshot                       | 同事务摘要、员工安全摘要、最新连续消息页和提问摘要            |
| GET /api/conversations/{id}/messages                       | 历史页；before/after/around 三类游标互斥                      |
| POST /api/conversations/{id}/messages                      | 发送输入，首次可携 agent_id 原子创建，返回 AcceptedSubmission |
| GET /api/conversations/{id}/requests/{key}                 | 只读核对提交；未查到返回 200/null                             |
| GET /api/conversations/{id}/responses/{response_id}        | 当前 ResponseSnapshot                                         |
| POST /api/conversations/{id}/responses/{response_id}/stop  | 精确停止，幂等返回当前 ResponseSnapshot                       |
| POST /api/conversations/{id}/responses/{response_id}/retry | 新键重试末次失败回复，返回 AcceptedSubmission                 |
| GET /api/conversations/{id}/responses/{response_id}/events | 已提交回复快照的 SSE 观察                                     |
| GET /api/conversations/{id}/questions                      | 用户提问目录、搜索、分页与锚点                                |
| GET /api/conversations/{id}/questions/{message_id}/preview | 该输入最新尝试的有界文字摘要                                  |

旧 /api/runs 和旧发送 URL 已移除，没有独立步骤 HTTP 接口；步骤随回复返回，页面本地折叠和分页。

AcceptedSubmission 包含 client_request_id、当前 conversation、原 input_message 和 response。ResponseSnapshot 包含同一次读取的 conversation 与 response。首屏、历史、接受、核对、GET 和 SSE 的助手部分使用同一 AssistantMessageView。

助手字段 content 已选好可见正文；content_state 为 empty/draft/complete/partial。status 表示处理状态，两者各司其职。steps 为有界实际动作，context 表示历史配对数量与截断；can_retry 由服务器表示当前是否可重试，前端还需检查末条回复和交互状态。回复不再包含 ci 或 work_kind。完整字段由 [schemas](../../backend/app/conversations/schemas.py) 和运行 OpenAPI 维护，不在本文复制全部 DTO。

SSE 事件为 response.snapshot、response.finished、access.revoked 和心跳。事件 ID 为回复版本，恢复是读取当前快照，不承诺 token 回放。终态通知只在事务成功提交后可见。连接上限、身份周期复核及所有退出路径的释放由 streaming 负责。

CI 试验接口和员工 ci_repository 字段已移除；发送请求不再接受 work，旧字段返回明确的输入错误。退役运行保留已交付文本和共享动作历史，can_retry=false；历史读取与新普通消息互不阻断。退役和数据规则见[说明](ci-diagnosis/README.md)。

## 前端交互

对话页左侧为正文与输入，右侧辅助栏在新进入对话时默认展开，可收起或通过顶栏重新展开。辅助栏有「历史对话」「员工能力」两项，不包含任务。历史沿用当前使用者与当前员工的服务端分页列表；新回复被接受后刷新列表摘要，切换历史不停止后台运行，侧栏失败不替换正文。

话题标题位于正文上方，顶栏保留员工层级和对话操作。辅助栏顶部统一显示员工身份，两种标签共用；历史使用轻量行与当前项状态，能力按技能、工具、个人知识库分组。附件操作与发送同处输入框，仍使用原上传和选择逻辑。

能力区显示当前启用技能及其就绪状态；有员工配置查看权限时展示已授权工具操作，账号入口沿用本人连接页。个人知识库按当前身份从共享数据层订阅读取，设置复用现有 EmployeeKnowledge 编辑器，保存后摘要同步更新。当前挂载资源不代表本轮实际调用；本轮来源和过程仍在回复中查看。右栏布局与窄屏规则见[对话布局](../../frontend/src/design-system/layout.md#对话与阅读布局)。

useConversation 处理对话交互，useMessage 提供逐条读取、停止、重试和复制，useResponseSubscription 管单个回复的观察与只读重连。内部控制器接收页面提供的身份隔离作用域。

首屏只读一个 snapshot。摘要 version 与单回复 version 分别合并，旧窗口和旧接受结果不会回退当前活动目标；如收到另一个活动回复的摘要，重新读取首屏。正文直接来自服务端，不再解释 SDK 的工具轮。

消息历史保持连续窗口，支持前后分页和按问题定位；问题目录只数用户输入，重试不增加问题编号。历史阅读与最新回复观察分开，迟到历史不能覆盖已观察的终态或正文。

问题导航从第三次用户提问起显示。高亮表示消息区内可见的问答组，可同时高亮多项：一次提问与通过 reply_to_message_id 关联的回复属于同一组，任一消息部分露出也计入；阅读长回复时，提问离屏仍保留该组高亮，重试回复不增加导航项。点击或键盘激活仍以提问起点为锚点，保留顶部阅读留白、焦点与气泡底色反馈；未加载的提问先读取所属窗口再定位。悬停／聚焦只预览，刻度可独立翻阅，不移动正文。键盘焦点与可见高亮分别表达操作位置和阅读范围。

正文区域统一管理消息节点、可见范围及定位反馈，导航通过问题 ID 和定位控制接入，不依赖正文 DOM 或完整会话状态。目录与预览负责各自的读取失败；定位的加载和错误以历史层 jump 状态为准，不混入前后分页错误，也不在菜单中维护副本。具体接入见[模块导航数据流](../../frontend/src/pages/conversations/README.md#导航数据流)。

待确认命令存入当前标签页，按身份和对话隔离。新存储记录版本 2 的回复目标；旧发送保持原键与原文，旧 Run 目标重试无法确认时保留记录并只读核对，不擅自转向最新回复。退役工作输入只核对原请求是否被接受，不转换成普通消息重发；旧入口和对应本地草稿清理后明确提示。

## 外部依赖、边界与错误

管理员能力与资源范围每次由服务器检查，知道回复 ID 不授予权限。配置错误、容量/频率、内容冲突和依赖不可用继续使用应用错误分类；已接受后的运行失败通过回复 status/error 表达，不能假装 POST 未接受。

公开数据不包含模型凭证、内部 SDK 状态或原始供应商异常。模型请求仍可能失败，连接检查成功不等于生成可用。真实上游与离线替身验证分开记录。

## 初始化与维护

启动前显式迁移至 head，应用不自动建表或升级。修改现有数据前按[后端操作](../guides/backend-operations.md#数据库迁移)停服并成套备份业务库、checkpoint 和密钥。不得因 demo 阶段删除历史。

## 验证与验收

[公开协议测试](../../backend/tests/test_response_contract.py) 使用普通 TestClient 验证新协议和真实 SQLite 快照并发；既有运行场景通过测试适配器继续验证执行 ID 下的内部状态。适配器不进入应用，也不证明旧 HTTP 路由仍存在。

## 取舍与后续扩展

保留模块化单体与当前 SQLite 单宿主。不为当前无需求的任务、目标、引擎注册和通用结果容器预建层级。新增来源需先说明自己的接受、授权和交付规则。

## 历史验证入口

本轮结果见[实施记录](../records/platform-refactor-implementation.md)，之前记录保留其当时条件；代码阅读可从[观测流程](../learning/observing-runtime.md)开始。

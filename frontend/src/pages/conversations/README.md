# 对话状态、消息读取与观察

对话页面让用户提交需求、观察员工处理、读历史与成果，并在允许时停止或重试。发送是否已被接受、后台是否成功、观察是否断线是不同状态；模块把它们清楚组织起来，避免网络重连无意重做一次工作。

## 模块设计

完整诊断由[共享执行日志](../../components/execution/README.md)的大弹窗承载，列表支持主题及 Conversation／Run ID 检索，按命中的执行尝试打开。旧 ExecutionTracePage 路由只转到相应宿主弹窗，不再渲染独立日志页；对话内的轻量过程仍原地展开。

页面使用左侧对话主体、右侧默认展开的辅助栏。辅助栏的历史列表与能力标签不创建第二个会话作用域；收起和标签切换不会重新初始化正文或提交工作。窄工作区将辅助栏放在正文下方并限制高度，消息与辅助信息分别滚动。

员工身份统一置于右栏顶部，两个标签共用；话题标题在正文上方。右栏通过画布色、圆角及内缩留白区分主辅，历史不使用表格外框。输入框内组合附件和发送动作，个人知识设置继续复用已有编辑器，仅允许调用方缩短触发文案。

### 一段对话只有一个交互作用域

路由页面取得员工、身份和对话 ID，再显式创建 `ConversationProvider`，传入稳定的 transport 和身份隔离存储键。Provider 创建这一会话的数据实例并负责清理；消息行调用 Hook 只订阅数据，不各自启动网络或后台工作。

`useConversation` 读取会话摘要、可见消息顺序、历史和发送/恢复等操作；`useMessage(id)` 读取指定消息的正文、执行状态、用量和动作，以及绑定这个 ID 的停止/重试/复制。完整正文变化不需要重建整份消息顺序，过期按钮也不能转而操作最新回复。

### 发送确认与回复观察怎样衔接

控制器为输入固定请求标识，并保存待确认命令后发送。接受响应、提交核对、首屏快照、单回复和 SSE 都带相同含义的回复读取结构；控制器分别合并对话摘要版本与回复版本，迟到结果不能倒退当前活动回复。

发送超时但结果未知时，沿用原标识和原输入核对或重发；服务端允许的失败重试使用新标识并生成新回复。观察断线只重新读取/订阅，不发送工作，观察恢复也不能顺手清掉提交错误。待确认停止先记录意图，拿到真实回复标识后才取消对应运行。

### 持续更新为什么按消息订阅

`conversationStore` 保存当前读取投影与消息索引，Context 只传固定实例，`useSyncExternalStore` 订阅会话或单条消息。`useResponseSubscription` 只观察一个目标，收到版本更新后把普通视图合入存储；未变消息和步骤保留引用。

消息组件卸载不拥有 SSE，关闭整个会话作用域才释放读取与订阅，后台仍继续。过程区用 Trace 时间线展示服务器保存的实际动作、名称与状态，思考及必要过程文字原地展开，不提供执行详情跳转；SDK 内部消息不进入浏览器。步骤折叠/分页是本地展示，不重复请求动作。

RunProgress 读取整次回复的当前动作，独立于过程分页显示阶段图标、文案与耗时；并行工具优先，运行阶段有短暂防抖，终态和回复保存状态立即更新。图标过渡通过原生动画实现，不重复请求或生成阶段；初次历史读取静态展示，快速切换或卸载会取消旧动画，减少动态效果时跳过动画。具体展示规则见[对话契约](../../../../docs/reference/conversations.md#前端交互)。

### 个人知识怎样进入本轮对话

右侧「员工能力」中的“我的知识库”复用[独立个人装配组件](../../components/knowledge/EmployeeKnowledge.tsx)，成员也可选择自己的库并独立保存，不要求编辑共享员工。入口显示本人装配数量，不更改员工卡片的共享资源数量，也不修改对话输入草稿或岗位指令。装配在提交消息时由后端捕获；按需模式提供检索工具，由模型判断，先检索模式由平台在回答前执行查询。未处理原件不会因为挂载而直接进入模型上下文。

RunActions从已保存的工具动作显示“检索知识库”“读取知识来源”、查询及知识片段来源，不能仅凭最终答复声称实际调用过工具。正文Markdown与过程来源共用[知识来源路径检查](../../lib/knowledgeSourceLink.ts)：只开放`/knowledge/{UUID}/documents/{UUID}?chunk={64位十六进制ID}`作为站内知识链接，不放行任意相对路径或自动剥除`sandbox:`等前缀。打开来源后仍核对当前库归属和具体片段；不存在的片段明确提示，不改跳到相近内容。

正式回答由[knowledgeCitations](../../lib/knowledgeCitations.ts)在解析后的Markdown树中识别实际知识链接并去重，代码示例不计入引用。[KnowledgeInlineCitation](../../components/knowledge/KnowledgeInlineCitation.tsx)按官方Base UI HoverCard和Button组合显示来源标题标签，打开时通过身份作用域KnowledgeStore读取指定片段；卡片展示章节、片段及原文入口。[KnowledgeSources](../../components/knowledge/KnowledgeSources.tsx)复用官方Trace折叠组合，在完成后的正文末尾列出实际引用来源。ConversationMessage从成功动作的safe_details.sources取得标题，候选元数据只负责名称，不决定引用数量。含知识路径的回答通过Streamdown提供的分块入口整篇解析，以便统一编号；其他正文保留默认分块。默认安全插件、HTML禁用及外链规则继续生效；存档和复制的原Markdown不变，过程原文仍按实际模型输出显示。

连续追问的已核验历史片段由后端提供给本轮。RunActions将接受时的knowledge动作显示为“核对历史知识来源”，可展开查看核验含义与原文链接；它与“检索知识库”是不同的实际动作。前端不从旧消息推断来源仍有效，不自行补登记或替换引用。

过程区和流式正文是观察中的草稿，正式成功结果以服务端的来源、权限和发布校验为准。保存个人装配会使旧装配的在途运行失效；页面保留实际失败说明及允许的重试入口，不自动把失败问答当成已有依据。

### 历史阅读为何使用连续窗口

`useConversationHistory` 保持最新窗口或一段连续历史。跨页定位直接按目标消息取得附近窗口，成功后才滚动/聚焦，失败保留原内容；不能把两个中间有空洞的窗口拼成连续历史。

问答导航另用问题摘要和锚点读取，预览是指定问题最新处理的已保存结果，不订阅生成草稿。目录浏览、正文位置和当前活动回复各有作用，不能用数组下标或 DOM 气泡推算业务轮次。

## 目录与职责

```text
conversations/
├── ConversationsPage.tsx          # 按路由和身份选择员工/会话，创建稳定对话入口和首条发送所需上下文
├── ConversationPanel.tsx          # 组合工具栏、正文区域和输入，提供身份/员工上下文及会话操作
├── ConversationSidebar.tsx        # 组合历史与能力标签及收起操作，历史沿用共享列表与分页
├── ConversationCapabilities.tsx   # 展示当前技能、工具许可及本人知识库，复用已有个人知识库设置
├── ConversationTranscript.tsx     # 组合正文与导航；私有阅读 Hook 管理节点登记、可见组、滚动定位与反馈
├── ConversationProvider.tsx       # 创建并发布当前会话实例，管理身份/会话作用域及读取订阅清理
├── conversationContext.ts         # 提供稳定会话实例给读取 Hook，不把每段正文变化塞进 Context 值
├── conversationStore.ts           # 保存已提交的会话/消息视图及订阅，按记录发布变化并保留未变引用
├── conversationState.ts           # 定义读取、提交、历史和观察的状态转移，并按各自版本合并服务器结果
├── useConversationController.ts   # 协调发送确认、原请求核对、停止/重试及历史和 SSE，区分提交与连接错误
├── useConversation.ts             # 暴露会话摘要、消息顺序、历史、发送和待确认恢复等会话级能力
├── useMessage.ts                  # 按明确消息 ID 订阅内容/步骤及操作资格，绑定停止、重试和复制目标
├── useResponseSubscription.ts     # 维护一个当前回复的快照观察和重连，关闭后取消读取但不取消后台工作
├── pendingSubmissionStorage.ts    # 按身份和会话保存未确认命令及原标识，防止断网后重复创建工作
├── conversationDraft.ts           # 管理尚未提交的输入草稿及隔离键，与已接受命令的恢复分开
├── useConversationHistory.ts      # 维护连续正文窗口、前后游标、指定目标定位和回到最新的读取生命周期
├── ConversationMessage.tsx        # 读取单条消息并展示正文/步骤，按明确消息 ID 和问题 ID 登记及注销节点
├── ConversationComposer.tsx       # 编辑需求和触发发送，依据会话/回复状态控制输入交互
├── ConversationControls.tsx       # 呈现当前允许的停止、重试或连接恢复操作，消费各操作失败
├── ConversationFiles.tsx          # 有界上传并显式选择当前对话文件，只将服务端引用放进提交
├── RunActions.tsx                 # 展示真实模型/方法/工具动作和来源状态，区分请求意图与已执行结果
├── RunProgress.tsx                # 从整轮实际动作派生阶段，显示图标、过渡、状态文字和耗时
├── actionPagination.ts            # 为过程区计算本地动作展示分页，不增加后端步骤查询
├── ConversationOutline.tsx        # 接收可见问题 ID 与定位控制，组合目录和预览，不接触正文 DOM 或会话 Provider
├── useQuestionNavigation.ts       # 管理问题摘要、分页/锚点、局部浏览窗口、缓存与旧请求取消
├── questionNavigation.ts          # 提供问答导航的数据约定及纯计算，保持业务标识与显示位置分开
├── useQuestionPreview.ts          # 读取指定可见问题的最新处理预览，切换/关闭时取消旧目标请求
├── ConversationRuler.tsx          # 呈现可访问的局部问题刻度，处理滚轮、触屏和键盘浏览
└── ConversationQuestionPreview.tsx  # 呈现短文本预览和定位反馈，不自行读取 DOM 或启动回复观察
```

历史列表已归入[共享对话历史](../../components/conversations/ConversationHistory.tsx)，由全局历史、对话侧栏和员工管理页复用；当前对话正文窗口与订阅仍留在本模块。

## 与其他模块协作

[对话 API 客户端](../../lib/api/conversations.ts)及[传输适配](../../lib/api/conversationTransport.ts)封装请求与事件，页面提供身份/路由上下文，基础 UI 负责显示与滚动。后端 [conversations](../../../../backend/app/conversations/README.md) 组织接受、查询与发布，execution/runs 和 execution/runtime 完成实际处理。

本模块使用独立会话作用域，不把高频正文放进员工/技能目录共享缓存；文件接口只处理上传和引用，工具许可在员工配置维护。

## 领域关系与 Hook 命名

Conversation 是整个会话容器，Message 是其中一条用户输入或助手回复。每条助手 Message 关联一个 Run，Run 包含多条 RunAction；用户消息的 run 为 null。失败重试复用用户 Message，创建新的助手 Message 和 Run，各次尝试的步骤互不覆盖。后端 Message 直接保存输入和回复正文；前端 Reply 则组合可见内容、状态和步骤。

| 入口                  | 作用域与职责                                                                                |
| --------------------- | ------------------------------------------------------------------------------------------- |
| useConversation()     | 当前会话的元信息、可见消息 ID 顺序、历史、交互 phase、发送、重连与待确认提交恢复            |
| useMessage(messageId) | 指定已加载消息的正文、执行 status、步骤、用量、执行错误，以及绑定消息 ID 的停止、重试、复制 |

Provider 负责作用域和生命周期，内部的回复订阅、历史窗口和步骤本地分页仍按职责拆分；它们不作为页面的额外业务 Hook 入口。

## 调用

```tsx
<ConversationProvider
  id={conversationId}
  transport={transport}
  storageKey={conversationSessionKey(owner, conversationId)}
  onAccepted={clearMatchingDraft}
>
  <ConversationView />
</ConversationProvider>;

function ConversationView() {
  const { messageIds } = useConversation();
  return messageIds.map((id) => <MessageRow key={id} id={id} />);
}

function MessageRow({ id }: { id: string }) {
  const { message, actions } = useMessage(id);
  if (!message) return null;
  return <button onClick={() => void actions.copy().catch(() => {})}>{message.content}</button>;
}
```

id 是服务端分配的 12 位数字 ID；transport 保持引用稳定。新草稿的 draft 标记只用于本地作用域，首条 send 传 null，由后端创建并返回正式 ID；create 参数提供员工。取得回执先保存真实 ID，再迁移 session 和页面路由。已有会话省略 create。Provider 接收显式 ID、transport 与可选的身份隔离 storageKey，不读取路由、身份、员工选择或导航。

附件区通过 `conversation.conversation?.id` 取得已受理对话的正式编号，不使用可能仍为本地草稿标识的 `conversation.id`。新草稿可独立上传附件，首条受理后才读取对话文件列表。

storageKey 保存真实 conversationId、是否已创建及待确认命令，确认后清理输入，不存凭证。Provider 按会话 ID 和身份存储键隔离实例；旧作用域关闭后，捕获的消息操作不能继续写入。onAccepted 表示提交已接受，可清除仍匹配的草稿，不表示执行完成。

## 问题导航与消息窗口

目录的问题、编号和锚点由服务器提供，不能按助手消息数量、重试次数或 DOM 节点定义业务轮次。ConversationTranscript 内的私有 useConversationReading 根据显式登记的节点与消息区的实际交集计算可见问题 ID；提问和通过 reply_to_message_id 关联的回复归为同一组，部分露出也计入，滚动定位的顶部留白不缩小阅读范围。

正文节点通过 RegisterConversationMessage 登记消息 ID、问题 ID 和元素，解绑时注销；正文适配层维护登记表，不依靠 data-question-id 或 DOM 文本识别归属。前插历史后的可见顺序按实际 DOM 顺序排列，旧登记的清理不能删除同 ID 的新节点。滚动按动画帧合并测量，ResizeObserver 观察消息区与消息行，离开正文后清理监听、观察与待执行定位；已捕获的旧定位命令不再访问会话。

目录保持局部浏览窗口，正文另保持当前连续消息窗口，两者通过稳定问题 ID 连接。DOM 只判断当前显示范围，不作为问题正文、数量或编号的数据来源。

点击未加载目标时，历史读取直接请求该目标附近窗口，成功后才滚动和聚焦。快速切换会取消旧请求并忽略迟到结果，失败保留原窗口和位置。返回最新后读取同一快照的摘要与消息，不把有空洞的历史接到最新末尾。

页面在现有 ConversationProvider 与 MessageScrollerProvider 内只接入正文组件：

```tsx
<ConversationTranscript
  agentName={agent.name}
  avatarId={agent.avatar_id}
  description={agent.description}
/>
```

正文组件内部将 conversationId（未创建时为 null）、latestQuestionId、visibleQuestionIds 和 navigation 传给 ConversationOutline。navigation 的 navigate 发起定位命令，pending/error 只取历史层的 jump 状态；导航不读取正文节点、不接受全量消息，也不保存独立定位错误。目录和预览继续各自拥有读取错误，定位错误由历史层负责，正文区域统一呈现历史读取失败。

### 导航数据流

| 参与者                                          | 接收什么，交给谁                                                       |
| ----------------------------------------------- | ---------------------------------------------------------------------- |
| ConversationPanel                               | 组合工具栏、ConversationTranscript 和输入，维护会话与身份作用域。      |
| ConversationTranscript                          | 登记消息节点，计算可见组，执行历史定位意图，向导航提供 ID 和定位控制。 |
| ConversationMessage                             | 按消息数据登记节点归属，挂载观察、解绑注销；不启动额外网络读取。       |
| ConversationOutline                             | 消费可见问题和定位控制，组合目录数据与预览，将选择交给正文区域。       |
| useQuestionNavigation                           | 按问题 API 读取摘要/锚点，维护有限缓存和局部浏览状态，取消过期请求。   |
| useQuestionPreview                              | 按指定问题读取最新处理的公开预览，关闭/切换时取消旧目标。              |
| ConversationRuler / ConversationQuestionPreview | 渲染刻度和短文本，支持键盘/触屏/滚轮，将明确目标交回业务层。           |
| useConversationHistory                          | 取得指定消息附近的连续正文窗口，提交成功后执行定位。                   |

预览读取已持久化结果，不订阅流式草稿，也不替换正文窗口；每次打开重新核对，避免失败重试后仍显示旧内容。目录数量及锚点以服务端为准，显示细节和窄屏行为见[对话界面契约](../../../../docs/reference/conversations.md#前端交互)。

## 维护与验证入口

[对话契约](../../../../docs/reference/conversations.md)和[运行读取契约](../../../../docs/reference/runtime.md)定义跨端含义；控制器、单消息、订阅与历史测试就近维护。重点核对未知提交、旧作用域回调、版本倒退、断线观察及连续历史，不把前端出现文字当作执行成功。

Run 执行成功与回复保存分别展示：acceptance=pending 时继续订阅并显示正在保存回复，accepted 后才形成正式消息，failed 不改写执行成功。isObserving 与 isActive 分开，等待保存期间不能再次取消已经完成的执行。

侧栏历史摘要在最后消息或对话业务版本变化时刷新，覆盖同一回复执行结束、成果接纳和占用释放；不按每个文字片段刷新，避免正文已完成而侧栏仍显示执行中。现场修复与验证见正式迁移记录。

测试的 transportFixture 直接构造当前 snapshot；首次读取和重新连接只模拟 getSnapshot，历史翻页才模拟 getMessages。夹具保持对话、提问、回复和步骤的标识关联，并保留显式指定的正文状态；待接纳草稿不能自动变成正式正文。请求核对以 200/null 表示未受理，404 是资源访问失败，不能吞成可重发的空结果。

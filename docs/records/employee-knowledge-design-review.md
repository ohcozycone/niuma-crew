# 员工知识装配技术初稿独立评审

日期：2026-11-01。范围：[技术初稿](../proposals/knowledge-assistant/employee-knowledge.md)。方法：独立读取现行员工、知识、对话、工具门控、执行记账、checkpoint和发布代码；未修改代码，未将文档目标当作已实现事实。结论：个人装配和知识模块独立的方向可实施，但须落实以下边界后再定稿。

## 必须修订

1. **高：知识工具不能直接复用MCP授权。** [authorize_tool/assert_binding](../../backend/app/agents/tool_grants.py)要求真实AgentToolGrant、连接和个人账号；[external_tools及ToolExecutionMiddleware](../../backend/app/agent_runtime/tool_calls.py)只构造MCP StructuredTool且拒绝未登记工具。增加明确knowledge binding种类及ConversationAuthorization分支，由knowledge模块检查范围，再接入现有begin_tool/complete_tool。注册工具schema和一段提示词本身不能完成执行授权。

2. **高：当前发起者与对话所有者可能不同。** [ConversationService](../../backend/app/conversations/service.py)将actor.user_id传入prepare，但Run.owner_user_id取conversation.owner_user_id；管理员resources:all可以读取/操作他人的对话。如果按发起者捕获个人知识，再发布到另一所有者会话，可能把管理员私库资料写给该会话所有者。知识启用时在接受及每次guard要求发起者、个人装配用户和会话所有者一致；不要凭Run owner读取别人的私库。管理员既有历史对话阅读权仍存在，不能同时声称任何其他账号绝不可能看到已经交付在对话中的资料。

3. **高：只复核装配revision不足以复用缓存或发布。** [RunStore.begin_tool](../../backend/app/execution/store.py)会先authorize再复用readonly成功结果，但不会检查结果中的文档或Chunk版本；[ConversationAuthorization](../../backend/app/conversations/authorization.py)当前仅检查用过的普通工具许可。knowledge需要持久化Run范围证据，包含kb/document/chunk/version/原文区间；缓存返回前、补读、每次模型guard和最终发布均检查文档仍存在且活动版本相符。重处理不等同撤销装配，须单独检测。证据ID不得跨Run使用。

4. **高：always预检索必须有可恢复的固定动作标识。** [execute_agent](../../backend/app/agent_runtime/langchain.py)会读取checkpoint并可能跳过首次输入构造。预检索应在首次进图前走相同受管工具调用，使用Run内稳定call key；恢复时复用经过重新授权的持久结果。上下文只能加入一次，不能每次恢复多扣预算或重复Embedding；模型循环内依然保留search/read工具。把预检索简单塞入prepare会导致事务内上游调用，把它仅塞入Prompt不能保证实际执行。

5. **高：引用失败/权限撤销不得作为成功或可信部分正文发布。** [ModelExecutionMiddleware](../../backend/app/agent_runtime/middleware.py)先保存模型输出，[PublishRun](../../backend/app/conversations/publication.py)只在成功发布时复核授权；默认快照allow_partial_output=True。知识引用校验失败时，明确禁止把其未验证文本作为有效部分回答交付，并保留安全错误/动作记录。已流出的draft不能当最终成功；页面状态沿用现有draft/complete含义。无需增加隐藏模型修复或自动拼装“已依据”声明。

6. **中：来源持久副本与资料删除后的读取语义要分清。** [ConversationFiles.download](../../backend/app/conversations/files.py)对source文件按对话归属放行，没有knowledge文档当前状态检查。若把知识全文放入普通source副本，再用该通道补读，会绕过删除/卸载规则。使用knowledge自有Run evidence表和受管补读入口；普通文件通道不能自动取得知识源权限。既有已交付聊天正文的历史保留，不等于仍可读取当前知识原件。

## 应写入完整方案的实施细节

- **配置与数据：** knowledge自有settings、选库关系和Run evidence；revision原子替换，最多10库；公共员工目录不暴露个人库名称、描述或数量。个人配置入口与共享员工配置的保存责任分开，普通成员也能从对话页维护自己的装配。
- **召回：** 每库复用当前[KnowledgeService.search](../../backend/app/knowledge/service.py)及[向量检索](../../backend/app/knowledge/vectors.py)，跨库按名次融合，全局Top-K和字节预算。auto可对未配置/失效向量使用BM25，但真实上游错误不得伪装成“无命中”。多个库串行Embedding须受整轮时限、取消检查及调用预算约束，不能让10库各自20秒的超时绕过全局责任。
- **引用：** 证据编号和链接由平台产生，模型仅选择已登记来源。仅接受本Run登记的知识URL/证据标识，精确核对kb/doc/chunk；最终检查只证明引用身份和当前可访问性，不证明每个自然语言结论都由证据支持。提示规则和真实题集评测承担语义效果验证。无工具调用或无命中时不得声称已查到资料。
- **职责说明：** 名称/用途序列化为资料目录数据，自动规则与真实schema分开装配，不改写员工岗位Prompt。资料文本、描述和工具返回中的指令都不能扩大当前权限、重定向到Web或索取Key。
- **就绪状态：** 仅原件、不完整关键词、部分向量、无命中、上游失败分别表达；按已生效文件检索，不能因一个未处理文件就禁用整库，也不能将原件全文自动送模。
- **模式边界：** on_demand是模型选择，不保证每次有关问题都检索；always保证先调用受管检索，不保证检索有命中或模型答案正确。无挂载不注册知识工具。现有旧快照缺少knowledge字段应按无装配兼容读取。

## 复核用例

普通成员个人装配与共享员工；两个用户使用同一员工隔离；管理员不能将个人KB带入他人对话；临时描述注入不改变权限；多库、pending-only、BM25-only、部分向量和明确vector故障；跨库Top-K/预算；未知证据ID/跨Run ID/伪造URL；运行中卸载、删除、重处理；readonly缓存复用仍授权；always恢复只检索一次；失败不发布错误引用正文；真实LangChain循环与页面选择→保存→提问→动作→来源查看。

本评审接受后续补充的“knowledge自有settings/links/run_evidence、专用binding、受管always预检索及无隐藏模型修复”作为最小落地路线。以上发现应合入最终方案与测试，不需要再把已授权技术选择交给用户确认。

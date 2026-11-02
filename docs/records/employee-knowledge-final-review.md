# 员工知识装配最终代码复核

日期：2026-11-01。独立子代理只读复核[实施定稿](../proposals/knowledge-assistant/employee-knowledge.md)对应的运行装配、授权、工具门控、证据、发布与引用渲染。此次未改实现、未重跑后端测试；测试和真实页面结果由主验收记录维护。

结论：本次静态查看时未发现授权、恢复缓存、always预检索或失败部分正文正式发布的阻塞缺陷；来源渲染核对只覆盖了平台生成的规范路径，不是全格式验收。后续真实Kimi页面测试发现模型会给相对来源加`sandbox:`前缀，原输出验证正则可能仅匹配后半段而误通过；本次静态评审未发现该模型格式问题。该问题转入后端修复与新增负例验证，发现、修复与最终结果以主验收为准，不能将这里的“未发现阻塞”理解为全覆盖或语义正确性保证。

## 核对依据

1. **个人资料与运行拥有者一致。** [会话接受](../../backend/app/conversations/service.py)拒绝把发起者的个人知识装入他人拥有的会话；[ConversationAuthorization](../../backend/app/conversations/authorization.py)复核本轮知识用户、Run拥有者并调用knowledge的当前状态检查。[assert_current与assert_evidence](../../backend/app/knowledge/employee.py)核对装配修订、所选库集合、库所有者、员工状态、Run发起人/拥有者及已登记Chunk存在性和完整快照，规则重切不能仅依赖不变的文档version蒙混。
2. **知识工具和缓存没有绕开宿主。** [知识工具适配](../../backend/app/agent_runtime/knowledge.py)只将query/library_ids或evidence_id/offset提供给模型，调用回调前后执行guard；[ToolExecutionMiddleware](../../backend/app/agent_runtime/tool_calls.py)沿统一begin/complete通道保存结果。[RunStore.begin_tool](../../backend/app/execution/store.py)在寻找并返回只读成功缓存前执行authorize及参数指纹检查，所以缓存命中仍经过当前装配和证据校验。知识回调从bootstrap经[ConversationPreparation](../../backend/app/conversations/preparation.py)注入，SDK适配器没有导入knowledge ORM或任意拥有者身份。
3. **always是实际操作，失败不冒充证据。** [LangChain执行入口](../../backend/app/agent_runtime/langchain.py)在首次模型调用前触发固定`knowledge:presearch`动作，同样经过预算、取消和恢复授权检查；结果仅加入当前输入作为不可信参考。显式向量或真实上游故障由[检索服务](../../backend/app/knowledge/employee.py)返回失败状态，auto只按当前可用能力选择BM25/混合。每库候选及跨库Top-K、证据序列化预算和来源补读长度均有限制。
4. **最终引用与发布有二次检查。** [准备流程](../../backend/app/conversations/preparation.py)给有知识装配的快照设置`allow_partial_output=False`；[PublishRun](../../backend/app/conversations/publication.py)在失败时清除正式部分正文，成功时在发布事务内再次授权并验证引用。[verify_answer](../../backend/app/knowledge/employee.py)检查Run范围证据ID和准确来源路径；[Markdown](../../frontend/src/components/common/Markdown.tsx)及[执行过程](../../frontend/src/pages/conversations/RunActions.tsx)共同使用[严格路径白名单](../../frontend/src/lib/knowledgeSourceLink.ts)，只开放UUID库/文档及64位片段标识的站内来源。来源打开后继续走原有知识库所有权和片段存在性检查。

## 结论限制

权限撤销、删除或重切后的行为还须以并发与恢复用例验收，不能靠静态阅读替代。当前模型流式过程可能先展示未完成的草稿，正式正文成功交付以最终校验及发布事务为准。引用登记及路径有效不证明回答结论已被资料充分支持；按需模式能否正确选择工具与查询词仍需实际模型题集核对。

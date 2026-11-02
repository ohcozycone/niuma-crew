# API：按用户操作提供能力

本文保留[已采纳方案](README.md)的对外协议设计，当前范围已实施。实际接口以[对话](../../reference/conversations.md)、[执行](../../reference/runtime.md)和[CI](../../reference/ci-diagnosis/api.md)契约。

## 1. API 不镜像后端目录

用户能看对话、发消息、停止回复、重试失败和浏览诊断。接口按这些操作组织。一个接口可以调用多个用例和模块；不为每张表提供 CRUD，也不要求前端知道 RunResult、SDK 图或内部调度器。

保留 /api/conversations。responses 表示“对话中的助手回复”，response_id 就是助手 Message ID，不新增 Response 表或服务。后端按对话和回复关联找到 Run，再检查归属与操作资格。

当前对话不公开 /api/turns；旧 /api/runs 只在限期切换期保留。未来若有独立执行管理客户端，再设计相应接口。

## 2. 当前能力的目标接口

| 方法与路径                                                       | 用户用途                 | 关键语义                                           |
| ---------------------------------------------------------------- | ------------------------ | -------------------------------------------------- |
| GET /api/conversations                                           | 对话列表                 | 按当前用户范围分页，支持现有员工筛选               |
| GET /api/conversations/{id}/snapshot                             | 首次加载或只读恢复页面   | 同一读取快照返回摘要、最新连续消息窗口与当前回复   |
| GET /api/conversations/{id}/messages                             | 浏览历史                 | before/after/around 互斥，保持稳定 ID 与连续窗口   |
| POST /api/conversations/{id}/messages                            | 发送输入                 | 首条可原子创建对话；接受202，同键重放200           |
| GET /api/conversations/{id}/requests/{key}                       | 核对提交是否已经接受     | 只读，不创建工作；未查到不能推断原请求永远不会到达 |
| GET /api/conversations/{id}/responses/{response_id}              | 读取某次回复             | 同一种助手读取结构，包括状态、正文与过程           |
| GET /api/conversations/{id}/responses/{response_id}/events       | 持续观察回复             | 只发已保存快照，断线不取消                         |
| POST /api/conversations/{id}/responses/{response_id}/stop        | 停止这次回复             | 幂等，绝不转而停止最新处理                         |
| POST /api/conversations/{id}/responses/{response_id}/retry       | 重试该失败回复           | 新请求键、新 Run 和回复，继续原用户输入            |
| GET /api/conversations/{id}/questions                            | 提问目录                 | 只数用户消息，支持筛选、锚点与现有分页             |
| GET /api/conversations/{id}/questions/{message_id}/preview       | 查看该问题最新回复摘要   | 不读取 SDK，不加载整段正文                         |
| GET /api/conversations/{id}/responses/{response_id}/ci-diagnosis | 查看专业阶段、来源与报告 | 返回 CI 自身版本；保持执行中专业进度可查           |
| POST /api/conversations/{id}/responses/{response_id}/ci-feedback | 反馈诊断                 | 仅成功且报告存在；相同内容重放，不覆盖不同反馈     |

保留现有身份、员工、技能、模型连接、公司规则、配置摘要、健康与公开信息接口的业务名称和行为。CI 配置与安装仍归其专业配置接口，不为改回复读取路径而搬入通用执行 API。

空对话创建仅在确有产品调用者时继续公开；当前“进入新对话”可以只是浏览器草稿，不需要先写空对话。

## 3. 发送与首次创建

请求保留现有字段含义，示意如下；最终结构由 schemas 与 OpenAPI 表达：

```json
{
  "client_request_id": "一次操作固定的 UUID",
  "content": "请分析这次构建为什么失败",
  "agent_id": "首次创建时指定的员工 ID",
  "selected_skill_ids": []
}
```

1. 新对话由客户端先生成 UUID，页面尚未提交时只是本地草稿。
2. 首条请求需要 agent_id；已有对话若仍传入，必须与原员工一致。
3. 同一接受事务保存对话、用户输入、空助手回复、Run、冻结输入和绑定；任何拒绝全部回滚。
4. 返回对话摘要、已保存用户消息与助手回复视图；前端立即获得准确回复 ID。
5. 同键重放沿用原用户消息、回复和 Run 的身份，返回这些记录的当前视图，不冻结第一次 queued 快照；不同内容使用相同键返回冲突。
6. 重放在归属检查后、当前容量和配置检查前完成，避免已经接受的请求因配置变化被误判成新失败。

规范化、摘要和操作名有版本；API 路径改变不随意改变旧幂等键的含义。待确认命令如何升级见[迁移](migration.md)。

## 4. 一种助手回复结构用于所有读取入口

用户消息较简单：id、role=user、sequence、content、created_at。

助手视图可表达为：

```typescript
type AssistantMessageView = {
  id: string; // 就是 response_id，也是助手 Message ID
  role: "assistant";
  sequence: number;
  reply_to_message_id: string;
  version: number;
  status:
    "queued" | "running" | "cancelling" | "succeeded" | "failed" | "cancelled" | "interrupted";
  content: string; // 服务器已经选好的可见正文
  content_state: "empty" | "draft" | "complete" | "partial";
  steps: PublicStep[];
  usage: PublicUsage | null;
  error: PublicError | null;
  context: { pair_count: number; truncated: boolean };
  ci: { version: number; has_report: boolean } | null;
};
```

这是公开读取格式，不是新实体。最终字段沿项目 snake_case 约定，并保留必要的当前时间、方法与来源展示信息。

- empty：当前没有文字，是否仍在处理只看 status；空正文失败也使用此值。
- draft：仍在活动且有可见文字。
- complete：succeeded 的非空完整答复。
- partial：其他终态保留了非空未完成文字。以上映射由所有读取入口共用。
- steps 是经过脱敏和限量的实际动作，不包括原始 SDK 对象或凭证。
- version 可由内部 Run.revision 映射；CI 更新时也在同事务推进观察版本。
- 终态正文来自 Message，活跃正文来自已保存的规范化进度；前端无需在 assistant_content、current_model 和 result 中自行选择。

首屏、历史、单回复、接受结果、请求键核对与 SSE 的助手部分使用同一结构与版本含义。

单回复 GET、停止响应、response.snapshot 和 response.finished 使用 ResponseSnapshot 外壳：conversation 为当前带版本对话摘要，response 为上述助手视图；两者来自同一读取事务。这样终态能把释放占用后的新 scope_version 传回页面，不能只本地清空活动目标却仍持有旧摘要版本。较旧版本不能覆盖较新版本，同版本不得返回互相冲突的正文或状态。

是否显示停止和重试由当前对话作用域、身份能力、末次回复及状态共同计算，不把这类会随其他回复变化的资格塞成一份不可更新的旧回复状态。服务器每次命令仍重新核对。

## 5. 首屏快照为什么单独提供

当前前端分别读元信息和消息页，需要修补“两次读取之间刚好接受新请求”的竞态。

snapshot 在同一真实数据库读取事务中得到：

- 对话摘要、员工安全摘要；
- active_response_id、last_response_id；
- 最新连续消息窗口与游标；
- 问题数量及最近问题标识等当前页面必要摘要。

对话摘要带 version，映射 Conversation.revision，作为 scope_version 使用；接受、释放占用和元信息变化同事务递增。客户端分别合并摘要版本与单回复版本，不能用旧 snapshot 回退 active_response_id 或重试资格。

发送、重试与请求键核对共用 AcceptedSubmission：client_request_id、conversation（当前摘要及 version）、input_message、response。请求未查到返回200及 null，仅表示此刻未找到。重试核对返回新回复，input_message 仍是原问题。迟到接受结果不能擅自把对应回复设为活动，应以带版本的当前摘要为准。

不同时加载完整历史、全部配置或整份 CI 来源。SQLite 实现必须确认真实开启一致读取，不能只因使用 with Session 就假定多次 SELECT 属于同一个快照；并发测试应在两次读取之间提交新处理，验证返回不会混合两个时点。

历史页继续独立读取，不因新接口一次返回首屏就取消按需分页。

## 6. 停止与重试

停止先核对用户、对话和准确回复关联：

- queued 可直接结束并释放占用；
- running 记录 cancelling，由看护收束；
- 已终止则幂等返回当前视图；
- 迟到请求不能影响别的回复。

重试仅接受当前对话末次 failed/cancelled/interrupted 回复，在对话空闲时使用新请求键：

- 复用原用户消息；
- 捕获当前有效配置；
- 创建新回复与 Run，记录重试来源；
- 旧回复、过程与正文不覆盖。

网络失败但不知道发送结果时使用“请求核对与原键重发”，不是调用这个重试接口。

## 7. SSE 与断线恢复

| 通知              | 内容与动作                                             |
| ----------------- | ------------------------------------------------------ |
| response.snapshot | 已保存的 ResponseSnapshot，分别按摘要和回复版本更新    |
| response.finished | 终态助手视图与提交后的对话摘要；只有发布事务成功后发送 |
| access.revoked    | 访问已经失效，清理敏感页面数据并关闭观察               |
| 心跳              | 维持连接，不改变业务状态                               |

事件 ID 使用公开回复版本。Last-Event-ID 用于决定是否需要补当前快照，不承诺回放所有 token 或中间通知。前端 GET 恢复与 SSE 使用同一读取方法。

观察建立前的错误按普通 HTTP 返回；连接建立后的撤权通过明确事件结束。离开页面只取消观察，不能把断线解释成用户停止。

当前动作有预算和大小上限，历史及 SSE 继续随回复返回过程；展开与步骤分页保留前端本地行为。本次不增加独立步骤请求或 token 事件总线。

## 8. 权限、错误和返回边界

所有接口继续使用 Cookie、Origin/JSON/体积校验、限流及资源范围检查。游客仍只看允许公开的字段；“知道 response_id”不是获得权限。

错误继续使用当前应用分类及公开代码：

- 未登录或身份失效；
- 权限不足、资源不可见；
- 参数无效或内容超限；
- 正在处理、不能重试、请求键内容冲突等业务冲突；
- 频率或执行容量不足；
- 当前依赖不可用。

已接受后的运行失败通过助手 status/error 表达，不伪装成最初 POST 没有被接受。原始异常、连接秘密、内部 SDK 状态不进入响应。公开提示不替代数据库和服务的实际检查。

CI GET 返回自身 version。反馈响应返回已提交的 CiDiagnosisView（含反馈与新专业版本）及当前 AssistantMessageView；反馈请求服务同事务递增 Run 观察版本，终态状态和正文不变。客户端切换回复或期待版本时取消旧读取，迟到旧版不能覆盖新版；has_report 不单独代表成功，反馈仍需 status=succeeded。

旧 HTTP 路由与新接口在切换期可以调用同一用例，但不双写数据。退出条件与删除批次见[实施计划](migration.md)。

## 实现位置：请求服务与共享流程

对话 HTTP 分组位于 api/routes/conversations：router 接参数并转换 HTTP 响应，service 组织发送/停止/重试/反馈请求事务，streaming 管 SSE。历史与快照直接使用已有查询，不增加只转调的服务方法。

准备、组合授权和最终发布分别位于 conversations/preparation、authorization、publication，API 与后台共用。其他配置接口继续调用所属模块 service；CI 配置安装留专业服务，对话内反馈由请求服务组织专业记录和公开版本的共同事务。

这次目录归位不改变本页的 URL、身份、幂等、响应结构和版本约定。具体调用和事务见[服务归属](service-boundaries.md)。

# HTTP 接入、协议与观察连接

页面保存岗位、发送消息或下载文件，都通过本模块的 HTTP 接口进入后端。它将请求变成明确业务调用，并把结果转换为 JSON、Cookie、文件、跳转或事件流；业务规则和事务仍由所属模块决定。

## 模块设计

### 一次普通请求经过哪些文件

应用由 bootstrap 装配具体服务、创建 FastAPI 应用并挂载浏览器安全中间件，`router.py` 汇合各组路由。写请求先校验来源、内容类型和体积；路由依赖读取会话，取得可信当前身份和已装配服务，再校验请求字段及入口能力。

例如修改员工时，`routes/employees.py` 接收岗位字段及预期版本，调用员工服务。服务检查创建者、版本及装配并共同保存，路由只转换响应。这使同一业务入口也能被后台等受信入口调用，而无需构造 HTTP 请求。

### routes/employees.py 到底管理什么

这里的员工是可复用岗位配置。该文件提供岗位的创建、目录查询、详情、修改与删除，随完整岗位配置读写工具许可，为当前使用者取得/设置本人账号绑定，并返回发起对话需要的使用摘要。技能与模型选择包含在员工编辑输入中，具体检查归员工服务；运行中的模型循环位于 execution/runtime。

路由按用户操作组织协议，不要求对后端每个内部对象各建一套 CRUD。公开展示使用单独字段白名单和有效会话；完整管理详情、公开目录和运行摘要有不同权限及数据范围。

### 耗时处理与观察接口为何分开

对话发送接口只接受工作并返回稳定回复标识。`streaming.py` 通过请求生命周期依赖预检并持有订阅名额，观察已保存的回复快照并定期复核访问权。路由产出官方 ServerSentEvent，FastAPI EventSourceResponse 生成器路由负责 JSON 编码、SSE 帧和空闲心跳。重连读取当前状态；浏览器断线、发送失败或取消均释放观察名额，明确停止请求才通知业务取消。

当前数据库为同步读写。普通同步路由由框架工作线程处理；异步上传、工具发现或 SSE 内需要同步读写时显式转线程，Session 不长期交给 HTTP 连接或共享给后台任务。

### 协议适配的结果怎样保持一致

JSON 由明确响应模型定义；上传、下载、OAuth、空响应和 SSE 使用各自协议。业务异常表达失败含义，错误适配决定 HTTP 状态及安全正文；前端静态交付另处理压缩、缓存和页面回退，未知 API 不能被前端页面吞掉。进程内限流控制登录等请求频率，多进程扩容时需要另外设计共享策略。

## 目录与职责

```text
api/
├── router.py                      # 注册各组业务路由及通用错误响应，将已装配能力暴露为 HTTP 协议入口
├── dependencies.py                # 从请求会话解析可信身份，检查入口能力，并取得应用启动时创建的业务服务
├── security.py                    # 在请求进入业务前校验来源、内容类型和大小，添加浏览器安全响应头
├── errors.py                      # 把业务/校验失败转换为 HTTP 状态与脱敏响应，保留可重试等待信息
├── failure_boundary.py            # 为 HTTP 响应关联诊断 ID，安全报告未知故障，保护已开始响应的协议
├── rate_limit.py                  # 按当前进程维护请求限速，约束登录、游客及其他高频操作
├── frontend_delivery.py           # 提供生产页面及静态资源，选择压缩副本、缓存和页面回退，保留 API 的真实错误
├── streaming.py      # 预检与持有订阅名额，产出官方事件对象，定期核对访问权
└── routes/
    ├── auth.py                    # 提供管理员/GitHub 登录、游客会话和退出，读写浏览器会话 Cookie
    ├── employees.py                  # 提供岗位配置的创建/查询/修改/删除，以及技能/工具装配和使用者本人账号绑定接口
    ├── skills.py                  # 提供方法编辑、标准包预览导入/导出、来源目录同步及支持文件读取接口
    ├── mcp.py                     # 提供工具服务与本人账号维护，发现远端操作并确认或丢弃候选清单
    ├── mcp_oauth.py               # 处理本人账号授权会话、轮询、撤销和标准 OAuth 回调
    ├── capabilities.py            # 接收搜索、类型和分页条件，返回技能及 MCP 服务的联合概要清单
    ├── model_connections.py       # 提供共享模型连接的维护、服务预设和主动连通检查，不在普通保存中生成回答
    ├── organization_rules.py      # 读取和带版本替换全员规范，交给规则服务检查保存冲突
    ├── conversations.py           # 接受发送/停止/重试命令，并提供对话历史、问答导航、回复快照和观察入口
    ├── files.py                   # 有界接收上传字节，按当前对话权限列出或下载已允许的文件
    ├── public.py                  # 向有效会话提供员工和技能的公开字段，不返回完整指令、账号或秘密
    ├── configuration_summary.py   # 返回员工、技能和收藏数量摘要，供目录与侧栏展示
    ├── health.py                  # 分别说明进程是否存活、执行宿主是否还能接受新工作
    └── knowledge.py               # 提供本人知识库/文档管理、后台处理、三种检索、员工个人装配与来源读取
```

## 与其他模块协作

API 依赖 auth 和所属业务入口，服务由 [bootstrap.py](../bootstrap.py) 创建。员工装配及本人账号选择归 employees，服务/账号/外部调用归 mcp，联合检索归 capability_catalog，接受与交付归 conversations。

业务服务继续显式检查权限及资源范围并拥有写事务。API 不反向被业务、执行宿主或模型 SDK 依赖，不在请求内重新创建默认配置服务，也不把短 HTTP 事务延伸到整段模型执行。

## 应用错误分类与 HTTP 转换

业务抛出 [app.errors](../errors.py) 的具体错误，只表达失败含义；[errors.py](errors.py) 映射 HTTP 状态、生成安全响应并保留 Retry-After。已登记分类的子类按 MRO 继承最近分类，未分类的 ServiceError 不映射为业务拒绝。已知业务错误返回 `{detail:{code,message}}`；参数校验的 422 返回脱敏条目列表，只保留 type、loc、msg。数据库 busy/locked 转为可重试的 503，未知故障保留服务器错误，不统一吞成业务拒绝。来源、体积和媒体类型拒绝由 security 处理。

[failure_boundary.py](failure_boundary.py) 只处理 HTTP，位于浏览器安全中间件外层；成功、已知错误、字段校验和来源等提前拒绝都返回 `X-Request-ID`。请求提供的 ID 必须符合 ASCII `[A-Za-z0-9._-]{1,64}`；缺失、重复、非法或超长值重新生成。ID 仅用于诊断，不参与认证、Run 身份或业务幂等。

未知异常发生在响应开始前时，API 返回 `500` 和 `{detail:{code:"internal_error",message}}`；非 API 返回安全通用文本 `500`，不会把资源故障全部改成 JSON。500 显式携带 `no-store`、`nosniff` 和关联 ID。响应已开始后，包括 SSE、普通流和 BackgroundTask，只记录 ID、异常类型与堆栈位置帧，再传播不含原异常值、cause/context 的安全异常；不发送第二个响应，也不宣称能修改已交付状态。取消不转换成 500，其他 ASGI scope 及脱离 HTTP 的 Runner/维护任务不由此接管。诊断不记录异常原文、源代码行、SQL/params、请求输入或凭据。

GitHub 登录回调以 303 跳转报告已知失败并清理临时 Cookie；工具 OAuth 回调由 tools 校验原平台会话及 state，不新增临时 Cookie，303 仅携带资源/授权会话标识，授权码不进入前端路由。回调访问日志去除查询串；SSE 建流后认证或权限失效发送 access.revoked。已接受工作的执行失败写入回复状态，不改写原接受响应。错误响应不得包含密码、凭据、原始数据库信息或上游异常正文。前端事实保留、身份重核、静态交付与恢复接入见[跨端异常标准](../../../docs/reference/failures.md)。

## 维护与验证

工程约束见[后端手册](../../../docs/engineering/backend.md)，协议语义从[现行契约](../../../docs/README.md#现行契约)进入，字段以 schema 和 OpenAPI 为准。重点验证见[API 职责](../../tests/test_api_responsibilities.py)、[资源边界](../../tests/test_resource_operation_boundaries.py)、[错误转换](../../tests/test_api_errors.py)、[安全 HTTP 边界](../../tests/test_failure_boundary.py)和[运行边界](../../tests/test_runtime_boundaries.py)。

工作提交通过对话路由进入 ConversationService，由应用组织输入并调用 execution/service.py 的内部受理操作。对话在首次发送时原子创建；摘要与正文通过 snapshot 和回复协议读取。工具许可随员工整体保存，个人账号绑定仍有独立的本人关系入口。没有独立 Run 路由、空对话创建、单独摘要读取或沙箱状态路由。

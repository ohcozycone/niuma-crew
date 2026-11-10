# 访问异常与恢复接入

本标准定义浏览器、HTTP、路由与 Run 失败如何进入产品界面。后端公开错误的分类和响应格式见本文后半部；视觉尺寸由设计系统 [C21](../design/components.md)维护。

## 一条事实链路，两个展示入口

```text
HTTP / 连接 / 路由 / Run.error
  → ApiError 或 clientFailure（来源与公开事实）
  → 原 Resource / 页面操作 / 会话控制器（状态与恢复所有权）
  → lib/failures.resolveFailure（上下文、文案、动作筛选）
  → FailureState 或 FailureNotice（仅展示与手动交互）
  → 原拥有者执行读取、核对、配置或返回
```

[`lib/failures`](../../frontend/src/lib/failures/resolve.ts)不依赖 React、路由或请求模块之外的业务状态；[`copy.json`](../../frontend/src/lib/failures/copy.json)为纯公开文案，静态生成器同源消费。分类精确规则、资源标题和插画注册集中在 [`catalog.ts`](../../frontend/src/lib/failures/catalog.ts)。新增业务 code 不必复制展示组件，也不要求后端导入前端枚举。

`Failure`保留 source、真实 status（无 HTTP 响应则 null）、code、公开 message，以及可选 requestId、retryAt 和字段 issues。普通 Error 仅进入安全通用提示；预期的客户端校验使用`clientFailure(code, message)`，不可把原始异常值当作文案。Resource 的`error`是由同一`failure`导出的兼容字符串，不另维护一份事实。

| 当下情况                            | 展示入口                                  | 恢复方式                                        |
| ----------------------------------- | ----------------------------------------- | ----------------------------------------------- |
| 首次读取失败且没有可用内容          | `FailureState`，占据原目标区              | 仅提供真实可执行的重读、配置或返回              |
| 同身份同资源刷新失败，仍有内容/草稿 | `FailureNotice`，保留原内容               | 重读；不得使编辑器卸载或宣称草稿已保存          |
| 明确401、403，或详情已不存在        | 原状态所有者清除受限/无效内容，再展示状态 | 登录重核或返回；清除后旧请求不得复活数据        |
| 保存、上传、连接测试等操作失败      | `FailureNotice`或原`FormField`定位        | 保留输入；配置拒绝先修配置；冲突先核对版本      |
| 写请求响应未知                      | 局部 Notice，`outcome: unknown`           | 先核对，过滤普通 retry；不能自动重放写请求      |
| SSE中断、Run终态失败                | 原会话消息/执行区域                       | SSE只重连GET；沿原提交键核对；Run不伪造HTTP状态 |
| 正常空列表、无搜索结果              | 原正常空态                                | 不包装成访问异常                                |

身份读取失败不自动降为游客；只有明确的身份401进入会话结束流程。无原因的`access.revoked`触发身份重核，不能凭空认定登录失效。上游模型或工具的认证错误属于配置，不代表平台账号退出。

## 六类插画与文案

| 类别       | 代表场景                              | 默认标题                         | 配图含义                         |
| ---------- | ------------------------------------- | -------------------------------- | -------------------------------- |
| 内容未找到 | 页面、员工、技能、知识库/文档不可访问 | 这个页面没有找到；按资源替换标题 | 极简飞碟接走网页，原处留下空位   |
| 身份与权限 | 401、403、错误凭据                    | 当前账号无法访问                 | 完整页面前的闭合访问挡杆与挂锁   |
| 连接问题   | 未建立连接、502、订阅中断             | 暂时无法连接服务                 | 网络插头与匹配服务端口尚未连接   |
| 服务异常   | 500、未分类处理失败                   | 服务暂时无法完成处理             | 烤面包机把工作做过头了           |
| 等待与限流 | 429、超时、容量不足、提交待确认       | 请稍后再试                       | 请求卡片在关闭的服务入口外等待   |
| 配置与冲突 | 前置配置不足、409/422、上游认证失败   | 当前配置需要检查                 | 所有部件都在，一块模块未对齐安装 |

分类优先使用明确 code，再按来源和真实状态兜底；同一 code 在详情与写入中的标题和策略可以不同。说明优先使用经过服务端脱敏的公开 message。没有维护信号不称“正在维护”，连接失败不归咎用户网络，没有响应不显示虚构500。插画不包含数字、文字或按钮，替换图片不影响右栏。

正式PNG位于[`public/failures`](../../frontend/public/failures)，生成来源、提示词和替换历史见[`failure-assets.json`](../../frontend/failure-assets.json)。正式组件和静态错误页使用同一资源，插画只辅助识别故障类别，具体原因由文字说明。

插画表达异常大类，真实原因仍由右侧文案与错误事实说明。等待图不表示服务已确认受理、正在处理或必然成功；配置图不宣称某个资源被删除。替换插画不改变分类、HTTP事实和恢复操作。

## 最小接入方式

```tsx
<FailureState
  failure={resource.failure}
  context={{ operation: "initial-read", resource: "agent" }}
  actions={[{ label: "返回数字员工", kind: "return", href: "/agents" }]}
/>

<FailureNotice
  failure={resource.failure}
  context={{ operation: "refresh", hasUsableData: true }}
  actions={[{ label: "重新读取", kind: "retry", onClick: resource.refresh }]}
/>
```

先选择已有的`ResourceStatus`、`useResource`、`useFailureState`或`useSaveOperation`适配器；只有不存在相应状态所有者时直接接入组件。页面提供上下文和实际动作，不通过字符串匹配判断401/404，不创建第二份请求缓存、全局错误 Provider 或全局跳转拦截器。

`actions`只描述存在的能力。中央策略过滤配置/权限上的盲目 retry，以及结果未知时的普通 retry；`configure`必须指向有权限的配置入口，`reconcile`必须是真正的结果核对。按钮等待异步动作完成并阻止重复点击。没有动作、说明或图像时不渲染空占位；图像加载失败自动退为文字。

`Retry-After`接受非负整数秒或规范 IMF-fixdate，转换为绝对`retryAt`。缺失、非法日期不编造等待时长；重挂载不重置，截止只解锁手动按钮。默认404不自动离开页面，不启用统一自动重试或自动重定向。

## 路由、启动与服务交付

路由的`RouteFailure`使用静态可加载的最小组件；根故障不依赖 Layout 或身份请求成功，工作台子故障保留壳层。懒加载失败由`routeModule`显式标记，不根据英文异常文案猜测版本。

SPA未知路由保存`source: client, status: null`，展示层单独显示逻辑码404；只有服务器文档响应才带真实HTTP404，不能把页面上的数字反写为传输事实。

后端HTTP边界为响应提供安全`X-Request-ID`，未开始响应的未知API异常返回安全500 JSON，非API故障返回通用文字。响应已开始只记录脱敏诊断并传播安全异常，不发送第二个响应；取消不转换成500。ID不参与认证、Run标识或幂等。

构建在压缩前生成独立404/500/502/503/504文档，并提供无JS与入口资源失败提示。React真实挂载后清理启动观察器。已知前端深链先交付SPA，未知文档导航返回真实404；API、资源、点路径、非文档请求保持原协议，不以错误HTML替代资源。

当前本地同源服务不能在自身完全停机时交付错误页。可选独立代理模板及验收前提见 [Nginx说明](../guides/backend-operations.md)；交付模板不代表安装或部署完成。

## 修改与验证

新增错误先核对来源和操作语义，再修改中央精确规则或公开文案；只有显示族变化时才增加美术资源。测试优先覆盖事实保留、同码不同上下文、撤权清理、写入核对和计时，避免为每个 code 复制相同组件测试。

正式可交互示例在文档站「业务样板」的交互示例中；开发环境另提供`/demo/failures`，可切六类、完整/短/极短/长文案、无图和服务端等待示例。两者使用同一正式组件；示例动作不访问业务数据。

设计文档内嵌时，宿主通过 `FailureState.illustrationSrc` 传入带文档挂载前缀的插画地址；默认仍使用平台资源目录，隐藏插画与加载失败后的文字回退保持不变。

## 执行失败事实与应用文案

Agent 与 Execution 上报 code 和技术 kind，执行层决定终态、取消、恢复与结果是否确定；应用侧决定文案、展示族及操作入口。技术类型不等于 HTTP 状态或界面分类，重试也不能仅凭类型或文字决定。

| 位置                                                         | 职责                                                                    |
| ------------------------------------------------------------ | ----------------------------------------------------------------------- |
| [app/errors.py](../../backend/app/errors.py)                 | CodedFailure 与 FailureKind；业务拒绝的具体异常类型；不包含运行文案目录 |
| [agent/errors.py](../../backend/app/agent/errors.py)         | 模型、工具循环及存档失败的稳定码与技术类型                              |
| [execution/errors.py](../../backend/app/execution/errors.py) | 执行错误定义、可信异常归一及终态处理；不依赖展示文案                    |
| [public_errors.py](../../backend/app/public_errors.py)       | 应用默认公开文案；HTTP 和对话在输出时选用，考核可使用自己的说明         |

技术 kind 包括校验、授权、配置、冲突、未找到、限额、依赖、操作、存储、中断、取消及内部故障。错误码和类型的含义须保持稳定；新增文案不使一个错误码获得执行资格，删除文案也不改变执行处理。未知原始异常保留安全的 `execution_failed`，不信任上游异常任意 `.code` 属性或异常正文。

对话 `error` 继续保留 code、message，新增可空 kind；message 是应用输出，不写入核心失败对象。诊断返回 `run.error_code/error_kind`，步骤返回自身 kind（动作类型）、action_key、parent_action_id、status、error_code 和 error_kind。动作身份与类型用于定位，不再给每个函数建立一套错误码，也不建立第二套失败台账。历史未登记码仍可读，无法确认的技术类型返回 null。

工具结果可以在 Agent 处理后继续执行，但步骤保留实际失败原因：参数校验为 `tool_arguments_invalid`，缺账号为 `tool_auth_required`，命令非零退出为 `command_failed`。结果未知的步骤保持 unknown；缺少更具体原因时使用 `tool_result_unknown`，不能改成确认失败或自动重放。模型服务超时使用 `upstream_timeout`，整次 Run 时限耗尽仍使用 `run_timeout`。

`ServiceError.message` 可以省略。HTTP 出口使用明确提供的安全说明或应用文案映射，保留原异常类型对应的状态与 Retry-After。引擎内的工具反馈面向模型，启动配置诊断面向运维；两者都不按普通注释批量翻译，也不直接充当用户错误文案。

## 应用错误分类与 HTTP 转换

业务抛出 [app.errors](../../backend/app/errors.py) 的具体错误，只表达失败含义；[errors.py](../../backend/app/api/errors.py) 映射 HTTP 状态、生成安全响应并保留 Retry-After。已登记分类的子类按 MRO 继承最近分类，未分类的 ServiceError 不映射为业务拒绝。已知业务错误返回 `{detail:{code,message}}`；参数校验的 422 返回脱敏条目列表，只保留 type、loc、msg。数据库 busy/locked 转为可重试的 503，未知故障保留服务器错误，不统一吞成业务拒绝。来源、体积和媒体类型拒绝由 security 处理。

[failure_boundary.py](../../backend/app/api/failure_boundary.py) 只处理 HTTP，位于浏览器安全中间件外层；成功、已知错误、字段校验和来源等提前拒绝都返回 `X-Request-ID`。请求提供的 ID 必须符合 ASCII `[A-Za-z0-9._-]{1,64}`；缺失、重复、非法或超长值重新生成。ID 仅用于诊断，不参与认证、Run 身份或业务幂等。

未知异常发生在响应开始前时，API 返回 `500` 和 `{detail:{code:"internal_error",message}}`；非 API 返回安全通用文本 `500`，不会把资源故障全部改成 JSON。500 显式携带 `no-store`、`nosniff` 和关联 ID。响应已开始后，包括 SSE、普通流和 BackgroundTask，只记录 ID、异常类型与堆栈位置帧，再传播不含原异常值、cause/context 的安全异常；不发送第二个响应，也不宣称能修改已交付状态。取消不转换成 500，其他 ASGI scope 及脱离 HTTP 的 Runner/维护任务不由此接管。诊断不记录异常原文、源代码行、SQL/params、请求输入或凭据。

GitHub 登录回调以 303 跳转报告已知失败并清理临时 Cookie；工具 OAuth 回调由 tools 校验原平台会话及 state，不新增临时 Cookie，303 仅携带资源/授权会话标识，授权码不进入前端路由。回调访问日志去除查询串；SSE 建流后认证或权限失效发送 access.revoked。已接受工作的执行失败写入回复状态，不改写原接受响应。错误响应不得包含密码、凭据、原始数据库信息或上游异常正文。前端事实保留、身份重核、静态交付与恢复接入见本文相应章节。

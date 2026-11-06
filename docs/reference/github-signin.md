# GitHub 登录与普通用户

本文维护当前已实现行为。实现与测试入口见正文；未来能力仅作为限制或链接，不构成已实现承诺。

## 需求与边界

访客可以使用 GitHub 登录，首次成功验证后自动创建普通用户；管理员密码登录与游客入口保留。界面直接使用 GitHub 返回的账户名，不提供站内修改用户名功能。稳定身份为 GitHub 数字 ID；GitHub 账户名发生变化时在下次登录同步，不按名称或邮箱自动合并账号。

只处理、保存登录需要的 ID、账户名；GitHub `/user` 返回的其他公开字段不使用。不请求邮箱、仓库、组织权限，不存储 GitHub 密码、access token 或 refresh token。普通用户可浏览员工与技能公开投影、创建本人对话和运行、管理本人 MCP Token；不获得员工编辑或模型配置管理权限。个人模型 Key、个人模型配置和免费额度尚未实现。具体账号边界见 [MCP 契约](mcp.md)。

## 数据与账号

- `users` 保留内部 UUID；`role` 支持 `admin`、`member`；仅管理员具有本地密码，GitHub 用户的 `password_hash` 为空。
- `users.username` 保存账户名；管理员用户名通过仅覆盖 `role = 'admin'` 的唯一索引保持唯一。GitHub 用户与管理员可以同名，密码登录和本机维护始终只查询管理员。
- 新增 `external_identities`：`id`、`user_id`、`provider`、`provider_user_id`、`created_at`、`updated_at`；`provider` 当前只允许 `github`，`(provider, provider_user_id)` 唯一。用户外键级联删除；一个用户同一供应商只能关联一个身份。
- 首次创建用户、建立关联、撤销旧会话及签发新会话在同一事务完成；SQLite 写锁在查询关联前取得，避免并发重复注册。不根据外部账户名授予或合并管理员身份。
- 管理员初始化只检查管理员是否已存在，普通用户先注册不会阻止本机管理员初始化。

## OAuth 与浏览器

| 方法与路径                      | 语义                                                                                                              |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| GET `/api/auth/providers`       | 返回 `{github: {enabled: boolean}}`，不返回应用密钥                                                               |
| POST `/api/auth/github`         | JSON `{next: "/agents"}`，执行现有 Origin、JSON、限速检查，设置临时 Cookie，返回 `{authorization_url}`            |
| GET `/api/auth/github/callback` | 验证临时 Cookie、state、授权码，读取 GitHub `/user`，创建或解析普通用户，签发现有 `app_session`，303 跳转站内地址 |

使用授权码流程和 PKCE S256；state、code_verifier、安全返回地址在有效期 10 分钟的 Fernet 加密 HttpOnly Cookie 中携带，密钥从专用 GitHub Client Secret 派生，与平台会话区分。Cookie 为 SameSite=Lax，生产使用 Secure，回调完成或失败都清除临时 Cookie。GitHub 授权码一次性使用；重复回调无法签发新会话。

后端只请求固定 GitHub token 和 `/user` 端点，超时、禁止重定向及环境代理，限制响应体；只提取 ID、账户名。外部响应和令牌不回显、不记录日志。仅获取身份后即丢弃上游令牌，不请求离线权限。回调设置 no-store、Referrer-Policy: no-referrer；错误通过固定错误码回到登录页，保留可用的管理员密码和游客入口。OAuth 回调是签发会话的 GET 特例，不改变业务写接口的 Origin/JSON 要求。

应用错误按[统一分类](../../backend/app/api/README.md#应用错误分类与-http-转换)处理。发起登录时，已获准但与回调站点不匹配的来源返回 422 github_origin_mismatch；未配置登录提供方返回 503。OAuth 上下文或授权码缺失、无效属于输入错误，上游 HTTP、超时及不可用响应属于服务不可用。回调捕获这些已知错误后继续返回 303 登录页跳转及固定错误码，并清理临时 Cookie；有等待建议时保留 Retry-After。

返回地址使用前后端相同的站内路由白名单，不允许外部来源、协议相对地址、反斜线或登录循环。身份切换沿用现有会话撤销和前端按身份清理状态；工作台重新聚焦时会重新确认身份。

## 配置与交付

`GITHUB_OAUTH_CLIENT_ID`、`GITHUB_OAUTH_CLIENT_SECRET`、`GITHUB_OAUTH_CALLBACK_URL` 三项全部缺省时关闭 GitHub 入口；部分配置直接启动失败。回调必须为允许来源下的 `/api/auth/github/callback`，无 query、fragment 或用户信息；发起登录的 Origin 必须与回调来源一致，避免跨主机丢失临时 Cookie。本机可使用 HTTP，正式环境遵循既有 HTTPS/Secure 规则。Client Secret 不进入前端或配置 repr。

登录页沿用共享主题和既有品牌布局；当前 React 接入由前端工程实施维护。GitHub 使用「其他登录方式」下的圆形图标按钮，始终展示，只有供应商状态确认可用后启用，不阻塞现有表单。未配置时保持禁用，不再隐藏图标；失败恢复表单不会改变供应商的可用状态。右侧布局由[登录页设计](signin.md)维护。普通用户账户菜单显示「普通用户」，可对话提示与游客只读区分。沿用现有账户名展示及退出行为。

外部身份与用户约束直接包含在初始迁移中，新库不会沿用旧管理员、会话或 GitHub 账号记录。OAuth 配置仍由部署环境提供，登录成功才创建新的 member 与关联。

## 验证口径与限制

验证旧库升级与 metadata 一致、管理员/游客回归、首次登录与重复登录、并发注册、同名隔离、上游改名、停用、state/PKCE、过期或篡改 Cookie、回放、取消、上游错误与响应限制、最小权限、站外返回拦截及前端双主题和窄屏。使用隔离数据库与受控 HTTP transport；没有配置真实应用及授权前，不声明真实 GitHub 登录已验证。

## 历史验证入口

历史检查的日期、范围和限制见实施与验证记录，不作为本次重新验收。

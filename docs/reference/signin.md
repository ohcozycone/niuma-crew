# Signin 登录页面

本文维护当前已实现行为。实现与测试入口见正文；未来能力仅作为限制或链接，不构成已实现承诺。

## 页面与身份

`/signin` 为独立 React 路由，不使用工作台外壳。品牌场景、马与字标、底线输入框、紧凑画布及日夜设计保持统一。右侧为登录标题、账号密码、主按钮；下方细分隔线标记“其他登录方式”，左侧圆形 GitHub 图标，右侧“随便看看”，同一行垂直居中。

表单调用既有 `/api/auth/login`、`auth/guest`、`auth/github`；公开供应商探测使用 `auth/providers`，身份探测使用 `auth/me`。身份探测不阻塞输入，用户交互后中止迟到探测；已登录用户进入合法 `next`，游客仍可登录。OAuth 回调错误显示固定文案，避免自动跳转掩盖错误。旧 `/login` 转到正式入口并保留安全返回地址。

GitHub 图标始终可见，探测中或不可用时禁用，提供可访问名称、焦点和跳转状态；探测失败不影响密码或游客入口。请求互斥，空值显示内联必填反馈，输入修改清除过期反馈；错误区域保留空间。密码或游客请求结束清理密码，GitHub 发起失败保留已输入内容。成功通知身份变化并直接进入工作台，管理员返回安全 `next`，游客进入根路径。

自动填充、键盘、输入文字选中及错误关联正常工作；普通页面文案的禁止选中仅限登录场景。API 与后端授权不由页面替代。真实 OAuth 配置和联调范围由 GitHub 专项维护。

## 实现归属

| 入口                                                                                                                      | 职责                                              |
| ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| [`SigninPage.tsx`](../../frontend/src/pages/signin/SigninPage.tsx)                                                        | 页面、品牌场景与 Base UI Form／Field／Button 组合 |
| [`useSigninForm.ts`](../../frontend/src/pages/signin/useSigninForm.ts)                                                    | 认证请求、互斥、反馈、探测与离页清理              |
| [`useSigninScene.ts`](../../frontend/src/pages/signin/useSigninScene.ts)                                                  | 初始几何、缩放、可选动效与生命周期                |
| [`layoutConfig.ts`](../../frontend/src/pages/signin/layoutConfig.ts)、[`motion/`](../../frontend/src/pages/signin/motion) | 几何配置与同源品牌动效                            |
| [`session.ts`](../../frontend/src/lib/identity.ts)                                                                        | 身份事件与安全返回地址                            |
| [`theme.css`](../../frontend/src/design-system/theme.css)                                                                 | 登录与全站主题的唯一视觉数值来源                  |
| [`build-brand.mjs`](../../frontend/scripts/build-brand.mjs)                                                               | 同一品牌图形派生公共资源                          |

页面与业务应用共用 Vite 构建，按路由加载；工作台与重型 Markdown 不进入登录路由的关键依赖。静态交付由统一 HTML 入口回退和压缩工具负责，GET／HEAD、ETag、404 与缓存契约见[前端架构](../architecture/frontend.md)。

场景根据布局视口在布局阶段设置运行时 CSS 变量；静态样式使用 Tailwind，主题颜色引用语义令牌。品牌 SVG 保持固定可信素材，动效独立导入，在快速连接、文档可见、未开始输入时播放一次；省流、弱网、减少动态效果、用户交互或资源迟到时保留静态图形。离开清理动画帧与监听，历史缓存恢复重新确认页面身份。

主题控制器与根令牌在 HTML head 内联，早于 React 执行；表单无需等待动效，主题无需等待业务请求。登录与工作台复用 React 主题控件和同一浏览器偏好。

## 验收与证据

检查空值、错误、请求互斥、密码清理、GitHub 可用性与失败恢复、安全返回、游客入口、身份探测竞态和卸载；检查键盘、自动填充、日夜、320／390px、桌面与短屏。动效不可用或减少动态效果不能阻止表单。

此前布局和真实 OAuth 验收分别保留于登录截图与[GitHub 设计](github-signin.md)；此前独立投递性能数据不能代表当前统一构建的加载耗时。

# 免费模型的后续方向（未实现）

设计状态：草案。实施状态：未开始。原记录日期：2026-10-22；2026-10-23 整理归属。当前行为以现行契约及代码为准。

## 免费模型的后续方向（未实现）

用户希望注册后自动可用，提出根据 GitHub 身份替用户向厂商申请免费 API Key。GitHub 登录本身不提供厂商 Key 或额度；网站账号也不能代替厂商账号。自动开通需要厂商正式开放的账户授权、账号创建及密钥发放接口。截至本次核对，未在 MiniMax 公开文档中找到面向第三方应用的这类完整接口；这属于调查结果，不声明厂商永远不支持。

可选方向仍待确定：厂商提供官方授权接入；或平台持有自己的 Key，向站内用户分配体验额度。后者对用户免费，实际费用和上游额度由平台承担，需新增用户级原子额度和执行边界。用户自行填写个人 Key 也是技术选项，但未被确认为本次需求。免费额度、有效期及限速由厂商决定，不将试用赠金承诺为永久免费。

厂商依据：[MiniMax 账号注册流程](https://platform.minimaxi.com/zh/protocol/user-agreement)、[开发者计划](https://platform.minimax.io/contact-us)、[Groq 免费计划限速](https://console.groq.com/docs/rate-limits)。

参考：[GitHub OAuth 授权](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps)、[稳定用户 ID](https://docs.github.com/en/rest/users/users#get-a-user-using-their-id)。

# 应用错误分类整理验收

日期：2026-10-26。适用快照：当前共享工作区，仓库尚无可引用提交。范围为应用错误分类、HTTP 转换、现有抛出与捕获调用、必要注释及契约；执行错误终态和数据库结构不属于本次修改范围。

## 实际改动

- 删除 AccessError；ServiceError 仅携带 code、可公开 message、可选 retry_after，不保存 HTTP 状态。
- 保留 NotFoundError、ConflictError，增加 AuthenticationError、PermissionDeniedError、InvalidInputError、RateLimitError、ServiceUnavailableError。
- API 集中映射七类错误和等待头；SQLite 繁忙复用相同响应。补齐 OpenAPI 中业务输入拒绝和字段校验两种 422 正文结构。
- 游客回退只捕获认证失败，执行及发布前的身份复核只把认证或权限失败转换为撤权；依赖故障不伪装成会话失效。
- OAuth 输入问题按输入错误分类，上游暂不可用按服务不可用分类。回调保留 303 跳转、等待建议、临时 Cookie 清理和原站内会话。
- 错误含义使用类的短说明；身份回退、撤权转换及 OAuth 处理附近说明捕获范围的原因。

## 实际验证

`make test-backend` 全量 455 项通过（72.23 秒），包含认证、OAuth、配置、执行、真实 SDK 假模型、进程恢复与迁移回归。错误边界测试 17 项通过，覆盖七类 HTTP 映射、等待头、字段错误脱敏、422 文档结构、未分类异常保持 500、游客故障不签发会话，以及执行/发布的身份复核。OAuth 测试覆盖输入与依赖分类及回调限流后的 Cookie/等待头。

`make lint-backend` 已通过 Ruff、格式和增量 mypy（9 个源文件）；类型检查范围以当前 pyproject.toml 为准。`make check-docs` 已通过，错误 0。应用、测试、脚本及前端源码中没有 AccessError 引用，应用异常没有遗留 HTTP 状态参数。

## 契约与限制

现行分类、错误正文及 OAuth/SSE 例外见[API 模块说明](../../backend/app/api/README.md#应用错误分类与-http-转换)，工程规则见[后端手册](../engineering/backend.md)。业务输入统一 422；浏览器传输层的 403/413/415 保留。已接受执行的失败继续记录在 Run 内。

测试使用隔离数据库、假模型及受控 HTTP；未调用真实模型或 GitHub，未访问或升级开发数据库。本次未修改前端代码，未运行前端测试；没有新增依赖或数据迁移。

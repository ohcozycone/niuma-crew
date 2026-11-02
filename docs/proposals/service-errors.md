# 应用错误分类整理

状态：已采纳、已实现并验收。更新日期：2026-10-26。范围为移除 AccessError、替换现有抛出和捕获、集中 HTTP 转换，并同步测试、契约与必要注释；不修改数据模型或执行错误的终态协议。

## 目标与职责

ServiceError 统一携带安全的 code、message 及可选 retry_after，不携带 HTTP 状态。保留 NotFoundError 和 ConflictError，增加 AuthenticationError、PermissionDeniedError、InvalidInputError、RateLimitError、ServiceUnavailableError。具体业务原因通过 code 区分，不为每个原因建类。

业务模块按失败含义抛出异常；api/errors.py 将七类错误固定映射为 401、403、404、409、422、429、503，维持 detail.code/message 响应。业务输入问题统一 422，上游暂不可用统一 503。框架字段校验保留现有脱敏结构，OAuth 回调仍将已知失败重定向到登录页。

## 实施与边界

1. 增加语义类型和统一 HTTP 转换，删除旧类及状态参数。
2. 替换所有抛出点；身份复核仅捕获认证与权限失败，游客回退只捕获认证失败；OAuth 回调捕获已知 ServiceError。
3. 保留限流等待时间、OAuth Cookie 清理和 SSE 撤权事件，避免将依赖故障误判为身份失效。
4. 回归认证、参数、容量、凭证、OAuth、执行撤权及事务失败，更新现行正文和实际验收。

## 验收

应用与测试没有旧类调用；异常不携带 status；HTTP 分类、错误码、等待头和敏感字段裁剪正确；已接受 Run 的错误仍记录在运行中；其他代码缺陷不转换为可公开的业务错误。

生效契约已合入 [API 模块说明](../../backend/app/api/README.md)及[后端工程手册](../engineering/backend.md)，实际验证见[验收记录](../records/service-errors.md)。

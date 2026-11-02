# CI 诊断接口退役

本页保留已移除接口的辨认信息，当前不再提供诊断能力。普通接口见[对话契约](../conversations.md)。

## 配置与提交

GET `/api/ci-diagnosis/capability` 与 POST `/api/ci-diagnosis/skill` 已移除。员工不再接受 ci_repository，发送请求不再接受 work，旧字段返回输入错误，不会自动降为普通对话。

## 观察与反馈

回复下的 `/ci-diagnosis` 和 `/ci-feedback` 专用端点已移除。历史回复不再返回 ci/work_kind，保留文本及共享步骤，can_retry=false。仅移除专用报告界面，不移除普通历史、SSE、复制或新消息入口。

## 失败与部署边界

CI 专用配置及实时错误目录已移除。存量错误使用安全历史提示，旧任务不能恢复或重试。GitHub 登录、用户登记的 MCP 和普通运行错误保持各自契约。数据退役顺序见[说明](data.md#迁移与后续范围)。

# CI 对话诊断试验退役说明

固定 GitHub Actions 诊断试验已移除，不再安装专用技能、配置仓库、提交失败运行或读取报告/反馈。本专题只保留退役与历史入口，不作为当前功能使用指南。

## 目标与价值边界

此次删除限于产品中的专用诊断链路。GitHub 身份登录、用户登记的通用 GitHub MCP、普通技能/工具和工程自身的 CI/CD 继续保留。

## 范围收缩

四个专用端点、员工 ci_repository、消息 work 和回复 ci/work_kind 已移除。旧输入明确拒绝，不能忽略参数后改作普通聊天。接口变化见[退役接口](api.md)。

## 职责与执行

保留已交付的消息正文、共享 Run 和动作作为只读历史；旧试验 can_retry=false，不自动恢复或重新执行。普通新消息和可靠执行继续使用[对话](../conversations.md)与[运行](../runtime.md)契约，没有替代的 CI 模块或工作流框架。

## 权限、凭证与故障

CI_GITHUB_TOKEN 与 CI_GITHUB_TOKEN_FILE 不再参与应用配置。不要因此删除 GitHub OAuth 登录配置或用户自己管理的 MCP 账号凭据。

## 前端与验证

专用配置、模式、报告与反馈界面移除。旧入口/草稿明确提示退役；旧待确认请求只核对是否曾接受，不转为普通输入重发。退役迁移和备份要求见[数据说明](data.md)。

## 历史验证入口

[早期验证](../../records/agent-model-rebuild.md)、[消息与执行归位](../../records/platform-refactor-implementation.md)只说明当时范围。退役设计见[模块边界方案](../../proposals/backend-module-boundaries.md#3-ci-试验链路的完整移除范围)，本轮实际结果从[记录索引](../../records/README.md)进入。

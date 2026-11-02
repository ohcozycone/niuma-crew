# 后端全面审查证据入口

本次审查于北京时间2026-10-29开始、2026-10-30完成。主报告是[后端全面审查报告](../backend-deep-review-2026-10-29.md)。目录名保留开始日期。这里保存取证过程、当前行为的隔离复现和范围清单，不表示问题已修复。

## 覆盖与快照

- [最终覆盖核对](evidence/coverage-validation.json)：140个应用Python文件全部归属，15个模块，无漏项、重复或源码散列变化。
- [后端文件清单](evidence/file-inventory.json)、[快照摘要](evidence/snapshot.json)：232个文件，排除运行数据、真实.env、缓存和虚拟环境，包含安全示例配置。
- [应用导入位置](evidence/imports.json)、[依赖摘要](evidence/dependency-summary.json)、[精确文件职责环](evidence/file-import-cycles.json)：AST静态引用，包括局部导入，不是动态调用图。
- [函数位置清单](evidence/functions.json)：654个函数。只有关键复杂函数另写微观分析，没有宣称逐函数形式化验证。
- [技能安装来源与摘要](evidence/installed-skills.json)：五个独立技能和一个完整插件内技能；完整审计插件包含工作流与函数分析代理，重复的独立入口已移至临时恢复副本。

## 独立模块分析

| 分组           | 分析                                                                           | 逐文件覆盖                                           |
| -------------- | ------------------------------------------------------------------------------ | ---------------------------------------------------- |
| 身份与配置     | [auth、agents、skills、模型连接、全员规则](evidence/configuration-review.md)   | [33个源码文件](evidence/configuration-coverage.json) |
| 对话与运行     | [conversations、execution、agent_runtime、CI、llm](evidence/runtime-review.md) | [44个源码文件](evidence/runtime-coverage.json)       |
| HTTP与资源边界 | [api、tools、files、sandboxes、数据库](evidence/boundary-review.md)            | [57个源码文件](evidence/boundary-coverage.json)      |
| 顶层与工程     | 主报告第7节，及下方两个函数记录                                                | [6个顶层源码文件](evidence/root-coverage.json)       |

## 实际检查的原始输出

- [lint-backend](evidence/lint-backend.log)：Ruff、格式和9个mypy入口通过。
- [后端测试首轮](evidence/test-backend.log)：575项，558通过，17项因本机端口权限失败。
- [17项进程与checkpoint测试重跑](evidence/checkpoint-unsandboxed.log)：17通过；使用本机端口、假模型与临时SQLite。
- [启动器和文档检查器测试](evidence/test-dev.log)：28通过。
- [最终文档检查](evidence/check-docs.log)、[交付核对](evidence/delivery-validation.json)：交付前生成。

复现探针中的 passed 表示观察到了当前缺陷或被测事实，不能解释为修复验收。复验在仓库根运行；都使用隔离临时存储，不以开发数据库或真实供应商为目标。

| 内容                                   | 可复查代码                                         | 原始结果                                        |
| -------------------------------------- | -------------------------------------------------- | ----------------------------------------------- |
| 员工筛选、无变化修订、无效ZIP的API结果 | [配置复现](evidence/configuration-reproduction.py) | [输出](evidence/configuration-reproduction.log) |
| 损坏压缩内容的最小异常                 | [ZIP探针](evidence/configuration-corrupt-zip.py)   | [输出](evidence/configuration-corrupt-zip.log)  |
| 撤权部分正文和对话列表查询数           | [运行探针](evidence/runtime-review-probes.py)      | [输出](evidence/runtime-review-probes.log)      |
| 文件残留、成员状态可见性、页面路径     | [边界探针](evidence/boundary-reproduction.py)      | [输出](evidence/boundary-reproduction.txt)      |
| 构造失败和关闭失败时的清理顺序         | [装配探针](evidence/bootstrap-repro.py)            | [输出](evidence/bootstrap-repro.log)            |

例如运行pytest探针：

```bash
PYTHONPATH=backend:backend/tests backend/.venv/bin/python -m pytest -q -s docs/records/backend-deep-review-2026-10-29/evidence/runtime-review-probes.py
PYTHONPATH=backend:backend/tests backend/.venv/bin/python -m pytest -q -s docs/records/backend-deep-review-2026-10-29/evidence/boundary-reproduction.py
```

原始配置脚本内含固定的隔离目录与正式迁移，运行方式见其源码；装配探针可用后端Python从仓库根执行。它们不纳入正式test目录，业务修复仍需补正式回归。

## 关键函数事实记录

这些记录先描述输入假设、顺序、跨函数依赖及未知项，问题优先级由主报告判断。

- [boundary-file-save：`FileService.save` in backend/app/files/service.py (L47-L109)](context/functions/boundary-file-save.md)
- [boundary-file-sweep：`FileService.sweep` in backend/app/files/service.py (L155-L192)](context/functions/boundary-file-sweep.md)
- [boundary-mcp-invoke：`MCPClient.invoke` in backend/app/tools/adapters/mcp.py (L136-L162)](context/functions/boundary-mcp-invoke.md)
- [boundary-network-request：`PinnedTransport.handle_async_request` in backend/app/tools/network.py (L61-L108)](context/functions/boundary-network-request.md)
- [boundary-sandbox-acquire：`SandboxService.acquire` in backend/app/sandboxes/service.py (L128-L173)](context/functions/boundary-sandbox-acquire.md)
- [configuration-auth-login：`AuthService.login` in backend/app/auth/service.py (L88-L128)](context/functions/configuration-auth-login.md)
- [configuration-capture-tools：`capture_tools` in backend/app/agents/tool_grants.py (L187-L246)](context/functions/configuration-capture-tools.md)
- [configuration-rules-update：`OrganizationRulesService.update` in backend/app/organization_rules/service.py (L28-L47)](context/functions/configuration-rules-update.md)
- [configuration-skill-update：`SkillService.update` in backend/app/skills/service.py (L389-L464)](context/functions/configuration-skill-update.md)
- [root-lifespan：应用生命周期事实记录](context/functions/root-lifespan.md)
- [root-load-config：配置装配事实记录](context/functions/root-load-config.md)
- [runtime-agent-execute：`execute_agent` in backend/app/agent_runtime/langchain.py (L109–L232)](context/functions/runtime-agent-execute.md)
- [runtime-ci-execute：`CiDiagnosisExecutor.execute` in backend/app/ci_diagnosis/executor.py (L24–L347)](context/functions/runtime-ci-execute.md)
- [runtime-coordinator-run：`ExecutionCoordinator.run` in backend/app/execution/coordinator.py (L60–L167)](context/functions/runtime-coordinator-run.md)
- [runtime-publication-finish：`PublishRun.finish` in backend/app/conversations/publication.py (L33–L78)](context/functions/runtime-publication-finish.md)
- [runtime-store-begin-tool：`RunStore.begin_tool` in backend/app/execution/store.py (L306–L355)](context/functions/runtime-store-begin-tool.md)
- [runtime-tool-invoke：`ToolExecutionMiddleware._invoke` in backend/app/agent_runtime/tool_calls.py (L195–L292)](context/functions/runtime-tool-invoke.md)

## 限制

未调用真实模型、GitHub/MCP或OpenSandbox，不覆盖真实负载、外部系统副作用、跨存储断电和目标Linux系统隔离。静态引用、完整文件阅读、假模型测试各证明不同范围，不能互相替代。独立模块记录保留局部细节，主报告统一修正了“历史”和“送模上下文”、普通Agent预算和CI专业预算等容易混淆的措辞。

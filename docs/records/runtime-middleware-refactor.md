# 运行中间件职责整理与验证

源码链接已按当前位置修复；本文保留记录时的名称和结论，当前行为以现行契约为准。

记录日期：2026-10-23。适用于本次工作区的运行中间件重构；Python 3.12、LangChain 1.4.7、Deep Agents 0.7.30。本文记录实际修改与验证，不代替[当前运行契约](../reference/runtime.md)。

## 修改范围

- 原 `EvidenceMiddleware` 的模型调用与技能加载职责分别落入 `ModelExecutionMiddleware`、`SkillLoadingMiddleware`；与框架中间件一起由 [middleware.py](../../backend/app/agent_runtime/middleware.py) 组装。
- [provider.py](../../backend/app/agent_runtime/langchain.py) 从 270 行缩减至 94 行，保留本轮输入、客户端、Agent 调用、最终交付及供应商错误映射。
- 模型步骤轮次复用 `ModelCallLimitMiddleware` 的计数，删除独立的模型计数器；共享用量累计迁入 [usage.py](../../backend/app/llm/usage.py)，普通对话与 CI 使用同一实现。
- 执行失败类型移入 [errors.py](../../backend/app/execution/errors.py)，避免中间件与 provider 循环依赖；运行器与 CI 直接引用其所属模块。

显式预加载和自动读取继续共用技能预算；缺失或未报告的累计用量继续保持未知。业务授权、固定正文校验、持久化步骤、取消与失败规则保持原契约，不引入外部追踪服务。

## 实际验证

| 检查                | 结果与范围                                                                                                                 |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `make test-backend` | 293 项通过；包括原有对话、CI、撤权、取消与存储故障场景，以及新增的并行读取预算、重复激活去重、预加载正文缺失和累计用量场景 |
| `make lint-backend` | Ruff 静态及格式检查通过，139 个 Python 文件符合格式                                                                        |
| `make check-docs`   | 121 份文档、1,416 个本地链接检查通过；102 个归档引用按默认规则计数                                                         |

验证使用隔离数据库与受控模型替身。未调用真实模型或 GitHub MCP，未执行浏览器验收；本次没有前端或数据库结构改动。命令通过临时 `UV_CACHE_DIR` 和 `UV_OFFLINE=true` 运行，避免访问受限的用户缓存目录及下载依赖。

## 2026-10-24：用量通过 Agent 状态交付

先前的组装函数同时返回中间件列表和 `ModelExecutionMiddleware` 实例，provider 通过实例的 `usage` 属性取得最终用量，形成了对中间件内部可变状态的依赖。

本次使用 LangChain 的 `AgentState` 与 `ExtendedModelResponse`：模型中间件从本轮状态读取累计值，通过 `Command` 更新 `model_usage`；provider 从 `ainvoke` 结果读取该字段。组装函数只返回中间件列表，删除实例上的用量状态。步骤记账继续即时持久化，失败和取消规则沿用当前契约。

新增真实 SDK 三轮工具往返测试，分别验证完整用量累计为 45，以及第二轮缺失用量后第三轮仍保持未知；同时核对技能只激活一次、三个模型步骤轮次连续。

本次 `make test-backend` 共 295 项通过，`make lint-backend` 的静态与 139 个文件格式检查通过，`make check-docs` 检查 121 份文档、1,416 个本地链接无错误；本次修改的 Markdown 格式检查通过。离线缓存缺少构建依赖，验证命令使用 `UV_NO_SYNC=true` 复用已安装环境，并设置临时缓存及 `UV_OFFLINE=true`；未验证重新安装依赖，未调用真实上游。

## 2026-10-24：运行时技能职责收拢

适用于本次工作区的技能职责重构，Python 3.12.13。技能目录构造、提示词、SDK 技能配置及 SkillLoadingMiddleware 已归入 runtime/skills.py，与现有快照捕获和实时许可检查共同维护。SkillCatalog 用同一组条目提供虚拟文件、路径查找和显式预加载名称；agent_loop.py 使用该目录，middleware.py 保持原有中间件顺序并负责模型执行及整体装配。

SKILL.md 正文和参数编码、快照版本、授权、共享读取预算、激活去重及动作记录保持原契约。新增真实 SDK 集成场景：两个同名技能使用不同参数，一个显式预加载、另一个按需读取，核对每轮可见正文和参数以及实际激活的技能 ID、来源，防止目录关联串用。

| 检查                                        | 实际结果                                                                                                                              |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| 技能、流式执行、普通对话、CI 与应用装配测试 | 85 项通过；执行 test_capability_runtime.py、test_runtime_streaming.py、test_conversations.py、test_ci_diagnosis.py、test_bootstrap.py |
| `make lint-backend`                         | Ruff 静态及格式检查通过，145 个 Python 文件符合格式                                                                                   |
| `make check-docs`                           | 127 份文档、1,480 个本地链接检查通过，102 个归档引用按默认规则计数                                                                    |

测试使用隔离数据库、真实 SDK 与受控模型及工具替身，运行命令复用已安装环境，设置临时 UV_CACHE_DIR、UV_OFFLINE=true 和 UV_NO_SYNC=true。未运行全量后端或前端测试，未调用真实模型或 GitHub MCP；本次无数据库结构和外部接口变更。

## 2026-10-24：技能执行数据命名统一

上节技能执行数据对象现统一命名为 `PreparedSkills`，准备函数为 `prepare_skills`；Agent、中间件的变量、参数及实例属性统一为 `prepared_skills`。模块说明与重构方案同步更新。按新旧标识符映射归一化语法树后，三个生产代码文件完全一致，确认本次只改名。

重新运行上节五个测试文件，85 项通过；`make lint-backend` 的静态及 145 个文件格式检查通过，`make check-docs` 检查 127 份文档、1,485 个本地链接无错误，102 个归档引用按默认规则计数。继续使用隔离数据和受控上游，未调用真实模型或外部 MCP。

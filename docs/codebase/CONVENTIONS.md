# 实际工程约定

调查日期：2026-10-31。区分“配置已启用”与“所有源码均已满足”；本次为文档调查，没有重跑全量 lint。详细工程规则继续维护在[共享约定](../engineering/shared.md)、[前端手册](../engineering/frontend.md)、[后端手册](../engineering/backend.md)。

## 1. 命名

| 项目              | 观察到的模式                                                  | 示例和证据                                                                                                                                                                                                                                                |
| ----------------- | ------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Python 文件/函数  | snake_case，内部辅助函数常有下划线前缀                        | [execution_config.py](../../backend/app/agents/execution_config.py) `capture_skills`；[config.py](../../backend/app/config.py) `_read_values`:L49                                                                                                         |
| Python 类型       | PascalCase；配置多用 dataclass/Pydantic                       | [config.py](../../backend/app/config.py) `AppConfig`:L28；[llm/config.py](../../backend/app/llm/config.py) `LLMConfig`                                                                                                                                    |
| TS 组件与普通文件 | 组件 PascalCase.tsx，Hook useX，普通模块 camelCase.ts         | [KnowledgeLibrary.tsx](../../frontend/src/pages/knowledge/KnowledgeLibrary.tsx)、[useResponseSubscription.ts](../../frontend/src/pages/conversations/useResponseSubscription.ts)、[workspaceData.ts](../../frontend/src/state/workspace/workspaceData.ts) |
| TS 目录           | kebab-case；目录按页面、状态职责与共享组件组织                | [eslint.config.mjs](../../frontend/eslint.config.mjs):L150–155；[设计系统](../../frontend/src/design-system/README.md)                                                                                                                                    |
| 常量/环境项       | Python 常量和环境名 UPPER_SNAKE_CASE；TS 允许三种明确命名形式 | [knowledge/service.py](../../backend/app/knowledge/service.py):L38；[.env.example](../../backend/.env.example)；[eslint.config.mjs](../../frontend/eslint.config.mjs):L156                                                                                |

观察覆盖 main/bootstrap/config、auth、agents、skills、tools、execution、knowledge 与前端 router/Layout/多个页面和 Store，不是从单个文件推定。Python 当前 Ruff 选择中不包含完整命名规则，命名风格主要是源码惯例；前端文件命名有实际检查。

## 2. 格式、静态与类型检查

| 工具       | 实际配置范围                                                                                                                      | 入口                                                                                                                 |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Ruff       | Python 3.12、100 列；E4/E7/E9/F/I，app 是 first-party；format 独立检查                                                            | [pyproject.toml](../../backend/pyproject.toml):L51；`make lint-backend`                                              |
| mypy       | disallow_untyped_defs、check_untyped_defs 等，但 files 只列执行契约、接受/查询/发布及 knowledge 等指定模块；follow_imports=silent | [pyproject.toml](../../backend/pyproject.toml):L64；`make typecheck-backend`                                         |
| TypeScript | strict=true、noEmit、bundler resolution；allowJs、skipLibCheck=true                                                               | [tsconfig.json](../../frontend/tsconfig.json):L2；`make typecheck`                                                   |
| ESLint     | TS 推荐、Hooks、命名、模块边界、样式限制；Hooks exhaustive-deps 是 warn，不是 error                                               | [eslint.config.mjs](../../frontend/eslint.config.mjs):L100–215；[配置回归测试](../../frontend/eslint.config.test.ts) |
| Prettier   | package.json 的 printWidth=100；生成资源、锁等按 .prettierignore 排除                                                             | [package.json](../../frontend/package.json)、[.prettierignore](../../frontend/.prettierignore)；文档用此配置格式化   |

ESLint 明确忽略 SVG 头像生成目录和 manifest；生成器本身仍在 lint scripts 范围。不能以生成文件体量推断人工业务复杂度。生产构建不执行 tsc，类型检查由独立命令承担：[package.json](../../frontend/package.json):L8–11。

## 3. 导入与模块依赖

- 后端以 `app.*` 绝对导入为主，Ruff I 排序；服务通常直接使用 SQLAlchemy，不强套 Repository。跨模块数据关系通过 ORM 和显式函数表达。[conversations/service.py](../../backend/app/conversations/service.py):L7–32。
- 启动装配使用 app.state，并把业务准备、授权和发布回调注入执行宿主。HTTP 通过 FastAPI Depends 获取具体服务，不传共享 Session 跨请求。[bootstrap.py](../../backend/app/bootstrap.py)、[api/dependencies.py](../../backend/app/api/dependencies.py)。
- 前端 `@/` 统一映射 src；同页私有文件通常相对导入。Vite、tsconfig、Vitest 均配置别名，不能按真实目录外的 `@` 包理解。[vite.config.ts](../../frontend/vite.config.ts):L26、[tsconfig.json](../../frontend/tsconfig.json)、[vitest.config.ts](../../frontend/vitest.config.ts)。
- ESLint boundaries 默认 disallow，覆盖 import/export/dynamic-import/require；页面不能随意互相导入，router 只加载 Page 入口；lib 不依赖 React 层。测试和展示有局部豁免。[eslint.config.mjs](../../frontend/eslint.config.mjs):L143、L168–215。
- 后端依赖方向主要由架构定向测试约束，没有发现覆盖全部业务边界的静态插件；不能由某次测试推定全局无循环。[test_runtime_boundaries.py](../../backend/tests/test_runtime_boundaries.py) `test_dependency_directions_prevent_sdk_and_application_state_leaks`:L76。

## 4. 错误、事务与日志

| 边界     | 实际规则与证据                                                                                                                                                                                                                                                                                        |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 业务拒绝 | 抛 ServiceError 子类，携带公开 code/message 和可选 retry_after；不在服务内选择 HTTP 状态。[errors.py](../../backend/app/errors.py):L4                                                                                                                                                                 |
| HTTP     | 集中映射错误类型；校验响应只保留 type/loc/msg，去掉原始输入；数据库 busy 503，其他 OperationalError 不伪装业务冲突。[api/errors.py](../../backend/app/api/errors.py):L64–100                                                                                                                          |
| 执行     | RuntimeFailure/ExecutionFailure 表示运行失败，协调器规范化错误码；异常导致终态或 degraded，不靠 HTTP 连接生命周期驱动。[coordinator.py](../../backend/app/execution/coordinator.py):L113–167                                                                                                          |
| 事务     | Database.transaction 成功提交、异常回滚；组合写使用同一 Session。reserve_writer 在读取前申请 SQLite 写者位置，避免读后升级竞争。[session.py](../../backend/app/infrastructure/database/session.py):L55；[transactions.py](../../backend/app/infrastructure/database/transactions.py) `reserve_writer` |
| 浏览器   | request 转 ApiError 并分发身份失效事件；Controller 区分明确拒绝和结果不确定，保留待核对命令。[http.ts](../../frontend/src/lib/api/http.ts):L48；[useConversationController.ts](../../frontend/src/pages/conversations/useConversationController.ts):L281                                              |

标准日志由 Python logging 输出，bootstrap 为 app logger 设置时间、级别、logger 名和消息；接受记录带 conversation/response/request，执行日志带 run，未知异常多记录类型而非完整外部响应。[bootstrap.py](../../backend/app/bootstrap.py):L50–55；[routes/conversations.py](../../backend/app/api/routes/conversations.py):L125；[coordinator.py](../../backend/app/execution/coordinator.py):L135。

秘密保护是具体边界行为：SQLAlchemy hide_parameters、SecretStr/repr=False、MCP 返回字符串脱敏、前端不保存模型 Key 草稿。不能扩大成“任何日志绝不可能泄密”的保证。[session.py](../../backend/app/infrastructure/database/session.py):L30；[llm/config.py](../../backend/app/llm/config.py)；[invocation.py](../../backend/app/tools/invocation.py):L100–108；[draft.ts](../../frontend/src/lib/draft.ts)。

## 5. 测试惯例

后端 `tests/test_*.py`，使用 tmp_path、monkeypatch、迁移数据库及假 SDK/HTTP transport；前端 `*.test.ts(x)` 就近，vi.mock 和 Testing Library，DOM 文件显式声明 jsdom。边界测试检查拒绝、回滚、重启和旧结果不覆盖，而非只测 happy path。部分旧场景通过 ScenarioClient 翻译旧测试断言，不能将它当正式 API。[conftest.py](../../backend/tests/conftest.py)、[scenario_client.py](../../backend/tests/scenario_client.py)、[knowledgeFlow.test.tsx](../../frontend/src/pages/knowledge/knowledgeFlow.test.tsx)。

没有在已调查的 pytest/Vitest/Makefile 配置中发现覆盖率阈值；`[TODO]` 当前覆盖百分比与完整测试结果。本次实际运行范围见 [TESTING](TESTING.md)。

## 6. 证据

- [Python 配置](../../backend/pyproject.toml)、[前端 ESLint](../../frontend/eslint.config.mjs)、[TS 配置](../../frontend/tsconfig.json)、[包脚本](../../frontend/package.json)。
- [事务](../../backend/app/infrastructure/database/session.py)、[应用错误](../../backend/app/errors.py)、[HTTP 错误](../../backend/app/api/errors.py)。
- [共享数据说明](../../frontend/src/state/README.md)、[后端 fixtures](../../backend/tests/conftest.py)。

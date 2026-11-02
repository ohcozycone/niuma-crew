# 测试结构与本次验证

调查日期：2026-10-31。以下区分“源码中有测试”与“本次实际通过”；没有用历史记录代替当前验证。架构主线见 [ARCHITECTURE](ARCHITECTURE.md)。

## 1. 技术栈与命令

后端 pytest（清单 >=9.1.1），断言使用 Python assert，替身使用 monkeypatch、假模型、httpx transport 与注入工厂。前端 Vitest（^5.0.4）、Testing Library、vi.mock；默认 node，DOM 用例文件声明 jsdom。[pyproject.toml](../../backend/pyproject.toml):L30、[package.json](../../frontend/package.json)、[vitest.config.ts](../../frontend/vitest.config.ts)。

```bash
make test-backend     # cd backend && uv run pytest
make test-frontend    # 生成头像 manifest 后 vitest run
make test-dev         # 开发监督器与文档检查器测试
make verify-checkpoint
make verify-knowledge
make check-docs
```

正式入口由 [Makefile](../../Makefile)维护。未发现已配置的统一 coverage 命令、覆盖率门槛或已接入的浏览器 E2E runner；`[TODO]` 覆盖百分比，不把测试文件数当覆盖率。独立 `experiments.knowledge_poc` 烟测使用假向量不代表模型回答质量。

## 2. 文件布局与初始化

- 后端集中 `backend/tests/test_*.py`；[conftest.py](../../backend/tests/conftest.py):L19 的 app_config 使用 tmp_path 下的数据库/密钥/运行锁/技能目录，默认禁用正式 Runner；migrated_config 使用 Alembic upgrade head；api_client 初始化测试管理员并登录。
- [scenario_client.py](../../backend/tests/scenario_client.py) 是旧场景断言的测试专用适配器，转换运行 ID 与当前 reply URL；它不证明旧 API 还存在。新契约测试需查看实际 wire 请求。
- [test_checkpoint_runtime.py](../../backend/tests/test_checkpoint_runtime.py) 通过独立 worker 和本机临时端口验证重启；[checkpoint_worker.py](../../backend/tests/checkpoint_worker.py) 用假模型驱动正式宿主。它需要监听权限，与纯 TestClient 测试的环境要求不同。
- 前端测试与组件/Store 同目录；[knowledgeFlow.test.tsx](../../frontend/src/pages/knowledge/knowledgeFlow.test.tsx):L1 使用 jsdom、MemoryRouter、mock API 和身份；[workspaceData.test.ts](../../frontend/src/state/workspace/workspaceData.test.ts) 测失效和跨业务同步。
- 跨端监督器和文档检查器测试集中 [scripts/tests](../../scripts/tests/)，与 backend/tests 是不同收集入口。

## 3. 测试范围矩阵

| 范围                  | 已有覆盖入口                                                             | 本次覆盖与限制                                                                        |
| --------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------- |
| 配置与启动            | test_bootstrap、test_config、test_database、test_migrations              | 本次运行 test_bootstrap；未全量运行配置/迁移套件，但所跑 API fixtures 均从迁移建立库  |
| 对话接受/幂等/取消    | test_conversation_submission、test_conversations、test_response_contract | 本次读源码并运行 execution 边界；未声称所有 HTTP 场景通过                             |
| 执行与发布事务        | test_execution_boundaries、test_runtime_boundaries                       | 本次通过，覆盖产品历史独立、发布回滚、取消竞争、动作及 SDK 边界                       |
| checkpoint 恢复       | test_checkpoint_runtime、test_sqlite_checkpoints                         | 本次 checkpoint_runtime 14 项通过，包含预算、撤权、取消、期限、最终存档修复与重启恢复 |
| 知识持久化            | test_knowledge_library                                                   | 本次通过，使用真实 SQLite FTS5，包含作用域、查重、查询转义、回滚和原件保留            |
| 工具、凭据、网络/沙箱 | test_mcp_management、test_stdio_mcp、test_agent_foundations 等           | 已定位，未在本次全量执行；没有连接真实上游                                            |
| 前端业务状态          | Controller、知识流程、WorkspaceData/Provider 测试                        | 本次定向运行四个文件，结果如下                                                        |
| 浏览器端到端/性能     | 当前已调查配置未见正式 E2E/压测入口                                      | `[TODO]` 真实浏览器、真实上游、负载和生产恢复                                         |

## 4. 替身与隔离边界

后端采用临时文件型 SQLite 而非只用 create_all；因此可验证正式迁移、外键、FTS 及事务行为。网络/模型用假 transport、fake chat model 或替换 executor；真实 SDK 测试仍不调用收费模型。并行任务通过独立 Session 和 to_thread，测试注入写入失败核对回滚。[conftest.py](../../backend/tests/conftest.py):L19–65；[test_runtime_boundaries.py](../../backend/tests/test_runtime_boundaries.py):L20、L58；[test_knowledge_library.py](../../backend/tests/test_knowledge_library.py):L153。

前端将 API 替换为 vi.fn/mock promise，校验组件状态与版本合并，不能证明后端已接受请求；后端 TestClient 不能证明浏览器 Cookie/代理/布局都正常。当前测试还有旧场景兼容适配，阅读失败时先区分断言转换与正式 wire DTO。[scenario_client.py](../../backend/tests/scenario_client.py)、[useConversationController.test.tsx](../../frontend/src/pages/conversations/useConversationController.test.tsx)。

## 5. 本次实际结果与质量信号

后端实际命令（使用现有 venv，避免重新安装依赖）：

```bash
cd backend
PYTHONPATH=tests:. .venv/bin/python -m pytest -p conftest \
  /tmp/niuma_codebase_probe.py tests/test_bootstrap.py \
  tests/test_execution_boundaries.py tests/test_runtime_boundaries.py \
  tests/test_checkpoint_runtime.py tests/test_knowledge_library.py -q
.venv/bin/python -m pytest tests/test_checkpoint_runtime.py -q --tb=short
```

首轮 **27 passed、14 failed**，14 个失败均在 `test_sqlite_checkpoints.server` 的 socket.bind 因沙箱禁止本机端口监听抛 PermissionError，未进入被测恢复路径。获准在沙箱外补跑上述 checkpoint 文件后 **14 passed**。合计确认 **40 个仓库测试通过，另 1 个临时调查用例通过**；临时用例证明现存索引恢复缺口，不能算作“问题已修复”。MCP 模块有 LangChainBetaWarning，未导致失败。

临时调查用例位于 `/tmp/niuma_codebase_probe.py`，依赖已有 conftest 和 test_knowledge_library 辅助函数，不加入七份正式文档目录；可复现步骤见 [CONCERNS](CONCERNS.md)。它只操作隔离库，未修改开发数据库或业务源码。

前端实际命令：

```bash
cd frontend
pnpm exec vitest run \
  src/pages/conversations/useConversationController.test.tsx \
  src/pages/knowledge/knowledgeFlow.test.tsx \
  src/state/workspace/workspaceData.test.ts \
  src/state/workspace/WorkspaceDataProvider.test.tsx
```

前端四个文件 **31 项测试通过**。文档链接及索引检查 `UV_CACHE_DIR=/tmp/niuma-codebase-uv-cache UV_OFFLINE=1 make check-docs` 通过（errors=0）；默认 uv 缓存目录在沙箱中不可写，因此改用临时缓存。额外核对 docs/codebase 恰好七个文件、必需主题与证据段存在、无未填模板占位符、证据行号不越界；Prettier 定向检查通过。行号范围检查不替代源码语义复核。`[TODO]` 本次未运行全量 lint、build、所有业务测试、真实外部集成、浏览器 E2E 和负载测试。此次仅新增文档和导航，不改业务实现。

## 6. 证据

- [后端配置与 fixtures](../../backend/tests/conftest.py)、[测试清单](../../backend/tests/)、[前端配置](../../frontend/vitest.config.ts)。
- [执行边界](../../backend/tests/test_execution_boundaries.py)、[运行时边界](../../backend/tests/test_runtime_boundaries.py)、[重启恢复](../../backend/tests/test_checkpoint_runtime.py)。
- [知识集成测试](../../backend/tests/test_knowledge_library.py)、[知识页面测试](../../frontend/src/pages/knowledge/knowledgeFlow.test.tsx)、[公共命令](../../Makefile)。

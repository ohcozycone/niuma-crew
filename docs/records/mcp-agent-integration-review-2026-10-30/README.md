# MCP 与 Agent 审查证据

日期：2026-10-30。结论见[主报告](../mcp-agent-integration-review-2026-10-30.md)，分级结论的机器可读版本见[report.json](report.json)。本目录是本轮审查证据，不是已经落实的业务契约或通过后的功能验收。

## 证据组成

| 入口                                                | 范围                                                                   |
| --------------------------------------------------- | ---------------------------------------------------------------------- |
| [上下文档案](context/DOSSIER.md)                    | 关键函数、调用关系、不变量与未落实假设                                 |
| [源码摘要](source-hashes.json)                      | 审查时核心源码的 SHA-256；重跑前应检查当前文件变化                     |
| [历史轨迹](evidence/historical-runs.json)           | 正式库只读的必要投影；不含秘密、密文或完整配置                         |
| [模型请求对照摘要](evidence/wire-summary.json)      | 五组 MockTransport 场景的调用次数、结果和已确认协议行为                |
| [纯内存对照摘要](evidence/zero-tool-scenarios.json) | 无 URL、显式 Context7、显式 URL 的三组结果                             |
| [wire 探针](probes/test_model_wire.py)              | 真实平台、LangChain、ChatOpenAI/OpenAI SDK，合成 MCP 目录与假模型 HTTP |
| [MCP 补充探针](probes/test_mcp_extra_probes.py)     | 进程内真实 MCP 协议、服务版本摘要、isError 与通用参数约束              |
| [草稿与历史探针](probes/test_output_projection.py)  | 核验前草稿、失败后正文/SSE，以及成功正文进入后轮历史                   |

wire 探针使用形似 Context7 的两个工具，但不是实际 Context7 上游；串行/并行通过仅证明协议路由，不能据此认为有依赖的两项真实工具适合并行执行。

## 重跑诊断探针

从仓库根进入 backend，再执行：

```bash
cd backend
PYTHONPATH="$PWD:$PWD/tests" \
  PYTHONDONTWRITEBYTECODE=1 \
  NIUMA_MCP_AUDIT_OUTPUT=/tmp/niuma-mcp-review-20261030-recheck \
  .venv/bin/python -m pytest -p conftest -p no:cacheprovider \
  ../docs/records/mcp-agent-integration-review-2026-10-30/probes -q
```

使用项目已安装环境和 backend 测试夹具，每例临时 SQLite 与密钥；模型 HTTP 为 MockTransport，真实 MCP 协议为 ASGITransport。输出默认写系统临时目录，也可由上述专用变量指定；不会重写本目录的历史证据。无需正式账号、外网、付费模型或启动第三方包。

本轮临时原版与归档版本均通过 12 项探针；归档版只调整输出目录、导入和格式。部分用例断言缺口仍然存在，因此“通过”表示复现成功，不表示修复完成。修复后应将相应拒绝/如实失败用例纳入正常业务回归，不能继续以接受虚构回答作为产品通过标准。

本轮后端相关回归命令（cwd=backend）：

```bash
.venv/bin/python -m pytest \
  tests/test_llm.py tests/test_capability_runtime.py \
  tests/test_tool_readers.py tests/test_tool_results.py \
  tests/test_stdio_mcp.py tests/test_mcp_accounts.py \
  tests/test_mcp_management.py tests/test_mcp_registry_import.py \
  tests/test_agent_foundations.py tests/test_runtime_boundaries.py \
  -q --tb=short
```

结果为 95 passed，保留 LangChain MCP beta 警告。没有以此代替全仓检查、生产部署或真实供应商行为评测。

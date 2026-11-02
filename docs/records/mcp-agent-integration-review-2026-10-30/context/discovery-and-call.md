# MCP 发现与调用补充审阅

范围：只读代码与安装依赖源码；临时探针使用 FastMCP + httpx.ASGITransport 进程内协议，不使用真实网络、正式数据库、真实凭据或外部包进程。未修改仓库业务代码。以下补充问题不作为用户本次 Context7 未调用的直接原因；根代理已另行确认该轮两个工具进入快照，且 `auth_required=false`。哈希调用名是否影响模型选择没有本次因果证据。

## 已复现：服务版本变化会把未变工具视为定义变化

`backend/app/tools/adapters/mcp.py` L33-L43 将 tool.metadata 纳入 descriptor_hash。当前固定依赖 LangChain 1.4.7 的 `langchain/mcp/tools.py` L183-L209、L296-L303 将客户端握手的 serverInfo（含 version）放入 metadata.mcp.server。因此原始 name、description、inputSchema、raw_descriptor 都不变，仅服务版本更新，也会改变工具摘要。

临时用两个同名 FastMCP 服务（版本 1.0.0 与 1.0.1）注册同一函数，逐一 discover 后断言原始定义相同，拿第一版摘要调用第二版。真实 MCPClient.invoke 在调用 guard/业务函数之前抛 `tool_catalog_changed`，并返回新候选目录。复现测试：`test_real_protocol_server_version_only_change_rejects_unchanged_tool`。

后续链：

1. `MCPClient.invoke` L142-L155 对摘要不一致报定义变化。
2. `ToolService.call` L564-L568 保存候选并抛出；执行错误信息仅为“远端工具目录已改变，请管理员重新审核”（`execution/errors.py` L15），不区分原始工具变动、说明变动和 server metadata 变动。
3. 连接所有者 approve 新候选会替换批准目录（`tools/service.py` L513-L519），但旧员工 grant 的摘要不变。
4. 新任务 capture_tools L223-L225 会过滤原摘要 grant，结果只返回保留项，无 skipped 原因。

实际影响：上游服务正常部署仅更新 version 时，可要求重新确认目录和重新装配未变工具；重新确认后旧工具可从本轮可用集合消失。该问题与 hash 调用名无关，原因是定义摘要混入握手服务身份元数据。

## 已复现：网页提取的参数策略作用于所有 MCP

`backend/app/tools/policy.py` L85-L93 先允许已批准 schema 与配置范围，随后 L94-L120 无条件把所有非 native 工具的 `url`、`urls` 参数视为公开网页提取，不检查具体工具或显式声明的能力类型。

临时探针均使用 `scope_policy={mode: provider}`，无额外参数限制、无域名限制：

- `batch_compare_urls` 的批准 schema 允许字符串数组；传入 4 个合法公开 HTTPS URL，被 L101-L102 拒绝为 `tool_arguments_invalid` / “每次最多读取三个网页”。
- `open_resource` 的批准 schema 允许字符串 URI；传 `url=resource://catalog/library`，被 L113-L120 拒绝为 `tool_url_denied`。

实际影响：接入任意新 MCP 后，schema 合法、授权范围允许的调用仍可能被已有网页提取假设拒绝；工具原始 schema 没有表达这个隐藏上限或 scheme 约束。限制执行在 `authorize_tool`/`ToolService.call`（`agents/tool_grants.py` L301；`tools/service.py` L538-L539），发生于真实调用之前。该问题不影响没有 `url`/`urls` 参数的 Context7 resolver/query 基本调用。

## 已验证的边界：MCP isError 没有被当作成功

当前 LangChain MCP 转换器 `langchain/mcp/tools.py` L168-L180、L283-L303 将 MCP `isError=True` 转成 ToolMessage(status=error)，保留错误文本供模型处理。平台 `MCPClient.invoke` L160-L162 返回该状态；`ToolService.call` L588 将非 success 映射 failed；ToolExecutionMiddleware L256-L265 进一步保留为 error。

临时 FastMCP 工具返回 `CallToolResult(isError=True, content=[TextContent(...)])`。经真实进程内 HTTP MCP discover+invoke 后，返回 status=error，错误文本存在，guard 只执行一次。测试 `test_real_protocol_is_error_preserves_failed_status` 通过。未发现该链把 isError 改成成功的问题。

## 验证证据与剩余范围

- 临时探针：`/tmp/niuma-mcp-audit-20261030/test_mcp_extra_probes.py`，最终 `5 passed`（两项 policy 拒绝、单纯 descriptor 摘要对比、真实 isError、真实服务版本变化）。
- 仓库原始用例 `tests/test_agent_foundations.py::test_mcp_official_adapter_discovers_and_calls_real_protocol` 单独并入首轮探针执行，通过。
- 当前 `langchain.mcp` 导入给出 BetaWarning，未造成测试失败；不能据此推断本次故障原因。
- 未验证真实 Context7 远端服务版本/目录是否曾变化；本次有效根因要以根代理的具体 Run、实际模型请求和执行轨迹为准。
- 已检查初次预算未知项：运行时 middleware L60-L64 确实包含实际工具 schema，不能报告“最终预算漏算全部工具”。

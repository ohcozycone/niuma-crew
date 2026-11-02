# MCP review 复核与 stdio 生命周期边界

日期：2026-10-29。复核来源为任务[排查模型未调用 Tavily MCP](codex://threads/01a18311-2d2b-7141-8995-7f5dd8df3a23)的最终 NiumaCrew 结论；该任务早期对 StaffDeck 的分析不直接作为本工程证据。只修改设计和核查文档，没有修改业务代码、数据库或真实 MCP 配置，没有调用真实模型、Tavily 或启动容器。

## 范围与版本依据

核对当前源码、已安装 SDK 和隔离测试。仓库尚无可引用提交，因此对主要核查文件保存 SHA-256；文件之后变动时，本记录不自动代表新实现。

| 文件                                       | SHA-256                                                            |
| ------------------------------------------ | ------------------------------------------------------------------ |
| backend/app/tools/adapters/mcp.py          | `8197181b7062dfd6f60b41bf38b4b87f318d80ab2689b69c46ed4bfc4168ea10` |
| backend/app/agent_runtime/langchain.py     | `ea60ccb3163b57c08cfbb5f266311aae722bd9c2faf81d3fff263605cfb2c76e` |
| backend/app/agent_runtime/skill_loading.py | `f60b0160c55d65f1c745726c39f8a36b9ad15542bf7521e1036e51e60b6a1c62` |
| backend/app/agent_runtime/tool_calls.py    | `7e1d1ace7ebad38c3c19743836cafe8d0de5eb8e27184f7935941d1da1b789b7` |
| backend/app/sandboxes/service.py           | `f30aab4bdf3f260844262855b4f35df497ba4b7daf8dfca969333bf95f7a0575` |
| backend/app/sandboxes/models.py            | `ece561e2c179d4568e72cfbca5149b1ab13b0f4852a95f50e1edf8c4e2768bd5` |

## 对 review 的核对结论

| 判断                           | 本轮结论与证据                                                                                                                                                                     |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 已装配技能的目录没有送模       | 不适用于当前工程。隔离模型请求中含名称、简介和路径，正文按需读取；显式选择后首轮有正文及参数                                                                                       |
| MCP 没有形成真实模型工具       | 不成立。[external_tools](../../backend/app/agent_runtime/tool_calls.py)以 StructuredTool 保留已确认的描述和输入 schema，交给 create_agent；官方协议发现/调用与模型请求接线测试通过 |
| 输入/输出/示例未进入技能正文   | 成立。API 保存标记成功，但实际模型请求中没有这些标记；[捕获](../../backend/app/agents/service.py)和[拼接](../../backend/app/agent_runtime/skill_loading.py)均未包含三字段          |
| 未调用外部工具仍可声称完成     | 成立。假模型直接声称读完指定 URL，网页调用数为零，Run 仍 succeeded；[结束检查](../../backend/app/agent_runtime/langchain.py)未验证目标证据                                         |
| full_text 表示比实际范围更强   | 成立。模拟登录提示文本也被标为 full_text=True；[标记逻辑](../../backend/app/agent_runtime/tool_calls.py)主要检查工具名及非空文本                                                   |
| 每个 MCP 都需要手写一套 prompt | 无此必要。描述和 schema 已自动传递；应补通用执行要求及服务可选说明链路，特殊业务结果按实际需要适配                                                                                 |

review 通过假模型证明的是平台会接受错误执行声明，不是证明某个真实模型跳过调用的内在原因。真实模型能力、提示词与历史影响仍需行为评测。

## 新确认的服务说明缺口

使用当前 MCPClient、官方 FastMCP Server 与 httpx.ASGITransport，在进程内提供唯一 instructions 标记、工具描述和返回 schema：

1. SDK 的 adapter.client.instructions 能读到标记，说明协议与 SDK 接收正常。
2. 项目 `_tools` / descriptor 只保存工具级对象；目录中没有标记，也没有其他捕获服务说明的模型入口。
3. 工具 description、输入 schema、服务身份 metadata 和 raw_descriptor.outputSchema 仍保留。
4. 运行时 external_tools 再次构造 StructuredTool，保留描述和输入 schema，但 metadata 为空；不能把目录中保存 SDK metadata 等同于模型收到说明。

临时探针为 `/private/tmp/test_niuma_mcp_metadata_review.py`。这验证“服务提供说明时当前平台无法继续传递”的能力缺口，没有使用真实 Tavily，不能证明该服务提供了说明或说明遗漏是该次幻觉的直接原因。旧版 MCP 的可选 instructions 见[生命周期规范](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle)；安装的 FastMCP 客户端提供跨协议版本的 instructions 访问属性。

## 本轮实际检查

1. 现有离线测试：test_capability_runtime、test_agent_foundations、test_tool_readers，合计 **42 passed**。
2. 阅读并在系统临时目录复跑 review 的三个探针；另加本轮服务说明探针，合计 **4 passed**。
3. 为 full_text 增加部分文本探针，目标文本仅为登录提示，确认仍标为全文，**1 passed**。

合计 47 项测试/探针通过，其中若干探针的通过表示成功复现缺口，不能写成缺陷已修复。现有测试使用临时数据库、脚本化模型、MockTransport 或进程内 MCP，无付费/外部模型请求。运行时出现官方 langchain.mcp beta 提示，没有因该提示修改依赖版本。

## stdio 与沙箱的核查

[SandboxResource](../../backend/app/sandboxes/models.py)以唯一 Run 外键归属；[SandboxService](../../backend/app/sandboxes/service.py)按 Run 创建，达到容量就报错，并在 Run 不活动或到期时清理。默认并发为一，[命令后端](../../backend/app/agent_runtime/sandbox_backend.py)提供有界命令执行，不是 MCP 的持续双向通信。当前没有 stdio 或沙箱资源等待队列。

因此只登记配置无需沙箱；目录发现或实际调用 stdio 才需进程。协议不强制容器，但云平台应按实际用户、连接及运行会话隔离。MCP 多工具可复用同一进程；不同用户和账号不能仅凭包名在全平台合并。带凭据的 MCP 与任意任务脚本默认分开，避免同权限进程共享秘密与文件。

原有容量、排队和回收原则可以复用；资源归属和会话语义需要扩展。首版推荐同一 Run 内复用同一连接实例、结束关闭；跨 Run 常驻或空闲复用为后续增量。统一计入资源总量并处理多资源准入，不能让任务占满所有脚本环境后永远等 MCP 环境。

设计已回写[stdio 生命周期增量](../proposals/skills-and-mcp/skill-package-and-runtime-integration.md#51-什么时候启动以及一份实例包含什么)，并澄清[旧沙箱方案范围](../proposals/skills-and-mcp/sandbox-service.md)。本轮没有验证实际容器、宿主网络、进程间隔离或真实 stdio 包。

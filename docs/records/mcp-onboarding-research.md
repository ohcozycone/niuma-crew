# MCP 连接配置标准与接入体验调研

日期：2026-10-29。方法：读取 MCP 官方协议、Registry 格式、Context7 官方服务描述、VS Code 与 Claude Code 客户端文档，并对照当前平台代码。本文区分外部标准、平台建议与当前实现；没有因本次调研增加 Registry 或 OAuth 功能。

## 结论

建议接入流程是：**导入服务方的描述或示例配置 → 填写连接参数与凭据 → 测试连接并读取工具 → 明确装配给员工**。手动填写地址、启动程序和环境变量名作为后备入口。HTTP 与 stdio 共用连接设置的产品结构，只在实际传输和凭据注入方式上分支。

这不是 MCP 规定的唯一页面流程，而是依据下述规范与客户端实践，对当前平台给出的产品建议。不要再把“先保存，另找账号入口，手动声明密钥变量，再分别发现和批准”作为所有服务的默认使用路径。

## 三层标准不能混为一份通用配置

| 层次                            | 解决的问题                                                          | 不负责什么                                            |
| ------------------------------- | ------------------------------------------------------------------- | ----------------------------------------------------- |
| MCP 运行协议                    | stdio/Streamable HTTP 通信、能力协商、工具发现与调用；HTTP 授权框架 | 不规定本平台页面、员工装配或一份统一客户端安装文件    |
| Registry 服务描述 `server.json` | 发布者、程序包或远程地址、安装参数、环境变量与请求头的输入描述      | 不保证每个服务均提供，也不要求 MCP 端点在握手中返回它 |
| 各宿主的安装配置                | 将服务配置给特定客户端，引用该宿主的环境变量、密钥输入与启动选项    | 不同客户端的字段和变量语法不完全通用                  |

MCP 官方 Registry 提供标准化安装与配置元数据，但目前仍标为 preview。它记录元数据并指向程序包或服务；来源命名验证不等于代码安全审查。当前平台无需为此先建设插件市场或自托管 Registry。[Registry 官方说明](https://modelcontextprotocol.io/registry/about)

VS Code 同时存在顶层 `servers` 与 `mcpServers` 等配置形式，交互输入、环境文件和变量引用的支持也不同。因此“JSON 是合法的”不等于“任意 MCP 客户端都能直接导入”。[VS Code 配置参考](https://code.visualstudio.com/docs/agents/reference/mcp-configuration)

## 对前面“字段能否自动发现”的修正

只给一个 MCP URL，仍不能保证平台自动知道全部 API Key、租户编号或自定义请求头。但如果服务方提供 Registry 描述，平台可以读取字段名称、说明、是否必填、是否保密、格式与默认值等，而不必总让用户查文档后手填变量名。之前的解释遗漏了这个标准化元数据来源。[Registry 格式](https://github.com/modelcontextprotocol/registry/blob/main/docs/reference/server-json/generic-server-json.md)、[服务描述 schema](https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json)

需要区分三个来源：

1. **服务描述**声明安装或连接需要哪些输入，可以用于生成表单。
2. **HTTP OAuth 元数据**用于找到授权服务器并完成授权；不等于任意静态 Key 的通用表单接口。
3. **工具的 inputSchema**描述搜索词、仓库名等调用参数，不是账号安装参数。

OAuth 的使用方式及发现流程见[官方授权规范](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)；业务工具结构见[官方工具规范](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)。协议规范版本不等于当前安装 SDK 的支持版本，连接仍须使用双方支持的版本协商。

## Context7 的真实例子

Context7 官方仓库提供 `server.json`，同时描述本地包与远程服务：

| 接入方式             | 公开描述中的凭据字段        | 描述含义                                   |
| -------------------- | --------------------------- | ------------------------------------------ |
| 本地 stdio 包        | `CONTEXT7_API_KEY` 环境变量 | 可选、秘密输入                             |
| 远程 Streamable HTTP | `Authorization` 请求头      | 可选、秘密输入；说明接受 Bearer 或原始 Key |

因此导入这份描述后，页面可以显示一个“API Key（可选）”密码框；用户无需先理解变量名。平台负责将用户输入映射到正确的环境变量或请求头。不能依据 stdio/HTTP 推断是否需要 Key。[Context7 官方服务描述](https://github.com/upstash/context7/blob/master/server.json)

版本需单独核对：此次读取的描述声明包版本 `4.0.3`；前次本机真实验证使用固定包版本 `4.4.4`。两份证据不能拼成“4.4.4 安装描述已完全验证”。导入时应保留来源和包版本，更新显式确认，不静默替换为最新版本。[本机接入验证](capability-integration-implementation.md#context7-真实-stdio-接入补验2026-10-29)

## 推荐给当前平台的页面流程

1. **添加 MCP**：默认可导入服务方描述或客户端示例；保留手动填写。导入仅解析与预览，不自动启动第三方程序。预览名称、来源、传输、地址或程序包与版本。
2. **连接设置**：同一位置展示匿名、API Key 或其他已支持认证。优先按描述生成必填/可选字段；普通配置和密码字段分开。没有描述时，允许高级用户依据官方配置声明字段，平台不猜测。
3. **保存并测试连接**：保存定义与凭据后，在数据库事务之外握手、获取工具。分别报告“已保存”“已连接”“已读取工具”，失败可以返回修改；不让远程网络请求长期占用数据库写事务。
4. **确认可用工具**：首次读取后展示真实工具与数量，可编辑展示别名，同时始终保留原始名。首次目录确认可并入向导完成步骤，不必让用户理解候选/批准等内部术语。
5. **员工主动装配**：选择连接及允许的工具，保存员工配置。接入服务不会自动给全部员工授权；个人凭据不会因共享员工而自动变成共享凭据。
6. **后续维护**：服务详情集中提供修改连接、替换 Key、测试连接、检查工具更新和删除。新工具可见性与员工许可分开；更新不会自动扩权。

VS Code 明确将添加配置、安装运行前提与实际验证分开；客户端文档也区分远程 HTTP 与本地命令启动。建议使用官方已托管 HTTP 服务处理纯远程业务；仅有本地包或确需本地系统能力时使用 stdio，避免不必要的本地进程管理。这是部署取舍，不是两种传输的能力高低。[VS Code 添加 MCP](https://code.visualstudio.com/docs/agent-customization/mcp-servers)、[Claude Code MCP 文档](https://code.claude.com/docs/en/mcp)

## 目录确认、身份与运行边界

目录候选、人工确认、中文别名、员工账号绑定属于本平台管理规则，MCP 不要求所有宿主实现相同审批流程。目录快照固定平台批准的定义与许可，不能冻结远端实现。删除、改名或不兼容定义变化应导致受影响调用不可用并提示维护；不能因为平台保有旧快照就承诺旧工具仍可运行。不同授权身份可能看到不同工具，目录须与实际连接身份对应。[工具规范](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)、[Claude Code 动态工具更新](https://code.claude.com/docs/en/mcp#dynamic-tool-updates)

stdio 是宿主通过标准输入输出连接子进程的通信方式，不自动带来隔离。当前平台将管理员登记的可信 MCP 子进程与不可信脚本的 Run 沙箱分开；不因支持标准描述就改成任意用户可以提交宿主程序。部署到腾讯云时，stdio 程序和运行环境位于后端所在机器，不是浏览器所在的 Mac。[传输规范](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports)、[当前 MCP 契约](../reference/mcp.md)

协议会话、工具转换与传输复用 SDK；账号归属、秘密持久化、员工授权、网络限制、进程配额和关闭回收由平台负责，不必为每个厂商重新写协议适配器。[LangChain MCP 文档](https://docs.langchain.com/oss/python/langchain/mcp)

## 当前实现与待讨论增量

| 能力                                        | 当前证据与状态                                           |
| ------------------------------------------- | -------------------------------------------------------- |
| HTTP、可信 stdio、Token/env、工具发现       | 已实现；Context7 stdio 有真实发现和工具调用记录          |
| 客户端配置导入                              | 当前只处理受限 `mcpServers` 格式，不承诺所有宿主配置兼容 |
| 已有匿名连接补 Key、更新凭据                | 已实现访问设置；没有因本次研究填写真实个人 Key           |
| 服务字段与账号凭据分开                      | 当前已分开持久化；页面仍有手动声明环境变量名等使用成本   |
| Registry `server.json` 导入、元数据生成表单 | 未实现；本次提出的建议，不当作现有功能                   |
| VS Code `inputs` 等输入语法                 | 未实现；不应把未解析占位符当实际密钥                     |
| OAuth 发现、登录与刷新                      | 按用户要求后置；不作为当前 Token 接入前提                |
| 一步连接向导与首次目录确认合并              | 产品改进建议，本次未继续改页面                           |

代码入口：[导入与定义](../../backend/app/tools/definitions.py)、[账号与凭据（现职责分工）](../../backend/app/tools/README.md)、[字段契约](../../backend/app/tools/schemas.py)、[接入页面](../../frontend/src/pages/tools/ToolsPage.tsx)、[访问设置](../../frontend/src/pages/tools/ConnectionSettings.tsx)。

本次只完成来源核对、代码对照与调研记录；没有验证每个服务描述都与其已发布包同步，没有实施元数据导入，没有新增真实第三方授权或云端部署。后续若采纳建议，应先将增量写入[实施计划](../proposals/skills-and-mcp/execution-plan.md)，再实施与验证。

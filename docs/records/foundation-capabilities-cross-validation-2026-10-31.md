# 内置基础能力与插件边界：八个 Agent 产品交叉核验

后续实施设计见[官方基础能力包与可靠交付方案](../proposals/skills-and-mcp/foundation-capability-packages.md)，状态为草案、未实施；本记录继续保留调研时点的证据与判断。

日期：2026-10-31，北京时间。外部快照采集于 2026-10-30 15:59 至 16:12 UTC 附近。状态：调研与架构建议，未采纳为新的现行契约，未修改业务实现。

## 结论

**NiumaCrew 应维护少量官方基础能力，并对这些能力的默认工具、使用方法和交付质量持续调优。基础能力可以使用外部服务，也可以通过官方插件实现。** 对通用数字员工而言，仅提供 MCP 接入、Skill 装配和运行循环，会把过多组合与排障责任留给使用者。

需要同时保留三条边界：

1. 内置的核心是产品责任：官方选择默认方案、维护兼容性、处理结果和失败、提供使用方法、验证真实任务。它不要求自研搜索引擎，也不要求把所有代码写进运行核心。
2. 插件是实现与扩展机制。官方基础插件、组织管理的连接器、用户自行安装的社区插件，承担的质量责任不同，不能只按打包形式归为一类。
3. 所有员工不必拥有所有基础能力。平台提供经过维护的能力包，员工仍按角色和当前使用者身份取得许可；存在、配置完成、获得授权、当前可用是不同状态。

本次证据支持这个产品边界判断，**不能证明改成内置后成功率会增加多少、token 会下降多少，也不能证明某个产品可靠性最高**。这些需要同题、同模型或受控模型组合的重复实验。

## 方法、样本与适用范围

以官方 GitHub 仓库、仓库内文档、配置默认值和具体实现交叉核对。先用搜索发现产品，再核验官方归属；没有把搜索摘要、自称官网的第三方站点或社区对比文章当作最终依据。未安装、运行这八个产品，未执行跨产品性能基准。

样本按产品形态选择：个人助理、可操作电脑的通用执行产品、团队数字工作台、应用与工作流平台。GitHub star 只用于说明关注度，不能证明活跃用户数、任务成功率或企业成熟度。八个仓库在采集时均有当天的 `pushed_at`；推送时间同样不是质量指标。

| 产品与官方仓库                                                | 本次关注度快照 | 核验的提交                                        | 定位与许可说明                                                                |
| ------------------------------------------------------------- | -------------: | ------------------------------------------------- | ----------------------------------------------------------------------------- |
| [OpenClaw](https://github.com/openclaw/openclaw)              |  393,450 stars | `225af953d1b14ff5da619da6441505fecf30f2b1`        | 个人助理与多入口运行；MIT                                                     |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent)  |        258,777 | `5057eaa3a4d0cbef0e30078418a5115faa62889e`        | 带记忆、技能与执行环境的个人 Agent；MIT                                       |
| [nanobot](https://github.com/HKUDS/nanobot)                   |         49,680 | `3e4068411275fac02fbc109926fffea855a94961`        | 轻量、自托管个人 Agent；MIT                                                   |
| [QwenPaw，原 CoPaw](https://github.com/agentscope-ai/QwenPaw) |         37,014 | `c26d31c0688aa9cce9bc1aef688177d2e14e25df`        | 多入口个人助理；Apache-2.0                                                    |
| [Agent Zero](https://github.com/agent0ai/agent-zero)          |         19,604 | `ff2a5b9c9c4e490ba38dd7c313e779510bb2071a`        | Linux 电脑、浏览器、文档协作与通用执行；根 LICENSE 为 MIT                     |
| [Goose](https://github.com/aaif-goose/goose)                  |         55,961 | `090dedb7625c8aadb9bb05d68028fd00f36b429e`        | 本机通用执行 Agent，扩展优先；Apache-2.0                                      |
| [OpenWork](https://github.com/different-ai/openwork)          |         24,329 | `0dcf407af6ee128ed9fe6a7527995148047fe480`，`dev` | 面向文件工作的桌面与团队工作台；非 `ee/` 为 MIT，`ee/` 使用专有源代码可见许可 |
| [Dify](https://github.com/langgenius/dify)                    |        160,007 | `ab3b0be88d8b636ef53e68a371ea668d2cbb3a5e`        | Agent、工作流及应用平台；修改版 Apache 条款，不能当作无附加条件的 Apache-2.0  |

关注度来自官方仓库 API 的 `stargazers_count`；例如 [OpenClaw 元数据](https://api.github.com/repos/openclaw/openclaw)、[Hermes 元数据](https://api.github.com/repos/NousResearch/hermes-agent)。许可证边界直接核对 [Agent Zero LICENSE](https://github.com/agent0ai/agent-zero/blob/ff2a5b9c9c4e490ba38dd7c313e779510bb2071a/LICENSE)、[OpenWork LICENSE](https://github.com/different-ai/openwork/blob/0dcf407af6ee128ed9fe6a7527995148047fe480/LICENSE)、[Dify LICENSE](https://github.com/langgenius/dify/blob/ab3b0be88d8b636ef53e68a371ea668d2cbb3a5e/LICENSE)。本研究把后三者的架构作为公开可读证据，不将所有目录笼统归为同一种开源许可。

检索期间 Tavily 深度研究接口报内部错误，后续通过 GitHub 连接器及官方网页直接完成核验；没有以失败的研究请求充当已取得的证据。Agent Reach 更新检查因 DNS 失败未完成，不影响已经取得的源码与文档。

## 八个产品分别证明了什么

### OpenClaw：搜索成为稳定产品接口，供应商仍可替换

官方搜索文档将 `web_search`、`web_fetch` 和浏览器区分使用；搜索供应商可配置。配置存在不等于服务可用，文档给出实际测试入口；缺少配置时可以不向模型暴露不可用的搜索工具。[官方搜索说明](https://github.com/openclaw/openclaw/blob/225af953d1b14ff5da619da6441505fecf30f2b1/docs/tools/web.md)

更直接的实现证据是 `web-search-output.ts`：核心边界把官方和外部供应商的返回归一为 error、results、answer、raw 四种分支，统一外部内容标记和输出预算；测试区分供应商 HTTP 错误、连接失败及超时。[输出实现](https://github.com/openclaw/openclaw/blob/225af953d1b14ff5da619da6441505fecf30f2b1/src/agents/tools/web-search-output.ts)、[错误测试](https://github.com/openclaw/openclaw/blob/225af953d1b14ff5da619da6441505fecf30f2b1/src/agents/tools/web-search.provider-errors.test.ts)

含义：内置可以指对统一能力负责，底层继续使用供应商插件。不能据此推导“所有结果都是完整网页”或“所有新功能都应进入核心”；其 [插件文档](https://github.com/openclaw/openclaw/blob/225af953d1b14ff5da619da6441505fecf30f2b1/docs/tools/plugin.md)仍把搜索、网页读取等列为插件可扩展能力。

### Hermes：基础工具组、使用场景与供应商插件一起维护

`toolsets.py` 明确定义共享核心工具组，覆盖搜索、提取、文件、终端、浏览器、技能、记忆等；同时定义 coding、safe 及不同入口的组合。工具进入核心列表不保证已配置、已启用或对每个会话开放，代码另有能力检查和入口过滤。[工具组源码](https://github.com/NousResearch/hermes-agent/blob/5057eaa3a4d0cbef0e30078418a5115faa62889e/toolsets.py)

其网页实现更接近本次问题：供应商代码位于 `plugins/web/<vendor>`，通用模块负责选择、缓存、失败处理和截断保存。显式选择了供应商时，部分路径会直接保留该供应商错误，避免静默切换；不能笼统描述为“失败必然自动换源”。长提取结果有保存全文、提示省略部分及精确续读方式的实现，并有无需 LLM 的对应测试。[网页入口](https://github.com/NousResearch/hermes-agent/blob/5057eaa3a4d0cbef0e30078418a5115faa62889e/tools/web_tools.py)、[截断与保存](https://github.com/NousResearch/hermes-agent/blob/5057eaa3a4d0cbef0e30078418a5115faa62889e/tools/web_tools_truncate.py)、[测试](https://github.com/NousResearch/hermes-agent/blob/5057eaa3a4d0cbef0e30078418a5115faa62889e/tests/tools/test_web_tools_truncate.py)

含义：调优对象是工具组、结果表达、上下文成本和读取方法，而不只是增加供应商。存在测试证明维护了这些边界，不代表本次已经运行其测试或验证其整体成功率。

### nanobot：轻量核心也保留受维护的搜索与读取能力

工具加载器区分内置工具与 Python entry-point 插件；保留调用方已提供的工具，检查启用条件，并处理插件与内置工具重名。网页模块维护搜索供应商选项，分别提供 `web_search` 和 `web_fetch`，工具描述明确摘要发现与具体页面读取的用途，并说明登录或重 JavaScript 页面可能失败。[加载器](https://github.com/HKUDS/nanobot/blob/3e4068411275fac02fbc109926fffea855a94961/nanobot/agent/tools/loader.py)、[网页工具](https://github.com/HKUDS/nanobot/blob/3e4068411275fac02fbc109926fffea855a94961/nanobot/agent/tools/web.py)

含义：少量基础接口与可扩展性可以共存。轻量不是只剩一个循环和任意外部工具，也不能按早期宣传把当前仓库理解为只有几千行代码的实验品；本次按当前实现核验。

### QwenPaw：同样使用 Tavily，仍可拥有自己的基础能力体验

原 CoPaw 官方仓库当前重定向到 QwenPaw。源码通过工具描述器登记内置工具；`web_search` 使用可插拔供应商，默认 Tavily，`web_fetch` 则使用直接 HTTP 与 HTML 转换。错误结果有明确的 ERROR 状态，不只依赖 MCP 请求是否成功。[内置登记](https://github.com/agentscope-ai/QwenPaw/blob/c26d31c0688aa9cce9bc1aef688177d2e14e25df/src/qwenpaw/agents/tools/__init__.py)、[搜索与读取](https://github.com/agentscope-ai/QwenPaw/blob/c26d31c0688aa9cce9bc1aef688177d2e14e25df/src/qwenpaw/agents/tools/web_search.py)

它还随产品维护浏览器及 PDF、Word、表格等 Skills。浏览器 Skill 对观察、动作、验证、人工接管和来源陈述作出具体要求，SDK 参考随 Skill 提供。[内置 Skills 目录](https://github.com/agentscope-ai/QwenPaw/tree/c26d31c0688aa9cce9bc1aef688177d2e14e25df/src/qwenpaw/agents/skills)、[浏览器 Skill](https://github.com/agentscope-ai/QwenPaw/blob/c26d31c0688aa9cce9bc1aef688177d2e14e25df/src/qwenpaw/agents/skills/browser-zh/SKILL.md)

含义：使用同一个搜索服务，也可以由产品方维护工具与方法。这是反对“只有一个搜索供应商就是主要问题”的具体证据。其 Shell/curl 降级提示适用于其执行环境，不能直接移植成 NiumaCrew 绕过授权或沙箱的备用通道。

### Agent Zero：基础能力本身可以是官方核心插件

当前产品提供 Linux 电脑、浏览器、文档协作与项目工作区。仓库明确区分随框架更新的 `plugins/` 与用户自定义的 `usr/plugins/`；前者已有浏览器、代码执行、记忆、Office、工具访问等核心插件。[产品 README](https://github.com/agent0ai/agent-zero/blob/ff2a5b9c9c4e490ba38dd7c313e779510bb2071a/README.md)、[核心插件说明](https://github.com/agent0ai/agent-zero/blob/ff2a5b9c9c4e490ba38dd7c313e779510bb2071a/plugins/README.md)、[核心插件目录](https://github.com/agent0ai/agent-zero/tree/ff2a5b9c9c4e490ba38dd7c313e779510bb2071a/plugins)

含义：如果把“插件化”本身当成问题，这个案例直接反驳该判断。需要区分官方负责的基础插件与用户自由拼装的插件。目录存在也不意味着全员强制开启；例如代码执行插件支持按项目和 Agent 配置，并非不可关闭的常量。[代码执行插件清单](https://github.com/agent0ai/agent-zero/blob/ff2a5b9c9c4e490ba38dd7c313e779510bb2071a/plugins/_code_execution/plugin.yaml)

### Goose：扩展优先，同时交付官方默认组合与方法

Goose 的扩展基于 MCP。配置源码指定默认 Developer 扩展，官方文档说明其默认开启；平台扩展源码则显式维护默认开关，例如 Extension Manager 默认开启，Todo、Chat Recall 默认关闭，部分能力还取决于构建特性。[默认配置](https://github.com/aaif-goose/goose/blob/090dedb7625c8aadb9bb05d68028fd00f36b429e/crates/goose/src/config/extensions.rs)、[平台扩展](https://github.com/aaif-goose/goose/blob/090dedb7625c8aadb9bb05d68028fd00f36b429e/crates/goose/src/agents/platform_extensions/mod.rs)、[使用说明](https://github.com/aaif-goose/goose/blob/090dedb7625c8aadb9bb05d68028fd00f36b429e/documentation/docs/getting-started/using-extensions.md)

Developer 实现不仅提供 Shell、编辑和目录工具，还通过 MCP server instructions 附带读取、搜索、编辑、验证和减少无谓轮次的使用指导。[Developer 实现](https://github.com/aaif-goose/goose/blob/090dedb7625c8aadb9bb05d68028fd00f36b429e/crates/goose/src/agents/platform_extensions/developer/mod.rs)

含义：可靠使用方法可以与对应扩展一起分发，不必全写入全局系统提示。官方默认能力、MCP 协议和产品调优并不矛盾；其本机自主执行默认值不适合直接作为多账号数字员工平台的权限策略。

### OpenWork：搜索留在连接器层，也是一种成立的产品选择

OpenWork 基于 OpenCode 提供文件工作台与团队能力管理。官方使用文档允许组织管理员接入 Exa，也允许个人添加 Exa MCP；这构成“搜索必须原生实现”的反例。[Exa 接入文档](https://github.com/different-ai/openwork/blob/0dcf407af6ee128ed9fe6a7527995148047fe480/packages/docs/start-here/connect-your-stack/enable-exa-search.mdx)

同时，浏览器有官方第一方扩展和明确使用边界：仅桌面提供，云 Worker 与 Web 不具备相同浏览器；文档说明会话标签所有权和人工接管。README 中的 OpenWork MCP 通过搜索与执行能力等四个工具暴露组织资源，而不是为全部后台能力永久展开所有 schema。[浏览器说明](https://github.com/different-ai/openwork/blob/0dcf407af6ee128ed9fe6a7527995148047fe480/packages/docs/start-here/do-work-with-it/control-the-browser.mdx)、[README](https://github.com/different-ai/openwork/blob/0dcf407af6ee128ed9fe6a7527995148047fe480/README.md)

含义：产品可以把重点放在工作台、连接治理与能力发现上，让搜索继续使用标准 MCP。这里能证明这种架构选择实际存在，不能在未实测时断言其搜索质量优于或逊于统一搜索接口。仓库 marketplace 架构文档含分阶段设计，本报告不把其中所有设想视为已实现。

### Dify：插件生态很大，仍不能把产品理解为只有工具装配

当前 README 已描述带独立沙箱、命令执行、安装工具及文件处理的新 Agent。仓库 `dify-agent` 以 Pydantic AI 运行，生产模块包含 shell、history、knowledge、output、tools 与 core_tools；插件层消费平台准备的 schema，并转换调用结果，核心工具层把需要平台凭证和本地状态的调用留在 API 进程边界。[当前 README](https://github.com/langgenius/dify/blob/ab3b0be88d8b636ef53e68a371ea668d2cbb3a5e/README.md)、[运行模块说明](https://github.com/langgenius/dify/blob/ab3b0be88d8b636ef53e68a371ea668d2cbb3a5e/dify-agent/docs/dify-agent/index.md)、[插件工具实现](https://github.com/langgenius/dify/blob/ab3b0be88d8b636ef53e68a371ea668d2cbb3a5e/dify-agent/src/dify_agent/layers/dify_plugin/tools_layer.py)、[核心工具实现](https://github.com/langgenius/dify/blob/ab3b0be88d8b636ef53e68a371ea668d2cbb3a5e/dify-agent/src/dify_agent/layers/dify_core_tools/layer.py)

含义：应用搭建平台与开箱使用的数字员工承担不同组合责任，不能因 Dify 有 Marketplace，就推导数字员工也应把全部基础体验交给市场。这里核对的是主分支实现，不保证 NiumaCrew 当前安装的其他框架版本具有相同行为。

## 对用户判断的支持与反驳

| 判断                                   | 本次结论               | 理由                                                                                   |
| -------------------------------------- | ---------------------- | -------------------------------------------------------------------------------------- |
| 通用数字员工应有少量官方基础能力       | 支持                   | 多个样本明确维护工具组、核心插件、默认扩展或工作区执行能力；符合直接交付工作的产品定位 |
| 应围绕基础能力持续调优                 | 支持，但须定义调优对象 | 应同时调整工具语义、结果表达、方法、预算与模型适配，并用任务质量和成本验收             |
| 基础能力不能是插件                     | 反对                   | Agent Zero、Goose 的基础能力就使用插件或扩展；Hermes 将搜索供应商放在插件目录          |
| 搜索必须原生实现                       | 反对绝对化             | OpenWork 通过连接器/MCP 提供 Exa；NiumaCrew 也可以继续复用 Tavily MCP                  |
| 应先增加很多搜索工具或供应商           | 证据不支持             | QwenPaw 默认也使用 Tavily；本工程原样本更直接的问题是预算截断、证据读取与事实判断      |
| 能力越多越通用                         | 反对                   | 能力目录规模、每轮暴露工具和单个员工权限是不同问题；过大的 schema 与重复说明会增加成本 |
| 通用能力可靠性可以全部泛化成同一套规则 | 只能部分成立           | 错误、来源、分页、权限等可共用；浏览器观察、文档验收、搜索证据充分性仍需各自方法和测试 |

## NiumaCrew 当前真正缺少什么

本工程已有原生文件目录、Skill 包、通用 MCP、结果持久保存、`read_tool_result`、沙箱接口及逐动作授权。应在这些基础上形成官方能力体验，而不是重新搭建另一套 Agent 循环。[当前工具契约](../reference/agent-tools.md)、[运行边界](../architecture/agent-runtime.md)

| 已确认现状                                                    | 对基础能力建设的含义                                                                      |
| ------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `tool_calls.py`、`tool_results.py` 中直接识别 Tavily 提取格式 | 平台已经在承担部分供应商适配；需要明确其归属，避免不断向通用循环追加供应商特判            |
| 长结果先给序列化 JSON 的 3000 字符预览，再允许续读            | 具备取回已返回结果的能力；仍应优化给模型看的摘要、正文定位与元数据占比                    |
| 续读只能读上游已返回的数据                                    | 必须区分工具返回读完、提取片段读完与原网页完整；上游 query 过滤过的内容不能靠本地分页恢复 |
| 原样本有 Tavily 429 被记为成功                                | 基础适配应分别表达协议成功、业务失败及可采取的下一步，不能全交给模型猜错误文本            |
| 原员工已有 Tavily 搜索、提取、抓取、映射、研究及 Context7     | 不能把问题描述成“只有一个工具”；缺口是有无可用、互补且使用清楚的能力组合                  |
| 文件、沙箱和输出发布边界已存在                                | 优先复用既有许可与交付路径；沙箱仍需目标部署环境验收，不能因接口存在就宣布可用            |

实现证据见 [ToolOutcome](../../backend/app/tools/contracts.py)、[外部结果包装](../../backend/app/agent_runtime/tool_calls.py)、[长结果读取](../../backend/app/agent_runtime/tool_results.py)、[调用状态转换](../../backend/app/tools/invocation.py)。具体故障取证及成功复测分别见[原诊断](agent-openspec-nonconvergence-2026-10-30.md)与[成功对照修订](openspec-successful-comparison-2026-10-30.md)。

原题在隔离续跑的第 9 次模型请求会回答，原来的 8 次上限提前终止；从头复测既有 2 轮错误回答，也有 5 轮核心正确回答。这说明需要同时处理收束与取证质量。**本次产品调研不能追溯性地把原失败改判为“缺少内置搜索引擎”**，也不支持以一次 Codex 轨迹确定通用轮数或 token 标准。

## 适合本产品的基础能力范围

以下是研究建议，不是已实施清单。以跨员工任务复用和可验收交付为选择依据，不因竞品有某项功能就立即跟进。

| 能力包         | 官方需要负责的完整范围                                                                     | 首轮边界                                                                                    |
| -------------- | ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------- |
| 信息获取       | 发现来源、读取具体页面、定位相关证据、保存来源、标明摘要/片段/正文、失败解释、引用交付     | 优先；先复用一个主供应商，针对读取缺口补互补路径，是否增加备用搜索供应商由测试决定          |
| 文件与成果     | 输入文件、受控读取/搜索/编辑、工作区、成果保存与实际下载；文档/表格可用官方 Skill 与库实现 | 优先；基础文件接口之外，选择少量真实常用文件任务验证，不能把“写了一个文件”当成成果合格      |
| 计算与代码执行 | 隔离执行、依赖环境、受限网络、超时与错误、输出取回；服务于数据处理和文档生产等多种任务     | 复用已有接口；实际目标主机通过验收后向适用员工开放                                          |
| 浏览器操作     | 页面观察、动作、状态验证、登录接管、会话隔离及资料回收                                     | 按登录/动态网页需求建设；无需为了普通公开网页查证就强制启用完整电脑操作                     |
| 记忆与持续工作 | 项目资料、跨轮延续、可检查的持久记忆；需要时再加入周期运行与通知                           | 区分已有会话/checkpoint、待接入知识业务和未来任务调度；不把三者打成一个必须一次上线的大模块 |

邮件、CRM、ERP、飞书、GitHub、行业数据等系统连接，继续优先使用插件/MCP；重要业务连接可以被官方维护，但不因此成为所有员工的默认工具。

判断某项是否进入官方基础包，可以依次检查：是否跨多个员工反复使用；失败是否会破坏大类任务的交付；是否需要稳定的模型交互方式；是否涉及平台持有的工作区、来源或成果；是否有能力持续维护和评测。低频、组织差异大的外部业务操作通常不应进入公共基础包。

## “如何可靠地使用能力”怎样沉淀

可以标准化一部分结构，但没有证据支持只制定一份万能协议就能替代每类能力的工程工作。

1. **平台共用机制**：能力可用状态、当前授权、预算、取消、结果保存、来源与引用、输出发布、工具发现、失败收束。沿用现有模块所有权，不把能力方法变成第二个执行宿主。
2. **每类官方能力的方法**：说明何时使用、输入怎么选、结果代表什么、失败后有哪些获准选择、何时可以交付。例如搜索区分摘要与网页证据；浏览器强调观察后动作、动作后核验；表格强调公式、数据范围与实际文件检查。
3. **可替换的供应商实现**：继续由 MCP、适配器、CLI 或官方插件连接服务。供应商专有错误与数据格式在对应适配处转换，通用循环消费稳定含义。
4. **版本化任务验证**：方法、工具定义、结果结构、默认预算和目标模型组合共同验收。基础包升级后回归，不能只靠 Skill 文本宣称可靠。

Goose 用 MCP instructions 提供方法，QwenPaw 将浏览器方法和 SDK 参考放进随产品维护的 Skill，Hermes 用通用网页模块连接供应商插件。这些是不同可行实现；不必为了“内化”而把全部方法永久塞进系统提示。

## 最小验证增量

建议先对“信息获取”形成一条可验收链路，再扩大基础能力范围。不要同时更换模型、供应商、循环框架和全局提示，否则无法判断收益来自哪里。

1. 固定一批真实任务与判分依据，包含项目分类、现行官方说明、多个来源冲突、长页证据位于中间或末尾、429、部分 URL 失败和服务不可用。原 OpenSpec 问题只作其中一个用例，避免围绕单题写规则。
2. 在现有授权和资源边界内，明确官方信息获取工具与方法；可以继续调用 Tavily MCP，不必先自研 HTTP 抓取或接第二家搜索。
3. 用相同模型、任务和独立起始上下文做改造前后重复对照；冻结资料测试判断证据使用，实时测试检查网络、配额与时效，分别报告。
4. 分别记录正确率、成功交付率、引用支持情况、错误/无资料时的诚实程度，以及模型次数、工具次数、总 token、缓存输入、时延。报告分布与失败样本，不只选最好的一次。
5. 若失败来自网页无法读取，补读取/浏览器路径；若来自供应商可用性，评估备用供应商；若已经取得足够证据仍继续调用，调整方法与收束；若同证据下概念仍判断错，再评估模型及提示。

建议首批使用约 20–30 个有代表性的任务、多次运行作为诊断起点；这不是统计充分性承诺，也不是生产默认阈值。实际验收标准应由产品要求和可承担成本确定。

## 本次完成与未覆盖

已完成八个产品的官方定位、源码/默认值、插件边界及本工程映射核验；保存可复现提交与直接来源。旧 CoPaw、旧 Goose 地址的迁移已追到当前官方仓库。没有把源码中存在的能力等同于默认可用、当前部署可用或可靠性实测通过。

本次仅新增研究记录与索引。未修改当前工具、员工授权、模型提示、预算、数据库、沙箱或线上配置；未执行八产品端到端对照。后续若实施能力边界增量，应先进入现有 `docs/proposals` 设计流程，再将生效规则合入现行契约。

文档已用现有 Prettier 格式化。`UV_OFFLINE=1 UV_CACHE_DIR=/private/tmp/niuma-agent-audit-54acf178/uv-cache make check-docs` 实际通过：检查 249 个文件、2641 个本地链接，错误为 0。该检查验证本地文档路径与索引，不代替外部来源内容核验或产品运行测试。

# Skill 与 MCP 接入只读核查

日期：2026-10-28。范围：本机当前源码、已安装 Python 包、现有业务库中与用户截图有关的执行轨迹及官方资料。未修改业务数据、未运行新模型请求、未执行第三方 MCP 包或部署验证；本记录不构成新功能验收。

## 版本与方法

通过本地 importlib.metadata、类签名、源码阅读及 SQLite 只读连接核查。安装版本为 Deep Agents 0.7.30、LangChain 1.4.7、FastMCP 4.1.4、langchain-openai 1.7.2。当前 langchain.mcp 属于官方 beta 接口，应按工程锁定版本验证，不能将文档新版能力默认视为工程已接线。

外部资料采用 Agent Skills 官方规范与客户端指南、LangChain Skills/MCP/Agent Evals、FastMCP transport 文档。agent-reach 的 Exa 路由返回网络协商失败，改用网页工具读取官方来源；没有以搜索摘要代替对实现的核对。

## 已确认发现

1. [Skill 表单](../../frontend/src/pages/skills/SkillEditor.tsx)及[模型](../../backend/app/skills/models.py)保存输入/输出/示例；[capture_skills](../../backend/app/agents/service.py)不捕获三者，[prepare_skills](../../backend/app/agent_runtime/skill_loading.py)只拼接 instructions 与装配参数，因此这三项未进入通用模型技能正文。
2. prepare_skills 只生成每项技能的 SKILL.md，[WorkspaceBackend](../../backend/app/agent_runtime/workspace.py)将它们投影为只读文件；没有标准包导入、多文件资产投影及技能脚本向沙箱的完整分发。
3. [MCP 客户端](../../backend/app/tools/adapters/mcp.py)构造 StreamableHttpTransport；本地 SDK 同时存在 StdioTransport，但平台未接入。官方客户端支持不能证明平台已具备隔离进程运行能力。
4. [external_tools](../../backend/app/agent_runtime/tool_calls.py)将本轮批准的描述与 schema 构造成 StructuredTool；[运行器](../../backend/app/agent_runtime/langchain.py)使用 create_agent 和官方 middleware。不是只有名称文本而没有真实函数定义。
5. 同文件 _preserve_external 将全量结果保存，但交给模型的 preview 最多 18,000 字节；无来源 read_file 许可时不提供可读取路径。当前并无自动补全长结果的分页读取流程。
6. MCP 别名与补充说明独立用于界面；[工具快照](../../backend/app/agents/tool_grants.py)沿用批准目录的原始 description，不把别名 note 当作模型指引。
7. 最终运行返回检查完整 AIMessage、非空文本和许可；[发布](../../backend/app/conversations/publication.py)核对授权与输出文件。尚未按用户目标验证外部调用是否完成，也没有逐句的来源真实性校验。

## 实际轨迹

只记录判断所需的 ID、计数及状态，不复制凭据、完整快照或用户对话内容。

| Run                                    | 记录事实                                                                             | 可得结论                                                             |
| -------------------------------------- | ------------------------------------------------------------------------------------ | -------------------------------------------------------------------- |
| `302bb4da-c081-4e57-b38a-ebaad1bf7d51` | 用户要求读取 B 站链接；快照有 5 个 Tavily 工具；tool_calls=0；最终正文声称已成功读取 | 该轮没有实际读取操作；当前发布路径未阻止无执行依据的成功声称         |
| `a61113df-1f78-4bbe-9d40-eb3d10d1f44f` | 一次 tavily_extract 成功，下一模型轮后以 skill_not_allowed 失败                      | 上游调用成功和本轮整体失败是不同事实；属于此前读取入口问题的历史证据 |
| `e414869e-a321-4c57-9f48-4b32557780c9` | 同样 5 个工具；两次模型调用、中间一次 tavily_extract 成功，Run succeeded             | 当前有成功的工具循环，不能把所有问题归为 MCP 没接上                  |

后一条仅证明该任务当时成功执行，不能证明所有页面、模型请求或结果覆盖范围都正确。此前读取入口修复的测试另见[test_tool_readers](../../backend/tests/test_tool_readers.py)；本轮没有重跑业务测试。

## 未验证与后续

未做模型 A/B、重复行为评测、标准包导入、脚本物化、stdio 进程、Mac/Linux 实际环境或新外部 MCP 调用。因此模型能力差异、历史影响和第三方接口兼容性保留为待验证因素。

改进建议见[标准包与执行可靠性增量](../proposals/skills-and-mcp/skill-package-and-runtime-integration.md)；页面建议见[能力库和装配改造](../proposals/skills-and-mcp/capability-library-and-assembly-ui.md)。

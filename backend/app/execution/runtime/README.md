# 执行运行时

runtime 统一承接后台执行控制和 Agent SDK 实现。RunWorker 调度和管理任务，RunTask 完成单次执行及资源管理，SDK 循环驱动模型与工具并返回成果。RunService、模型和原子存储仍位于 execution 根目录。

## 运行入口

[RunWorker](worker.py) 只协调队列、在途任务和服务生命周期；[RunTask](task.py) 统一执行、看护与资源生命周期。Worker 为每条记录创建 Task 并调度 execute；Task 通过统一完成回调提交执行结果，协调层处理持久化重试和接纳通知。完整目录及文件职责见[执行子系统](../README.md#完整目录与文件职责)。

## 协作与依赖

Worker 和 Task 是平台控制代码，可以按职责使用执行模型、Store、Service 与资源服务；其余 SDK 文件只通过 AgentContext 操作平台，不直接访问业务 ORM 或具体 Worker/Task。runtime 作为整体不处理 HTTP 或对话业务，模型与存储也不反向依赖 runtime。snapshot 不导入 runtime 或 SDK；共享 prompts 是不依赖业务库及 SDK 的纯文本模块；ToolResults 在 runtime 内只通过受限资源保存和读取结果，不直接读取 ORM。

完整文件职责、协作和恢复机制统一见[执行子系统](../README.md)。[Agent 入口](agent.py)负责资源生命周期、显式中间件顺序、官方 create_agent 的执行与成果交付，不再另套通用中间件构建器。摘要配置与受管调用由[模型适配](model_calls.py)的单一入口创建；摘要和普通回答必须共用本轮唯一的 RunUsage，不在中间件内部另建累计器。模型和工具请求都通过受限 AgentContext 申请平台动作。固定指令和模板统一从 execution/prompts.py 取得，启用条件和 SDK 注入继续在当前运行模块。

[工具适配](tool_calls.py)在同一处将 MCP 和知识绑定转换为 SDK 工具，再与中间件附带工具一起拒绝重名；中间件工具仍由官方工厂注册。执行检查从 request.tool 取得本次工具及输入定义，在同一文件内校验普通 JSON Schema，不再复制或回填整份工具目录。私有执行函数保留许可、缓存复用、参数校验与结果保存的顺序；注册成功不代替平台资源授权。新工具必须同时接入 SDK 工具定义和本轮授权绑定。

SDK 实现直接使用单份 AgentContext，各调用点只接收一次 context。执行控制、资源访问和长结果保存属于同一上下文，不再用 hooks、resources 或 results 别名重复传递。

[技能发现与加载](skills.py)引用共享技能目录模板，维护文件工具选择和技能正文校验，激活事实只保存于 PreparedSkills.active_skill_ids，供技能中间件与工作区共用。工具读取预算由外层工具执行入口统一申请，技能加载不再保留第二套计账开关。工作区工具及技能正文的读取和激活共用外层 ToolExecutionMiddleware 的工作区锁，技能层不另建锁，普通外部工具可并行执行。

[工具执行](tool_calls.py)按预期 Run 和官方调用 ID 核对上下文，平台在动作事务中检查授权及预算。Agent 的 context_schema 与调用时 context 传入普通 AgentRuntimeContext；工具从官方 ToolRuntime 取得同一本轮 host。知识与结果读取工具采用官方注入；动态 MCP 使用请求内的独立工具副本绑定调用，保留远端参数，许可不写入共享上下文。

[结果处理](tool_results.py)在同一 ToolResults 对象内保存原始结果、生成有界预览、分页读取并核验网页来源覆盖，不再通过跨文件函数回调核验。

streaming 把模型文字与思考合并成进展；[工作区](workspace.py)用同一份配置、技能与上下文完成路径路由、资料投影和激活技能投递，不再维护重复的内部绑定对象或传递固定编解码回调。只读资料后端、可写状态后端和内部沙箱后端在同一文件分别落实各自的权限与协议；沙箱按需申请，环境生命周期仍归 Task 与 environments。HTTP SSE 在 API，沙箱环境的申请和回收归 environments，协议连接归 MCP。

[checkpoint 模块](checkpoints.py)负责连续线程的存档字段、SQLite 保存和查询；存档文件与业务库统一使用 .db。Agent 入口通过少量内部函数区分新 Run 初始化和同 Run 恢复，正常续聊只提交增量消息，不重建整份 history。模型调用模块的 ReferenceContextMiddleware 通过官方 request.override 临时提供本轮资料，随后进入原有模型动作门；临时资料不写回用户消息。新 Run 从已成功接纳的明确存档开始；恢复原 Run 则查找属于该 Run 的最新点。摘要使用框架算法，调用仍受平台许可、次数和时限约束。详细边界见[运行契约](../../../../docs/reference/runtime.md)。

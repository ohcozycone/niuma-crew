# 执行日志查看

为对话历史和考核报告提供只读诊断弹窗。用户先凭问题、执行状态、耗时和 Token 判断关注点，再沿模型／工具路径核对输入、参数和结果；关闭后保留宿主页面。

workspace 容器由标题栏和独立滚动正文组成，不叠加普通弹窗的外层内边距；标题栏只有标题与关闭按钮，并通过全宽分隔线与正文分开。滚动正文有外侧轨道留白、内侧内容留白及稳定滚动槽位。概况用中文编号标签配等宽数字，不改变前后端标识含义。

ExecutionLogDialog 接收对话与可选 responseId，或员工、考核批次与题目关联。弹窗按身份及目标重建作用域，切换动作取消旧读取，活动执行串行刷新，关闭后停止请求。列表与报告只管理目标及 URL，不参与证据解释。旧 trace 路由只重定向到宿主并打开弹窗。

```text
execution/
├── ExecutionLogDialog.tsx       # 读取合法证据，组合路径、跨页错误定位与运行事件
├── ExecutionOverview.tsx        # 展示已知消耗、执行状态和调用数量
├── ExecutionConsumption.tsx     # 失败请求预算对照与逐步耗时、Token 和占比
├── ExecutionActionDetails.tsx   # 按实际证据选择栏目，优先完整响应并折叠思考
├── ExecutionFailures.tsx        # 将失败步骤、错误码和关联事件的源码位置放在一起
├── ExecutionToolResult.tsx      # 嵌套 JSON、知识命中列表及原始返回核对
├── executionMetrics.ts         # 已知数值、时间与占比，缺失不补零
├── executionPresentation.ts    # 统一动作名称、失败投影及错误事件判断
└── ExecutionLogDialog.test.tsx  # 验证动态栏目、思考折叠、跨页错误及读取生命周期
```

结构化对象复用 [JsonInspector](../ui/JsonInspector.tsx) 的只读树；使用正式 Dialog 的 workspace 容器与共享 PageTabs，不建立另一套配色或 Tab 状态。数据与授权仍属于后端既有执行查询和业务关联；缺失或受限不能显示为 0，不从 checkpoint 补造历史。完整内容、ID 约定及权限见[执行证据契约](../../../../docs/reference/execution-evidence.md)。

metrics 是从已有且有权查看的请求／响应提取的数值摘要，跨步骤切换后仍保留阶段消耗。思考包含在输出中；耗时可能重叠，表格不做父子求和。工具 JSON 只做展示解析，命中正文复用安全 Markdown，原始返回及下载保持原始已采集内容。

# 技能库改造方案与交互演示检查

日期：2026-10-27。对象为[官方复用复审版方案](../proposals/skills-and-mcp/unified-capability-library.md)、[拟议模块图](../proposals/skills-and-mcp/diagram/unified-capability-library.svg)及对话内模拟原型。本记录只证明方案、SDK 离线实验和原型检查；产品功能、迁移、真实账号和上游尚未按该方案实施。

## 复审结论及取代关系

初版的自定义模板语言、发布版本体系，以及模板/来源/共享定义/许可子表四表设计已撤回。当前方案直接复用官方 MCPConfig/MCPAdapter、标准 Agent Skills 目录及 SkillsMiddleware/include_tools/resolver。平台增加一个轻量 MCP 接入分组，扩展现有连接、许可和 Skill 内容管理；不再维护重复的加载或激活状态机。

技能库、八项内置展示、共享/员工专用 Key、员工原子装配需求保留。同步更新模块图、交互演示、索引、拟议术语及 C01–C32。标准包导入导出纳入目标；OAuth/stdio 的框架支持与平台尚待接线分别说明。v4 的理由改为包文件依据和工具暴露语义，旧 v2/v3 不改写。

另核对当前 StoredFile 只有 input/source/output 用途，因此方案明确增加 skill 用途与 CHECK/DTO/配额分支、Skill/Run 包资源引用和回收协调，避免把多文件支持只写成一个文件路径。

## 官方 SDK 离线实验

使用本项目 `backend/.venv/bin/python`，实际安装版本为 LangChain 1.4.7、FastMCP 4.1.4、Deep Agents 0.7.30；官方文档和已安装源码同时核对。

1. 调用官方 `MCPConfig.model_validate`，解析多服务 HTTP/stdio 示例成功。仅解析，没有创建 transport、运行进程或访问网络。
2. 实验证实官方模型保留未知字段。因此方案要求额外的平台支持检查，不能把“模型解析成功”当成已通过平台执行检查。
3. 在临时目录创建标准 SKILL.md 和 references 文件，使用官方 FilesystemBackend 与 SkillsMiddleware 的公开生命周期接口完成目录发现，正确取得 `metadata.include_tools`。
4. 向 SkillsMiddleware 传入 resolver，通过 Runtime.context 区分员工；截取官方 `wrap_model_call` 提供的工具集合。未读取时无目标工具；官方 pin 后出现目标工具；移除相关上下文后消失；另一员工解析为空；普通 tools 中的直接工具始终可见。通过官方 `disclosed_skill_tool_names` 核对披露结果。

实验使用 fake model，仅截取请求，不调用模型；resolver 返回本地工具 fixture，不搜索、不调用应用数据库、不使用真实凭证。这证明锁定版本可支持目标接入路径，不证明平台授权与存储已完成。

## 原型交互检查

使用 jsdom 执行原型实际脚本并操作 DOM，以下模拟流程通过：

1. 首屏八项内置可见、执行未就绪；没有模拟凭证拒绝账号保存。
2. 保存连接、发现、批准、员工装配四个动作分开；批准不自动授予员工，装配缺账号时整体不保存。
3. 共享连接可被两员工显式选择；专用连接只出现在目标员工选项；轮换一份连接不改另一份或偷偷回退账号。
4. 标准目录示例包含 SKILL.md/references/scripts，预览使用官方 frontmatter 和空格分隔 include_tools；缺少标准必填项拒绝，保存后保留文件清单。
5. Skill 需求没有对应工具时整份装配拒绝；映射获准工具和账号后保存。随 Skill 工具在模拟读取前隐藏、读取后出现、模拟压缩后隐藏；直接工具读取前仍可见。
6. 账号轮换后，即使已模拟读取 Skill，也不会出现该账号未就绪的工具；员工仍保留原绑定，无账号切换。
7. 官方形态多服务 MCP JSON 可预览、选择单服务填表；无认证服务无需凭证，Header 示例秘密单独配置；stdio 明确提示官方支持但平台未接线，导入不执行命令。
8. 原型没有 fetch、XHR 或 WebSocket，不接受真实 Key；本次组合流程保存的演示状态小于 16 KiB。

初次复跑旧原型脚本时，旧“只填名称与正文”的用例因新增标准 Skill 必填项失败；更新为技术名、描述和正文的实际表单后通过，新增流程全部通过。

## 浏览器与图形检查

本地临时预览使用 visualize 沙箱渲染器。在真实浏览器检查：1024 像素日间目录，标准 Skill 示例导入及 include_tools 预览，320 像素日间目录，390 像素夜间 MCP 表单和 JSON，以及 1024 像素夜间官方/平台分工说明。未见横向裁剪或控件重叠；修正分工页侧栏选中与面包屑。

SVG 已解析并转为 2 倍 PNG，人工检查节点、箭头、文字与官方/平台分区。浏览器保存目录和分工页截图作为本轮预览。完整短屏、读屏和键盘矩阵仍属于产品实施验收，不能由此次局部检查替代。

## 工程检查与限制

文档本地链接/锚点检查 `make check-docs` 通过；修改的 Markdown 和 HTML 接受 Prettier 检查。原型脚本在格式化后复跑。

本轮未修改 backend/app、frontend/src 或锁文件，未执行迁移、写业务库、保存真实 Key、发起搜索或创建沙箱。未重跑应用全量测试，历史测试数量不作为本轮通过证据。演示中的 JSON 校验、包导入、批准、装配和读取均为模拟，不是官方 Python 在浏览器运行，也未实现产品全部并发、权限、文件回收和迁移机制；这些已列入方案及实施验收。

## 2026-10-28：当前前端组件开发演示

新增仅在 Vite 开发模式注册的 `/demo/capabilities`，页面源为 [CapabilityDemoPage](../../frontend/src/pages/design-system/CapabilityDemoPage.tsx)，样例数据为 [capabilities](../../frontend/src/pages/design-system/fixtures/capabilities.ts)。本节与上方对话内原型分别验收，不将前一次结果作为当前依据。

复用当前品牌、主题、PageHeading、员工卡片、SkillCard、输入、选择、开关、标签页与对话框，员工来自已有知识专员／研发助理样板。保留 CI 专用只读仓库配置，以及工具连接保存、目录发现、批准和员工许可的分离。拟新增的员工补充说明与当前装配 JSON 独立，空技能参数规范仍拒绝非空对象。

本机 Chrome 实际操作通过：技能参数拒绝与补充说明保存、两员工配置隔离、CI 仓库保存、MCP 四步流程不自动授权、八项原生工具与未保存保护、Skill 单文件和 MCP 配置预览。记录到的业务 API 请求为零，页面 JavaScript 错误为零。日夜主题在 1440、1024、390、320px 的能力库页面均无横向溢出；检查员工页及目录截图。没有覆盖其他浏览器、真实上游和所有对话框的完整无障碍矩阵。

`make lint-frontend`、`make build`、`make check-docs` 通过。生产构建保留既有大体积 chunk 提醒；未修改依赖。本次没有实施正式能力库合并、后端聚合保存、标准 ZIP、多文件执行或真实账号接入；演示保存仅在页面内存，刷新重置。前端全量单元测试未重跑，浏览器操作用于验证本次独立演示的交互边界。

### 同日：目录快照与员工授权分离

将 MCP 连接创建、目录检查、别名维护和确认更新移至独立的能力库管理视图，员工面板只保留已确认目录和操作许可。演示状态分别保留远端、候选、快照、员工指纹；新增 [目录规则](../../frontend/src/pages/design-system/demoCatalog.ts)、[管理视图](../../frontend/src/pages/design-system/McpCatalogManager.tsx)与[模拟调用](../../frontend/src/pages/design-system/DemoInvocationDialog.tsx)。

四项规则测试通过，覆盖无关新增不影响已有工具、新工具不自动授权、中文别名不改变调用身份、定义变化必须重新授权，以及改名按删除与新增识别。本机 Chrome 完整操作通过：未确认更新不进入装配列表、确认新增后默认关闭、原许可保持；定义变化在确认前阻断目标调用、确认后旧许可仍失效、显式开启后恢复；原名改动不迁移别名或许可；删除阻断调用、丢弃候选保留快照；新连接在能力库准备，切换连接不继承授权。交互中业务 API 请求与页面 JavaScript 错误均为零。

上述检查使用明确的模拟远端，不连接真实 MCP；不证明生产后端已支持展示别名、目录差异审阅或这套交互。

最新前端静态／类型／格式检查、生产构建及文档检查通过；生产 JavaScript 中未包含开发演示路由和组件。另验证目录管理视图在日夜主题的 1440、1024、390、320px 均无横向溢出，并检查手机上的员工许可和模拟调用弹窗。原有大 chunk 构建提醒仍存在，未修改相关打包策略。

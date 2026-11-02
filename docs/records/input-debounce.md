# 输入框盘点与搜索防抖验收

日期：2026-10-31。适用范围：本次工作区前端源码；按输入事件、状态变化和实际请求依赖核查，不依据占位文字推断是否请求服务器。实施依据见[增量方案](../proposals/input-debounce.md)，现行接入规则见[输入、选择与反馈](../../frontend/src/design-system/components.md#输入选择与反馈)。

## 输入分类与处理

| 场景                                                                                | 输入与请求关系                                                                               | 本次处理与入口                                                                                                                                                                                                                |
| ----------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 员工目录，包含管理员与游客/普通成员                                                 | q 写入 URL，按条件读取服务端分页                                                             | 两个视图启用 300ms 防抖；[管理员目录](../../frontend/src/pages/agents/AgentDirectory.tsx)、[其他身份目录](../../frontend/src/pages/agents/AgentsPage.tsx)、[查询读取](../../frontend/src/pages/agents/useAgentDirectory.ts)   |
| 能力库关键词                                                                        | q 改变联合目录查询，类型和分页同属 URL                                                       | 启用 300ms 防抖；[CapabilitiesPage](../../frontend/src/pages/skills/CapabilitiesPage.tsx)                                                                                                                                     |
| 员工“添加能力”候选、独立“添加技能”候选                                              | 候选关键词改变 skillPage 请求；混合候选中的工具部分是本地过滤                                | 两个入口启用 300ms 防抖，混合候选一次提交同一关键词；[混合装配](../../frontend/src/pages/agents/AgentCapabilityAssembly.tsx)、[技能候选与分页](../../frontend/src/pages/agents/AgentSkillAssembly.tsx)                        |
| 全局员工/技能搜索                                                                   | 每次已提交查询并行读取员工与技能，原有独立 150ms 计时                                        | 改用共享输入的 300ms 防抖，移除结果组件的重复计时；[Layout](../../frontend/src/Layout.tsx)、[GlobalSearch](../../frontend/src/components/navigation/GlobalSearch.tsx)                                                         |
| 知识库名称/用途、文档标题/文件名                                                    | q 保存在 URL，但只过滤已加载集合，不触发按关键词请求                                         | 保留即时筛选；[知识库](../../frontend/src/pages/knowledge/KnowledgeLibraries.tsx)、[文档](../../frontend/src/pages/knowledge/KnowledgeLibrary.tsx)                                                                            |
| 大脑/向量连接名称与模型标识                                                         | 已加载连接的本地过滤                                                                         | 保留即时筛选；[ModelConnections](../../frontend/src/components/configuration/ModelConnections.tsx)                                                                                                                            |
| 已装配能力、独立工具候选、技能集合展示                                              | 在已有数组内筛选，不请求远程关键词查询                                                       | 保留即时筛选；[混合装配](../../frontend/src/pages/agents/AgentCapabilityAssembly.tsx)、[工具装配](../../frontend/src/components/tools/ToolAssembly.tsx)、[技能集合](../../frontend/src/components/skills/SkillCollection.tsx) |
| 知识检索问题                                                                        | 点击检索或提交表单后才更新 question 并请求                                                   | 保留明确提交；[KnowledgeSearch](../../frontend/src/pages/knowledge/KnowledgeSearch.tsx)                                                                                                                                       |
| 知识库名称、用途、切分数字规则；文档上传名称；全员规则正文                          | 创建/保存/上传才写入；修改处理规则隐藏旧预览，点击预览后才读取                               | 保留即时草稿与明确提交；[知识模块](../../frontend/src/pages/knowledge/README.md)                                                                                                                                              |
| 员工名称、职责、工作指令；技能参数；删除名称确认                                    | 修改员工草稿、预览或确认状态，保存/确认后才提交                                              | 不延迟输入与校验；[员工模块](../../frontend/src/pages/agents/README.md)                                                                                                                                                       |
| 技能名称、分类、路径、正文、支持文件和参数规范；导入名称                            | 编辑草稿；保存、导入预览/确认或同步按钮才请求                                                | 不延迟草稿；[技能模块](../../frontend/src/pages/skills/README.md)                                                                                                                                                             |
| MCP 名称、说明、URL、命令、参数、环境变量、账号名、鉴权头/密钥、工具说明与范围 JSON | 维护本地表单；保存、连接测试、目录确认或解析才请求；快捷导入选文件后读取配置属于明确文件操作 | 保留即时编辑、校验与按钮提交；[工具模块](../../frontend/src/pages/tools/README.md)、[工具装配](../../frontend/src/components/tools/ToolAssembly.tsx)                                                                          |
| 模型连接名称、模型标识、API Key                                                     | 保存或测试连接后才请求                                                                       | 保留即时编辑；[ModelConnections](../../frontend/src/components/configuration/ModelConnections.tsx)                                                                                                                            |
| 登录用户名/密码；对话正文；文件选择与选择开关                                       | 登录/发送后才提交；文件选择按原上传入口执行                                                  | 不延迟输入或文件操作；[登录](../../frontend/src/pages/signin/SigninPage.tsx)、[对话输入](../../frontend/src/pages/conversations/ConversationComposer.tsx)                                                                     |
| 设计系统、演示页和只读样板                                                          | 本地演示状态或只读输入                                                                       | 保持原行为，不作为正式接口防抖入口                                                                                                                                                                                            |

下拉选择、开关和分页属于离散操作，继续立即执行。防抖只合并尚未发送的关键词，已发出的请求仍由原资源订阅/AbortController 处理；不改变接口、缓存或业务保存边界。

## 实现与验证

共享 [useDebouncedInput](../../frontend/src/hooks/useDebouncedInput.ts) 管理即时输入、计时及清理，[SearchInput](../../frontend/src/components/common/SearchInput.tsx) 负责输入法与键盘/清空操作。普通输入和本地搜索默认不延迟。

定向验证：共享输入覆盖连续输入、即时模式、中文组词、IME 确认键、回车、按钮/键盘清空、外部值替换、最新回调、禁用和卸载；员工目录、能力库与混合候选测试在实际页面到 API 替身链路验证请求次数及最终参数，目录/能力库同时验证分页归零。

本轮实际检查：

| 检查                                                              | 结果                                                                                                                                                       |
| ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `make lint-frontend`                                              | ESLint、TypeScript、前端格式检查全部通过                                                                                                                   |
| `make test-frontend`                                              | 76 个测试文件、528 项测试通过                                                                                                                              |
| `make build`                                                      | 生产构建与静态资源压缩通过，仍有超过 500kB 的分包提示                                                                                                      |
| `UV_CACHE_DIR=/tmp/niuma-input-debounce-uv-cache make check-docs` | 289 份 Markdown、3414 个本地链接，0 错误；默认 uv 缓存目录受沙箱限制，改用临时缓存后运行同一入口通过                                                       |
| Impeccable detector                                               | 本次修改的 8 个 UI 文件无机械检查发现                                                                                                                      |
| 本机浏览器，1280×720，游客身份                                    | 员工目录输入“架构”后 URL 与单条结果正确、输入保持焦点；全局搜索打开自动聚焦，输入/回车得到匹配员工，清空立即恢复员工与技能列表，共享控件与结果区域显示正常 |

自动化使用虚拟时钟与 API 替身验证请求次数和参数，浏览器使用本机真实平台 API 验证游客目录与全局搜索。未在浏览器登录管理员核验能力库/候选弹窗，未覆盖窄屏、其他主题、其他浏览器和真实设备输入法；组词事件边界由 jsdom 测试覆盖。未连接真实第三方 MCP 或模型；本次只修改平台查询输入。

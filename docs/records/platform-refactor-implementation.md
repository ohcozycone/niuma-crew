# 平台重构实施与运行验收

日期：2026-10-27。范围：当前完整前后端、正式迁移和本地开发启动；依据[已采纳方案](../proposals/platform-refactor/README.md)。仓库当时没有 Git HEAD，全部工程为未跟踪文件；实施前保存源码快照，本记录不虚构提交号或 PR。

## 已实施范围

| 方向           | 实际结果                                                                                                                           |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| 服务归属       | 对话请求服务在 API 分组；共享准备、组合授权和发布在 conversations。配置模块保留自己的业务服务，无全局 use_cases/application        |
| Agent 与宿主   | agent_runtime 独立 SDK 循环、片段和 checkpoint；普通 AgentRequest/AgentOutput、受限 RuntimeControl，不暴露数据库、身份服务或 Store |
| 共同执行       | scheduler、coordinator、control、store 管领取、预算、动作、取消和恢复；模型开始前的授权、预算与动作记录原子保存                    |
| 正文与专业数据 | 0005 将最终正文归 Message、每次尝试建立独立助手回复、CI 过程/报告/反馈归 CiDiagnosis；统一发布事务                                 |
| 对外协议       | 按对话和 response_id 操作回复；统一 AssistantMessageView 和 conversation/response 包络；原 Run HTTP 入口移除                       |
| 前端状态       | 员工/技能目录与编辑局部请求；导航独立读取、共享配置仅失效信号；编辑器显式登记脏状态和丢弃回调；回复和对话版本分别合并              |
| 文档和学习     | 当前契约、模块说明、完整中文注释树和从页面开始的观测流程同步维护                                                                   |

保留 Conversation/Run、useConversation/useMessage 和现有普通聊天、受控 CI 算法。没有加入任务中心、计划/目标模式、通用 MCP 或第二个 Agent 引擎。保留显式创建空对话与读取元数据的既有 API，默认界面仍在第一次发送时原子创建；这两个接口本身没有职责冲突，不为追求删除数量移除。

## 数据保护与本地升级

1. 停止经过进程和工作目录核对的旧开发启动器，保存业务库、checkpoint 和模型主密钥；先在私有临时副本执行 0005 与 Alembic check。
2. 演练核对 3 个对话、21 次 Run、42 条消息，21 份已成功助手正文逐份一致；现有身份、配置、运行和动作记录保持，外键检查与 quick_check 通过，checkpoint 文件未改变。
3. 2026-10-27 对本地开发库应用 0005。再次确认原答案、数量、外键和数据库一致性；没有清空、重建示例库或重新调用模型生成历史。
4. 持久备份分别在 `~/.niuma-crew/data/backups/20261027T033533Z-platform-refactor` 和 `~/.niuma-crew/data/key-backups/20261027T033533Z-platform-refactor`，私有目录及文件权限受限。源码与原始检查输出在本机私有 `/private/tmp/niuma-platform-implementation-20261027/`，临时证据可能被系统清理。

带历史的降级必须停服并恢复成套备份，不能对新版数据强行降级。本次升级不替代其他部署环境的迁移预检。

## 验证方法与结果

| 检查         | 实际范围与结果                                                                                              |
| ------------ | ----------------------------------------------------------------------------------------------------------- |
| 后端完整测试 | 473 项通过，包括接口权限、竞争、取消、故障、迁移与真实 HTTP 子进程的崩溃恢复；假模型/假外部响应、独立临时库 |
| 前端测试     | 40 个文件、321 项通过，含保存保护、迟到读取、同步保存门闩和对话版本竞争                                     |
| 静态与类型   | Ruff、Python 格式和 mypy 9 个入口通过；前端 ESLint、TypeScript、Prettier 与生产构建通过                     |
| 开发与文档   | 启动器和文档检查工具测试 28 项通过，Markdown 路径、章节和索引检查无错误                                     |
| 迁移         | 空库和已有历史演练、损坏输入拒绝、实际开发库升级与 Alembic check 通过                                       |
| HTTP         | 8000/health、8000/ready、OpenAPI、3000 页面及 API 代理通过；38 条 OpenAPI 路径，旧 /api/runs 返回 404       |
| 浏览器       | IAB 的游客工作台显示员工目录与公开详情，返回导航正常；无 console warning/error                              |

既有大量生命周期场景通过 tests/scenario_client.py 将测试中的内部 Run 目标转换为当前回复 URL，并适配旧测试读取形状；这是测试夹具，不是生产兼容层。test_response_contract.py 使用未经适配的 TestClient 独立核对实际新协议、同一快照和旧入口移除。Agent 的内存控制测试直接运行真实 SDK，验证不依赖应用存储。

未覆盖：本次未实际调用模型供应商或 GitHub；管理员浏览器发送流程未用真实账号操作，权限与提交由隔离接口测试验证。生产构建仍有第三方 Markdown/代码高亮大分块提示；构建成功，本次不进行无关性能改造。这里记录的通过只对应本次源码和环境。

## 当前启动与观测入口

使用 make dev 启动，前端 `http://127.0.0.1:3000`，后端 `http://127.0.0.1:8000`；执行就绪检查为后端 `/ready`，Vite 前端同名路径是页面回退，不能据此判断后端就绪。日志位于 `/private/tmp/niuma-platform-implementation-20261027/dev.log`。当前浏览器是游客，提交需自行使用现有管理员账号登录，未重置账号或代造登录会话。

按[观测指南](../learning/observing-runtime.md)从目录、详情、现有对话、发送、后台动作、发布逐步深入，再读停止、重试、重启与 CI。[完整树与逐文件去向](../proposals/platform-refactor/target-tree.md)用于定位，[当前架构](../architecture/backend.md)与[Agent 边界](../architecture/agent-runtime.md)用于解释职责。

# 后端模块：谁保存数据，谁组织操作

本文保留[已采纳方案](README.md)的职责划分，当前范围已实施；现行规则见[后端架构](../../architecture/backend.md)。按实际规则、调用和数据所有权划分，不要求每个模块都套统一的多层目录。逐项证据见[全工程职责复核](responsibility-review.md)。

## 1. 先区分业务组织和运行管理

**对话 API 请求服务组织当前请求，共享回复流程留在 conversations，execution 管理运行，agent_runtime 执行内部循环。**

发送要同时检查身份、员工、对话并建立 Run，由对话 API 请求服务组织接受事务。execution 接到登记后处理排队、时限、取消和恢复，不创建聊天内容或校验专业报告。agent_runtime 接收冻结输入并返回候选，不自行查询业务配置。

execution 是模块，Run 是其中的记录；不是“Message 调用 Turn 再调用 execution”的对象流水线。

## 2. 身份、配置与资产

| 模块               | 拥有的规则与数据                                       | 边界                                               |
| ------------------ | ------------------------------------------------------ | -------------------------------------------------- |
| auth               | 用户、会话、游客、Actor、权限范围与 GitHub 登录        | 提供可信身份与本模块规则，不保存对话或调度         |
| agents             | 员工身份、岗位指令、模型绑定、方法装配、修订与就绪规则 | 提供配置事实和员工检查，完整运行准备归对话共享流程 |
| skills             | 方法正文、参数规范、启停与修订                         | 方法内容不自动授予执行许可                         |
| model_connections  | 受信协议、端点、连接检查、凭证与修订                   | 解析当次调用设置，不处理员工岗位与对话             |
| organization_rules | 全员规则正文、修订与继承                               | 提供明确版本，不主动调用模型                       |

auth 保留 actor、permissions、service、github、cli；不重新建立 authorization 模块。会话有效性判断在 service 共用，前台维护与后台只读仍区分，最终授权支持调用方 Session。

agents 不保留 execution.py，也不换名为另一个工作配置文件：

| 原逻辑                                       | 目标归属                       | 原因                                    |
| -------------------------------------------- | ------------------------------ | --------------------------------------- |
| 员工存在、启用、模型绑定、装配参数与修订检查 | agents/service.py              | 员工规则与配置读取属于同一所有者        |
| 快照结构、正文哈希、数量与字节限制           | conversations/preparation.py   | 为本次处理固定依据                      |
| 公司规则、岗位指令、连接与专业输入合成       | conversations/preparation.py   | 跨模块准备                              |
| 整体依据、身份、连接和 CI 授权组合           | conversations/authorization.py | 不向员工服务传入完整 RunSpec 或 CI 对象 |

员工检查接收调用方 Session；require_agent 仍只确认存在，不把管理读取变成工作就绪检查。装配复核保留 revision 与 created_at，以识别删除后重装。

资源数量由 service 统一生成，schemas 表达字段；CI 数量从其真实工具声明计算，不重复硬编码。摘要、详情和公开读取入口分别明确，在原 service 复用查询，不为每类读取新建文件。连接版本复核同样提供调用方 Session 入口；解密保留事务外处理。

skills 的 parameters、模型 credentials/presets 和组织规则三类文件都有实际消费者或独立规则，保留。配置服务可直接用 SQLAlchemy，不为每张表增加 repository。

## 3. conversations：交流内容与读取

| 文件       | 职责                                                            |
| ---------- | --------------------------------------------------------------- |
| models.py  | Conversation、Message、ConversationRun 及归属/顺序/活动唯一约束 |
| writes.py  | 在调用方事务创建输入、回复与关联，填正文并释放占用              |
| queries.py | 归属、历史、问题目录、预览、上下文和统一回复组合读取            |
| schemas.py | 请求、用户内容、助手视图、公开步骤和分页结构                    |
| README.md  | 模块协作、事务及测试入口                                        |

select_context 只接明确的读取限制，返回消息与截断信息，不修改 RunSpec，不识别 CI 快照。是否选聊天上下文和如何组成运行依据归 preparation。

查询种类多不等于需要拆 access/history/context/projection 等文件。公开内容读取业务记录，不读取 SDK 存档。

## 4. 对话请求服务与共享回复流程

详见[服务归属与调用关系](service-boundaries.md)。不保留全局 use_cases，不新增 application，也不为每个 router 配一个 Service。

| 文件                                  | 职责与实际调用方                                                            | 为什么放这里                                                |
| ------------------------------------- | --------------------------------------------------------------------------- | ----------------------------------------------------------- |
| api/routes/conversations/router.py    | 对话命令、查询与观察的 HTTP 参数和响应                                      | 请求接入及 200/202 属于传输                                 |
| api/routes/conversations/service.py   | ConversationRequestService：请求授权、目标与请求键、接受/停止/重试/反馈事务 | 当前命令只由对话 API 使用，已迁出后台共用部分；不增加转发壳 |
| api/routes/conversations/streaming.py | SSE 限额、身份重验、心跳与所有退出路径释放                                  | 连接生命周期有真实复杂度，断线只结束观察                    |
| conversations/preparation.py          | API 捕获当前依据，后台从冻结依据绑定具体执行函数                            | 接受与启动/恢复共用，不归 HTTP 或员工配置                   |
| conversations/authorization.py        | 接受、启动、动作、等待和发布的组合授权                                      | 各时点调用同一规则；本模块检查仍归所属服务                  |
| conversations/publication.py          | PublishRun：正文、专业报告、Run 终态和占用原子提交                          | 后台完成、恢复补发布和排队停止共同使用                      |

捕获与执行准备是 preparation 内两个函数，恢复不能重新抓提示词。CI 保存回调也在这里绑定，实际修改调用 CI service 和 store，使用一个短事务，不为一个回调新增文件。

请求服务持接受、停止与反馈事务；后台发布入口持最终事务；排队停止调用 publication.finish 使用已有 Session。不能连续调用会自行提交的公开方法来代替共同事务。

其他 auth、agents、skills、model_connections、organization_rules、ci_diagnosis 服务保留本模块规则与真实操作。简单配置路由直接调用它们，不新增 ApiService 转发类。只读对话路由继续调用查询，不绕一层空服务。

当前正式运行来源是对话，因此三个共享流程归 conversations。执行宿主仅接收注入的准备、授权和发布回调，不能反向导入本模块或 API。未来真实任务入口出现后再比较共性，不提前建立全局协调框架。

## 5. execution：处理记录、队列与控制

| 文件                     | 目标职责                                                       | 关键边界                               |
| ------------------------ | -------------------------------------------------------------- | -------------------------------------- |
| models.py                | Run、RunAction 字段和数据库约束                                | 不含 Message 或 CI 报告                |
| store.py                 | 领取、请求停止、预算、动作、结束与启动恢复的持久操作及状态规则 | 支持调用方 Session，不调用跨模块发布器 |
| admission.py             | 同键重放、容量与登记                                           | 不拼员工配置或创建对话                 |
| scheduler.py             | 队列、并发、进程锁、启动恢复调度与后台生命周期                 | 不决定模型内部步骤                     |
| coordinator.py           | 单 Run 总时限、停止与授权看护、执行函数调用和故障收束          | 不解释 SDK 图状态                      |
| control.py               | 受限控制、授权、动作、普通内容缓冲与恢复                       | 不公开 Store，不解析 SDK 片段          |
| queries.py               | 执行记录、动作和安全事实读取                                   | 不反向依赖对话响应类型                 |
| contracts.py / errors.py | 宿主执行依据、准备结果、终态意图和错误                         | 不复制 Agent 协议或公开页面 DTO        |
| config.py / README.md    | 执行预算设置、协作与维护入口                                   | 配置经应用统一解析                     |

driver 改 scheduler，hooks 改 control。SDK 解析迁走后，progress 的剩余缓冲是控制对象内部状态，合入 control；不再新增 lifecycle，已有 store 集中状态操作。API 请求服务不直接赋值取消字段。

旧 API 退出后删除 execution/schemas，公开步骤归 conversations/schemas。只有确实跨事务传递的数据才定义宿主内部类型，不机械复制旧 RunRead。

store 不再保留仅转调发布器的 complete；协调器调用注入的发布能力。恢复产生需收束事项，由调度/协调入口处理。

## 6. agent_runtime：当前一个实现，目录压平

| 文件                      | 职责                                                  |
| ------------------------- | ----------------------------------------------------- |
| contracts.py              | 普通输入、控制协议、动作/内容更新、候选输出与边界异常 |
| langchain.py              | 当前 Agent 构造、模型工具循环、继续/完成/不可恢复判断 |
| streaming.py              | SDK 片段、模型轮、工具请求与完整响应转普通内容        |
| middleware.py             | 动作前后接入受限控制、记账与结果报告                  |
| skill_loading.py          | 方法虚拟资源、读取验证与真实激活                      |
| checkpoints.py            | SDK 自有存档、可信完成与兼容读取                      |
| `__init__.py` / README.md | 无副作用包声明、协议与隔离测试说明                    |

不再套 langchain_adapter 子目录。宿主只使用 contracts，具体实现由 bootstrap 装配。运行实现可以依赖自己的协议和 llm，不导入 auth、execution、conversations、api 或业务 ORM。

ContentUpdate 等边界类型只在此定义，execution 使用其公开类型，不复制一份再转型。存档资源直接注入具体运行实现，不通过 control.store 获取。

## 7. ci_diagnosis：专业规则与实际执行

| 文件         | 职责                                                     |
| ------------ | -------------------------------------------------------- |
| models.py    | CiDiagnosis 过程、报告、版本与一次反馈                   |
| contracts.py | 目标、证据、草稿、报告、反馈校验与轻量工具声明           |
| service.py   | CiDiagnosisService：配置安装、范围、专业授权、读取与反馈 |
| executor.py  | 受控取证、模型分析、来源复查和候选报告                   |
| report.py    | 来源规范化、覆盖与引用核验、确定性正文                   |
| mcp.py       | 有界 MCP 技术访问、错误规范化与资源关闭                  |
| README.md    | 专业数据、协作与回归入口                                 |

配置事务和长网络循环有真实变化原因，保留 executor/report 拆分；不再新增 feedback/progress/queries 文件。服务类与 ORM 分别叫 CiDiagnosisService、CiDiagnosis。

CI 执行器共用运行控制，不自建队列。专业过程通过准备时注入的保存回调写入，正式报告仍由共享发布流程与正文、终态一同提交。反馈不能覆盖报告或改变处理是否成功。

## 8. 技术与入口

| 模块                             | 责任及必要调整                                                                             |
| -------------------------------- | ------------------------------------------------------------------------------------------ |
| llm                              | 单次模型设置、工厂、网络资源、普通用量与上游错误；usage 不依赖 SDK 类型                    |
| infrastructure/database          | 数据库设置、连接、事务、字段、底层错误和 ORM 注册；DatabaseConfig 与 Database 同放 session |
| api                              | HTTP 身份解析、请求保护、限流、错误、路由、必要的请求编排、SSE 和静态交付                  |
| api/routes/configuration_summary | 原配置计数入口改文件名，URL 不变；允许保留一条只读汇总 SQL，不另建计数服务                 |
| api/frontend_delivery            | 原 frontend 文件改名；静态目录由 AppConfig 显式传入                                        |
| config                           | 聚合各模块设置并解析环境与路径，不让技术层反向导入它                                       |
| bootstrap / main                 | 具体装配与关闭 / ASGI 导出；授权和准备闭包迁入对话共享流程                                 |
| migrations                       | 正式结构和数据升级，历史迁移冻结                                                           |
| tests / experiments / datasets   | 隔离验证、独立试验、教学资料，分别维护                                                     |
| scripts / Makefile               | 跨端启动、端口与检查入口                                                                   |

数据库错误识别、应用错误与 HTTP 转换继续分开。集中 ORM 注册是迁移/装配例外，业务测试直接从所属模块导入模型。

## 9. 依赖方向

1. API 命令调请求服务，简单配置调所属服务，读取调查询；CI 安装规则归专业服务。
2. 请求服务与共享流程按操作持有共同事务；写辅助不自行提交，后台不导入 API。
3. 对话读取可组合 Message 与安全执行事实；execution 不反向导入对话。
4. 执行宿主使用注入的准备、授权、执行与发布能力，不导入 CI 专业实现。
5. Agent/CI 执行器只取得受限控制，不取得 Store、认证服务或业务 Session。
6. llm/数据库等技术模块不反向依赖 AppConfig、业务用例或页面。
7. bootstrap 可导入具体实现，元数据注册可导入所属模型；这两处是明确装配例外。

模块化单体在需要原子性的地方直接调用并共享事务。没有理由为目录整齐改成异步事件，再承担重放和最终一致性。

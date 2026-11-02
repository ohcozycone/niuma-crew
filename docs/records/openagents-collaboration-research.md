# OpenAgents 工作空间与协作机制调研

| 项目     | 范围与依据                                                                                                                                                                   |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 调研日期 | 2026-10-24，Asia/Shanghai                                                                                                                                                    |
| 外部对象 | `openagents-org/openagents`，默认分支 `develop`；不包括其他同名项目                                                                                                          |
| 源码快照 | [`791fa6d86b85848953ee3a74053f69e1d3e3f0d9`](https://github.com/openagents-org/openagents/commit/791fa6d86b85848953ee3a74053f69e1d3e3f0d9)，提交时间 2026-10-24 03:32:24 UTC |
| 方法     | 阅读官网文档、仓库内契约与发布记录，追踪目标实现、调用方、配置及相关测试；对照本地当前源码与未实施方案                                                                       |
| 限制     | 未登录托管版、未安装或执行 OpenAgents、未运行其测试；没有取得线上部署版本和环境开关。代码存在、默认值、历史发布说明与生产可用性分别判断                                      |
| 本地状态 | 本次只增加调研记录及索引；建议为待讨论方向，不修改现行契约、已有方案或业务代码                                                                                               |

## 1. 结论与适用边界

OpenAgents 已经是该构想的直接对照对象：以工作空间组织人、Agent、线程和共享资源，在公开可见的讨论中分派工作、查看进度、介入并分享结果。不能将「多人 + 多 Agent + 分享」本身当作 NiumaCrew 的独有方向。[官方工作空间说明](https://openagents.org/docs/en/workspace/what-is-workspace)

最值得借鉴的是四组边界：工作空间与线程分开，内容访问与使用 Agent 分开，人类讨论与执行指令分开，授权内的实时链接与对外公开快照分开。

源码还包含线程角色指令、审查交接和完成驱动的连续分派。相关新功能开关默认关闭，仓库中 10 月 15—16 日发布记录注明未启用或仍待发布验证。由此只能确认「实现存在且有离线测试」，不能确认托管版已经默认提供这些新行为。[配置默认值](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/workspace/backend/app/config.py#L122)、[发布记录](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/workspace/docs/thread-collaboration-rollout.md)

NiumaCrew 值得验证的差异化是「围绕任务交付的协作与学习」：明确任务目标、证据、人工指导、审查发现、成果修订和验收，并将它们组织成可分享案例。这是产品建议，尚未构成已实现优势，也不证明竞品在其他路径中完全没有相关能力。

## 2. 工作空间怎样组织工作

| 层次                  | OpenAgents 的作用                                                              | 对产品理解的影响                                               |
| --------------------- | ------------------------------------------------------------------------------ | -------------------------------------------------------------- |
| 工作空间 Workspace    | 团队、连接的 Agent、线程、文件、知识、任务、工作流的容器                       | 一个空间容纳多项工作，不依靠一个无限增长的大群聊承载全部上下文 |
| 线程 Channel / Thread | 一段持久交流，关联人类参与者、Agent 参与者、可见性、负责人及协作设置           | UI 中的一个聊天窗口对应具体线程；资源归属与对话范围明确        |
| Agent 与运行设备      | Agent 可由本地或远端连接器运行，也可使用云端运行时；拥有者与运行资源有各自归属 | 平台负责组织协作，Agent 可以在不同运行环境完成动作             |
| 共享资源              | 文件、知识、浏览器及任务等通过空间和资源权限关联                               | 共享上下文需要内容管理与授权，不只是向模型拼接消息             |

当前源码将人类成员与 Agent 成员分别存储；在线程中，人和 Agent 也有各自的参与关系。统一协作界面不要求它们具备相同执行权限或生命周期。[对象模型](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/workspace/backend/app/models.py#L94)

官网的「Agent 能读历史」需要按具体上下文机制理解。已核对的本地连接器会取得最近消息候选，再加入有上限的聊天摘录：最多 30 条、单条约 2,000 字符、合计约 16,000 字符；需要更多材料时再使用历史工具。完整持久历史与某轮实际模型上下文是两个概念。[连接器历史整理](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/packages/agent-connector/src/adapters/thread-history.js)、[实际接入位置](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/packages/agent-connector/src/adapters/base.js#L1428)

## 3. 多人协作怎样处理身份与权限

### 3.1 空间成员与资源范围

账号模式中，用户通过成员关系与角色加入工作空间；资源再按拥有者、参与者和授权判断访问。已识别用户创建的新线程默认私有，`public` 表示工作空间内可读，与面向互联网的公开分享链接不同。系统创建和兼容路径仍有不同默认值，不能概括为所有新线程均私有。[线程创建入口](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/workspace/backend/app/mods/workspace_mod.py#L451)

资源许可区分 `read`、`act`、`share`。私有线程的管理员入口仅提供元数据，管理员仍有强制转移拥有者等治理能力，因此不能将它描述为管理员在任何条件下都无法接触内容。[权限实现](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/workspace/backend/app/services/access_model.py)、[线程治理入口](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/workspace/backend/app/routers/thread_access.py#L225)

### 3.2 能看到线程与能使用其中的 Agent 分开

线程参与不应自动使一个人获得另一个人的全部 Agent 执行资格。当前界面提供「在本线程共享我的 Agent」的关闭、允许、需批准选项；源码另有线程限定的授权请求、撤销和每次使用时的复核。线程限定授权的新建功能受默认关闭的开关控制。[线程设置界面](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/workspace/frontend/components/chat/thread-settings.tsx)、[授权发布边界](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/workspace/docs/thread-collaboration-rollout.md)

新线程继承旧会话时，后端会检查私有来源，避免把拥有者的私人上下文直接带入新共享请求。连接器的跨 Agent 连续交接还保留原始请求者身份，以继续应用共享使用限制；线程职责单独注入，不覆盖员工全局描述。[私有上下文继承检查](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/workspace/backend/app/mods/workspace_mod.py#L583)、[线程职责存取](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/workspace/backend/app/services/thread_collaboration.py)、[连接器请求者处理](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/packages/agent-connector/src/adapters/base.js#L1531)

### 3.3 不宜照搬的兼容边界

自托管文档提供零外部依赖的空间共享 token 模式；它与实名成员模式的身份和权限粒度不同。当前源码还保留没有具体 Agent 身份的机器调用兼容分支。资源规则中，Agent 可继承其拥有者的访问范围；「每次读取都与当前请求者权限取交集」在相应权限契约中仍列为后续范围。因此这些实现不能被解释为任意共享 Agent 都已获得严格的最小权限保证。[认证文档](https://openagents.org/docs/en/self-hosting/authentication)、[访问检查](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/workspace/backend/app/access.py#L322)、[权限契约及后续范围](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/workspace/docs/permission-model-v1.md)

NiumaCrew 已有登录账号，建议从账号与空间成员授权接入，同时限制 Agent 可用资源；不引入共享 token 来替代用户身份。

## 4. 多人发言怎样变成多 Agent 工作

### 4.1 先决定谁应该响应

一条消息进入服务端后，会经过身份检查、空间协作处理和持久化。协作处理计算目标 Agent，连接器按事件领取消息并回传回复；云端 Agent 有对应触发路径。此次核对的线程协作主路径是服务端事件分派与运行适配，不能仅凭 Agent 互相发言就认定采用了某个 A2A 协议。

已核对的目标选择规则包括：

1. 明确 `@Agent` 是用户指定的接收者，尽量不再让模型猜测；可同时指定多个 Agent。
2. 被动响应线程要求明确寻址；主动响应线程可以在现有可用参与者中由路由模型选择。
3. 只与其他人交流的消息、无人应答的消息，保留为讨论，不广播唤醒全部 Agent。
4. 路由不确定或不可用时，显示供请求者选择的卡片。
5. 指定指挥人后，其他人未 `@Agent` 的发言作为资料信息；明确 `@Agent` 仍可形成请求，但被标记为非指挥人意见。该机制不等于指挥人独占所有发令权。

规则见[会话目标选择](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/workspace/backend/app/mods/workspace_mod.py#L1264)、[指挥人规则](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/workspace/backend/app/mods/workspace_mod.py#L1969)。连接器按 Agent 和线程排队，避免同一员工在同一线程中同时处理多条请求；其他线程可以独立推进。这种隔离也不自动意味着共享工作目录中的文件修改完全互不影响。[消息队列消费者](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/packages/agent-connector/src/adapters/base.js#L1428)

### 4.2 一名 Agent 完成后，如何交给另一名

新完成驱动路径由本轮最终回复触发。服务端检查回复具有完成标记、关联到确实指派给该员工的请求，并属于当前尚未被替代的工作链。状态消息、部分失败、无法关联的后台回复不会自动启动下一名员工。

通过检查后，调度模型根据原始请求、近期完成结果、线程职责和此前交接决定：继续交给一个具体员工并附具体工作、请人选择、等待输入，或结束。它不是仅凭回复里出现另一个 Agent 名字就无限触发。源码有重复结果去重、初始并行分工完成等待、停止和权限复核；交接默认上限为 6 次，可配置范围为 1—20。超限转为人工选择，不宣称自动达成共识。[完成驱动实现](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/workspace/backend/app/services/completion_routing.py)

相关测试包含「实现 → 审查 → 修改 → 复核 → 停止」、重复结果、停止、权限变化和并行完成场景，但路由决定由替身提供。它们能说明预期调度边界，不能证明真实模型会正确判断工作质量，也不能代替本次没有执行的测试。[回归测试源码](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/workspace/backend/tests/test_completion_routing.py)

一个需要借鉴时再细化的行为是：代码按最新人类聊天识别当前请求，新人类消息可使旧交接链失效。多人随时补充资料时，应明确哪些发言只是信息，哪些正式改变任务目标；不能直接采用「新消息替代旧请求」覆盖全部团队场景。

### 4.3 固定审查流程如何表达

工作流采用步骤、Agent 或人类负责人、可选条件跳转及循环上限。启动时冻结模板，修改模板不改写执行中的步骤。可以表达「A 产出，B 审查，有问题返回 A，再由人验收」。[工作流模型](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/workspace/backend/app/models.py#L918)

当前步骤是否完成和条件是否成立由模型判断；超过循环次数会停在需处理状态。具体实现中，条件判断不可用时按条件未命中顺序推进，因此涉及关键验收的流程应专门设计判断失败的处置。存在回路只证明可组织迭代，不证明两名 Agent 最终一致、结论正确或已被人接受。[步骤判断与跳转](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/workspace/backend/app/services/workflow.py#L287)

## 5. 过程观察与分享到底包含什么

| 使用方式     | 实际机制                                                     | 可见范围                                                       |
| ------------ | ------------------------------------------------------------ | -------------------------------------------------------------- |
| 空间内跟进   | 保存事件、状态与消息，运行适配器回传进度和结果               | 有权限的成员观察同一工作；实际记录完整性取决于适配器提供的事件 |
| 实时线程链接 | 使用线程 ID 定位，打开时重新检查内容权限                     | 链接本身不扩大授权，可查看后续变化                             |
| 对外公开快照 | 创建时从线程事件筛选 `chat` 消息，复制为独立快照并生成 token | 无需登录读取固定副本；不跟随后续对话更新                       |

分享弹窗将实时线程链接与公开快照列为两个选项。[分享界面](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/workspace/frontend/components/chat/share-dialog.tsx)、[实时链接的权限检查](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/workspace/backend/app/routers/thread_access.py#L462)

快照保存的核心字段是发言者、人员或 Agent 类型、正文与时间。它排除非聊天消息，包括状态、思考、审批和制品事件；聊天正文中已有的链接可以保留，但不构成附件完整打包或目标资源自动授权。查看端直接读取快照数据，撤销时软删除并使后续读取返回不存在。所查快照接口与模型没有到期字段、消息范围选择、自动脱敏或结构化工具证据导出。[快照创建、读取与撤销](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/workspace/backend/app/routers/shares.py)、[快照模型](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/workspace/backend/app/models.py#L1182)

这些结论限定于已核对的会话快照链路，不能扩大成全产品没有其他制品分享或审计能力。对本项目而言，聊天快照可以作为轻量首版；用户希望分享交付全过程时，还应补充目标、依据、审查与修订的关联。

## 6. 与 NiumaCrew 的对应关系

| 主题       | 本项目当前事实                                                                         | 可借鉴增量                                                                                         |
| ---------- | -------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| 私人对话   | Conversation 绑定单个 Agent 与 owner；管理员拥有跨 owner 访问能力；member 尚无执行权限 | 明确按用户私聊边界、空间成员范围和管理权限，不把 owner 字段当作完整隔离                            |
| 工作空间   | 现有「员工工作页」为聚合视图草案，没有团队空间成员主体                                 | 新空间承载人员、Agent 与共享工作；员工工作页继续围绕单员工，不混用术语                             |
| 多人交流   | 当前输入与回复围绕一名员工组织                                                         | 共享讨论增加真实发言者、参与关系和指令语义，保持私人历史独立                                       |
| 执行       | 有快照、幂等、预算、真实步骤、取消、checkpoint 和 SSE；同会话单活跃 Run                | 复用单员工执行内核，在外层增加协作任务、角色和交接；不靠把 Agent 轮流塞进一个 SDK 会话实现多人协作 |
| 后台授权   | Run 与发起登录会话关联；会话失效会取消                                                 | 明确谁发起、谁授权、谁付费、谁能停止、发起人退出后是否继续，再定义空间任务执行授权                 |
| 成果与验收 | Task、Deliverable、Review 尚是未实施草案                                               | 延续成果版本与人工验收分离的设计，增加团队协作范围及审查关联                                       |
| 过程分享   | 暂无对应公开分享功能                                                                   | 区分实时协作链接和固定分享副本；对外输出经过选择的安全过程投影                                     |

本地依据：[当前架构](../architecture/overview.md)、[对话契约](../reference/conversations.md)、[运行契约](../reference/runtime.md)、[Conversation 模型](../../backend/app/conversations/models.py)、[权限实现](../../backend/app/auth/permissions.py)、[Run 与步骤](../../backend/app/execution/models.py)、[员工工作页草案](../proposals/agent-workspace/README.md)、[任务与成果草案](../proposals/agent-workspace/tasks.md)。

这些基础能减少重复建设，但没有自动解决多方发言排序、不同员工上下文、任务交接和共享权限。当前同会话单活跃 Run 的约束，扩展到并行协作时也需按任务和员工执行重新设计，不能机械放开唯一约束。

## 7. 候选差异化及验证方式

### 7.1 可学习的交付案例

将分享组织成「最初任务 → 采用材料 → 关键执行 → 审查发现 → 人工指导 → 修订成果 → 最终验收」。默认先读目标与成果，按需展开关键转折，并能定位到对应记录。不暴露模型隐藏思考，也不把模型自述当成工具操作证据。

验证：未参与任务的人能否在短时间内说清目标、关键修改原因、仍有何限制；与只读聊天快照比较理解时间和答题正确率。

### 7.2 能核对的审查与验收

审查意见绑定具体成果版本和证据，区分待处理、已修复、复核通过及保留分歧。Agent 完成、审查者同意与人类接受成果分别记录。OpenAgents 已核对的看板路径会用模型分类近期回复推进 `done`；这为本项目设计更明确的验收契约提供了具体对照，而非全产品缺少人工审查的结论。[看板分类实现](https://github.com/openagents-org/openagents/blob/791fa6d86b85848953ee3a74053f69e1d3e3f0d9/workspace/backend/app/mods/workspace_mod.py#L1717)

验证：与单员工基线比较有效问题发现率、修复后通过率、错误共识率、人工复核时间及额外模型成本。记录未达成共识的合法终态，不以更多轮次作为成功指标。

### 7.3 能看见指导如何影响成果

人可以讨论、补材料、提出修改或正式调整要求；系统保留哪些指导被采用、影响了哪个成果版本。把当前任务中的反馈沉淀为共享方法时，由有权维护者确认范围、来源与版本。

验证：其他人能否理解某条人工意见为什么被采用；方法能否在新任务中提高交付质量，而非仅积累聊天数量。该方向仍需观察真实团队是否愿意整理、复用和维护这些经验。

### 7.4 低门槛的岗位协作

以本项目已有的员工职责与能力配置为基础，提供少量有明确完成要求的协作方式，例如「起草—审查—修订—验收」。先减少用户组织工作和判断完成的负担，再考虑大量异构运行器、设备接入和通用编排配置。

验证：首次使用者能否完成一次真实交办；创建流程所需时间、成果采用率和复核负担是否改善。岗位名称与角色数量本身不作为差异化证据。

## 8. 建议实施顺序与首个验证场景

以下仅为建议，不修改已有阶段方案。

1. 明确私人对话、空间和线程的内容边界，开放合适的普通成员执行范围；保留员工配置的独立维护路径。
2. 完成多人围绕一个任务与一名员工协作、观察和验收，再提供只读过程分享。此阶段即可验证共同指导和学习的核心价值。
3. 增加一名审查员工，绑定发现、修订、复核及交接上限。先验证双员工比单员工更有用，再增加更多参与者。
4. 依据真实需求扩展协作模板与外部 Agent 接入；A2A 等协议选型随外部互通需求推进。

首个场景可沿用现有任务草案中的部署答复：

1. 提出者上传或粘贴获准材料，交办部署答复草稿，并写清完成要求。
2. 员工 A 形成 D1，员工 B 针对材料与要求提出具体发现。
3. 领域成员补充信息；系统明确这次是补充依据还是修改目标。
4. A 修订为 D2，B 复核；达不到标准则保留分歧并请负责人决定。
5. 负责人接受 D2，分享选择后的案例副本；旁观者能查看指导、审查和修订依据。

验收应同时覆盖成员移除后的读取拒绝、私人内容不被带入、重复完成不重复交接、停止后迟到回复不重启、普通讨论不意外改派、分享撤销及成果版本定位。执行中的权限变化和资源状态仍由服务端强制检查。

## 9. 本次验证与未覆盖项

本次核对了公开源码的写入、分派、读取和分享链路，并阅读相关调度、线程职责、工作流及连接器测试。没有运行这些测试，没有调用真实模型，也没有证明托管版的部署状态、协作质量、负载表现或全部安全边界。

本地验证：`UV_CACHE_DIR=/tmp/niuma-crew-uv-cache UV_NO_SYNC=1 make check-docs` 通过，文档路径、章节与索引检查 `errors=0`；两份修改文档按前端现有 Prettier 配置格式化并检查通过。缓存路径改到临时目录以适应本次沙箱，未安装依赖。

下一步若转入产品设计，应另写工作空间增量方案，明确与现有 owner 私有任务草案的衔接，再进入实现。

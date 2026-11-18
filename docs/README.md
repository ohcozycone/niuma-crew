# 文档索引

| 阅读任务     | 正文                                                                                                                                                                                                                                    |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 理解建设目标 | [平台定位](product/README.md)、[组织资产](product/组织资产.md)、[员工设计](product/员工设计.md)                                                                                                                                         |
| 理解整体协作 | [系统架构](architecture/overview.md)、[对话流程](architecture/对话流程.md)、[后端设计](architecture/backend.md)、[前端设计](architecture/frontend.md)                                                                                   |
| 深入技术机制 | [工具装配](architecture/工具装配.md)、[智能体执行](architecture/执行机制.md)、[知识检索](architecture/知识检索.md)、[能力评估](architecture/能力评估.md)                                                                                |
| 使用指南     | [使用流程](product/workflows.md)、[功能范围](product/功能范围.md)、[环境设置](engineering/开发入门.md#环境设置)、[配置与备份](guides/backend-operations.md)、[工具与环境](guides/agent-tools.md)、[问题排查](guides/troubleshooting.md) |
| 修改代码     | [开发入门](engineering/开发入门.md)、[共享工程约定](engineering/shared.md)、[后端约定](engineering/backend.md)、[前端约定](engineering/frontend.md)                                                                                     |
| 修改界面     | [设计系统](design/README.md)，按需查阅颜色、组件和布局                                                                                                                                                                                  |

## 主题关系

```text
平台介绍
├── 平台定位：个人积累为什么需要共同沉淀
├── 组织资产：共享、维护与经验发布
└── 员工设计：任务闭环与最小能力
技术解析
├── 开发参考：技术栈、目录结构、环境设置与设计系统
├── 架构设计：系统架构、对话流程、后端设计、前端设计
├── 运行机制：工具装配、智能体执行
└── 检索与评估：知识检索、能力评估
使用指南
├── 操作：员工、资料、对话与考核
├── 部署：启动、配置、备份与环境
└── 排错：现象、证据与恢复
```

主题页中的“建设中”说明尚未完成的方向，不代表已提供操作入口；实验结果只覆盖注明的样本与环境。

## 行为规则

| 问题                     | 唯一详细位置                                      |
| ------------------------ | ------------------------------------------------- |
| 身份、会话与读取范围     | [身份规则](reference/auth.md)                     |
| 员工、技能、装配与修订   | [配置规则](reference/configuration.md)            |
| 模型与凭据变更           | [模型连接](reference/model-connections.md)        |
| 连接、工具目录与许可     | [工具规则](reference/mcp.md)                      |
| 知识入库、检索与证据     | [知识规则](reference/knowledge.md)                |
| 对话提交、历史与正式回复 | [对话规则](reference/conversations.md)            |
| 动作、预算、取消与恢复   | [执行规则](reference/runtime.md)                  |
| 文件、配额与代码环境     | [文件与环境](reference/files-and-environments.md) |
| 专项考核与报告           | [考核规则](reference/employee-evaluations.md)     |
| 错误与恢复语义           | [失败规则](reference/failures.md)                 |

## 实现说明

正文解释机制与取舍，源码旁说明维护内部协调，不要求每个目录都有说明文件。

| 范围               | 实现入口                                                                                                                                                      |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 技能发布与工具接入 | [技能](../backend/app/resources/skills/README.md)、[工具](../backend/app/resources/mcp/README.md)                                                             |
| 检索与模型         | [知识](../backend/app/resources/knowledge/README.md)、[模型客户端](../backend/app/infrastructure/llm/README.md)                                               |
| 执行与资源         | [执行](../backend/app/runtime/execution/README.md)、[文件](../backend/app/resources/files/README.md)、[环境](../backend/app/resources/environments/README.md) |
| 事务与前端数据     | [基础设施](../backend/app/infrastructure/README.md)、[共享数据](../frontend/src/state/README.md)、[对话交互](../frontend/src/pages/conversations/README.md)   |

## 方案、记录与学习

[方案索引](proposals/README.md)维护有效未实施增量及状态。组织资产闭环见[协作复盘方案](proposals/对话协作复盘与经验沉淀.md)，持续任务与记忆仍按各自方案讨论，不作为当前架构事实。

[后端模块边界迁移](records/后端模块边界迁移验收.md)、[组织资源迁移](records/组织员工资产改造验收.md)、[工具发现实验](records/工具按需发现验收.md)、[运行控制审查](records/data/Agent运行控制价值审查.json)和[质量验证](records/关键故障与质量验证.md)保留限定时点的证据，不能代替当前验证。

[工具结果交付改造验收](records/工具结果交付改造验收.md)记录官方移存接线、旧逻辑清理和真实模型对照，工具发现保持不变。

[回答证据边界复验](records/回答证据边界复验.md)记录后续两版说明未通过验收并撤回的依据，不能当作整体质量已通过。

[学习路线](learning/roadmap.md)管理练习与掌握判据，[运行观察](learning/observing-runtime.md)提供实际请求的观察方法。文档职责及更新关系见[文档规范](documentation.md)，站点发布与构建见[站点说明](../docs-site/README.md)。

[提交历史重建验收](records/提交历史重建验收.md)记录隔离分支的实际提交顺序、树一致性和离线回归结果；通过验证的重建主线已发布至 main，原始历史与未提交内容保留，发布与恢复入口见验收正文。

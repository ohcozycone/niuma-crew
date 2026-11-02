# API 请求服务与共享流程归属修订记录

2026-10-27。适用范围为[平台重构方案](../proposals/platform-refactor/README.md)的服务位置、调用关系、目标树与图示统一修订。设计仍为推荐草案，**业务代码、API、测试、构建配置和数据库未改**。

## 1. 依据与范围

本轮工作区开始时有 569 个工程文件，其中 432 个非 docs 文件建立了内容哈希。原始目录复核基线继续保留 567 个路径，已新增的报告和记录由目标新增清单管理，不改写历史记录当时的数量。

核对入口包括当前 ConversationCommands 的 API 调用、bootstrap 装配、AuthService 的 CLI/后台使用、模型连接的运行解析、员工及共享方法公开/管理读取、CI 的捕获/执行/反馈，以及 Run 登记的正式来源。当前 app 中 RunAdmission.accept 的唯一正式来源为 conversation；没有为测试构造的假来源建设通用发布框架。

沿用上一轮固定源码调研：

- LobeHub：canary，`ab57dc331efa16903acc1e97d60319d2643a8e8f`。
- StaffDeck：main，`fcc28c003ef188e6d0a11596d44fdfb3723b275b`。

开源证据与适用范围已写入[服务专题](../proposals/platform-refactor/service-boundaries.md#8-开源调研采用什么拒绝什么)，未额外运行远程项目、测试或外部模型。

## 2. 推荐设计变化

1. 对话请求命令迁到 api/routes/conversations/service.py，拟名 ConversationRequestService；router 与 SSE streaming 就近组织。
2. preparation、authorization、publication 归 conversations，供请求、后台启动、动作检查、恢复、完成和排队停止复用。
3. 撤销全局 use_cases 目标，不新增 application；其他模块服务留所属模块，不给每个 API 增加转发服务。
4. 请求服务与共享流程按操作持有事务；共同协作者使用当前 Session，不通过多个自行提交的方法拼接原子操作。
5. 运行宿主通过注入回调准备、授权和发布；后台及 Agent 不反向导入 API。
6. 保留 Conversation/Message/Run、单宿主 SQLite、CI 专业执行、原子交付和前端契约。没有因调研引入任务框架、Node 进程池或通用插件机制。

这些结论取代讨论中的“全部集中 application”“全部放业务 service”“全部迁 API”三个过度统一的方向。目标树只包含本轮选定结构，不同时保留几套可选目录。

## 3. 修改位置

- 新增[服务归属与调用](../proposals/platform-refactor/service-boundaries.md)，说明每个服务、五条调用路径、事务矩阵、排除项与验收。
- 同步总方案、后端模块、API、运行边界、端到端流程、迁移步骤、取舍、前端与职责复核专题。
- 更新目标树生成器和逐文件映射；保留当前源码路径作为来源，目标路径明确为尚未移动。
- 更新两张主图和四张分层图的生成源与输出，图中职责分区不再暗示一个全局 use_cases 目录。
- 更新方案与记录索引。现行 architecture/reference 和源码旁说明在实际实施后再改。

## 4. 实际检查

- 修改范围：432 个非 docs 文件哈希全部一致；新增文件仅为服务专题和本记录，当前文件无删除。
- 清单覆盖：原始 567 个基线文件各有一行映射，无重复或遗漏；全部当前路径均在基线或新增清单中，目标共 589 个文件。
- 结构检查：目标中没有 use_cases/application；API 对话分组与三项共享流程均在正确位置；每个树节点均有中文职责和设计原因。
- 生成工具：三份 Python 生成源通过 Ruff 检查和格式检查；方案和索引通过 Prettier。
- 文档检查：153 个文档、1619 个本地引用、67 个归档引用，错误 0。
- 图示：重新生成六张 SVG，XML 均有效；五张受影响图转为 PNG，检查标题、文本、箭头和边界，未发现遮挡或溢出。
- 无业务代码变更，因此未运行业务测试、前后端构建或数据库迁移。

## 5. 未覆盖项

没有执行业务测试、前后端构建、数据库迁移、真实模型调用或部署。文档和图示检查不能证明拟议业务代码已实现。

本轮只证明方案、映射与图文一致，并核对非文档文件没有被本轮改动。实施前仍需依照[服务专题的验收项](../proposals/platform-refactor/service-boundaries.md#9-实施与验收)验证权限、事务、取消、反馈与恢复行为；已有测试历史结果不能代替实施后验证。

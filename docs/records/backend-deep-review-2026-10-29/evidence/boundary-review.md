# HTTP、工具、文件、沙箱与数据库独立评审

本组阅读发生于北京时间 2026-10-29 至 2026-10-30。范围是 `backend/app/api`、`tools`、`files`、`sandboxes`、`infrastructure` 全部 57 个 Python 文件，共 5,285 行。逐文件职责、导入和 SHA-256 在 [coverage](boundary-coverage.json)；本记录是当前工作区的只读分析，不修改业务实现。

先按项目契约建立调用和所有权，再依据安装的 Python 结构/设计/代码规范、架构和 audit-context-building 技能分析。没有把缺 Repository、缺 `__all__` 或文件超过某个行数作为缺陷。五个复杂函数的逐块上下文在 `../context/functions/boundary-*.md`；这些上下文只记录实现、假设和问题，下面才给出评审判断。

## 结论及已复现问题

五个模块的主边界基本成立：HTTP 负责传输与入口许可，工具模块拥有账号和协议调用，文件模块管理字节但不反查对话权限，沙箱模块负责环境债务，数据库只统一机制。优先修复三项可以触发的问题；无需先把工程重写成更多层。

### B1 / P2：配额拒绝后仍留下完整文件，账号配额约束不到真实磁盘占用

`files/service.py:L65-L76` 先把临时文件同步并重命名到 UUID 最终键；随后 `L77-L93` 才检查用户与 Run 配额。超额抛错时，`L107-L109` 只尝试删除已不存在的旧临时路径，最终 UUID 文件保留。孤立清理到 `L185-L192` 才在超过 retention 后删除，默认是一天（`files/config.py:L15`）。

**触发：** 账号达到限额后继续上传合法大小文件。HTTP 已经接收并调用 save，最终返回拒绝，但每次都增加磁盘字节。`api/routes/files.py:L24-L30` 的每分钟20次与单文件10MiB只限制增长速率；不会让已拒绝文件计入用户配额。按默认值，单个账号每分钟仍可遗留约200MiB，直至全局余量保护触发或保留期清理。这里的数值是代码上限推算，没有进行大文件或磁盘耗尽实验。

**隔离复现：** 将用户配额设成1字节；成功保存1字节后连续3次上传2字节，均收到 `file_quota_exceeded`。数据库仍是1条/1字节，目录却有4个最终文件/7字节。使用真实 Alembic head 的临时库，没有触碰开发数据库。

**建议：** 区分明确回滚与提交结果未知。明确配额拒绝可立即回收本次 UUID 字节；对 commit 结果未知或崩溃保留现有孤立回收补偿。继续保留写锁内配额检查，不能把校验简单搬到无锁读取之前，否则会产生并发超额。添加“连续拒绝后的真实磁盘占用不增长”测试，同时覆盖 Run 配额。

### B2 / P2：普通成员可以读取全平台沙箱运行元数据

`api/routes/tools.py:L22` 的 `admin_read` 实际仅检查 `tools:read`；`auth/permissions.py:L36-L45` 已把该能力授给 member。`GET /api/sandbox-status` 在 `routes/tools.py:L78-L81` 复用这一依赖，随后不接收 Actor，也没有用户范围过滤。`sandboxes/service.py:L76-L93` 返回全局未销毁资源，含资源 ID、Run ID、状态、过期时间、重试次数和错误。

**触发：** 任意已登录 member 调用该接口即可看到其他用户的资源。资源ID并不直接赋予对话读取权限，也没有发现管理密钥泄露；问题是全局运维信息越过了现行管理员边界。`docs/reference/agent-tools.md:L75` 和 `docs/guides/agent-tools.md:L106` 都明确写管理员读取。

**隔离复现：** 管理员创建 Run 并留下 unknown 资源；换成通过 GitHub 登录生成的 member，接口返回200且包含管理员的 Run ID。

**建议：** 为沙箱运维状态使用明确管理能力，不要回收 member 管理本人 MCP 所需的 `tools:read`。补 member=403、admin=200 测试。如果产品实际希望成员看到就绪性，可以另返回不带资源列表的公共投影，并先明确新契约。

### B3 / P2：个人连接页面在后端静态交付时无法直接打开或刷新

前端 `frontend/src/router.tsx:L139-L140` 注册 `/agents/:id/connections`；个人 MCP 绑定入口也使用该路径。后端 `api/frontend_delivery.py:L15-L19` 的 PAGE 白名单只允许 `/agents`、`/agents/new` 和 `/agents/{id}`，没有 connections 子路径。`FrontendFiles.get_response:L53-L54` 因此不回退 index.html，而是按静态文件查找。

**触发：** 使用后端统一交付前端时，刷新该页面、从外部地址或新标签直接打开个人工具连接页得到404。在独立 Vite 开发服务内通过 React 跳转可以成功，所以普通页面组件测试掩盖了这个部署差异。

**隔离复现：** 临时 index.html + 真实 `mount_frontend`；`/agents/review-agent` 返回200，`/agents/review-agent/connections` 返回404。现有 `test_frontend.py:L27-L47` 的路由矩阵未覆盖这条前端路由。

**建议：** 补齐精确业务路径，并让静态交付测试覆盖前端可直接访问的全部生产路由。继续保持未知静态文件/API错误不回退HTML，不能改成所有路径一律 index.html。

## 全局协作与依赖

1. **浏览器写操作：** `BrowserSecurityMiddleware` → Actor 解析/能力依赖 → 所属服务 → `Database.transaction`。Origin/体积/媒体类型只保护传输，资源所有权还需服务校验；公开DTO用字段白名单投影，而非前端隐藏秘密。
2. **对话提交：** `api/routes/conversations/service.py:submit` 在同一个 SQLite writer 事务里核对会话范围、幂等、容量、员工/附件、快照、消息与 Run；模型不在这个事务里运行。router只设置接受/重放状态和非秘密日志。
3. **工具执行：** Agent宿主先记账 → `ToolService.call` 取当前连接 → MCP握手和重新列目录 → 定义/说明摘要比较 → guard再核权 → 外部调用 → 结果脱敏。HTTP适配器不写 RunStore，避免协议层暗中拥有执行状态。
4. **文件发布：** FileService先保存字节/元数据 → conversation持有消息关联 → ConversationFiles核对具体对话范围后下载。文件服务的 `read(id)` 是受信内部能力，不是匿名下载API。
5. **沙箱：** `RunSandbox` 按Run懒申请 → DB保存requested意图 → 事务外创建 → ready/初始化 → 产物先可靠保存 → release和定时补偿。unknown资源继续占容量，避免超时后盲目重建。
6. **数据库：** 各领域模型依赖Base/fields；`database/models.py` 反向导入只为迁移元数据注册，不等于基础设施拥有全部业务模型。事务工具要求先预占writer后进行业务读取；这在真实SQLite测试中有证据。

## 逐模块与内部文件组织

### API

- `dependencies`、`security`、`errors`、`rate_limit`、`frontend_delivery` 的变化原因不同，分文件有实际价值；`router` 只接线，未发现反向导入 bootstrap/main。
- 各资源 router 参数/响应/能力检查都紧邻入口。`auth.py` 对Cookie/OAuth跳转做协议适配，`files.py` 在异步流中读取有界上传后转线程保存，同步CRUD让FastAPI工作线程承接同步Session。
- 对话组内 `router/service/streaming` 各有清楚生命周期：请求服务拥有一次接受/取消事务，streaming仅观察已持久化快照，不因断线取消Run。SSE在头已发送后用access.revoked说明失效，并在生成器与响应双重finally释放名额。
- `configuration_summary.py` 和 `tools.py:capabilities` 直接写跨模块查询，这是明确的读聚合；不必为了形式统一给每条SQL加Repository。但后者同时解析Skill公开协议名、做联合分页并认识Skill ORM，已比其他薄路由更重。能力库继续演进时可移到有命名职责的只读查询对象，路由保留筛选与响应。
- `admin_read/admin_write` 名称已与真实权限脱节，B2就是这种命名误导的实际后果。改为能力含义命名，同时为运维能力单列依赖。
- `agents.py` 有些作者检查在单独请求事务，随后调用服务；不是所有服务天然有Actor约束。新增CLI/后台入口仍需核对这个授权位置，不可假定调用service就自动安全。此项为维护边界，未据此宣称现有作者可变竞态。

### tools

- `models` 区分服务定义与账号身份，`access` 判所有者，`schemas` 接输入/投影，`contracts` 是普通类型与摘要；`catalogs` 把别名和候选丢弃从真实操作授权中隔开，归类合理。
- `definitions.py` 拥有固定接入定义、去重与惰性导入。HTTP允许列表、stdio固定argv/env字段在登记时校验，预览不会安装包或启动程序。stdio只有管理员登记，普通账号不能通过凭据注入PATH/PYTHONPATH/NODE_OPTIONS等控制环境。
- `network.py` 把HTTP目标固定、TLS身份保留、DNS/私网和原始响应限量集中；`policy.py` 执行路径和参数范围。它们不是同一个职责，也不能将部署者允许访问某host误当作用户拥有该host全部操作权限。
- `adapters/mcp.py` 处理官方协议、目录/服务说明、认证错误和guard；`adapters/stdio.py` 负责Run会话、全局实例名额、串行协议访问与取消；`stdio_runner.py` 只补进程组后代回收，代码和文档都没有把它宣称为安全沙箱。
- `service.py` 当前还同时管理连接CRUD、加密、候选、调用、RunToolCaller。并非“大于600行所以必须拆”；真正的拆分理由是连接维护与运行会话有不同的生命周期/依赖。可先把RunToolCaller和调用投影单独归属执行适配，把MCP管理事务留原服务。
- `definitions` 局部导入 service.valid_header，service又局部导入definitions的validate_stdio、matching_service、check_unique_service，存在双向知识。局部导入避免了立即启动循环错误，但阅读规则时必须来回跳。把header/env/stdio接入规则下沉到明确的定义校验文件，身份去重留definitions，避免泛化成utils。
- 凭据加密复用模型模块的vault能力（由装配层注入），结果/目录会检查真实凭据并脱敏，快照不含Token。字符串精确脱敏不是任意编码的秘密识别器；没有据此声称能检测上游改写后的所有秘密。

### files

- `models` 是字节身份/哈希/用途，`config` 定部署限额，`service` 管保存/读取/捕获/回收；目录浅且职责一致，不需拆成每表repository。
- 保存时临时文件与目录fsync、读取时NOFOLLOW/大小/哈希都是实际完整性保护；capture限制重复/数量/owner及已发布allowed_ids。
- 业务引用通过回调注入sweep，避免反向依赖conversations。成功文件账面配额在写锁内求和，拒绝字节物理回收缺口见B1。
- DB候选清理128项有界；但孤立扫描把全部storage_key加载成set并扫描全部目录（`service.py:L183-L192`），所以整个维护并非完整有界。大量持久文件下可再做游标/批次和耗时指标；当前无规模压测，不将其写成已发生性能故障。
- `FileConfig.max_text_file_bytes/max_text_workspace_bytes` 目前未被其他app源码读取，而对话接受路径使用固定128KiB/512KiB。它们看起来可配置却不实际生效，建议删除无效配置或接入单一来源；默认行为本身一致，此项是维护建议。

### sandboxes

- `config/models/service/provider` 按部署参数、持久债务、生命周期、外部SDK划分；`verify` 与 `cli` 是受信部署运维入口，无需塞入HTTP router。
- 用精确metadata归属而非模型给出的remote_id直接kill；创建前意图落库、未知结果占容量、不自动重放，处理的是外部副作用可知性，设计有明确理由。
- provider关闭隐藏重试、用服务代理、限制传输，初始化仅root建立只读输入；实际命令UID1000由Agent backend控制。真实runsc/磁盘/网络不是代码能自证，必须依赖目标Linux主机验收。
- RunSandbox线程锁与数据库写锁分别保护本地handle和跨请求容量，不应互相替代。创建/初始化与TTL维护并发的交错缺少专项测试；本次未复现泄漏，不列确定缺陷。
- 清理失败保留unknown/cleanup并输出固定错误类别，运维债务可见；但全局投影权限需修复B2。

### infrastructure/database

- `base/fields/session/transactions/errors/models` 各有独立机制职责。没有泛化CRUD层，业务能在同一Session完成原子协作。
- `Database.transaction` 保证成功提交/异常回滚/释放；连接打开前PRAGMA设置外键、WAL和FULL，SQLAlchemy隐藏绑定参数。
- `reserve_writer` 先零匹配UPDATE，再由业务读取；测试验证即使空表也取得writer、读者不阻塞且回滚不修改行。
- 唯一错误识别要求SQLite驱动码、表、完整列完全匹配；BUSY/LOCKED识别不把未知完整性异常包装成可重试业务冲突。这比抓整个IntegrityError父类更可判断。
- `fields.py` 的通用编码与各领域模型约束并存；不能从ORM校验推出直接SQL写入全部受同样规则保护。迁移注册与正式迁移由主评审另核对，不在这里重复宣称通过。

## 验证、覆盖和限制

读过与以上范围直接相关的11个测试文件，详见coverage；包括数据库真实锁/回滚、HTTP错误脱敏、认证投影/Origin、静态交付、MCP账号/更新/导入、真实stdio进程和Agent基础资源测试。全仓测试与静态检查由主评审统一执行，本组没有重复全量运行。

另外运行三个独立复现，结果 **3 passed**。它们的“通过”表示预期的缺陷现象被观察到，不表示业务已修好。源码为 [复现脚本](boundary-reproduction.py)，输出为 [原始结果](boundary-reproduction.txt)。从仓库根可用以下方式复验：

```bash
PYTHONPATH=backend:backend/tests backend/.venv/bin/python -m pytest -q -s docs/records/backend-deep-review-2026-10-29/evidence/boundary-reproduction.py
```

脚本复用conftest的临时配置、真实Alembic升级和假模型能力，不调用真实模型、MCP或OpenSandbox，不读取开发库或秘密文件。复制到records只是保存证据，不纳入正式业务回归测试。

未做真实外网/Token账号验证、目标Linux隔离验收、磁盘耗尽/大规模压力实验。stdio原始JSON解析前没有平台字节闸门可在锁定SDK源码看到，但本次只将它保留为接收边界与压力验证问题；没有运行超量进程实验，也未把它升级成确定的宿主内存耗尽故障。

# 后端运行、配置与维护

本文维护当前后端的运行配置与操作。所有公共命令在仓库根目录执行；首次启动见[项目说明](../../README.md)。

## 运行

源码统一位于 `app/`，Python 导入前缀为 `app`；ASGI 入口为 `app.main:app`，账号 CLI 为 `app.auth.cli`。`tests/`、`migrations/`、依赖与迁移配置保留在后端工程根目录，目录职责见[后端架构](../architecture/backend.md#工程目录与应用包)。

以下命令均在仓库根目录执行；完整前后端启动流程见[根目录说明](../../README.md#本地运行)。

```bash
make setup
make db-upgrade
make dev
```

`make dev` 在后端端口占用时自动避让并更新前端代理；单独排查使用 `make dev-backend BACKEND_PORT=8000`，端口固定。同一数据目录仍只允许一个后端实例。启动前须迁移至 head，应用不自动建业务表或升级；checkpoint 的 SDK 自管表由应用初始化。初始化无需模型密钥，不导入演示员工或示例知识。`GET /health` 只检查进程存活；开发环境 `/docs`、`/openapi.json` 提供接口文档，启用 Secure Cookie 后关闭。完整进程与端口规则见[本地开发设计](local-development.md)。

## 配置入口与来源

[load_config / AppConfig](../../backend/app/config.py) 是部署配置的统一入口：先读取 `backend/.env`，再由进程环境覆盖，包含显式空值；模块按职责维护类型、默认值与校验。可填写的变量及必要说明见[环境变量示例](../../backend/.env.example)。

| 配置类别       | 维护位置                                                           | 内容                                                         |
| -------------- | ------------------------------------------------------------------ | ------------------------------------------------------------ |
| 应用与数据库   | [AppConfig / DatabaseConfig](../../backend/app/config.py)          | 模块装配、数据库、密钥和锁文件路径                           |
| 认证与登录     | [AuthConfig / GitHubOAuthConfig](../../backend/app/auth/config.py) | 浏览器来源、Cookie、会话期限和可选登录                       |
| 运行预算与调度 | [RuntimeConfig](../../backend/app/execution/config.py)             | 图步数、模型与技能预算、输出、容量、期限及观察间隔           |
| 单个模型连接   | [LLMConfig](../../backend/app/llm/config.py)                       | 从大脑配置解析并显式传入工厂，不从 `.env` 读取模型与 API Key |

配置字段的中文注释说明单位与边界。部署配置修改后重启生效；运行预算在接受请求时冻结，新提交及显式重试采用新值。

## 登录与游客访问

管理员维护共享配置；GitHub 普通用户可使用员工并管理本人 MCP 账号，游客只读公开概要。首次初始化管理员，密码由终端隐藏输入并确认（8～20 个字符），已有管理员时跳过：

```bash
make admin-create ADMIN_USER=admin
```

本机账号维护命令如下；重复初始化不会覆盖账号，改密、启停和撤销会话会使该账号已有会话失效：

```bash
make admin-reset-password ADMIN_USER=admin
make admin-disable ADMIN_USER=admin
make admin-enable ADMIN_USER=admin
make admin-revoke-sessions ADMIN_USER=admin
make admin-cleanup-sessions
```

| 环境变量                            | 默认值                                        | 说明                                                          |
| ----------------------------------- | --------------------------------------------- | ------------------------------------------------------------- |
| `AUTH_ALLOWED_ORIGINS`              | `http://127.0.0.1:3000,http://localhost:3000` | 逗号分隔的完整来源，不包含路径；写请求必须精确匹配            |
| `AUTH_COOKIE_SECURE`                | `false`                                       | 仅允许 `true` / `false`；非本机来源必须为 HTTPS 并开启 Secure |
| `AUTH_SESSION_MAX_AGE_SECONDS`      | `604800`                                      | 用户绝对期限，最多一年                                        |
| `AUTH_SESSION_IDLE_TIMEOUT_SECONDS` | `86400`                                       | 闲置期限，不能超过绝对期限                                    |
| `AUTH_GUEST_MAX_AGE_SECONDS`        | `604800`                                      | 游客绝对期限，最多一年                                        |

生产环境须配置 HTTPS 来源并开启 Secure Cookie。登录限速使用单进程内存计数，经开发代理访问时来源额度可能共享；正式入口需独立限速，当前不能通过增加后端 worker 扩容。会话与写请求规则由[登录与访问设计](../reference/auth.md)维护；Vite 保留原始 Origin 和会话 Cookie，并移除不可信转发地址头。

### 启用 GitHub 登录

1. 由部署者注册本站专用 OAuth App，回调为站点同一来源下的 `/api/auth/github/callback`；本机默认是 `http://127.0.0.1:3000/api/auth/github/callback`，浏览器与回调不可混用 `localhost`、`127.0.0.1`。
2. 在后端 `.env` 或进程环境配置 `GITHUB_OAUTH_CLIENT_ID`、`GITHUB_OAUTH_CLIENT_SECRET`、`GITHUB_OAUTH_CALLBACK_URL`。全部缺省时关闭入口，部分配置会启动失败；Client Secret 仅保存在后端。
3. 重启后端后用 `GET /api/auth/providers` 确认启用，再验证首次及重复登录、退出、管理员密码和游客入口。正式部署遵循上述 HTTPS 与 Cookie 规则。

登录不申请额外 scope，不持久化上游 token；普通用户通过已获准员工使用固定模型连接，不取得模型密钥；共享配置管理仍限管理员。协议、账户关联与迁移限制见[GitHub 登录设计](../reference/github-signin.md)。

## 数据库与本地文件配置

本地运行先参考[环境变量示例](../../backend/.env.example)创建 `backend/.env`；示例配置 `APP_DATA_DIR=~/.niuma-crew/data`，将运行数据保存在工程外，进程环境优先。下表列出代码未读取到对应配置时的缺省值，设计文档通过链接引用。

| 变量                         | 默认值                      | 含义                                                                               |
| ---------------------------- | --------------------------- | ---------------------------------------------------------------------------------- |
| `APP_DATA_DIR`               | `.data`                     | 本地文件基准目录；相对路径以 `backend/` 为基准，支持绝对路径                       |
| `DATABASE_URL`               | `sqlite+pysqlite:///app.db` | SQLAlchemy 连接 URL；当前仅支持文件型 SQLite，相对文件路径以 `APP_DATA_DIR` 为基准 |
| `SQLITE_BUSY_TIMEOUT_MS`     | `5000`                      | SQLite 写锁冲突时等待的毫秒数；允许 0，超时后抛出错误                              |
| `MODEL_CONNECTIONS_KEY_FILE` | `model-connections.key`     | 加密主密钥文件；相对路径以 `APP_DATA_DIR` 为基准，支持绝对路径                     |
| `RUNNER_LOCK_FILE`           | `runner.lock`               | 运行器进程锁；相对路径以 `APP_DATA_DIR` 为基准，支持绝对路径                       |

按本地示例配置后，数据库、主密钥和运行锁分别为 `~/.niuma-crew/data/app.db`、`~/.niuma-crew/data/model-connections.key`、`~/.niuma-crew/data/runner.lock`；备份保留在该目录的 `backups/`、`key-backups/`。`~` 会展开为当前用户主目录。若完全未配置 `APP_DATA_DIR`，代码仍使用 `backend/.data/`，不会自动寻找其他位置的旧库。

`APP_DATA_DIR` 相对路径以 `backend/` 为基准，其余文件路径及 SQLite URL 中的相对路径以该目录为基准。绝对 URL 示例：`sqlite+pysqlite:////srv/niuma-crew/data/app.db`。显式空值为配置错误，改变数据库 URL 不改变主密钥或锁文件位置；已有绝对文件路径也不会随 `APP_DATA_DIR` 自动变化。

迁移已有目录时先停止后端和其他数据库访问，创建一致性备份，再一并移动数据库、模型与工具主密钥、持久文件、技能资产和历史备份，更新 `.env` 中的路径后核对并重启。修改配置不会搬迁文件，也不会自动将旧库升级或导入新位置；保留原密钥，不生成替代密钥。此次本机迁移过程和验证见[配置切换与数据保留](../records/agent-model-rebuild.md)。

未来 Docker 部署须将宿主机持久化目录挂载到容器内，例如 `/srv/niuma-crew/data` 挂载到 `/data`，并在容器内设置 `APP_DATA_DIR=/data`；初始化迁移和正式服务使用相同挂载与配置。当前仓库尚未提供 Docker 部署配置。

当前仅支持本机磁盘上的文件型 SQLite，不接受内存库、URI、URL 查询参数或其他数据库驱动。数据库与 WAL、SHM 文件不进入 Git；自定义位置需同步排除。连接与 WAL 约束见[数据库配置设计](database-configuration.md#运行与维护约束)，事务机制见[数据库模块](../../backend/app/infrastructure/database/README.md)。

## 数据库迁移

```bash
make db-current
make db-check
# 新增或修改模型后生成迁移，审核代码后再升级
make db-revision MIGRATION_MESSAGE="describe schema change"
make db-upgrade
```

新增模型须在 `infrastructure/database/models.py` 注册。生成的迁移需审核字段重命名、数据转换及 SQLite batch 重建；未升级或存在未记录的模型差异时，`alembic check` 会失败。

迁移前停止后端与其他数据库访问，做 SQLite 一致性备份。当前包含业务库与 checkpoint 库：例如 app.db 对应同目录 app.checkpoints.sqlite，后者由数据库文件名替换扩展名派生。停写后分别用 SQLite backup 保存两库，并保留对应模型与工具主密钥、文件和技能资产；移动数据目录必须同时移动两库及关联文件。不要在服务写入时分别拷贝两个文件，也不要遗漏未合并的 WAL 内容。

历史迁移继续保留，当前 head 为 [0012](../../backend/migrations/versions/0012_retire_ci_diagnosis.py)。Message 直接保存正文，每次 Run 关联输入和独立助手回复；0012 移除 CI 专用表、员工字段与固定试验装配，保留共享历史。应用启动不自动升级，SDK 存储按执行需要打开。

0004 将旧 checkpoint 输出搬入业务历史，0005 再将稳定正文和专业数据归位。升级已有库必须保留原业务库、checkpoint 和模型主密钥；迁移会预检内容、归属和已知报告格式，损坏或不一致时明确失败并回滚，不能跳过错误。0005 不改写 SDK 文件，也不重新生成历史答案。

CI 退役需要读取和核对已有记录，应在线执行正式迁移；不要用离线 SQL 或空库代替升级。删除的专业数据不能靠降级无损恢复，需要回退时停服并恢复成套备份。0003 名称重复仍需先修正，不能覆盖或合并员工。

开发或部署均按“停服 → 两库一致性备份与密钥备份 → make db-upgrade → make db-check → 启动并观察”操作。本次开发库升级和保留检查见[实施记录](../records/platform-refactor-implementation.md)，它不替代其他环境升级前的备份。

## 大脑与模型配置

管理员在 `/brains` 保存员工对话连接；硅基流动 BGE-M3 向量连接从知识库检索配置入口管理。普通保存不请求上游；聊天检查只验证模型目录，向量检查发送固定短文本验证实际 API。模型与 API Key 无需预先写入 `.env`。

资料建设功能先执行 `make db-upgrade` 升至 0017，再重启后端。上传只暂存原件，在库内手动提交处理后由后台逐文件发布关键词索引；可离开页面，任务不会随浏览器关闭取消。处理器随应用生命周期运行，使用独立知识任务进程锁；测试关闭运行宿主时需直接驱动处理服务。

在知识库检索配置新建「硅基流动 · BGE-M3」，地址和模型自动填写，只需保存名称与 Key；测试通过后，在知识库「检索测试」选择连接、建立向量索引，再切换向量检索。已处理资料需显式建向量索引；新增待处理文件不影响已有向量，删除只清理该文件，重处理后该文件需补向量。当前构建入口仍重建全部已处理片段，完整后台增量构建尚未实施；不需要部署本地模型或额外向量数据库服务。代理请求超时应覆盖索引构建预算及一次上游调用，规则见[知识库契约](../reference/knowledge.md#硅基流动向量接入)。

Key 加密保存。[共用凭据机制](../../backend/app/infrastructure/credentials.py)供模型与工具使用，各模块分别转换自己的故障。主密钥优先读取 `MODEL_CONNECTIONS_ENCRYPTION_KEY`，未设置时使用 `MODEL_CONNECTIONS_KEY_FILE`，首次保存连接才创建权限为 0600 的密钥文件。显式空值报错，已有密文但主密钥缺失时不能自动生成替代密钥。数据库与主密钥必须分别备份；不能直接替换已有主密钥作为轮换。

连接停用、修订变化和引用保护由[模型连接模块](../../backend/app/model_connections/README.md)维护，字段与接口见[大脑配置设计](../reference/model-connections.md)。

## 真实对话与运行器

同一数据库只能有一个 Runner；所有服务进程须共享 `RUNNER_LOCK_FILE`，禁止多个 Uvicorn worker。锁使用 POSIX 文件锁，当前支持 macOS/Linux，不提供跨主机互斥；独立环境应使用各自的数据库、密钥与锁。

重启自动恢复支持版本的普通聊天，复用原 Run、快照与 checkpoint，重新检查授权，预算和总时限不重置；已取消运行不继续，退役试验和不支持恢复的快照保持安全中断，不转为普通工作。已落盘节点不重做，未完成模型请求可能重发及重复计费。细节见[运行契约](../reference/runtime.md#checkpoint历史与恢复)。

断开 SSE 仅停止观察，显式停止或发起会话失效才取消执行；存储故障或后台扫描退出会拒绝新执行；用 `/ready` 检查执行服务就绪，`/health` 只表示存活。普通对话按需读取技能和支持文件，通过获准工具完成操作，SSE 持续展示已保存的分轮草稿、思考和实际步骤；成功时助手正文、输出文件关联、终态和活动关联释放在同一业务事务提交；checkpoint 仅负责 SDK 恢复。

`RUN_` 加 [RuntimeConfig](../../backend/app/execution/config.py) 字段大写名可覆盖配置，计数及字节字段须为正整数，时间字段须为有限正数；`enabled` 仅供测试注入，没有环境变量开关。主要默认值如下：

| 环境变量                | 默认值 | 含义                                      |
| ----------------------- | ------ | ----------------------------------------- |
| RUN_CONCURRENCY         | 2      | 并发运行数                                |
| RUN_QUEUE_CAPACITY      | 20     | 最大排队数                                |
| RUN_PER_USER_CAPACITY   | 2      | 每账号未结束运行数                        |
| RUN_RUN_TIMEOUT         | 180    | 一次运行总时限，秒                        |
| RUN_QUEUE_TIMEOUT       | 30     | 排队时限，秒                              |
| RUN_RECURSION_LIMIT     | 64     | 普通 Agent 的 LangGraph 计算步数上限      |
| RUN_MAX_MODEL_CALLS     | 8      | 普通 Agent 每 Run 的模型调用次数上限      |
| RUN_MAX_SKILL_READS     | 16     | 每 Run 技能加载上限，预加载与读取共用     |
| RUN_MAX_OUTPUT_TOKENS   | 4096   | 模型输出 token 上限                       |
| RUN_MAX_INPUT_BYTES     | 16384  | 单条输入 UTF-8 字节上限                   |
| RUN_MAX_OUTPUT_BYTES    | 131072 | 每轮可见输出字节上限                      |
| RUN_MAX_REASONING_BYTES | 32768  | 每 Run 思考展示字节上限，达到后截断展示   |
| RUN_CONTEXT_BYTES       | 131072 | 输入正文总字节上限，不等于模型 token 限额 |
| RUN_CONTEXT_PAIRS       | 20     | 最多历史成功轮次                          |

`RUN_RECURSION_LIMIT` 计算图步数，包含模型、工具及部分中间件节点；不等于模型调用次数、工具数或总时限。图步数、模型调用或技能加载预算耗尽时返回 `agent_budget_exceeded`。

运行生命周期、取消与修订复核见[运行器模块](../../backend/app/execution/README.md)，接口与读取契约见[运行设计](../reference/runtime.md)。

## CI 试验退役与历史处理

<a id="github-ci-诊断"></a>

产品内的固定诊断试验已退役。CI_GITHUB_TOKEN/CI_GITHUB_TOKEN_FILE 不再参与配置；旧端点、仓库字段及报告/反馈入口移除。GitHub OAuth 登录和用户登记的通用 GitHub MCP 不受影响。

已有部署按以下顺序操作，不先启动新 Runner：

1. 停止旧后端、其他数据库写入、平台技能同步及外部技能目录写入。
2. 成套备份业务数据库、SDK checkpoint、模型/工具主密钥、不可变技能资产及可编辑技能目录。归档工具不代替整套备份，也不删除不可变 blob。
3. 在迁移 0012 删除固定技能记录前，用[技能源归档工具](../../backend/migrations/retire_ci_source.py)盘点并归档。工具读取 0011 的技能源字段；更旧的库应先按备份流程升级到 0011，暂不执行 0012。显式提供真实绝对路径，归档目录必须位于技能扫描根之外，并与来源位于同一文件系统：

   ```bash
   uv run --directory backend python -m migrations.retire_ci_source \
     --database-url 'sqlite+pysqlite:////绝对路径/app.db' \
     --library-directory '/绝对路径/skills' \
     --archive-directory '/同一文件系统/扫描根之外/ci-archive'
   ```

   默认仅盘点和校验，不移动技能源或修改数据库。报告为 ready 时，在同一命令末尾加 `--apply`；工具核对固定 UUID、已发布清单和来源字节，在技能目录锁内先备份完整元数据，再原子移动来源，不按技能名称查找或删除。

   | 报告状态                    | 后续操作                                                                       |
   | --------------------------- | ------------------------------------------------------------------------------ |
   | ready                       | 来源已核对但未归档，追加 --apply 执行                                          |
   | archived / already_archived | 本次已归档或核对已有匹配归档，可继续升级                                       |
   | metadata_only               | 记录本来没有来源指针；加 --apply 备份元数据，不猜测其他目录                    |
   | source_missing / blocked    | 退出码为 2，停止升级，先处理来源缺失、内容不符、路径或权限问题                 |
   | skill_absent                | 只表示数据库没有固定技能记录，不能证明来源已归档；必须核对升级前备份和来源处置 |

4. 确认来源归档或无来源的元数据备份已完成，再执行 `make db-upgrade` 到 0012，然后启动新代码。检查旧活跃试验已安全收尾、普通历史仍可读，并按备份核对恢复方案。

旧试验只读且不能重试，前端旧草稿不转为普通消息重发。退役边界和历史处理见[退役说明](../reference/ci-diagnosis/README.md)。

## 前端静态交付

构建 `frontend/dist` 后，FastAPI 自动提供同源页面与 API；未构建时仍可独立运行 API。用进程环境变量 `FRONTEND_DIST` 指定其他构建目录。

业务深链返回客户端入口；未知 API、缺失静态资源和越界路径保持错误响应。文本资源支持 gzip／Brotli、ETag 与 GET／HEAD；网关需保留这些行为并关闭 SSE 缓冲。生产来源加入 `AUTH_ALLOWED_ORIGINS`，启用 Secure Cookie。

完整本机预览在仓库根目录执行 `make build`、`make start`，默认 3000 端口，前提是后端环境已安装并完成迁移；使用 `START_PORT` 修改端口时须同步来源配置。构建与预览方式见[前端说明](../../frontend/README.md#构建与预览)。

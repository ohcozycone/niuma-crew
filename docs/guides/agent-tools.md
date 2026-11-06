# 基础工具接入与沙箱部署

本页是操作指引，不表示外部服务已在每个环境部署。

## 1. 升级应用与备份

1. 备份现有 SQLite、模型主密钥和工具主密钥（模型密钥路径追加 `.tools`）；已有文件目录也一并备份。不要打印或提交真实凭证。
2. 在项目根运行 `make setup-backend`、`make db-upgrade` 升级到当前 head。`0006` 建立工具、文件和沙箱底座，`0007` 增加 MCP 服务、账号和个人绑定；不会把旧 CI 凭证迁入通用工具。
3. 构建前端并重启单后端进程；当前仍使用单主机 Runner，不使用多个后端 worker。

## 2. 先让文件工具可用

1. 管理员从“能力库 → 平台工作区”创建原生工作区。平台直接提供受信目录，无须安装外部 MCP。
2. 在员工“能力装配 → 工具装配”选择 `read_file`、`ls`、`glob`、`grep`，按需要增加 `write_file`、`edit_file`；删除需要另选 `delete`。
3. 在高级范围约束中指定只读输入/来源及可写工作区/输出。页面提供初始 JSON，服务端验证才是最终权限；与员工配置一起保存。
4. 上传一个小 CSV，发送“读取输入，生成一个 CSV 到 /outputs/”。检查实际工具步骤，再下载产物并刷新复核。附件不能仅凭文件 ID 越过对话权限。

当前 UI 上传提示为 10 MiB；虚拟文本单文件仍只有 128 KiB，总量 512 KiB。大文件和二进制请使用后面的沙箱工作区。

## 3. 接搜索与网页

1. 准备 Tavily 的受限服务凭证；从“能力库 → 接入 MCP”登记服务，地址使用 `https://mcp.tavily.com/mcp/`，再创建 Bearer Token 账号连接。凭证保存在服务端，不拼到 URL。
2. 点击“检查连接与目录更新”，检查返回名称、描述和 schema，再“确认候选目录”。只保存 Token 或发现候选均不能让员工装配操作。
3. 在员工“能力装配 → 工具装配”点击“刷新连接列表”，选择 `tavily_search`、`tavily_extract`，设置调用预算、账号方式与必要参数限制，保存员工配置。需要读取长来源时，同时授予原生 `read_file` 的 `/sources` 范围。目录管理在新标签页完成，刷新不会清除当前员工草稿。
4. 发送一个需要当前资料的问题，核对实际搜索、所选页面的提取、来源状态和保存材料。搜索摘要不代表已读全文，提取失败不能展示为已核实。

接入 HTTP(S) MCP 无须配置域名或私网主机白名单，支持本机、内网及代理 DNS 映射。例如本机服务可直接填 `http://127.0.0.1:8765/mcp`，Notion 官方服务填 `https://mcp.notion.com/mcp`，认证信息单独填在账号访问设置中。`TOOL_MCP_ALLOWED_HOSTS` 和 `TOOL_MCP_PRIVATE_HOSTS` 已移除，旧环境即使保留这两项也不再生效。

TLS 校验、原始 Host/SNI、请求目标固定和响应限额继续生效；链路本地、多播和未指定地址仍拒绝。传输不自动使用环境代理；本机代理的 DNS 映射可直接使用，显式 HTTP 代理环境变量不会被采用。域名无法解析时检查后端机器的 DNS 或网络，不能通过更换 Token 修复；401 则检查账号认证。完整边界见[工具契约](../reference/agent-tools.md#工具范围与网络)。

第三方提取只处理适合交给该服务的公开网页。登录、点击、表单、内部站点和完整浏览器自动化未在首版开放。MCP 协议成功也不证明特定服务的账号额度、费用或资源范围，需用实际账号完成有界联调。

### OAuth 与 Notion 免费基础接入

1. 升级到迁移 `0018`，沿用既有工具主密钥；单后端进程运行，无需 OAuth 中转服务或额外数据库。
2. 设置 `TOOL_OAUTH_CALLBACK_URL` 为浏览器访问平台的同一来源，路径固定 `/api/tool-connections/oauth/callback`。代码缺省是 `http://localhost:3000/api/tool-connections/oauth/callback`；本机使用 `127.0.0.1` 时必须改为 `http://127.0.0.1:3000/api/tool-connections/oauth/callback`，并将该来源纳入现有 `AUTH_ALLOWED_ORIGINS`。线上使用本站 HTTPS 地址，反向代理将此路径转发到后端。
3. 后端和反向代理均不要记录回调查询串。应用已过滤 Uvicorn 的固定回调路径；代理采用仅路径的日志字段，例如 Nginx `$uri`，不要记录 `$request` / `$request_uri`。回调使用 no-store/no-referrer。
4. 登记 Notion 地址 `https://mcp.notion.com/mcp`，访问设置选“OAuth（浏览器授权）”，高级参数留空。已有 Bearer 连接可直接修改认证方式，不需要另建服务；保存会使原目录和身份依据失效。
5. 点击“连接账号”，在 Notion 官网选工作空间、核对 NiumaCrew 和本站回调后同意。返回后读取候选工具，确认清单，再到员工页面装配。OAuth 成功不等于目录或业务调用已经验收。
6. 刷新页面后仍应显示连接；出现 `reauth_required` 点击重新连接，临时网络错误先检查后端网络。断开只清理平台授权，不替代在 Notion 端撤销连接。

Notion [官方 FAQ](https://developers.notion.com/guides/mcp/get-started-with-mcp#faqs)说明 MCP 面向所有套餐；工作区成员可使用 OAuth，不要求购买 Business/Enterprise MCP Token。基础搜索、页面读取和写入按服务额度使用，跨应用 AI 搜索等付费功能不在免费范围。本方案不新增订阅或付费连接器，原有模型、主机和网络成本独立计算。

其他标准 OAuth MCP 使用相同操作。服务要求预注册时才填写 Client ID/Secret 和 scopes；不支持标准元数据、动态注册且没有预注册资料时，会明确失败，不做厂商专用兜底。

## 4. 在 Linux 部署 OpenSandbox

### 可信本机 MCP

需要运行 `npx/bunx/python` stdio MCP 时，可在 Mac 或 Linux 后端的环境中开启以下配置，不需要 Docker 或另起 OpenSandbox 容器：

```dotenv
TOOL_MCP_STDIO_ENABLED=true
TOOL_MCP_STDIO_MAX_PROCESSES=4
TOOL_MCP_STDIO_WAIT_SECONDS=10
```

默认关闭。重启后由管理员在能力库登记可信程序、固定包版本和环境变量键；账号页保存对应变量值，再检查、确认目录并给员工装配。先确保相同宿主账号可找到 `npx`、`bunx` 或绝对解释器路径，提前安装依赖，避免第一次下载超时。导入 JSON 不执行安装，程序启动只发生在目录检查或实际调用。

以 Context7 为例，下面是本机实际验证过的固定版本配置，可粘贴到“导入配置”：

```json
{
  "mcpServers": {
    "Context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp@4.4.4"]
    }
  }
}
```

点击“检查导入配置 → 填入接入表单 → 保存服务”；手填等价于程序 `npx`、参数 `["-y", "@upstash/context7-mcp@4.4.4"]`、环境变量名留空。创建个人连接后检查并确认目录，可看到 `resolve-library-id` 和 `query-docs`，最后到员工页面主动装配。这份配置以匿名方式调用，实际可用性受服务方限额影响；需要个人 API Key 时，在登记配置的 `env` 中声明 `CONTEXT7_API_KEY` 空位，再在账号连接里填写真实值；已有匿名服务可先在“编辑服务信息”补充允许的字段，再点击现有连接的“配置密钥”，不必重建 MCP。不将密钥放入公开启动参数。参见 [Context7 官方客户端配置](https://context7.com/docs/resources/all-clients)。

如果检查阶段提示“部署尚未开启可信本机 MCP”，说明当前实例未开启前述开关；更换 JSON 不会解决。若能保存服务但发现目录超时，再核对 Node 版本、包下载与后端机器的外网连接。Context7 `4.4.4` 要求 Node.js 至少 `20.18.1`。

这是宿主子进程，拥有后端账号权限，只有实例数与等待时间限制，不提供容器 CPU/内存/网络隔离。管理员应同时信任程序和暴露工具的实现，不向普通用户开放会把参数当宿主代码执行的工具；平台不能仅凭 schema 自动判断服务的所有行为。平台内置的代码执行与 Skill 脚本仍需要下面的 OpenSandbox 配置，导入包不会成为宿主进程启动定义。不同 Run/账号不会共用此进程；任务结束和停服负责回收进程组及临时目录。

### OpenSandbox 服务

模板位于 [deploy/opensandbox](../../deploy/opensandbox/sandbox.example.toml)。本轮选择 OpenSandbox 服务/SDK `1.1.1`、Docker、gVisor `runsc`，适配包锁定 `langchain-sandbox-opensandbox==0.1.2`；应用依赖见 pyproject/uv.lock。目标是腾讯云 Linux 单机，不需要 Kubernetes。服务端操作按[官方部署与配置](https://open-sandbox.ai/getting-started/configuration)及[安全运行时](https://open-sandbox.ai/guides/secure-container)复核。

1. 安装 Docker Engine 与对应架构的 runsc。云虚拟机优先验证 `systrap`，不以 KVM 或嵌套虚拟化为前提。
2. 对专用 Docker 数据目录配置真实磁盘配额。[daemon 示例](../../deploy/opensandbox/daemon.example.json)采用 overlay2/XFS project quota、每可写层 256 MiB；宿主 XFS 须支持对应配额，runsc 使用 `--overlay2=none`。不要覆盖现有 Docker 配置或自动重启承载其他服务的 daemon；若存储驱动不支持该方式，先实现等效硬配额，再运行验收。
3. 以受信控制服务身份安装固定版本：`uv venv /opt/niuma-sandbox/server-venv`，再执行 `uv pip install --python /opt/niuma-sandbox/server-venv/bin/python opensandbox-server==1.1.1`。该身份的 Docker 访问属于主机控制权限，不给工作负载。
4. 复制 [server TOML 模板](../../deploy/opensandbox/sandbox.example.toml)到权限受限的配置文件，替换 API Key。execd/egress 使用对应发行版镜像，部署时固定验收 digest。保持 bridge、runsc、no-new-privileges、PID 上限、dns+nft、禁 IPv6、空宿主路径授权与关闭自动续租。
5. 用[工作负载 Dockerfile](../../deploy/opensandbox/Dockerfile)构建镜像：显式提供 `--build-arg PYTHON_IMAGE=python:3.12-slim-bookworm@sha256:<已验证摘要>`。镜像预装 Python、Git、Node 和进程管理工具，工作用户 UID/GID 为 1000。构建后将工作负载固定为 registry digest 或本机 `sha256:<image-id>`，不使用浮动标签运行。
6. 同机服务仅监听回环地址，工作负载端口也绑定回环；后端使用服务代理访问文件/命令。跨主机另配置受限内网和 TLS，必须同时验证管理 API 与文件/命令通道。Docker socket 和应用数据目录不进入工作负载。
7. [systemd 模板](../../deploy/opensandbox/niuma-opensandbox.service)供显式配置控制服务身份与启动路径。模板不会自动修改主机、安装软件或启用服务。

隔离配置的目标是：命令与子进程不能获取平台凭证，输入不可修改，工作负载不能通过直连、IPv6、私网或云元数据绕过网络边界，CPU/内存/进程/磁盘受限。Docker、域名列表或提示词单独存在都不等于这些目标已经满足。

## 5. 验收与启用代码能力

在应用配置或部署秘密中设置以下非秘密项和管理密钥，参见 [env 示例](../../backend/.env.example)：

```dotenv
OPENSANDBOX_ENDPOINT=http://127.0.0.1:8080
OPENSANDBOX_IMAGE=sha256:<已验证的工作负载 image-id>
OPENSANDBOX_DEPLOYMENT_ID=niuma-crew
OPENSANDBOX_VERIFIED_PROFILE=/etc/niuma-sandbox/verified-profile.json
OPENSANDBOX_CPU=1
OPENSANDBOX_MEMORY=512Mi
OPENSANDBOX_MAX_CONCURRENCY=1
OPENSANDBOX_COMMAND_SECONDS=60
OPENSANDBOX_TTL_SECONDS=240
```

API Key 通过私有环境或秘密管理注入 `OPENSANDBOX_API_KEY`。镜像及 UID、网络、资源配置变化后重新验收。

1. 在实际 Docker Linux 主机、backend 目录运行 `uv run python -m app.sandboxes.verify --output /etc/niuma-sandbox/verified-profile.json`。验证程序会创建自己标记的短时环境，检查真实 Docker runtime、UID、权限、资源、网络和实际磁盘拒绝行为，最后销毁；未通过不生成可用依据。磁盘试验最多写到指定上限，请保留主机空间。
2. 检查主机 nftables/防火墙与 IPv6 路径，额外覆盖宿主和非许可内网的真实可达测试；脚本中的有限网络探针不代表穷尽所有旁路。验收文件是受信部署依据，当前有效期一天；应由运维在配置不变的条件下定期更新。
3. 重启应用，工具页沙箱状态就绪后创建“原生沙箱工作区”，为员工选择文件工具及 `execute`。每员工最多启用一个原生工作区连接；替换旧连接时同次保存许可集合。
4. 让员工执行简单 Python、处理 CSV、将结果写到 `/outputs/`。核对实际退出码、日志、可下载文件、取消后进程停止，以及回收后文件仍可下载。
5. 模拟创建超时、销毁失败和后端重启。确认资源债务仍可查询，后台仅回收本部署归属，不恢复旧容器继续运行。没有真实目标主机的验收，不将代码能力标为可用。

## 6. 回收、故障与维护

普通销毁失败保留待清理资源，应用每隔一段时间和启动时重试；管理服务 TTL 作为最后补偿。部署者使用 `uv run python -m app.environments.cli` 查看待回收资源；就绪依据在配置捕获和实际申请时核验，不另设闲置 HTTP 状态入口。

创建超时且尚未取得远端 ID 时，空查询不能证明请求不会晚到，平台保守占用容量并持续核对。运维可在 backend 目录运行 `uv run python -m app.sandboxes.cli` 查看申请 ID、Run、期限及清理次数。核对服务日志、实际资源和到期时间，确认过期请求没有遗留环境后，使用 `--resolve-absent <申请ID> --confirm-absent` 释放这条逻辑占用；命令仍会再次按精确 metadata 查询。未过期或已记录远端 ID 的资源不能用此方式消除记录。

文件字节、SQLite 和密钥按各自用途备份；临时沙箱与 checkpoint 不替代正式文件。`FILES_*`、`RUN_MAX_TOOL_CALLS` 与沙箱环境上限来自部署配置，员工许可只能收紧。修改配置需重启，新 Run 重新固定依据，旧 Run 不透明换身份、镜像或额度。

## 从标准目录同步 Skill

`SKILL_LIBRARY_DIR` 默认运行后端的系统用户目录 `~/.agents/skills/`。这是 [Agent Skills 官方接入指南](https://agentskills.io/client-implementation/adding-skills-support#where-to-scan) 推荐的跨客户端目录约定，不是包格式强制的位置。Mac 开发时使用本机用户目录；Linux 使用服务用户目录，不能读取网页访问者电脑的技能。管理员显式同步才会把该目录的包登记到平台共享能力库，启动时不自动扫描或发布。共享部署可显式指定独立持久目录，容器部署需挂载到配置路径并给予后端读写权限。已有 `SKILL_STORAGE_DIR` 是运行快照存储，不要把两个目录配置为同一处。

旧版默认使用数据库父目录下 `.agents/skills`；升级时若已有技能，可显式配置原目录继续使用，或停服后将完整技能目录迁往新位置。平台不自动合并两个根目录，也不改已发布版本与员工装配关系。

每个直接子目录包含 `SKILL.md`，目录名与其中 `name` 相同；scripts、references、assets 等文件随包保存。通过命令行安装时，将安装器目标设置为页面显示的实际路径，或把完整标准技能目录复制进去；不保证任意 CLI 默认安装位置恰好相同。不要使用指向其他位置的符号链接，当前有界扫描会拒绝。

在能力库点击“同步目录技能”，先核对展示的后端路径，再执行同步并查看新增、更新、无变化、来源缺失和错误。新增技能使用包内名称，可在配置页设置显示别名；更新保留员工关联。上传/在线创建也写入同一目录。外部编辑后先同步，再继续页面编辑，避免互相覆盖。目录被删除时保留已发布内容，不自动删除或解除员工装配。

备份需包含数据库、标准目录和不可变技能存储。正式迁移只增加关联和输入描述字段，不在数据库升级时读取技能文件；旧技能在首次同步时物化到标准目录。同名不同内容先报冲突，需要核对后处理。同步不会执行脚本、安装依赖或自动给员工装配。

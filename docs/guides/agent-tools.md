# 工具与环境

面向管理员和部署者。外部工具通过组织工作连接装配给员工；平台文件读写直接提供，运行程序则需要已验收的 OpenSandbox。

## 接入前准备

新环境先安装后端依赖、升级数据库并初始化管理员。已有环境先按[数据库迁移](backend-operations.md#数据库迁移)停写、备份并核对升级条件，尤其是已有工具和知识资源的 0028 接纳清单。升级使用当前 `head`，不只停留在某个旧功能的引入版本。

前端重新构建，后端保持单进程。以下部署配置写入服务实际使用的环境，修改后重启。

## 验证文件读写

无需登记文件插件或原生连接。新对话可以读取本次输入、获准资料和技能文件，写入 `/workspace/` 与 `/outputs/`；不能借此访问后端宿主目录。

上传一份小型 UTF-8 CSV，让员工读取并把汇总文件保存到 `/outputs/`。核对执行日志与正式回复中的下载文件。未配置沙箱时，文本工作区单文件上限 128 KiB、可写总量 512 KiB，不能执行程序；附件上传限额与工作区限额分别检查。

## 接入 HTTP 工具

以 Tavily 搜索和页面提取服务为例：

1. 从“能力库 → 添加能力 → 添加 MCP 服务”进入接入页，填写服务地址 `https://mcp.tavily.com/mcp/`，在访问设置中选择 Bearer Token 并保存凭据。不要把凭据拼入地址。
2. 点击“保存并测试”。在返回的“可用工具”中核对实际名称、说明和参数，点击“确认工具列表”；已有连接使用“检查工具更新”“应用工具更新”。
3. 打开员工“能力装配”，选择该工作连接，只勾选任务需要的搜索和提取操作，例如清单中提供的 `tavily_search`、`tavily_extract`。设置调用上限及已有范围规则，再点击员工“保存配置”。
4. 发起一项需要查询公开资料的工作，检查实际搜索、页面提取和返回来源。提取失败时，不能把搜索摘要当成已读全文。

HTTP(S) 地址可以指向后端可达的本机、内网或外部服务，不需要维护部署域名白名单。地址不能包含用户名、密码、查询参数或片段；密钥在访问设置中保存。传输不自动读取环境 HTTP 代理，域名解析失败时先检查后端网络与 DNS；401 则检查认证。

不同服务的额度、费用和数据访问范围由其账号决定。先用小范围请求联调，并只装配需要的操作。完整的地址与调用限制见[工具规则](../reference/mcp.md)。

## OAuth 与 Notion 接入

工具 OAuth 使用本站浏览器来源，和 GitHub 登录分开配置。

1. 将实际浏览器来源加入 `AUTH_ALLOWED_ORIGINS`。线上使用 HTTPS 并设置 `AUTH_COOKIE_SECURE=true`；工具回调默认使用发起授权的受信任来源，固定路径为 `/api/tool-connections/oauth/callback`。
2. 服务方要求固定回调时，再设置 `TOOL_OAUTH_CALLBACK_URL`。其来源必须在允许列表中，浏览器也须从同一来源发起授权；反向代理要将该路径转发到后端。
3. 在 MCP 接入页填写 `https://mcp.notion.com/mcp`，认证选择“OAuth（浏览器授权）”，通常可先保留高级参数为空。服务要求预注册客户端时，填写其提供的 Client ID、Secret 和 scopes。
4. 点击“保存并连接账号”，在 Notion 页面选择工作空间并核对授权。已有连接可点击“连接账号”或“重新连接账号”。返回后读取并确认工具列表，再到员工配置中选入所需操作。
5. 刷新后核对连接状态，再做一次实际操作。状态为 `reauth_required` 时重新授权；临时网络错误先检查网络。平台“断开账号”清理本地授权，服务方的连接撤销需在其账号中另行处理。

Notion 的连接要求见[官方接入说明](https://developers.notion.com/guides/mcp/get-started-with-mcp)，可用工具与额度以实际账号为准。

回调查询串可能含授权码，后端、网关及上游代理都应避免记录完整请求 URL。应用对工具回调采用不缓存、不发送来源的响应策略，并过滤固定回调路径的 Uvicorn 访问日志；代理日志需单独配置。更换域名后更新来源和固定回调，再重新连接旧来源授权。

## 接入可信本机程序

stdio MCP 运行在后端宿主上，具有服务账号的权限，不提供容器级隔离。部署者确认程序可信后，在后端环境开启：

```dotenv
TOOL_MCP_STDIO_ENABLED=true
TOOL_MCP_STDIO_MAX_PROCESSES=4
TOOL_MCP_STDIO_WAIT_SECONDS=10
```

确保后端服务账号能找到程序，提前安装依赖并固定版本。导入配置只解析内容，“保存并测试”会启动程序并读取工具。平台内置代码执行和技能脚本仍通过沙箱运行，不使用此入口。

以下固定版本的 Context7 配置可作为快捷导入示例，实际版本要求按[服务方说明](https://context7.com/docs/resources/all-clients)核对：

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

通过“快捷导入”的“解析并填入”回填表单，核对程序和参数后保存、测试、确认工具列表。需要密钥时，在服务信息的“允许配置的凭据字段”声明 `CONTEXT7_API_KEY`，再在工作连接的“配置密钥”中填写值，不把密钥写入公开启动参数。

提示“部署尚未开启可信本机 MCP”时，先开启部署开关并重启；目录读取超时则检查程序路径、依赖下载和后端外网。连接与任务结束后由平台回收进程组及临时目录，主动脱离进程组的程序不属于恶意代码隔离保证。

## 部署 OpenSandbox

以下按同机 Linux、Docker 和 gVisor `runsc` 部署。服务模板使用 OpenSandbox `1.1.1`；应用 SDK 和适配包版本以仓库锁文件为准。准备步骤与[官方配置说明](https://open-sandbox.ai/getting-started/configuration)对照执行。

1. 在目标主机安装 Docker Engine 和对应架构的 `runsc`，验证运行时可用。云虚拟机可先验证 `systrap`，不依赖嵌套虚拟化。
2. 为专用 Docker 数据目录配置有效磁盘配额。[daemon 示例](../../deploy/opensandbox/daemon.example.json)采用 overlay2/XFS project quota，每可写层 256 MiB；宿主文件系统需支持配额，`runsc` 使用 `--overlay2=none`。先合并核对已有 Docker 配置，不直接覆盖或重启承载其他服务的 daemon。
3. 用专用服务身份安装固定版本：

   ```bash
   uv venv /opt/niuma-sandbox/server-venv
   uv pip install --python /opt/niuma-sandbox/server-venv/bin/python opensandbox-server==1.1.1
   ```

4. 在仓库根运行 `make sandbox-init`，生成私有服务配置，并将相同密钥和本机地址写入 `backend/.env`。默认服务配置位于 `backend/.data/opensandbox/sandbox.toml`；重复运行保留已有密钥，不启动服务或生成验收文件。需要部署到 `/etc/niuma-sandbox` 时，显式指定目录：

   ```bash
   backend/.venv/bin/python scripts/init_sandbox.py --directory /etc/niuma-sandbox --app-env /绝对路径/backend/.env
   ```

5. 使用[工作负载 Dockerfile](../../deploy/opensandbox/Dockerfile)构建镜像，显式传入已核对摘要的 `PYTHON_IMAGE`。镜像包含 Python、Git、Node 和进程工具，命令以 UID/GID 1000 执行。将最终工作负载固定为 registry digest 或本机 `sha256:<image-id>`。
6. 检查生成的[服务配置](../../deploy/opensandbox/sandbox.example.toml)：保持回环监听、bridge、`runsc`、`no-new-privileges`、PID 上限、`dns+nft`、禁用 IPv6、空宿主路径许可和关闭自动续租。execd 与 egress 镜像按匹配发行版固定摘要，Docker socket 和平台数据不挂入工作负载。
7. 按服务身份可读的路径启动 `opensandbox-server --config /绝对路径/sandbox.toml`。[systemd 模板](../../deploy/opensandbox/niuma-opensandbox.service)默认使用 `/etc/niuma-sandbox/sandbox.toml`，路径须与第 4 步一致；默认初始化路径与模板路径不能混用。

服务身份拥有 Docker 控制权限，工作负载不应继承该权限。连接已有 OpenSandbox 时，直接使用其地址和密钥，不运行本机初始化覆盖它。

## 验收并启用代码执行

在后端环境填写以下配置。`make sandbox-init` 已写入的地址、密钥和验收文件路径保持一致；密钥通过私有配置或秘密管理注入，不写入示例或日志。

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

1. 在实际运行沙箱的 Linux Docker 主机进入 `backend/`，使用同一环境执行：

   ```bash
   uv run python -m app.environments.verify --output /etc/niuma-sandbox/verified-profile.json
   ```

   输出路径须与 `OPENSANDBOX_VERIFIED_PROFILE` 一致。程序会创建测试沙箱，检查实际运行时、UID、权限、CPU、内存、进程限制、网络和磁盘拒绝行为，最后销毁。默认磁盘探针最多写到约 256 MiB，主机需预留空间。

2. 补查主机防火墙、IPv6、宿主及内网可达路径。脚本的有限探针不覆盖全部网络旁路。通过后的验收文件有效期为 24 小时，部署者须定期重新验收；镜像、资源或隔离配置变化后也需重做。
3. 确认业务数据库已升级到当前 `head`，重启后端。在员工“能力装配”顶部检查“代码执行：已就绪”。配置与验收匹配后，新受理工作自动使用沙箱，无需创建文件插件或增加员工代码许可。
4. 让员工读取小型 CSV、执行简单 Python、将结果写入 `/outputs/`。核对退出码、文件下载及内容，再测试取消、创建超时、回收失败与重启后的清理结果。

验收文件只说明所记录配置的检查结果，实际服务、网络和文件下载仍需上述联调。更换密钥时同步修改应用与服务端，再重启相关服务。

## 回收与故障处理

工作结束后释放沙箱；销毁失败会保留待回收记录，应用启动和后台维护继续重试，服务 TTL 提供到期回收。临时容器不用于恢复旧任务，也不替代正式文件备份。

在 `backend/` 用服务实际环境查看记录：

```bash
uv run python -m app.environments.cli
```

创建结果未知且尚无远端 ID 时，平台会保留容量占用。先核对服务日志、实际资源与到期时间；确认已过期且没有遗留环境后，才可执行：

```bash
uv run python -m app.environments.cli --resolve-absent <申请ID> --confirm-absent
```

命令会再次按归属信息查询。尚未到期、已取得远端 ID 或归属其他部署的记录，不能用此方式清除。

## 同步目录技能

`SKILL_LIBRARY_DIR` 默认指向后端服务用户的 `~/.agents/skills/`，不是网页访问者的电脑。共享部署可指定独立持久目录；它与 `SKILL_STORAGE_DIR` 的不可变存储必须分开。

1. 在该目录下放置标准技能包，每个直接子目录包含 `SKILL.md`，目录名与包内 `name` 一致。将需要的 scripts、references、assets 一并复制，不能使用指向其他位置的符号链接。
2. 管理员在“能力库”更多操作中选择“从服务器目录同步技能”，核对后端路径，再点击“同步到能力库”。查看新增、更新、无变化、来源缺失和错误；同步不执行脚本或安装依赖。
3. 在员工“能力装配”选入同步后的技能并保存配置。目录同步不会自动装配给员工，删除来源目录也不会自动删除已发布内容。

在线创建和上传技能也使用这份标准目录。外部编辑后先同步，再继续页面编辑；同名不同内容发生冲突时先核对来源。备份同时保留数据库、标准目录和不可变技能存储。

# 后端运行、配置与维护

本指南描述当前单机运行方式。生产容器及反向代理见[部署指南](deployment.md)，所有公共开发命令在仓库根执行。

## 运行

```bash
make setup
make db-upgrade
make admin-create
make dev
```

ASGI 入口是 `app.main:app`。业务表由 Alembic 正式迁移建立，应用不自动迁移；缺表或字段不匹配会使后台启动或业务查询失败，不能将存活检查当作完整结构验证。当前迁移 head 是 0024，以实际迁移代码和 `make db-current` 为准。

`make dev` 使用前端 3000 端口，后端从 8000 避让并更新代理；3000 已占用会失败。生产先 `make build`，再执行 `make start`，由单个 Uvicorn 同源交付前端与 API；另需部署进程守护、HTTPS 和正确的来源配置。

`GET /health` 仅检查进程存活，`GET /ready` 检查运行器是否接受工作；两者不验证外部模型、MCP、沙箱或全部业务表。上线还需读取实际 API 并核对日志。生产开启 Secure Cookie 后关闭 Swagger 与 OpenAPI 入口。

## 配置入口与来源

[AppConfig](../../backend/app/config.py) 读取 `backend/.env`，进程环境优先，包含显式空值。完整可选变量见[示例](../../backend/.env.example)，修改部署配置后重启。模型和 API Key 由管理员在大脑中保存，不从 `.env` 读取聊天模型。

| 配置                       | 默认或示例                    | 边界                                                  |
| -------------------------- | ----------------------------- | ----------------------------------------------------- |
| APP_DATA_DIR               | 示例为 `~/.niuma-crew/data`   | 未配置时为 backend/.data；相对路径以 backend 为基准   |
| DATABASE_URL               | `sqlite+pysqlite:///app.db`   | 只支持本机文件 SQLite；相对数据库路径以数据目录为基准 |
| MODEL_CONNECTIONS_KEY_FILE | `model-connections.key`       | 相对路径以数据目录为基准，首次保存凭据时创建          |
| RUNNER_LOCK_FILE           | `runner.lock`                 | 同一数据目录只运行一个后端进程                        |
| KNOWLEDGE_VECTOR_DIR       | 数据库旁 `knowledge-vectors`  | Chroma 持久目录，单进程使用                           |
| SKILL_LIBRARY_DIR          | 运行账号的 `~/.agents/skills` | 部署时显式指向专用持久目录                            |
| SKILL_STORAGE_DIR          | 数据库旁 `skill-assets`       | 不可变运行技能，不能与编辑目录相同                    |

配置字段的类型、单位、上限由所属配置类校验。改变路径不会移动旧文件或升级数据库。Chroma 在默认运行器启动时初始化，不能因尚无知识库而删除其依赖。

## 登录与访问

管理员由 `make admin-create ADMIN_USER=admin` 创建，密码隐藏输入，已有管理员不会被覆盖。维护账号可执行：

```bash
make admin-reset-password ADMIN_USER=admin
make admin-disable ADMIN_USER=admin
make admin-enable ADMIN_USER=admin
make admin-revoke-sessions ADMIN_USER=admin
make admin-cleanup-sessions
```

`AUTH_ALLOWED_ORIGINS` 必须列出浏览器实际使用的完整来源。公网使用 HTTPS，并设置 `AUTH_COOKIE_SECURE=true`；开发默认只允许本机。Cookie、Origin、会话期限与权限见[认证契约](../reference/auth.md)。当前只有单进程限速；正式入口应配置独立限速，不能通过多后端 worker 扩容。

GitHub 登录为可选能力。注册 OAuth App 后配置 `GITHUB_OAUTH_CLIENT_ID`、`GITHUB_OAUTH_CLIENT_SECRET`、`GITHUB_OAUTH_CALLBACK_URL`；回调为同源 `/api/auth/github/callback`。三项全部缺省时关闭，部分配置会失败。配置步骤见[GitHub 登录](../reference/github-signin.md)。

## 数据库与本地文件配置

数据库、checkpoint、文件、技能、向量、日志和加密主密钥只保存在部署数据目录，不能提交到 Git。app.db 的 checkpoint 是旁置 app.checkpoints.db。密钥与数据库分别保管；已有密文而密钥丢失时不能用新密钥代替。模型与工具分别使用受管凭据存储，工具文件密钥在模型密钥旁追加 `.tools`。

首次部署以空库执行 `make db-upgrade`；不导入本机业务数据。升级已有环境先停止写入，分别用 SQLite backup 制作业务库与 checkpoint 一致性备份，再保存文件、技能、索引及原密钥，随后在副本上验证迁移。

```bash
make db-current
make db-upgrade
make db-check
```

0021 的数字 ID 迁移不转换旧业务数据；有旧数据时不能直接升级或清库。后续迁移有不可逆变更，不以降级代替恢复。回退需同时恢复匹配代码、成套数据库、文件及原密钥。完整路径规则见[数据库配置](database-configuration.md)。

## 模型、知识、工具与沙箱

聊天连接保存后，检查连接主要验证模型目录；必须真实对话才能证明生成可用。知识向量通过硅基流动 BGE-M3 接入，显式建索引后才有向量覆盖；上传或重新处理不会自动保证向量就绪。库内检索测试不生成回答，员工知识装配通过受管工具提供引用依据。

MCP 服务、账号及员工许可分别管理。可信 stdio 程序具有后端系统账号权限，默认关闭。OpenSandbox 为可选外部基础设施，必须在目标 Linux 主机完成约束验收后启用；本部署不自动授予命令权限。参见[工具与沙箱操作](agent-tools.md)。

## 记录与排查

执行证据可能包含实际模型输入、输出和工具参数，即使凭据字段被脱敏，也仍属于私有业务数据。Uvicorn 对 GitHub 与工具 OAuth 回调去除查询串；反向代理也须避免落盘带授权码的完整请求行。日志设置不能替代部署目录权限及数据保留策略。按[常见问题](troubleshooting.md)先核对请求、资源权限、当前版本、持久化与上游结果。

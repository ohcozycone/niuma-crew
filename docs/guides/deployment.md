# 应用与文档站部署

当前支持单台 Linux、一个后端进程和持久化 SQLite。应用服务使用 3000，文档静态服务使用 3001。两个端口只发布到宿主机回环地址；公网由现有 HTTPS 代理接入。

## 从空环境启动

安装 Docker Engine 与 Compose 插件，检出仓库后在根目录执行：

```bash
cp deploy/app.env.example .env
# 修改 PLATFORM_URL 为实际 HTTPS 来源，并设置 AUTH_COOKIE_SECURE=true。
docker compose --env-file .env -f deploy/compose.yaml build app
docker compose --env-file .env -f deploy/compose.yaml build docs
docker compose --env-file .env -f deploy/compose.yaml up -d
docker compose --env-file .env -f deploy/compose.yaml exec app python -m app.auth.cli create-admin admin
```

管理员密码由终端隐藏输入。数据保存在独立 Docker volume `niuma_app-data`，首次启动显式执行 Alembic，随后运行单个 Uvicorn。源码不携带数据库、默认账号、模型连接、密钥或用户资料。无需模型密钥即可启动；真实对话需在页面配置大脑和员工。生产不运行 Vite 或 Next.js 开发服务。

本机 HTTP 试用可将 PLATFORM_URL 改为 `http://127.0.0.1:3000`，同时设置 AUTH_COOKIE_SECURE=false；公网必须使用 HTTPS。后端所有配置见[维护指南](backend-operations.md)，可选 GitHub OAuth、MCP 和 OpenSandbox 需另配后端环境，首次部署默认关闭未配置的外部能力。

## 现有 Nginx Proxy Manager

确认现有代理容器的 Docker 网络名称，写入 .env 的 PROXY_NETWORK；增加代理网络覆盖文件：

```bash
docker compose --env-file .env -f deploy/compose.yaml -f deploy/compose.proxy.yaml up -d
```

只编辑目标域名的 Proxy Host：默认转发到 `http://niuma-app:3000`，增加 `/docs` 自定义 location 转发到 `http://niuma-docs:3001`，保留请求路径。启用目标域名的证书和 Force SSL。文档首页为 `/docs/`，正文路由在 `/docs/docs/` 下；它是独立站点的路径前缀与站内文章路由组合。

为应用上游配置：

```nginx
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 600s;
proxy_send_timeout 600s;
client_max_body_size 12m;
access_log off;
```

转发须保留真实 Origin、Host、Cookie。OAuth 查询串不得进入持久访问日志，原始请求行也可能出现在代理错误日志；没有安全过滤时关闭目标主机错误日志。更具体的同源交付边界见[现有 Nginx 模板](../../deploy/nginx/README.md)。配置保存前备份目标主机原配置，不能修改其他域名的服务或数据库。

## 构建与路径

文档 Docker 构建固定挂载 `/docs`。本地 `make build-docs` 默认不加前缀；其他挂载路径需同时修改 NEXT_PUBLIC_DOCS_BASE_PATH、静态服务根目录与代理 location 后重新构建。独立静态站保留每页 index.html 与 404.html，不使用应用的 SPA 回退。

Docker 构建固定按 uv/pnpm 锁文件安装。内存较小的主机按 app、docs 顺序构建；文档构建限制 JavaScript 堆并使用单个构建 CPU。构建过程仍需访问镜像与软件包源。

## 验证、更新和恢复

1. 在切换代理前核对 `docker compose ... ps` 健康状态，检查宿主机 `/health`、`/ready`，并读取真实业务 API。
2. 验证 HTTPS 首页、文档首页和正文、品牌资源、中文搜索、文档中的“进入平台”。检查管理员与游客权限、来源拒绝和数据库迁移状态。
3. 模型配置后单独验证一次真实对话、SSE、取消及历史；未配置的模型、MCP、沙箱不能标记为通过。
4. 重启应用后确认健康与已有资料可读。更新前停止写入，备份业务库、checkpoint、文件、技能、向量及原密钥；不能只复制仍在写入的 SQLite 主文件。
5. 保留上一镜像和代理目标。首次切换失败恢复代理；有数据库迁移时，回退同时使用匹配代码和成套备份。`docker compose down` 不删除 volume；不要以 `down -v` 代替升级或清理。

应用日志和执行证据也是私有数据。部署完成后由管理员配置模型与资源，不从开发机器复制业务库或凭据。

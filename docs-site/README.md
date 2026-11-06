# NiumaCrew 独立文档站

本应用使用 Fumadocs 与 Next.js 静态导出，正文来源为仓库现行 Markdown。产品、部署和开发文档从发布清单进入导航，进一步阅读页面沿已核对的本地链接生成。临时讨论、历史记录及架构图片不随公开版本发布。

## 启动与检查

需要 Node.js 22.12+、pnpm 11。在仓库根执行：

```bash
make setup-docs
make dev-docs
make check-docs-site
make build-docs
make preview-docs
```

开发与预览使用 `http://127.0.0.1:3001`，占用即失败。文档站不依赖平台、数据库或模型。静态产物位于 out，生成目录不提交；修改正文回到原文件，不编辑生成副本。

## 独立部署与路径前缀

NEXT_PUBLIC_PLATFORM_URL 配置“进入平台”的地址；NEXT_PUBLIC_DOCS_BASE_PATH 配置站点挂载路径。两者均在构建时确定。例如：

```bash
cd docs-site
NEXT_PUBLIC_PLATFORM_URL=https://niuma.example.com NEXT_PUBLIC_DOCS_BASE_PATH=/docs pnpm build
```

Next Link 自动添加路径前缀；图片、搜索索引和 Markdown 下载使用 public-path.ts 明确添加。默认本地构建不加前缀；Docker 版本挂载 /docs，首页为 /docs/，站内文章位于 /docs/docs/。发布时保留静态目录结构，每页使用 index.html，未知路径返回真实 404。完整容器与反向代理配置见[部署指南](../docs/guides/deployment.md)。

## 内容与维护

scripts/content.mjs 维护六章和 15 篇主页面；sync-content.mjs 解析本地链接、按明确类型复制资源并生成原文索引。禁止发布真实环境文件与凭据，不读取仓库外文件。开发同步先校验所有输入，再原子发布变化的文件；失败保留上次可用内容。

.generated、.source、public/repository、public/brand、.next 和 out 都是可重建产物。修改发布清单或站点配置后重启开发服务。内容、类型、定向测试、格式和生产构建均由 make check-docs-site 检查，原文链接由 make check-docs 检查。

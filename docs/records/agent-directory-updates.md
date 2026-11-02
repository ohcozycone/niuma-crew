# 员工收藏与目录更新验收

日期：2026-10-29。范围：本地工作区的员工目录、卡片状态操作、导航收藏读取和共享分页反馈；工作区尚无 Git 提交，本记录以相邻实现及测试为复现入口。设计见[增量方案](../proposals/agent-directory-updates.md)，当前规则见[员工模块](../../frontend/src/pages/agents/README.md#目录读取与收藏同步)。

## 方法与结果

1. [目录流程测试](../../frontend/src/pages/agents/AgentDirectoryFlow.test.tsx)通过模拟 PATCH、分页读取和导航摘要验证：星标即时更新、同员工请求串行、其他员工并发、失败恢复与重试、新 revision 续写、409／断网／服务端错误只重读核对、收藏移除与补位、末页回退、启停筛选补位、切换筛选期间写入完成、读写交错的旧响应丢弃、保留较新 revision 和身份隔离。普通列表收藏成功后没有额外员工列表或目录总数请求，只核对导航；卡片 DOM 保持复用。
2. [导航流程测试](../../frontend/src/components/navigation/navigationFlow.test.tsx)验证独立导航失效不推进配置版本，核对失败保留收藏与计数、可重试，以及新写入取消旧导航请求并忽略迟到响应。
3. `make lint-frontend` 通过 ESLint、TypeScript 和前端格式检查；`make test-frontend` 通过 52 个测试文件、380 项测试；`make build` 成功。构建仍提示部分既有资源分块超过 500 kB，该提示未阻断产物生成。
4. Impeccable 机械检查对修改的卡片、目录、页面和分页组件返回空问题集。浏览器使用独立前端端口 3001 与仅监听本机的内存模拟接口，虚构三位员工，GET 延迟 1.5 秒、PATCH 延迟 2 秒。约 576px 宽视口下检查日夜主题、局部收藏锁、保留内容的刷新、读取失败反馈及重试入口。原开发服务后端未连通，未使用或更改真实业务数据。

## 限制

`UV_CACHE_DIR=/private/tmp/niuma-crew-uv-cache make check-docs` 扫描到 21 处失效引用，全部位于本轮未修改的 `.impeccable/critique/2026-10-29T08-26-54Z__frontend-src.md`：包含把文件行号当作路径的链接及缺失历史截图。该全局检查未通过；本轮新增和修改文档未报告路径或章节错误。

接口为离线测试替身和浏览器内存模拟，不能证明真实后端的授权、持久化或多客户端竞争行为；接口与数据库契约未修改。未覆盖 Safari、Firefox、触屏实机和完整尺寸矩阵。本次同步限于当前工作台，跨标签页和其他客户端没有新增实时推送。

# 开发命令与排错

## 分端和生产预览

```bash
make dev-backend BACKEND_PORT=8001
make dev-frontend BACKEND_URL=http://127.0.0.1:8001
make build
make start
```

分端端口不避让。start使用已构建静态产物和单个后端同源交付，默认3000；preview只查看静态产物，不提供生产API代理。更改START_PORT时同步来源和OAuth配置。相同数据目录只能有一个后端，端口避让不隔离数据库和运行锁。

## 开发与文档检查

| 目的           | 根命令                                               |
| -------------- | ---------------------------------------------------- |
| 静态/类型/格式 | make lint；按需make lint-backend、make lint-frontend |
| 业务离线验证   | make test；按需make test-backend、make test-frontend |
| 启动器与头像   | make test-dev、make test-avatars                     |
| 文档路径与站点 | make check-docs、make check-docs-site                |
| 完整离线交付   | make check                                           |

[Makefile](../../Makefile)维护实际命令，包依赖由uv.lock与pnpm锁文件维护。

## 文档站与实验

make setup-docs安装文档应用依赖；make dev-docs在3001启动；make build-docs与make preview-docs构建和预览。详细发布机制见[站点说明](../../docs-site/README.md)。

make verify-checkpoint使用临时SQLite、假模型与真实HTTP子进程验证连续对话和恢复；make dev-checkpoint启动[独立实验](../../backend/experiments/sqlite_checkpoint_chat.py)，默认8001及临时存档，CHECKPOINT_DB/CHECKPOINT_PORT可覆盖。make verify-knowledge为独立知识实验验证入口，不是生产检索质量证明。

make verify-tool-results运行[正式结果交付隔离测试](../../backend/tests/test_result_delivery.py)及旧读取/工具门回归，使用假模型、独立业务库、文件与checkpoint，不访问开发业务库或远端MCP。早期适配原型已由正式测试替换，原型的时点证据见[验证记录](../records/工具结果官方适配验证.md)。真实模型对照另用[验收脚本](../../scripts/benchmark_result_delivery.py)，会调用当前已授权的Kimi服务，只发送合成问题/结果与已批准工具定义；不执行真实MCP业务操作。

make verify-evidence-boundary使用仓库固定目录与合成返回，离线捕获六类真实链路末轮上下文，另验证首个429保存后结束；不读取开发库、密钥或调用真实模型。两版未采纳说明及付费复验范围见[证据边界记录](../records/回答证据边界复验.md)。[脚本](../../scripts/benchmark_evidence_boundary.py)通过 --candidate-report 显式选择待比较说明，不修改生产提示；没有候选变化时拒绝发起付费比较。

## 启动器定位与失败

[scripts/dev.py](../../scripts/dev.py)负责端口、就绪等待和子进程清理；它保留后端监听套接字直到交给Uvicorn，避免探测与绑定间竞争。3000占用、数据库未迁移、配置缺失或共享运行锁冲突应按首个错误处理。任何一端启动失败或退出会清理本次另一端；超时和进程回收参数以脚本与Makefile为准。

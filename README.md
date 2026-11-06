# NiumaCrew 牛马工程

NiumaCrew 是用于交流学习的数字员工平台。管理员配置岗位、模型、技能和工具许可，用户通过对话交办工作；平台保存回复、执行过程和交付文件，并提供个人知识库与固定题库专项考核。

## 当前能力

| 能力       | 当前范围                                                                               |
| ---------- | -------------------------------------------------------------------------------------- |
| 员工与大脑 | 岗位指令、共享模型连接、全员规范；支持 Kimi Code、智谱、DeepSeek 聊天预设              |
| 对话与执行 | 流式结果、历史、取消、失败重试、执行证据与 checkpoint 接续                             |
| 技能与工具 | 标准技能包、按需读取、HTTP MCP、可选可信 stdio MCP、员工工具许可与个人账号             |
| 文件       | 附件、受控工作区和正式交付物；命令执行另需已配置并验收的 OpenSandbox                   |
| 知识库     | UTF-8 文本入库、来源阅读、BM25、硅基流动 BGE-M3 向量及混合检索、个人员工知识装配与引用 |
| 员工考核   | BFCL v4 simple_python 400 题专项；固定题库不含用户成绩，不能代表通用岗位能力           |

管理员使用本地密码登录；可选 GitHub OAuth 用于普通成员登录；游客仅浏览公开员工和技能。模型、MCP 和沙箱的真实可用性取决于部署后的凭据、网络及权限配置。

## 本地运行

需要 Python 3.12+、uv、Node.js 22.12+、pnpm 11 和 make。在仓库根执行：

```bash
make setup
make db-upgrade
make admin-create
make dev
```

管理员密码由终端隐藏输入。应用地址为 `http://127.0.0.1:3000`；Ctrl+C 结束本次前后端。数据默认在 `~/.niuma-crew/data`，不会自动导入员工、模型连接或知识资料。启动不需要模型密钥，真实对话前在“大脑”配置连接并绑定员工。

文档站独立运行，不依赖业务数据库或模型：

```bash
make dev-docs
```

访问 `http://127.0.0.1:3001`。应用与文档站分别构建和部署，生产步骤见[部署指南](docs/guides/deployment.md)。

## 验证

```bash
make check          # 文档、静态、类型、离线测试及两个生产构建
make db-check       # 当前环境的数据库与模型差异
```

测试使用独立数据库与确定性替身，不调用真实模型。正式功能的题库、虚构测试样本和测试辅助代码随仓库提供；个人业务库、对话、附件、索引、日志、环境文件与凭据不属于源码。

## 阅读入口

- [平台与功能](docs/product/README.md)、[使用流程](docs/product/workflows.md)
- [系统架构](docs/architecture/overview.md)、[文档索引](docs/README.md)
- [后端配置与维护](docs/guides/backend-operations.md)、[排查指南](docs/guides/troubleshooting.md)
- [前端](frontend/README.md)、[后端](backend/README.md)、[文档站](docs-site/README.md)

当前为单机、文件型 SQLite、单个后端进程。SOP、正式任务计划、多租户和分布式 worker 尚未接入。

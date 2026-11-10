# NiumaCrew

NiumaCrew 是一个用于交流与学习的数字员工平台，探索怎样把个人积累的方法、技能、工具使用经验和知识，沉淀成多人可以使用、共同维护的组织资产。

维护者为一类工作装配共享员工，选择必要的方法、知识和工具操作；使用者提供本次材料与要求。工程围绕最小能力装配，研究智能体的执行机制、知识检索和效果评估。当前已有共享配置与对话入口，经验复盘及发布闭环仍在建设。

## 文档阅读

| 主题       | 入口                                                                                                                                                                        |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 平台介绍   | [平台定位](docs/product/README.md) → [组织资产](docs/product/组织资产.md) → [员工设计](docs/product/员工设计.md)                                                            |
| 开发参考   | [开发入门](docs/engineering/开发入门.md)：技术栈、目录结构、环境设置与设计系统 |
| 架构设计   | [系统架构](docs/architecture/overview.md) → [对话流程](docs/architecture/对话流程.md) → [后端设计](docs/architecture/backend.md)／[前端设计](docs/architecture/frontend.md) |
| 运行机制   | [工具装配](docs/architecture/工具装配.md)、[智能体执行](docs/architecture/执行机制.md)                                                                                      |
| 检索与评估 | [知识检索](docs/architecture/知识检索.md)、[能力评估](docs/architecture/能力评估.md)                                                                                        |
| 使用指南   | [使用流程](docs/product/workflows.md)、[功能范围](docs/product/功能范围.md)、[部署维护](docs/guides/backend-operations.md)                                                  |

完整主题与开发入口见[文档索引](docs/README.md)。文档站复用仓库正文，修改原文后同步发布。

## 主要目录

```text
niuma-crew/
├── AGENTS.md                 # AI 理解工程、执行任务时遵循的约定
├── README.md                 # 项目介绍、启动步骤与主要文档入口
├── Makefile                  # 统一的安装、启动、检查和构建命令
├── backend/                  # 后端服务
│   ├── app/                  # 接口、业务逻辑、智能体执行和数据存储
│   ├── migrations/           # 数据库结构与数据升级脚本
│   ├── tests/                # 后端自动化测试
│   ├── datasets/             # 检索样本、教学资料和考核题库
│   └── experiments/          # 模型、检索和恢复机制的独立实验
├── frontend/                 # 平台的网页界面
│   ├── src/                  # 页面、组件和前端状态管理
│   ├── public/               # 图片、字体等静态资源
│   └── scripts/              # 前端构建与资源生成脚本
├── docs/                     # 产品、开发与维护文档的正文
│   ├── README.md             # 按建设、技术和使用任务查找文档
│   ├── documentation.md      # 文档如何分类、更新和归档
│   ├── product/              # 平台定位、组织资产、员工设计与使用流程
│   ├── guides/               # 开发启动、部署维护、工具接入和排错步骤
│   ├── architecture/         # 系统架构、对话流程、工具、执行、检索与评估
│   ├── reference/            # 功能的权限、状态、限制、错误和兼容规则
│   ├── engineering/          # 开发约定：代码组织、模块依赖、事务和验证
│   ├── design/               # 必要的界面原则与组件查阅
│   ├── learning/             # 学习路线、练习和运行机制导读
│   ├── proposals/            # 待评审或实施中的变更方案与计划
│   └── records/              # 重要设计决定、数据迁移和验证记录
├── docs-site/                # 文档网站与发布脚本，复用仓库 Markdown 正文
├── deploy/                   # 反向代理与沙箱服务的部署配置
├── scripts/                  # 开发启动、文档检查和沙箱初始化脚本
└── diagram/                  # 对话成果交付流程图
```

文档的详细分类与维护规则见[文档规范](docs/documentation.md)，具体文章从[文档索引](docs/README.md)查找。

## 本地运行

需要 Python 3.12+、uv、Node.js 22.12+、pnpm 11 和 make。首次启动按以下步骤执行，命令均在项目根目录运行。已有安装先按[数据库迁移](docs/guides/backend-operations.md#数据库迁移)备份并核对升级条件。

1. 安装依赖并升级数据库：

   ```bash
   make setup
   make db-upgrade
   ```

2. 首次管理配置前初始化管理员；已有管理员可跳过。按终端提示输入密码：

   ```bash
   make admin-create
   ```

3. 启动完整开发环境：

   ```bash
   make dev
   ```

4. 打开[应用](http://127.0.0.1:3000)，使用管理员登录或选择游客浏览。前端固定 3000；后端从 8000 自动避让，实际地址见终端输出，接口文档位于该地址的 `/docs`。Ctrl+C 统一结束本次前后端进程；3000 已占用时直接报错。

按环境变量示例配置后，本地 SQLite 数据库位于 `~/.niuma-crew/data/app.db`，与源码目录分开保存，不会自动导入示例员工。已有 `.env` 不会被上述命令覆盖，文件路径和备份要求见[后端配置说明](docs/guides/backend-operations.md#数据库与本地文件配置)。启动和管理员初始化无需模型密钥；真实对话前，需由管理员在“大脑”中配置模型连接，并将其绑定到可接单的员工。

## 验证

```bash
make check-docs # 文档文件、章节与索引检查
make lint       # 静态、类型和格式检查
make test       # 前后端与开发启动器离线测试
make build      # 前端生产构建
make db-check   # 检查本地数据库与迁移、模型是否一致
```

## 核心流程

1. 创建数字员工：设置岗位、边界、工作指令并选择大脑。
2. 配置员工能力：选择技能、授予工具许可，并按岗位需要固定组织知识范围。
3. 发起会话：从数字员工列表进入并发送消息。
4. 执行并观测：在执行日志中核对模型调用、检索、技能、工具和输出。
5. 核对结果：阅读执行日志、检查知识来源或运行专项考核；长期记忆、定时任务仍为后续能力。

## 文档

- [文档站运行说明](docs-site/README.md)：执行 `make setup-docs`、`make dev-docs`，在 `http://127.0.0.1:3001` 阅读平台介绍、技术解析及使用指南文档；正文复用现有 Markdown。

- [文档索引](docs/README.md)：按任务查阅现行文档、待实施方案与历史记录。
- [总体架构](docs/architecture/overview.md)：当前模块、协作、生命周期与能力边界。
- [前端说明](docs/architecture/frontend.md)：开发、静态交付与工程入口。
- [后端说明](docs/architecture/backend.md)：模块与维护入口，链接配置、账号和迁移指南。

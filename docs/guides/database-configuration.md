# 数据库连接与本地文件配置

本文维护当前行为或操作，历史结果按记录索引查阅；未执行的目标能力不属于本页已实现范围。

## 目标与范围

保留 SQLAlchemy 和 Alembic，先拆开数据库连接与本地文件存储配置。项目处于初期，直接更新配置契约、全部调用方和测试，不保留旧配置别名或回退分支。

本阶段不改变业务表、API、事务策略或数据内容。仍只支持文件型 SQLite；PostgreSQL/MySQL 的字段、索引、并发和数据迁移适配尚未实施，生产数据库选型待定。容器化和 CI/CD 属于后续工作。

## 现状与目标

原配置只保存 SQLite 路径，数据库 URL 由连接层拼装，主密钥和 runner 锁文件名由数据库路径推导。目标是统一以 SQLAlchemy URL 表达连接，密钥和锁分别使用显式路径；改变数据库连接时，不再隐式改变密钥或锁位置。

运行参数及默认值统一维护于[后端配置说明](backend-operations.md#数据库与本地文件配置)。`APP_DATA_DIR` 为本地文件的基准目录，相对路径基于 `backend/`；SQLite URL 内的相对文件路径、密钥文件和锁文件的相对路径基于该目录，绝对路径不受其影响。

## 模块职责与流程

1. `load_config()` 合并 `.env` 与环境变量，后者优先，包括显式空值。解析并校验 URL 和路径，返回绝对路径；不创建目录、不连接数据库、不修改进程环境。空值和不支持的 URL 明确报错，错误不包含原始连接字符串。
2. `DatabaseConfig` 保存 URL 和 SQLite 锁等待设置。当前仅接受 `sqlite+pysqlite` 文件连接；不接受内存库、URI/query 参数或网络连接字段，保持现有 WAL 与事务约束。其他数据库在正式适配前启动失败，不制造已支持的假象。
3. `Database` 持有连接池和事务工具，按 SQLite URL 创建父目录并设置驱动和 PRAGMA。Alembic 在线迁移共用该工具，离线 SQL 使用同一 URL 且不创建数据库文件。
4. `bootstrap` 将独立的主密钥路径交给 `CredentialVault`，将独立的锁路径交给 `Runner`。环境注入主密钥的既有优先级保持不变。
5. Runner 创建锁目录，取得锁后才恢复未结束的执行。同一数据库部署的所有进程必须指向同一锁文件；使用不同路径或不同主机不能相互排斥，仍禁止多个 Uvicorn worker。退出或启动恢复失败时释放锁。

URL 不出现在配置对象的 `repr` 中。主密钥仍不存入数据库或镜像，首次保存才创建文件；已有密文而密钥缺失时继续报错，不生成替代密钥。

## 运行与维护约束

SQLite 数据库应位于本机磁盘。完整消息与执行状态在业务库旁的 checkpoint 文件，例如 app.db 对应 app.checkpoints.db；SDK 自管其表，Alembic 仅管理业务表。迁移、备份或移动数据时先停止后端，同时处理两库及对应模型主密钥；具体步骤见[数据库迁移](backend-operations.md#数据库与本地文件配置)。独立环境使用各自的数据库、存档、密钥与锁文件。

连接使用 Python `sqlite3` 驱动、WAL、外键与 `synchronous=FULL`；显式事务、保存点及 PRAGMA 初始化由[数据库模块](../../backend/app/infrastructure/database/README.md)维护。启用 WAL 时应使用包含 WAL-reset 修复的 SQLite 版本，例如 3.51.3 及以上，见 [SQLite 官方说明](https://www.sqlite.org/wal.html)。

## 历史实施记录

已执行的迁移与检查见历史记录。当前操作仍按前文与[后端指南](backend-operations.md)执行。

## 知识向量索引目录

正式向量使用本地 Chroma，默认目录为业务数据库旁的 `knowledge-vectors/`；`KNOWLEDGE_VECTOR_DIR` 可设置独立持久路径，支持 `~`，相对路径以 `APP_DATA_DIR` 为基准。同一路径只允许一个进程使用。原件和 SQLite 业务数据是重建依据，Chroma 是派生索引；恢复时缺失索引，启动核对会使其变为需重建，不会下载默认模型或自动补收费请求。备份须先停写；恢复完整索引时，业务指针与 Chroma 目录必须来自同一停写批次。

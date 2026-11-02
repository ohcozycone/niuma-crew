# 配置装配事实记录

## `load_config` in backend/app/config.py（L87 至 L157）

**目的：** 将部署来源解析成 AppConfig，为启动器、迁移与应用提供一致配置。

**输入与假设：** backend_dir 是可信路径，默认项目backend目录；环境变量覆盖 dotenv_values 的同名值，含显式空值（L51至L53）。秘密字段不会在本次记录展示。

**输出与效果：** 返回不可变配置对象，不在函数内创建目录、数据库连接或后台任务。模块配置的校验继续由各 dataclass 承担。

**分块顺序：**

1. L89 至 L95 合并来源、解析数据路径和 SQLite URL，校验 busy timeout 文本是否整数。
2. L96 至 L109 解析身份与OAuth，组合密钥路径、前端目录和运行预算。AppConfig.**post_init** 在L47至L48再次检查OAuth来源关系。
3. L110 至 L125 组合MCP部署允许目标、stdio开关和名额。值是否合法还依赖ToolConfig校验。
4. L126 至 L152 组合技能可编辑/不可变目录、持久文件和沙箱配置，路径统一按data_dir解析。文件额度采用int解析，没有在此建立磁盘配额预留。
5. L153 至 L157 组合CI凭证来源。只是配置，不证明凭证有效或远端可用。

**跨函数依赖：** _load_database_url（L68至L84）只接纳文件型sqlite+pysqlite，拒绝内存、URI、认证/主机和连接参数。_resolve_path（L63至L65）展开用户目录并解析相对路径。各模块load/config负责自己的边界，不能据本函数返回便认定外部服务验收通过。

**调用方与共享状态：** bootstrap.create_app使用应用配置；迁移env调用统一数据库配置。_read_values不写os.environ，避免一个测试或加载过程污染另一个配置加载。测试中的Database URL由隔离环境变量覆盖。

**开放问题：** 真实部署环境、凭证、远端连接有效性与运维密钥轮换不在本次审查。部署者直接构造AppConfig时的配置质量由调用方与各配置类型检查负责，不等同于经全部环境文本解析。

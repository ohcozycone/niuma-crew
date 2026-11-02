# 应用生命周期事实记录

## `create_app.lifespan` in backend/app/bootstrap.py（L51 至 L137）

**目的：** 为一个应用生命周期构造数据库、业务服务、执行宿主及后台维护任务。没有这段装配，HTTP 依赖无法取得服务。

**输入与假设：** settings 是 load_config 或调用方提供的 AppConfig，属于部署可信输入。假设某一构造/关闭步骤抛错后仍能释放此前取得资源；当前构造阶段没有外层清理登记，`nothing found`。模型密钥按需使用，不在此读取业务记录。

**输出与效果：** 向 app.state 写服务；启用运行时才启动 Runner、沙箱和文件维护。退出时关闭这些对象及数据库。

**分块顺序：**

1. L52 至 L86 建数据库和各能力服务，设置运行状态；这里没有已进入的 finally。
2. L88 至 L124 创建授权、发布器、checkpoint、准备和请求服务，再创建 Store/Coordinator/Runner。准备与发布由装配层注入执行宿主，执行核心不导入 HTTP 或对话业务。
3. L125 至 L130 进入 try，按 Runner→Sandbox→Files 顺序启动后 yield。start 阶段失败会进入 finally。
4. L131 至 L137 顺序 stop/close。若其中一个 await 抛错，后续语句没有另一个 finally 或异常汇总机制；`nothing found`。

**跨函数依赖：** Database.**init** 创建 engine/sessionmaker；close 调 engine.dispose（session.py L26 至 L38、L65 至 L66）。Runner.start/stop 管文件锁和看护（scheduler.py）；各资源内部可能有自己的清理，但不能替代装配层释放其他独立服务。调用方是 FastAPI lifespan。

**共享状态与约束：** SandboxService 持有查询活跃 Run 的回调；execution_store 在真正启动任务前已赋值。此顺序成立，不能把 L80 的 lambda 误判为构造时访问未初始化 Store。

**验证：** evidence/bootstrap-repro.py 注入 ToolService 构造异常，Database.close 调用为0；注入 Runner.stop 异常，后续沙箱/文件/工具/数据库关闭均未执行。它只验证清理控制流，不测真实远端容器泄漏。

**开放问题：** 各真实 stop 失败或启动失败的资源残留量、远端清理后果未测；需要目标服务故障注入。修复判断在主报告F06，本记录不把假对象结果扩大为真实系统泄漏量。

## `ExecutionCoordinator.run` in backend/app/execution/coordinator.py (L60–L167)

**Purpose:** 看护一次已登记的 Run，决定执行结束、取消、超时或存储故障怎样进入统一发布。它不解释 SDK 消息，也不创建业务正文实体（L70–L112、L153–L163）。

---

**Inputs & Assumptions:**

- `run_id`：可信内部调度标识；`Runner._loop` 从已提交 queued 元数据取得它（scheduler.py L102–L117）。
- 冻结快照为半可信持久数据。入口明确核对协议版本（L71–L72）；运行时限通过 `RuntimeConfig` 正数校验，再由接受流程捕获（config.py L47–L61，preparation.py L114–L129）。
- 当前会话和装配仍有效不靠快照保证，由注入 `authorize` 持续读库（L78、L86–L88，authorization.py L17–L57）。
- `prepare` 返回具有 `execute` 与 `publish_partial` 的策略，由 bootstrap L115–L117 接线和 `ExecutionStrategy` 类型建立；任意第三方插件的行为不在此静态证明范围。
- 隐式输入：started_at、持久状态、UTC 时钟、异步取消、存储可用性。

---

**Outputs & Effects:**

- 返回 None；领取、动作和内容由 Store/Control 事务执行；最终提交由注入 publish 执行（L79、L90–L93、L153–L163）。
- 存储故障将运行放入 pending_failures 且使宿主 degraded；扫描器稍后以 persistence_unavailable 收束（L118–L121，scheduler.py L86–L100）。
- 宿主取消时，可恢复运行保留活动状态等待重启；不可恢复运行拟发布 interrupted（L113–L117）。

---

**Block-by-Block:**

```python
# L74–L81
remaining = row.config_snapshot["run_timeout"]
if row.started_at:
    remaining -= (utc_now() - row.started_at).total_seconds()
async with asyncio.timeout(max(0, remaining)):
    await asyncio.to_thread(self.authorize, row)
    if not await asyncio.to_thread(self.store.claim, run_id):
        finish = False
        return
```

- **What:** 继续使用原开始时间并先授权，再原子领取。
- **Why here:** 重启不能重新获得全额运行时间，未领取成功不能再终结另一个执行者的运行。
- **Assumes:** claim 在事务中检查 queued；store.py L55–L62 建立此条件。
- **Establishes:** 领取成功后本次才拥有执行职责。
- **Depended on by:** 准备、控制对象恢复及执行任务启动（L84–L93）。

```python
# L94–L100
done, _ = await asyncio.wait((execution, watcher), return_when=asyncio.FIRST_COMPLETED)
if watcher in done:
    await watcher
result = await execution
```

- **What:** 任一任务先结束就进入判定，看护的异常优先。
- **Why here:** 同时完成时优先处理已经观察到的停止/存储故障。
- **Assumes:** watcher 无正常完成路径，始终循环或抛错；`_watch` L41–L58 建立。
- **Establishes:** 取得 result 前不忽略本轮已完成的看护错误。
- **Depended on by:** 候选结果合法性和最终 guard（L101–L112）。

```python
# L122–L134
except Exception as error:
    # 错误码白名单检查后：
    status = terminal_status(code)
    if isinstance(error, ExecutionFailure) and (plan is None or plan.publish_partial):
        text = error.partial_text or ""
```

- **What:** 将明确 RuntimeFailure 的可用部分正文转为失败候选，普通异常不补抓最后工具轮。
- **Why here:** 避免未确认输出被兜底提升成正文。
- **Assumes:** 失败候选若含正文，当前仍允许交付。此处和发布器的 failed 分支没有新授权检查；**nothing found**。成功路径在 L110 和 publication.py L42–L51 检查，不能覆盖此分支。
- **Establishes:** 只透传执行器明确提供的部分文字。
- **Depended on by:** finally 中的 Completion.content（L155–L162）。

```python
# L138–L143, L151–L167
for task in (execution, watcher):
    if task and not task.done():
        task.cancel()
await asyncio.gather(*(task for task in (execution, watcher) if task), return_exceptions=True)
```

- **What:** 先停止执行/看护，再提交终态；可恢复停服分支只保存允许进度。
- **Why here:** 进入发布时不再允许并行执行任务继续报告新动作。
- **Assumes:** 底层外部资源响应本地取消；普通模型客户端由 model_session 关闭，准备器 execute 的 finally 释放沙箱/MCP；远端请求的实际撤回没有保证。
- **Establishes:** 本协调器创建的两个 task 已结束。
- **Depended on by:** 调度器回收并发名额和停止生命周期。

---

**Cross-Function Dependencies:**

- `RunStore.load/claim/restore_control`（internal）：各自使用短事务；load 返回脱离 Session 的 Run ORM 与冻结消息（store.py L39–L42），claim 检查 queued 并返回 bool（L53–L61），restore_control 返回技能集合、普通内容与用量构成的恢复 dict（L70–L92）。
- `ConversationAuthorization.check`（external-source-available）：会话/员工/连接/工具许可；只把认证与权限失效转成会话撤权，其余错误保留。
- `ConversationPreparation.execution`（external-source-available）：解析冻结连接、checkpoint 和独占资源，提供执行与清理。
- `PublishRun`（external-source-available）：负责取消优先、终态幂等和业务数据原子提交。失败转义为 PublicationFailure 后，本协调器降级。
- `asyncio.timeout/to_thread/wait`（external-source-available，已安装标准库）：线程取消不能自动撤回已经发生的数据库或远端操作；持久状态检查和发布事务承担结果边界。
- Callers：Runner 扫描器和隔离测试；共享状态为 Run、RunAction、pending_failures 和 ExecutionStatus。

---

**Open Questions:**

- 真实供应商在取消后是否继续收费，以及远端沙箱停止的实际时长，需上游环境验证。
- 失败部分正文与撤权的组合行为，需独立动态复现；分析记录本身不评定严重性。

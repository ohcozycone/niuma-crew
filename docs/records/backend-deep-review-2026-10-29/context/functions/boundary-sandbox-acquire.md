## `SandboxService.acquire` in backend/app/sandboxes/service.py (L128-L173)

**Purpose:** 创建一次 Run 的唯一沙箱申请，在外部创建前持久化意图，失败后仍保留清理责任。

**Inputs & Assumptions:**

- `run_id`：可信运行宿主提供；SandboxResource.run_id 外键及 unique 保证归属存在且仅一条申请。
- `inputs` / `read_file`：可信文件引用和受控读取回调；provider.initialize 按宿主生成路径写入，不把模型路径转主机路径。
- 部署配置：trusted；L129 调用 load_verification 比对端点/镜像/资源与24小时有效证据。

**Outputs & Effects:**

- 返回 SDK handle；DB 状态 requested→ready；调用失败时 close 本地 handle 并 release 远端，未知结果保留债务。

**Block-by-Block:**

```python
# L130-L145
with self.database.transaction() as db:
    reserve_writer(db, SandboxResource.__table__)
    # 拒绝相同 run 的任何既有申请，再检查所有未销毁资源数。
```

- **What:** 同写锁内完成去重和容量检查。
- **Why here:** 两个并发申请不会都看到可用的最后名额。
- **Assumes:** 已 destroyed 的同 Run 也不能重建，这是 L133-L138 显式规则；重试应产生新 Run。
- **Establishes:** 一 Run 一申请，未回收债务占用容量。
- **Depended on by:** L146-L154 保存请求。

```python
# L146-L157
row = SandboxResource(..., state="requested", expires_at=utc_now() + timedelta(seconds=self.config.ttl_seconds))
# db.flush；退出事务提交
handle = self.provider.create(self.metadata(row))
```

- **What:** commit 意图后发出 SDK 创建。
- **Why here:** create 超时也有 metadata 可在重启后找回资源。
- **Assumes:** 精确 metadata 能在管理服务识别本申请；SDK/server 查询语义未真实上游验收。
- **Establishes:** 远端成功但本机不知道时仍有清理线索。
- **Depended on by:** `_destroy` L188-L198 对未知创建处理。

```python
# L158-L173
current.remote_id, current.state = handle.id, "ready"
self.provider.initialize(handle, inputs, read_file)
# 任意 BaseException：handle.close（若有），release(run_id)，再抛。
```

- **What:** 保存远端ID后初始化只读输入；任何失败都回收而不重试创建。
- **Why here:** 初始化失败也不能丢掉远端资源ID。
- **Assumes:** release 对实际 kill 失败会留债，`_destroy` L205-L210 保证该路径；数据库自身不可写时没有第二存储保证。
- **Establishes:** 正常返回具备初始化工作区；异常路径尝试清理。
- **Depended on by:** RunSandbox.acquire 的线程锁保证同本地资源只 acquire 一次。

**Cross-Function Dependencies:**

- `load_verification`（internal，provider.py L139-L175）：检查受信部署文件，不把 Agent 自报当主机证明。
- `OpenSandboxProvider.create`（internal，provider.py L75-L84）：固定镜像、资源、deny 网络、无隐藏重试；SDK 外部副作用。
- `initialize`（internal，provider.py L107-L136）：root只负责建目录和只读输入，实际命令UID/GID1000由Agent backend执行。
- `release/_destroy`（internal，L175-L210）：基于精确metadata查询、kill，超时/未知保留cleanup/unknown。
- Shared state：maintenance `sweep` L212-L220 在非active或过期时触发 release；active IDs 由 execution store 注入，不反向导入该模块。

**Open Questions:**

- 创建/初始化超过TTL并与维护同时进行的交错，现有测试没有覆盖；未复现，保持为测试缺口，不判定为实际泄漏。
- 真实 runsc/磁盘/网络证据没有在本次离线评审执行。

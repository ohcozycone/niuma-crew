## `FileService.save` in backend/app/files/service.py (L47-L109)

**Purpose:** 把已收到的有限字节存成不可变对象，再登记元数据；HTTP 上传和 Agent 产物共用这一入口。

**Inputs & Assumptions:**

- `data: bytes`：不可信内容；L57-L58 校验单文件上限。上传路由在 `api/routes/files.py` L24-L30 已按相同上限限流式接收。
- `owner_id` / `run_id`：可信宿主提供；数据库外键检查真实身份与 Run 存在；本函数不判断调用者是否能访问这些身份，由路由或运行宿主负责。
- `name`：不可信，`safe_name` L22-L26 去掉目录、拒绝控制符及点路径，并裁到180字符。
- 目录为受部署者控制的本机路径，来自构造函数 L40-L42；磁盘余量预查 L62-L64 不是并发磁盘空间预留。

**Outputs & Effects:**

- 返回 `file_ref` 白名单；写本地对象、StoredFile 元数据；L77 的事务退出成功后才把返回值交给调用方。
- 已知数据库拒绝后 UUID 字节是否立即删除：nothing found；L107-L109 只清理旧临时路径。

**Block-by-Block:**

```python
# L57-L64
if len(data) > self.config.max_file_bytes:
    raise InvalidInputError("file_too_large", "文件超过上传或产物大小上限。")
```

- **What:** 在写盘前检查单个对象、名称和文件系统空间。
- **Why here:** 拒绝无需创建对象的输入。
- **Assumes:** 多个写入的总空间由操作系统最终决定；预查后空间仍可能变化。
- **Establishes:** 单对象大小有界。
- **Depended on by:** 后续磁盘写入与内存哈希。

```python
# L67-L71
stream.write(data)
stream.flush()
os.fsync(stream.fileno())
os.replace(temporary, self.directory / key)
```

- **What:** 先保证字节可靠，再以随机键发布；L72-L76 同步父目录。
- **Why here:** DB 引用不会先于字节出现。
- **Assumes:** 配额拒绝后的已发布字节能由后续清理收回；L185-L192 仅在超过 retention 后扫孤立字节。
- **Establishes:** final key 可用于之后的元数据引用。
- **Depended on by:** L94-L105 登记元数据。

```python
# L77-L85
with self.database.transaction() as db:
    reserve_writer(db, StoredFile.__table__)
    # 按 owner 求和后比较 max_owner_bytes。
```

- **What:** 串行检查账号配额，L86-L93 同样检查 Run 配额，然后插入。
- **Why here:** 取得 SQLite 写锁后读取，防止两个成功保存一起突破账面总量。
- **Assumes:** 被拒绝数据不会持续占用物理总量：nothing found；当前只保证 metadata 账面总量。
- **Establishes:** 成功登记的用户/Run 字节总量受限。
- **Depended on by:** `capture` 和发布流程只引用登记成功的文件。

**Cross-Function Dependencies:**

- `Database.transaction`（internal，session.py L55-L63）：成功 commit、异常 rollback 并释放；不会回滚本机文件。
- `reserve_writer`（internal，transactions.py L8-L18）：零匹配 UPDATE 先取写入资格，锁随当前事务释放。
- `file_ref`（internal，service.py L29-L37）：白名单不输出 storage_key 和宿主目录。
- `sweep`（internal，L155-L192）：按保留期回收元数据和无元数据字节。
- Callers：`api/routes/files.upload`、`conversations/preparation.py` 注入的产物保存回调；调用者把返回 ref 关联业务。

**Open Questions:**

- 对 crash/commit 结果未知与明确 quota rollback，是否需要分别保留/立即删除 UUID 字节？这是随后评审的策略问题。

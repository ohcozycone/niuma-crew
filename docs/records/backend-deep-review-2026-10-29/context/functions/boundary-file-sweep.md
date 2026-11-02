## `FileService.sweep` in backend/app/files/service.py (L155-L192)

**Purpose:** 分批回收过期且业务不再引用的文件记录/字节，并补偿磁盘与DB之间的孤立对象。

**Inputs & Assumptions:**

- `retained(db, candidates)`：可信注入回调。conversations/files.py L14-L29 保留消息关联、活动Run和工具结果/来源引用；files 不反向认识对话模型。
- retention 是部署配置，FileConfig L17-L25 保证正整数。
- `cleanup_after` 为实例游标；由单个 maintenance 循环拥有（L197-L201），没有跨进程分布式清理锁。

**Outputs & Effects:**

- 删除最多128条候选元数据；之后删除对应文件。
- 对所有已登记storage_key建集合，再扫描整个目录找过期孤立字节；这部分不是128项有界批次（L183-L192）。

**Block-by-Block:**

```python
# L158-L175
with self.database.transaction() as db:
    reserve_writer(db, StoredFile.__table__)
    # 按 created_at/id 游标读取最多128项，调用 retained。
```

- **What:** 写锁内按稳定顺序检查候选和业务引用。
- **Why here:** 业务关联写入不能在这次检查后抢先提交。
- **Assumes:** 其他引用创建也经过相同数据库；retained 回调没有外部IO，实际实现只SQL查询。
- **Establishes:** 本批候选是否可回收是在同一事务内决定。
- **Depended on by:** L176-L179 删除记录。

```python
# L176-L181
if row.id not in keep:
    removed.append(row.storage_key)
    db.delete(row)
# 事务成功后逐个 unlink。
```

- **What:** 先撤掉DB引用，再删字节。
- **Why here:** unlink失败或进程崩溃时，剩余对象仍可由孤立扫描回收。
- **Assumes:** storage_key 是宿主随机UUID，来自 save L60/L101。
- **Establishes:** 不删除仍有元数据的有效对象。
- **Depended on by:** 孤立扫描及下一轮维护。

```python
# L183-L192
known = set(db.scalars(select(StoredFile.storage_key)))
# 非known、普通非软链接、mtime过期才unlink。
```

- **What:** 处理写字节后DB未提交、删记录后unlink未完成等孤立情况。
- **Why here:** SQLite与本机字节没有共同事务。
- **Assumes:** 正在 save 的字节不会早于保留期；没有活动保存键集合或额外持久预留，nothing found。默认24小时远大于普通事务等待，短retention仍需另验。
- **Establishes:** 孤立字节最终可回收，但已知拒绝也会保留到retention。
- **Depended on by:** 文件生命周期的最终回收。

**Cross-Function Dependencies:**

- `retained_file_ids`（internal callback，conversations/files.py L14-L29）：维护业务引用集。
- `Database.transaction/reserve_writer`：与 save/capture发布等同库协作。
- `start/stop`（internal，L194-L214）：定期异步转线程，维护失败只写固定warning，不泄露内容；停止等待当前循环结束。

**Open Questions:**

- 已登记文件量及目录对象非常大时，全量known集合与全目录扫描的耗时/内存未压测；不能因DB候选128项就宣称完整维护有界。

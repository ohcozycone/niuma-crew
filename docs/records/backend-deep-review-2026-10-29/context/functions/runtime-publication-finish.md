## `PublishRun.finish` in backend/app/conversations/publication.py (L33–L78)

**Purpose:** 把一个普通完成意图变成业务可见结果，保证状态、CI 报告或输出文件、Message 正文和活动占用一起提交（L54–L78）。

---

**Inputs & Assumptions:**

- `db: Session`：可信调用方事务。`PublishRun.__call__` L82–L86 在取得写入资格后调用；请求服务取消 queued 时也使用同一调用方写事务（api service L237–L246）。
- `row: Run`：该事务中的持久实体；`intent: Completion` 为受信运行器的候选，不等于已经交付。
- 原运行、用户、员工与消息归属一致由 `bind_run` 和 `publish_conversation` 两端检查（writes.py L58–L66、L95–L101），同对话外键由 models.py L69–L74 建立。
- 输入的输出文件属于本次执行，不能只信任引用；L64–L73 重新读文件行并核对 owner、origin、purpose 和 hash。
- 隐式输入：最新状态、授权、文件行、专业结果和当前业务事务。

---

**Outputs & Effects:**

- 返回 None；非活动 Run 不写入。取消中转 cancelled；CI 非成功禁止部分正文；成功空正文被拒绝（L34–L53）。
- 调用 Store 写终态、专业记录/文件关系、对话正文与占用，并 flush；commit 归调用方（L54–L78）。任何后续错误通过外层事务回滚，不形成半交付。

---

**Block-by-Block:**

```python
# L34–L41
if row.status not in ACTIVE:
    return
if row.status == "cancelling":
    intent = replace(intent, status="cancelled", content=None, error=None, structured=None)
if intent.status != "succeeded" and not row.config_snapshot.get("allow_partial_output", True):
    intent = replace(intent, content=None, structured=None)
```

- **What:** 优先终态幂等和持久取消，再执行专业部分输出规则。
- **Why here:** 不让迟到成功复活已停止运行，CI 失败不能带走未经校验的报告。
- **Assumes:** caller 在读状态前取得同库写入资格；两条正式调用路径均建立。
- **Establishes:** 取消中的运行不会交付候选文字或专业数据。
- **Depended on by:** 后续终态与正文写入。

```python
# L42–L51
if intent.status == "succeeded":
    try:
        self.authorize(row, db=db)
    except Exception as error:
        if not hasattr(error, "code"):
            raise
        code = error.code
        intent = replace(intent, status=terminal_status(code), error=code, content=None, structured=None)
```

- **What:** 只对成功意图做同事务现行授权，已分类错误改为无正文失败，程序错误抛出。
- **Why here:** 外部调用完成与授权失效可能先后发生，最终提交必须使用当前许可。
- **Assumes:** 对含部分正文的 failed 意图，授权由其他路径足够新地建立。针对提交点的证明：**nothing found**；协调器失败分支也没有最后 guard（coordinator.py L122–L134）。
- **Establishes:** 成功候选交付时有本事务中的授权依据。
- **Depended on by:** 下方正式正文、文件关系和 CI 报告。

```python
# L54–L58, L77–L78
RunStore.finish(db, row, intent)
if row.config_snapshot.get("ci"):
    from app.ci_diagnosis.service import publish_diagnosis
    publish_diagnosis(db, row, intent.structured)
self.publish_content(db, row, intent.content)
db.flush()
```

- **What:** 先用确定终态决定专业交付，再写对话和释放活动关联。
- **Why here:** 专业发布器检查的是更新后的状态，但仍在同事务，不能被外部读到中间状态。
- **Assumes:** 被调用者不自行 commit。已读 RunStore.finish、publish_diagnosis 和 publish_conversation，均只使用当前 Session。
- **Establishes:** 若调用方提交成功，Run、Message、专业记录及占用一致。
- **Depended on by:** 查询和 SSE 只读已提交快照。

---

**Cross-Function Dependencies:**

- `RunStore.finish`（internal-source-available）：验证终态、关闭未完步骤、未知用量和版本。
- `publish_diagnosis`（external-source-available）：成功时再次校验 Draft 引用；不成功时不写 report。
- `publish_content` 默认 `publish_conversation`（external-source-available）：验证归属、释放占用、保存正文。
- `ConversationAuthorization.check`（external-source-available）：会话、装配、模型修订、CI 范围和实际用过的工具。
- Callers：后台 publish 和 queued cancel；共享状态还有停止命令、进度更新与文件清理，需要同数据库写事务串行。

---

**Open Questions:**

- failed 部分正文没有提交点授权的影响需动态验证；分析记录不预先评价。
- 来源语义和模型根因判断是否正确不是此函数能证明的条件。

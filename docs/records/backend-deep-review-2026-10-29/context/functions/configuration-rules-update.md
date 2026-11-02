## `OrganizationRulesService.update` in backend/app/organization_rules/service.py (L28-L47)

**Purpose:** 将部署唯一规则替换为客户端正文，只有客户端读到的revision仍有效时成功；避免覆盖其他编辑者刚保存的规则。

**Inputs & Assumptions:**

- data.instructions：管理员输入；Pydantic严格字符串、≤20000字符，纯空白归一为空字符串（schemas.py:L11-L18）。
- data.revision：严格非负整数（schemas.py:L13）。字段名为revision，其调用语义是客户端预期版本。
- 路由先检查organization_rules:update能力，本服务没有Actor（`backend/app/api/routes/organization_rules.py:L24-L32`）。
- migration已创建id=1的规则行；current_rules在缺行时抛RuntimeError，不自行建默认数据（service.py:L13-L17）。数据库有id=1、revision≥0和长度CHECK（models.py:L14-L18）。

**Outputs & Effects:**

正常返回OrganizationRulesRead；真实正文变化时revision加1并更新时间。保存事务由Database.transaction提交/回滚；本函数无外部调用、不生成模型提示词、不更新员工或Run（L29-L47）。

---

**Block-by-Block:**

```python
# L29-L40
with self.database.transaction() as session:
    result = session.execute(
        update(OrganizationRules)
        .where(OrganizationRules.id == 1, OrganizationRules.revision == data.revision)
        .where(OrganizationRules.instructions != data.instructions)
        .values(instructions=data.instructions,
                revision=OrganizationRules.revision + 1, updated_at=utc_now())
    )
```

- **What:** 第一条数据库操作是带版本条件和正文不同条件的UPDATE。
- **Why here:** 不先读取旧版本，SQLite无须升级已经过时的读快照；竞争写会在该写语句串行。
- **Assumes:** 调用开始前没有共享Session；Database.transaction每次建立独立Session（`backend/app/infrastructure/database/session.py:L55-L63`）。
- **Establishes:** 匹配一行时只有同revision且不同正文会更新；两个相同预期版本、不同正文的竞争者不能都成功递增。
- **Depended on by:** 后面读当前行区分“本来就没变化”和“预期版本已经过时”。

```python
# L41-L47
row = current_rules(session)
if not result.rowcount and row.revision != data.revision:
    raise ConflictError("rules_revision_conflict", "规章制度已被其他管理员修改，请核对最新版本后再保存。")
return OrganizationRulesRead.model_validate(row)
```

- **What:** 在同一事务读取当前值。无更新且revision不同才报冲突；无更新且revision相同返回不变内容。
- **Why here:** rowcount=0有两种业务含义，不能一律报冲突；缺行仍由current_rules视为迁移/数据库异常。
- **Assumes:** 数据库在同一事务内保持已写入状态可见；模型read DTO从ORM属性读取（schemas.py:L21-L26）。
- **Establishes:** 相同正文+相同revision不递增；相同正文+旧revision仍冲突。返回表达式计算后with退出才提交，提交失败不会给调用方一个正常成功结果。
- **Depended on by:** API返回revision供下一次PUT，conversations只在接受新运行时读取当前规则并冻结（preparation.py:L75-L112）。

**Cross-Function Dependencies:**

- `current_rules`（internal，L13-L17）：按主键1查找，缺行抛RuntimeError；并没有把缺行默认为空规则。
- `utc_now`（external-source-available，infrastructure/database/fields.py）：提供有时区UTC时间，具体持久化格式由UTCDateTime定义。
- `Database.transaction`（session.py:L55-L63）：成功commit、异常rollback；SQL忙/锁异常在HTTP统一转换，当前函数未将所有DB错误包装为版本冲突。
- `ConversationPreparation.prepare`（conversations/preparation.py:L75-L112）：把rules正文、revision、updated_at一起捕获到Run；规则服务没有把更新推送到已接受Run。
- 调用方：组织规则GET/PUT路由（routes/organization_rules.py:L15-L32），后台准备通过current_rules用调用方Session读取。

**Open Questions:**

- 修改规章制度是否应撤销已经接受的运行，需要产品语义；本函数只维护当前版本，未找到全员Run撤销机制，不把“未找到”当作缺陷结论。
- 本次隔离测试未模拟真实断电；SQLite FULL同步设置是实现事实，不构成已完成灾难恢复演练的证明。

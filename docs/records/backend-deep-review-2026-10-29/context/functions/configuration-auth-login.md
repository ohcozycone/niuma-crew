## `AuthService.login` in backend/app/auth/service.py (L88-L128)

**Purpose:** 将已校验的本地管理员密码转换成可撤销的服务端会话；HTTP Cookie 由调用路由处理（`backend/app/api/routes/auth.py:L167-L176`）。

**Inputs & Assumptions:**

- username/password：不可信输入；HTTP Pydantic 限定为严格字符串，长度上限64/128（`backend/app/api/routes/auth.py:L24-L26`）。本函数不采用创建账号的用户名正则，失败统一返回凭证错误。
- old_token：不可信 Cookie；只做摘要并在当前事务撤销匹配会话，不被解释为当前已登录身份（L111-L116）。
- database/config/clock：构造时注入（L45-L48）；数据库 transaction 确保异常回滚、成功提交、关闭 Session（`backend/app/infrastructure/database/session.py:L55-L63`）。
- 账号 password_hash 可被 pwdlib 正常读取：应用创建路径使用 hash_password（L34-L37、L50-L61），User CHECK 约束仅保证管理员非NULL，并不校验哈希格式（`backend/app/auth/models.py:L23-L27`）。直接损坏数据库哈希的自动修复：nothing found。

**Outputs & Effects:**

返回 Actor 和随机 token（L128）；数据库只保存 token_digest，旧 token 可被撤销（L111-L123）。身份 Actor 在 flush 得到会话ID之后建立（L125-L127），实际返回发生在事务上下文退出之后。

---

**Block-by-Block:**

```python
# L89-L94
username = username.strip().lower()
with self.database.transaction() as db:
    user = db.scalar(select(User).where(User.username == username, User.role == "admin"))
valid = PASSWORDS.verify(password, user.password_hash if user else DUMMY_HASH)
if not valid or user is None or not user.is_active:
    raise AuthenticationError("invalid_credentials", "用户名或密码错误。")
```

- **What:** 只找同名管理员，读事务退出后计算密码。
- **Why here:** 密码计算在取得写锁之前；不存在的账号仍做 dummy hash 校验。
- **Assumes:** 密码哈希来自可信账号创建/维护路径，Session 提交后 ORM 属性可读取；后者由 expire_on_commit=False 建立（`session.py:L38`）。
- **Establishes:** 此刻读到的启用账号匹配密码；尚不说明写入会话时账号仍有效。
- **Depended on by:** 条件 UPDATE 必须带旧 password_hash 才能确认同一凭证。

```python
# L95-L110, predicate excerpt
now = self.clock()
token = secrets.token_urlsafe(32)
with self.database.transaction() as db:
    confirmed = db.scalar(
        update(User)
        .where(User.id == user.id, User.password_hash == user.password_hash, User.is_active.is_(True))
        .values(updated_at=User.updated_at)
        .returning(User.id)
    )
    if confirmed is None:
        raise AuthenticationError("invalid_credentials", "用户名或密码错误。")
```

- **What:** 在首个写语句重新检查密码与启用状态；这里无业务字段变化。
- **Why here:** SQLite 写资格在随后撤销/签发会话之前取得，密码维护路径先写账号，再撤销会话（L72-L86），双方串行。
- **Assumes:** 当前数据库是 SQLite 同步短事务；实际连接启用 WAL、foreign_keys 和 FULL 同步（`session.py:L40-L53`）。
- **Establishes:** 事务中签发依据仍与已验证账号一致。
- **Depended on by:** 后续 AuthSession 可以指向该账号，不会从此前读取直接跳过并发复核。

```python
# L111-L128, structural excerpt
if old_token:
    db.execute(update(AuthSession).where(AuthSession.token_hash == token_digest(old_token)).values(revoked_at=now))
session = AuthSession(kind="user", user_id=user.id, token_hash=token_digest(token),
                      created_at=now, last_seen_at=now,
                      expires_at=now + timedelta(seconds=self.config.max_age_seconds))
db.add(session)
db.flush()
actor = self._actor(session, user)
return actor, token
```

- **What:** 旧会话撤销与新会话创建共享事务，返回发生在 with 外（原文L128）。
- **Why here:** 避免响应发出一个未提交的会话，也避免只撤销成功却未签发成功。
- **Assumes:** token_digest 用SHA-256，随机token来自secrets（L23-L24、L96）；唯一约束兜底（models.py:L65）。
- **Establishes:** 返回成功意味着事务已提交。提交故障、唯一冲突等不在这里伪装为凭证错误。
- **Depended on by:** write_cookie 仅在 login 正常返回后调用（route auth.py:L174-L175）。

**Cross-Function Dependencies:**

- `PasswordHash.verify`（external-black-box）：本次未逐行审计 pwdlib/Argon2 源码；依赖其密码验证，未把它当作可保证固定耗时的证明。
- `token_digest`（internal，L23-L24）：只产生摘要；`_actor`（L199-L208）只投影可信账号/会话，无数据库或HTTP副作用。
- `Database.transaction`（external-source-available，session.py:L55-L63）：成功提交，失败回滚；不能把 _actor 已建立误当提交成功。
- 调用方路由先做来源级和用户名级限流，再写 Cookie（routes/auth.py:L169-L175）；本机维护与初始化通过 CLI 进入（auth/cli.py:L36-L44）。
- 共享状态：maintain_user 可改密码/启用并撤销会话；resolve/_validated_actor 在每次请求检查撤销、期限和账号（auth/service.py:L210-L252）。

**Open Questions:**

- 配置的密码策略与真实身份风险是否匹配，需要产品与部署环境决定；本次只记录当前8～20字策略（L34-L37）。
- 真实 pwdlib 的异常类型、极端损坏哈希和实现内部资源使用未逐行分析；当前代码没有把这些异常改成 invalid_credentials。

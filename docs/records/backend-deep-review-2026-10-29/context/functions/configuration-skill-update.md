## `SkillService.update` in backend/app/skills/service.py (L389-L464)

**Purpose:** 保存 Skill 的平台字段或整包内容，将文件目录替换与数据库修订校验组合成一个可在异常时恢复的操作。

**Inputs & Assumptions:**

- skill_id：HTTP UUID 经过字符串化（`backend/app/api/routes/skills.py:L122-L128`），受管理员能力保护；service 本身没有 Actor。
- data：经过 SkillPatch 校验；预期修订必填、严格正整数，省略字段用 model_fields_set/exclude_unset 区分（`backend/app/skills/schemas.py:L70-L82`）。
- 可编辑目录/字节库：构造时分开，禁止二者根目录完全相同（service.py:L46-L57）；平台目录写入需要库文件锁（library.py:L44-L52）。
- 旧 DB 内容和 manifest：来自发布路径；本函数要求 blob 存在并通过哈希验证（packages.py:L295-L306）。丢失 blob 的自动重建：nothing found。

**Outputs & Effects:**

返回 SkillRead；修改时可能先写无引用 blob、再替换可编辑源目录、最后更新 DB。数据库事务失败时目录恢复；强制杀进程/掉电的跨存储原子恢复不由本函数保证（library.py:L129-L157）。

---

**Block-by-Block:**

```python
# L390-L395
current = self.get(skill_id)
changes = data.model_dump(exclude_unset=True, exclude={"expected_revision", "package_files"})
if "name" in changes and changes["name"] is None:
    changes["name"] = current.protocol_name
```

- **What:** 读取当前发布版本，识别实际提交字段，空别名恢复标准名。
- **Why here:** 后续文件替换需要旧主文和 manifest 的 fingerprint；单独清别名不触碰包。
- **Assumes:** 初次读取并非排他锁，不能当作最终修订授权；最终检查由 _update_record 重做。
- **Establishes:** changes 只代表本次显式提交。
- **Depended on by:** 后续决定是否需要读取和保存整包。

```python
# L396-L420, structural excerpt
if "skill_md" in data.model_fields_set or "package_files" in data.model_fields_set:
    current = self.get(skill_id)
    if current.revision != data.expected_revision:
        raise ConflictError(...)
    files = self._files_input(data.package_files) if "package_files" in data.model_fields_set else {...}
    # L413-L419 compare dual sources, then replace SKILL.md
    changes.update(self._package(files))
```

- **What:** 整文件集合或主文更新会重建完整包；同时提交两份 SKILL.md 时必须一致。
- **Why here:** 耗时文件解析/摘要和 blob 写入在数据库写事务前完成。
- **Assumes:** _files_input 检查路径重复，decode_file 检查文本/Base64互斥（service.py:L96-L103；packages.py:L154-L165）；_package 再校验整体路径、大小和主文（service.py:L83-L94；packages.py:L168-L188）。
- **Establishes:** changes 中的主文、instructions、description、manifest 来自同一包；失败可能留下无引用blob，不会先发布DB引用。
- **Depended on by:** 数据库保存与目录替换使用同一 files 内容。

```python
# L421-L438, structural excerpt
with self.library.locked(), ExitStack() as filesystem:
    if "package_manifest" in changes:
        name = parse_skill_md(changes["skill_md"])["name"]
        if current.source_path and current.source_path != name:
            raise ConflictError(...)
        filesystem.enter_context(self.library.replace(name, files, fingerprint(self._published_files(current)) if current.source_path else None))
        changes["source_path"] = name
```

- **What:** 禁止已关联目录改标准名，比较当前目录与已发布fingerprint，暂存/替换整目录。
- **Why here:** 文件锁保持到DB提交以后；外部已完成的编辑会形成冲突，不被静默覆盖。
- **Assumes:** 外部安装器不共享平台锁（library.py:L3-L5）；read(name) 拒绝链接、特殊文件、超限包，replace 比较 expected（library.py:L68-L101、L120-L128）。
- **Establishes:** 当前Python上下文拥有用于回滚的旧目录；不是跨存储崩溃事务日志。
- **Depended on by:** _update_record 抛出异常时 ExitStack 触发 replace 的异常恢复分支。

```python
# L439-L464, structural excerpt
elif any(key in changes for key in (...)):
    with self.database.transaction() as session:
        legacy = not require_skill(session, skill_id).skill_md
    if legacy:
        source = legacy_skill_md(SimpleNamespace(**{**current.model_dump(), **changes}))
        filesystem.enter_context(self.library.replace(...))
        changes["source_path"] = current.source_path or current.protocol_name
with self.database.transaction() as session:
    return self._update_record(session, skill_id, data, changes)
```

- **What:** 旧内容入口按需编译源目录；最终保存统一经过 _update_record。
- **Why here:** 标准包和旧表单共用存储与revision逻辑，不生成第二份共享技能。
- **Assumes:** _update_record 在首读前 reserve_writer（L466-L468），重新检查修订（L469-L473），参数规范更新预检启用关系（L474-L480），标准包拒绝独立旧字段覆盖（L481-L499）。
- **Establishes:** 同一事务真实变化时revision+1、setattr、flush并生成响应（L500-L508）；return 表达式先计算，事务上下文随后提交，提交异常可向外触发目录恢复。
- **Depended on by:** API 只有正常返回才发出更新响应。

**Cross-Function Dependencies:**

- `get/_response`（internal，L254-L260、L62-L81）：读发布状态与关联数量，主文解析失败不伪造空包。
- `_published_files`（L142-L148）从当前主文和不可变blob组文件；`SkillBlobStore.read` 确认内容hash，缺失为NotFoundError，损坏为package_error。
- `SkillLibrary.replace`（external-source-available，library.py:L116-L157）：抛异常时删除新目录并恢复旧目录，finally删暂存；目录锁由更外层持有。
- `validate_parameters`（parameters.py:L45-L62）：只允许JSON对象、≤16KiB，并依规范校验；失败不回显参数。
- 其他共享写入：create/delete/sync_library 均持同一库锁（service.py:L129、L152、L511），其DB事务仍各自完成。

**Open Questions:**

- 外部安装器在fingerprint检查之后、目录rename之前修改文件时的实际行为，本次没有并发复现；锁不约束它们。
- kill -9/掉电发生在目录已替换、DB未提交时的恢复需要人工核对；本次未做崩溃恢复演练。

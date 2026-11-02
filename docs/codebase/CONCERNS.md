# 风险、差异与调查边界

调查日期：2026-10-31。仅记录本次有证据的问题、实现限制和待验证项，不把历史建议或目录命名当缺陷。风险等级是本次工程判断，不代表已发生生产事故。架构事实见 [ARCHITECTURE](ARCHITECTURE.md)，实际测试见 [TESTING](TESTING.md)。

## 1. 优先风险

| 优先级             | 已确认事实 / 推断                                                                                     | 影响与建议                                                                                                                                                                                                                                                                          |
| ------------------ | ----------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 中：索引恢复缺口   | **已确认且隔离复现：** search 拒绝旧 lexical_version；upload 对相同 hash 直接返回旧文档，未重建索引   | “重新导入”提示不足以恢复；当前须先删除旧文档再上传。建议后续设计重建入口或使重复上传识别旧版本，另补回归测试。证据：[service.py](../../backend/app/knowledge/service.py) `existing`:L231、`upload`:L257、`search`:L377                                                              |
| 部署约束：单宿主   | **已确认：** SQLite 文件库与 fcntl 本机锁，不存在跨主机租约/独立 worker                               | 不能仅增加应用副本扩容；同库进程若误配不同锁文件会绕过本机互斥。后者为**推断**，本次未进行破坏性并发实验。[scheduler.py](../../backend/app/execution/scheduler.py):L30、[config.py](../../backend/app/config.py):L100                                                               |
| 运维完整性         | **已确认：** 业务库、checkpoint、原件、Skill blob 与密钥分开保存；**推断：** 单备份业务库无法完整恢复 | 沿现有[备份指南](../guides/backend-operations.md)做协调恢复演练；本次未验证部署备份。[checkpoints.py](../../backend/app/agent_runtime/checkpoints.py):L45、[files/service.py](../../backend/app/files/service.py):L47、[skills/service.py](../../backend/app/skills/service.py):L49 |
| 外部副作用不确定性 | **已确认：** 已有非 readonly 调用不允许恢复重放，未知沙箱创建继续占用容量                             | 属于安全失败策略；用户需核对远端结果后重试，不能承诺 exactly-once。真实上游故障恢复是 `[TODO]`。[store.py](../../backend/app/execution/store.py):L319、[sandboxes/service.py](../../backend/app/sandboxes/service.py):L184                                                          |

### 已复现：重新上传不更新过期索引

1. 在正式迁移建立的临时库中，经 API 建立知识库并上传一份 Markdown，取得 document id。
2. 仅在隔离数据库把该 LibraryDocument.lexical_version 改为 `obsolete-probe-version`，模拟依赖/分词版本变化；检索返回 409 knowledge_index_outdated。
3. 用新的 client_request_id 重传完全相同的字节，API 返回 201、document id 与原文档相同；再次检索仍返回同一个 409。

相关测试代码要点如下，复用 [test_knowledge_library.py](../../backend/tests/test_knowledge_library.py) 的 create/upload 和 [conftest.py](../../backend/tests/conftest.py) 的 api_client；以 `PYTHONPATH=tests:. .venv/bin/python -m pytest -p conftest /tmp/niuma_codebase_probe.py -q` 可运行临时用例。

```python
from sqlalchemy import update
from app.knowledge.models import LibraryDocument
from test_knowledge_library import create, upload


def test_same_content_reupload_does_not_rebuild_outdated_index(api_client):
    kb = create(api_client)["id"]
    first = upload(api_client, kb).json()
    with api_client.app.state.database.transaction() as db:
        db.execute(
            update(LibraryDocument)
            .where(LibraryDocument.id == first["id"])
            .values(lexical_version="obsolete-probe-version")
        )
    again = upload(api_client, kb)
    assert again.status_code == 201 and again.json()["id"] == first["id"]
    result = api_client.post(f"/api/knowledge-bases/{kb}/search", json={"question": "一等座"})
    assert result.status_code == 409
    assert result.json()["detail"]["code"] == "knowledge_index_outdated"
```

lexical_version 包含 jieba 包版本、字典 hash 和 SQLite 版本，因此不只有修改业务分词规则才触发过期：[lexical.py](../../backend/app/knowledge/lexical.py) `lexical_version`:L21。上述是条件成立时的恢复缺口，不表示当前开发库已经过期。本次未修业务代码。

## 2. 技术债与维护负担

| 项目                    | 代码事实及未知原因                                                                                                              | 建议及边界                                                                                                 |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| SkillService 多介质协作 | [service.py](../../backend/app/skills/service.py) 567 行，包解析、目录同步、CRUD 与跨文件/DB 更新集中；选择原因没有追溯提交历史 | 修改时沿 library.replace/fingerprint/事务回滚测试，不按行数直接拆分；复杂度风险为推断                      |
| 查询与投影集中          | [conversations/queries.py](../../backend/app/conversations/queries.py) 549 行，承担历史、回复、问题目录及 DTO 读取              | 修改一类投影时核对历史、重试和 SSE 的共同版本含义                                                          |
| MCP 定义入口较大        | [definitions.py](../../backend/app/tools/definitions.py) 521 行，接入格式、定义生命周期与配置校验相连                           | 以真实变更原因拆职责；不能据体量断言存在性能缺陷                                                           |
| 类型检查非全量          | mypy 仅显式 files，follow_imports=silent；前端 TS strict 已开                                                                   | 当前未覆盖 Python 文件不等于无类型错误；按风险逐步扩大，[pyproject.toml](../../backend/pyproject.toml):L64 |
| 测试旧协议适配          | [scenario_client.py](../../backend/tests/scenario_client.py) 翻译旧场景断言，而正式路由已使用 reply 模型                        | 新契约测试使用真实 wire；维护时避免把适配字段当正式接口                                                    |

本次只在 `backend/app`、`frontend/src`、正式脚本的 Python/TS/TSX/MJS 中检索生产 TODO/FIXME/HACK（排除测试），未匹配。根扫描匹配的是历史证据内引文，不是生产待办；不能据“无标记”声称“无技术债”。

## 3. 安全关注

| 信任边界                             | 已有缓解证据                                                                                                                                                                                  | 残余风险/未知项                                                             |
| ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| 可信 stdio 宿主执行（配置风险）      | 默认关闭、管理员定义、连接环境凭据隔离；[stdio.py](../../backend/app/tools/adapters/stdio.py)、[config.py](../../backend/app/config.py):L108                                                  | 程序仍拥有后端宿主权限；隔离沙箱是另一条路径，需部署者只登记可信程序        |
| 外部 HTTP（SSRF 边界，OWASP A10 类） | allow/private hosts、PinnedTransport、拒绝跳转、无环境代理；[network.py](../../backend/app/tools/network.py)                                                                                  | 本次未做完整安全审计或真实 DNS/网络攻击验证，不能据此给“无 SSRF”结论        |
| 资源所有权（A01 类）                 | [KnowledgeService.require_base](../../backend/app/knowledge/service.py):L107 始终检查 owner；[ConversationAuthorization](../../backend/app/conversations/authorization.py):L17 复查会话与许可 | 所跑知识隔离/执行边界通过；全 API 授权矩阵未重跑                            |
| 凭据与备份                           | [CredentialVault](../../backend/app/infrastructure/credentials.py):L14；SQL 参数隐藏和 MCP 输出脱敏                                                                                           | `[TODO]` 现网 Key 备份/轮换、历史秘密扫描；没有把未读取 .env 写成凭据已审计 |

这些是边界核查和已知信任模型，不是新增漏洞认定。

## 4. 性能与扩展

| 机制                        | 已确认依据                                                                                                                     | 当前症状 / 扩展推断                                                                                |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| 每个 SSE 订阅轮询持久快照   | [conversation_streaming.py](../../backend/app/api/conversation_streaming.py):L30–64                                            | 未测当前延迟；并发观察者增加会放大数据库读取，已有订阅数量和寿命上限                               |
| SQLite 单写者，动作频繁落盘 | [session.py](../../backend/app/infrastructure/database/session.py):L25；[store.py](../../backend/app/execution/store.py):L171  | 未压测容量；WAL 不提供多写者并行，动作、接受与清理会争写锁                                         |
| 库摘要逐库 count            | [KnowledgeService.libraries/base_read](../../backend/app/knowledge/service.py):L115、L166                                      | 已确认每库两次计数查询；账号库数增加时存在 N+1 查询增长，未测实际瓶颈                              |
| 入库字符切片与分词          | [service.py](../../backend/app/knowledge/service.py):L262                                                                      | 请求期执行、to_thread 避免阻塞 event loop，但仍占线程/CPU；已有 128 KiB 和数量限制，无独立入库队列 |
| 文件/Skill 额外字节         | [files/service.py](../../backend/app/files/service.py):L65、L155；[skills/service.py](../../backend/app/skills/service.py):L84 | 文件回收已实现；不可变 Skill blob 的长期增长/回收策略需另查使用历史，当前未测磁盘增长              |

## 5. 易变与高变更区域

`git log -1` 实际返回 main 没有提交，`git status --short` 显示工程主要文件未跟踪。技能根扫描因此没有 90 天 churn。**未知：** 哪些文件最近修改最多；不把“无提交”写成“稳定”。

可定位的耦合区域是 bootstrap 装配、conversations 的接受/授权/发布、execution.store 的预算/恢复、Skill 的目录与 DB 协调、MCP 目录/连接修订，以及前端 Controller 的待确认状态。它们的脆弱性来自具体竞态/多阶段协作；本次没有历史 churn 证据。安全修改应复用 [TESTING](TESTING.md)中的相应边界测试。

## 6. 意图项与文档/实现差异

本次任务是解释实际架构，无须用户决定新产品行为；**没有待解的 `[ASK USER]` 意图问题**。以下差异分别处理，不擅自把调查结论变成改造需求。

| 描述/可能误读                            | 核查结果                                                                                                                  |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| 索引过期后“重新导入资料”即可检索         | 同字节直接重传被去重挡住；已复现，恢复建议需明确“先移除再上传”，或后续补重建能力                                          |
| 总体架构开头把“后续知识”整体指向方案     | 同页后文、产品说明和源码已接入个人库/文本/BM25；应把后续限定为向量/问答/员工装配。本次同步纠正概述开头的范围用语          |
| 文档多处画出模块/未来 worker             | 正式运行仍是一个应用进程；独立沙箱服务与知识 POC 不等于正式业务已拆服务；当前 README 已明确 worker 未接入，属已确认一致项 |
| scan 显示“未检测到工作区/入口/容器/模板” | 是脚本根目录识别不足，非项目事实；人工已补查两个工程、隐藏模板和 deploy                                                   |

`[TODO]` 真实部署/上游、完整全量质量状态、端到端体验、负载和协调恢复演练。它们是验证缺口，当前没有依据要求用户回答产品意图问题。

## 7. 证据

- [知识上传/检索](../../backend/app/knowledge/service.py)、[分词版本](../../backend/app/knowledge/lexical.py)、[知识迁移](../../backend/migrations/versions/0013_knowledge_libraries.py)。
- [执行恢复](../../backend/app/execution/store.py)、[进程锁](../../backend/app/execution/scheduler.py)、[checkpoint](../../backend/app/agent_runtime/checkpoints.py)。
- [Skill 多介质更新](../../backend/app/skills/service.py)、[前端 Controller](../../frontend/src/pages/conversations/useConversationController.ts)、[测试结果](TESTING.md)。

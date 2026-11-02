"""Allowlisted fictional teaching sources, imported only on explicit user action."""

import hashlib
import json
from pathlib import Path

DATASET = Path(__file__).resolve().parents[2] / "datasets/travel-expense"
TECHNICAL = {
    "发布与回滚.md": """# 星桥项目：发布与回滚

本文是虚构的技术演示资料，不对应生产环境或真实客户。

## 发布前检查
每次发布必须具备变更说明、测试结果及上一版本的可恢复包。值班工程师先检查预发布环境，再核对本次配置修订。数据库结构变更应单独说明回退条件，不能假设应用回滚也会恢复数据库。

## 分批发布
先将一台实例切换到新版本，观察十分钟。确认健康检查和关键业务请求正常，再依次更新其余实例。发布负责人记录版本号、开始时间和检查结果。

## 回滚条件
新版本连续三分钟无法通过健康检查，或关键请求错误率超过百分之二时，停止扩大发布。值班工程师将流量切回上一稳定版本，并通知发布负责人。

## 回滚后确认
回滚后重新执行健康检查和一条关键业务流程，保存失败日志。若包含不可逆的数据迁移，先停止写入并联系数据库负责人，不直接执行旧应用包。
""",
    "API错误处理.md": """# 星桥项目：API 错误与请求重试

本文为虚构的接口教学文档，不包含真实服务地址和访问凭据。

## 输入错误
HTTP 422 表示提交内容不符合接口约束。客户端应展示字段错误并保留用户输入；修改内容前不要重复提交同一个请求。

## 修订冲突
HTTP 409 表示记录状态或修订发生冲突。客户端先读取当前记录，让用户核对差异，再根据新修订提交。禁止直接用旧表单覆盖服务器数据。

## 网络中断
网络中断不等于服务端没有执行。创建资源或上传文件时，客户端保留同一个请求标识重试，由服务器返回已确认的结果，避免重复创建。

## 频率限制
HTTP 429 表示当前请求过于频繁。若响应包含 Retry-After，客户端按该等待时间重试；后台批次不能无限并发请求。
""",
    "备份与恢复.txt": """星桥项目：持久化备份与恢复
本资料是虚构的技术演示文档，没有真实主机、账号或客户信息。

## 备份范围
每天凌晨两点备份业务数据库、持久文件目录和加密主密钥。主密钥与数据库分别保管，备份报告仅记录路径标识和内容摘要，不记录密钥正文。

## 恢复流程
先停止应用写入，选择同一备份批次的数据库和文件目录。将备份恢复到独立目录，核对文件摘要与数据库引用，再在隔离端口启动应用。

## 恢复验收
必须验证登录、读取历史资料、下载原件及一次库内检索。全部通过后才切换到恢复目录。只看到数据库文件存在，不能判定恢复成功。

## 演练频率
每月执行一次隔离恢复演练，记录备份批次、耗时、失败项和处理人。本文不保证某个真实环境已经完成备份。
""",
    "项目开发约定.md": """# 星桥项目：开发约定

此文档为虚构的项目约定，用于测试知识库的加载、切分和关键词检索。

## 工程职责
后端负责访问权限、业务规则和长期数据，前端负责输入与结果展示。索引是原文的可重建副本，不能作为原始文档的唯一保存位置。

## 文档格式
首批资料使用 UTF-8 Markdown 或纯文本。标题应写明业务对象，章节描述一个完整主题。代码示例不包含访问密钥，示例接口使用保留域名 example.com。

## 提交与验证
修改业务行为时同步接口说明，运行相关测试。测试替身只能说明本地逻辑，真实服务连通性必须单独验证。失败记录与未验证范围应留在交付说明中。

## 查阅方式
项目研发资料供研发岗位查阅，差旅报销资料由行政知识库维护。遇到其他领域的问题，应说明资料范围，不从名称相似的无关片段推断规则。
""",
}


def sample_files(preset: str) -> list[tuple[str, bytes]]:
    if preset == "technical":
        return [(name, body.encode()) for name, body in TECHNICAL.items()]
    manifest = json.loads((DATASET / "manifest.json").read_text())
    result = []
    for entry in manifest["documents"]:
        path = (DATASET / entry["path"]).resolve()
        if not path.is_relative_to(DATASET / "documents"):
            raise ValueError("invalid teaching manifest path")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError("teaching source checksum mismatch")
        result.append((path.name, data))
    return result

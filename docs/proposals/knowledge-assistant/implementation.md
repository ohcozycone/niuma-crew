# 知识库建设方案导航

| 项目     | 内容                                                                                           |
| -------- | ---------------------------------------------------------------------------------------------- |
| 设计状态 | 草案；路线和技术建议待 Review，未视为已采纳                                                    |
| 实施状态 | 独立 POC、多库文本入库 API/业务表与页面已实现；硅基流动向量接入已实现，员工知识装配待接入      |
| 更新日期 | 2026-10-31                                                                                     |
| 阅读入口 | [Notion：NiumaCrew｜知识库建设方案](https://app.notion.com/p/409eab92f60081798b8bc16a975ddc9a) |

方案正文已按“先判断方向，再选技术，再拆实现”迁到 Notion 子页。本文件只保留工程导航，不再堆放整套细节。

2026-10-31 已实施[资料建设闭环](document-processing.md)：原件暂存、手动后台处理、逐文件关键词发布、库设置与全局上传。当前契约见[知识库](../../reference/knowledge.md)，验证见[验收记录](../../records/knowledge-document-processing.md)。已进一步实现[短章节合并与处理预览](chunk-preview.md)，受控阈值与页面验证见[记录](../../records/knowledge-chunk-preview.md)。现已接入[员工个人多库装配与问答](employee-knowledge.md)，按需/先检索、受管工具和引用的结果见[验收](../../records/employee-knowledge.md)。完整异步增量向量仍待实施。

当前检索入口增量见[检索测试与配置入口](retrieval-testing.md)；该页记录大脑与知识库配置的职责及混合检索范围。

## 先 Review 方向与选型

1. [01｜路线判断](https://app.notion.com/p/409eab92f600810b9ac5caa8f3c62b7e)：对比全文上下文、纯向量、混合检索及更复杂方式，结合当前平台提出建议。
2. [02｜LangChain 选型与决策清单](https://app.notion.com/p/409eab92f60081cfa7e1ca0e3b640f02)：集中登记 D01—D08、选型理由与代价。

已明确的是分层短文、LangChain 生态优先、入库/召回两条主线、真实评测和页面来源。混合 RAG、模块部署、BM25 后端、向量存储和融合组件仍是建议；具体模型、切分参数、候选数、权重与验收数值待验证。

本轮建议调整为 SQLite FTS5 词法索引、Chroma 向量持久化和平台小型 RRF 函数；bm25s 与 EnsembleRetriever 保留为对照候选。[02.1｜BM25 后端对比](https://app.notion.com/p/409eab92f6008107bb99c3b0fea7f31d)记录依据和代价；调整仍是建议，不代表用户已经确认或效果已验证。

## 入库主线

上传/API → 文件加载 → 内容切分 → 同一批切片分别构建 BM25 与向量索引 → 保存来源关系 → 发布。

- [03｜入库主线](https://app.notion.com/p/409eab92f60081869fd6de21f44e0e33)
- [A0｜上传、导入与重试](https://app.notion.com/p/409eab92f600814ca8c8dc7a4629ee7e)
- [A1｜文件加载](https://app.notion.com/p/409eab92f6008107858dc49ba34c2892)
- [A2｜内容切分](https://app.notion.com/p/409eab92f60081148d36d509e958d1cc)
- [A3｜索引与存储](https://app.notion.com/p/409eab92f60081c9b807c9d28ce0aa4c)

具体契约：[A2.1｜来源映射](https://app.notion.com/p/409eab92f600811d938acc26b4bd8d62)、[A3.1｜存储、发布与恢复](https://app.notion.com/p/409eab92f60081eebc74d2d951dfdca3)。

## 召回主线

问题与授权版本 → BM25/向量两路召回 → 融合排序与 Top-K → 组织证据 → 模型回答 → 来源校验与页面展示。

- [04｜召回主线](https://app.notion.com/p/409eab92f60081189016d290f4983bab)
- [B1｜混合召回与排序](https://app.notion.com/p/409eab92f60081e69e3dcbef18267c7a)
- [B2｜回答与来源](https://app.notion.com/p/409eab92f6008145ab7ad90ad767eb4a)

[B2.1｜回答与来源协议](https://app.notion.com/p/409eab92f600815d933fe6fa86360185)给共用检索、模型工具适配与页面数据。

## 实施与验收

用户已授权实施[技术 POC 增量](poc.md)及[多库文本入库](library-upload.md)；后者的当前规则见[知识库契约](../../reference/knowledge.md)，本机 9 份原件/43 片段及界面验收见[实施记录](../../records/knowledge-library.md)。核心组件与离线验证已运行。代码入口为[知识核心](../../../backend/app/knowledge/README.md)，实际验证与未完成项见[POC 记录](../../records/knowledge-poc.md)；不把组件烟测当作真实语义效果通过。

[05｜效果评测与分步交付](https://app.notion.com/p/409eab92f60081dd9b12ddfebd5cd61b)维护小样本验证、入库闭环、召回闭环、真实效果与恢复的交付顺序。先审核已有开发题，再固定比较条件；尚未产生真实效果、性能或费用成绩。

[05.1｜首轮实验](https://app.notion.com/p/409eab92f60081ea958fcabf0a30c765)给暂定配置、证据与评分样例；[审查跟进](https://app.notion.com/p/409eab92f60081ef8529c9aad0f0f1e9)区分文档补齐和待 POC。

## C 端页面组织

[07｜页面组织与使用流程](https://app.notion.com/p/409eab92f6008118bd14e26fdd840d4e)：建议按知识库、文档和固定版本阅读分层；库内保留文档、检索测试、设置三个入口，导入/构建进度就地展示，保留全员规章现有入口。其中库列表、文档、BM25 测试与固定正文阅读已实现；当前保留文档/检索两个主入口，库设置通过按钮弹窗进入；关键词处理已支持后台任务与逐文件发布，向量仍为显式整库构建，不增加人工发布步骤。

## 工程文档如何衔接

- [当前数据库配置](../../guides/database-configuration.md)、[文件模块](../../../backend/app/files/README.md)与[后端架构](../../architecture/backend.md)描述现有实现。
- [知识助手专题](README.md)、[目标字段草案](../agent-capabilities/data.md#知识资产处理与发布)保留产品交互与数据契约补充，不把未审建议视为现行规则。
- [全文学习子迭代](plan.md)保留学习任务，不作为本轮混合检索建设的前置；Notion 原学习进度不改写。

Notion 维护本轮方案 Review 正文；用户确认并实施后，将生效契约合入仓库现行文档，验收证据进入 records。不同时维护两份完整的方案正文。

正式向量增量见[硅基流动接入](siliconflow-embedding.md)，当前产品使用 SQLite 保存向量并精确计算余弦相似度，Chroma 保留在独立 POC。该选择面向小库和低内存部署，不表示已通过真实语义效果评测。

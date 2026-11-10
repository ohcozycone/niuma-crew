# 切分验证资料

`faq.md`为补充的虚构FAQ，验证同父短章节合并和跨父拒绝；不作为真实企业制度。其余制度、流程和技术资料复用[差旅教学资料](../travel-expense/README.md)及[技术演示资料](../../experiments/knowledge_demo.py)。

在backend目录执行`.venv/bin/python -m experiments.knowledge_chunking`，比较0、100、200、300字符阈值下的片段数、短片段数和固定BM25 Top-6引文覆盖。差旅参考证据只在索引完成后用于评分，不送入索引。结果说明这一小组受控资料上的表现，不证明语义检索或回答质量，也不承诺默认阈值适合全部文档。

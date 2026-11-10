# BFCL 固定资源与评分器维护

正式运行资源位于 [app/evaluations/data](../../app/evaluations/data/manifest.json)，随后端包一起交付，不在开始考核时联网下载。

- 来源：[Gorilla BFCL](https://github.com/ShishirPatil/gorilla/tree/main/berkeley-function-call-leaderboard)。
- 范围：BFCL v4 `simple_python` 400道问题及400份可能答案，保留英文、函数定义、题目标识及可接受值。
- 许可：[Apache-2.0](../../app/evaluations/data/LICENSE)。
- 固定依据：manifest登记每个原文件的Git blob及SHA256，已逐字节验证Git blob。上游问题为 `356a0db61e54eb1d92d8e10d014463cf2eb513cc`，答案为 `268c55641a21b51fc15730ce39ce906444a935a1`，评分源为 `160fd75cfc8b2b7ef9f83a244f81da0fe0244e39`。

`build_checker.py` 使用AST从保存的官方评分源提取Python路径，保留严格类型、可接受值、字符串规范化及嵌套参数规则，去掉Java/JavaScript路径与模型名称改写依赖。平台JSON协议保留函数名中的句点，因此不需要原生工具名称改写。生成命令为仓库根的 `python3 backend/datasets/bfcl/build_checker.py`，随后运行 Ruff 格式化。

生成结果位于 [bfcl_checker.py](../../app/evaluations/bfcl_checker.py)。窄范围 Ruff 豁免保留上游精确类型检查，不改为 `isinstance`，避免把布尔值当整数。生成源使用 `.py.txt` 保留原字节，不能直接格式化或执行未知答卷。

评分一致性测试使用同一官方源，在全部400题的可接受答卷及额外参数错误上对比结果。平台只支持单调用JSON答卷，解析失败和多调用在协议层判为未通过；不执行模型生成的Python。增加类别、改变输入协议或升级规则时，必须更新版本、manifest和一致性测试；不能静默替换旧报告的测试条件。

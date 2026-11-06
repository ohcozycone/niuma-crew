"""Offline scoring controls; generated answers are never employee benchmark results."""

import argparse
import json
from pathlib import Path

from app.evaluations.benchmark import SUITE_ID, grade, load_suite


def scoring_controls() -> dict:
    """Use explicit public inputs so wrong-answer rejection can be reproduced."""
    case = next(case for case in load_suite()[1] if case["id"] == "simple_python_0")
    name = "calculate_triangle_area"

    def call(arguments, *, function=name):
        return json.dumps([{"name": function, "arguments": arguments}], ensure_ascii=False)

    correct = call({"base": 10, "height": 5})
    controls = [
        ("正确调用", correct, True),
        ("错误函数", call({"base": 10, "height": 5}, function="wrong_function"), False),
        ("缺少必填参数", call({"base": 10}), False),
        ("参数值错误", call({"base": 999, "height": 5}), False),
        ("参数类型错误", call({"base": True, "height": 5}), False),
        ("额外参数", call({"base": 10, "height": 5, "unexpected": 1}), False),
        ("空调用", "[]", False),
        ("多个调用", json.dumps(json.loads(correct) * 2), False),
        ("直接回答数值", "25", False),
        ("拒绝回答", "我不知道", False),
    ]
    results = []
    for label, answer, expected in controls:
        grading = grade(case["functions"], case["expected"], answer)
        results.append(
            {
                "control": label,
                "answer": answer,
                "expected_valid": expected,
                "actual_valid": grading["valid"],
                "expectation_met": grading["valid"] is expected,
                "grading": grading,
            }
        )
    return {
        "mode": "offline_scoring_controls",
        "notice": "固定控制答卷，只验证评分器，不调用模型，不代表任何员工成绩。",
        "suite_id": SUITE_ID,
        "question_id": case["id"],
        "controls": results,
        "all_expectations_met": all(item["expectation_met"] for item in results),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="可选JSON报告路径；默认只输出到终端。")
    args = parser.parse_args()
    report = scoring_controls()
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n")
    print(rendered)
    if not report["all_expectations_met"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

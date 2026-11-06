"""Pinned public BFCL data, a bounded answer protocol, and the supported grader."""

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from app.evaluations.bfcl_checker import simple_function_checker

SUITE_ID = "bfcl-v4-simple-python"
GRADER_VERSION = "bfcl-python-160fd75-derived1-json1"
DATA = Path(__file__).with_name("data")
SCOPE = (
    "BFCL Python 单次调用专项：保留岗位指令和模型，关闭实际工具、技能和个人知识装配；"
    "检查调用提议，不验证业务工具执行，不直接对标官方榜单。"
)


@lru_cache(maxsize=1)
def load_suite() -> tuple[str, list[dict]]:
    manifest = json.loads((DATA / "manifest.json").read_text())
    blobs = {}
    for name in ("questions.jsonl", "answers.jsonl"):
        content = (DATA / name).read_bytes()
        if hashlib.sha256(content).hexdigest() != manifest["files"][name]["sha256"]:
            raise RuntimeError("BFCL 固定题库校验失败。")
        blobs[name] = [json.loads(line) for line in content.splitlines() if line.strip()]
    answers = {row["id"]: row["ground_truth"] for row in blobs["answers.jsonl"]}
    cases = [
        {
            "id": q["id"],
            "question": q["question"],
            "functions": q["function"],
            "expected": answers[q["id"]],
        }
        for q in blobs["questions.jsonl"]
    ]
    if len(cases) != 400 or len({q["id"] for q in cases}) != 400 or len(answers) != 400:
        raise RuntimeError("BFCL 题目和答案数量不匹配。")
    return manifest["files"]["questions.jsonl"]["sha256"], cases


def catalog() -> list[dict]:
    version, cases = load_suite()
    return [
        {
            "id": SUITE_ID,
            "name": "工具调用专项 · BFCL",
            "category": "simple_python",
            "total": len(cases),
            "version": version,
            "grader_version": GRADER_VERSION,
            "scope": SCOPE,
            "source_url": "https://github.com/ShishirPatil/gorilla/tree/main/berkeley-function-call-leaderboard",
        }
    ]


def exam_prompt(case: dict) -> str:
    return (
        "这是函数调用提议考核。只根据下面的函数说明和问题填写调用，不实际执行函数。"
        '只输出 JSON 数组，每项严格为 {"name":"函数名","arguments":{参数}}。'
        "保持函数名（包括句点）原样，不输出解释或代码围栏。\n函数说明：\n"
        + json.dumps(case["functions"], ensure_ascii=False)
        + "\n问题：\n"
        + json.dumps(case["question"], ensure_ascii=False)
    )


def grade(functions: list, expected: list, answer: str) -> dict:
    """Parse JSON values only; never execute or eval a proposed call."""
    try:
        calls = json.loads(answer)
    except (json.JSONDecodeError, RecursionError):
        return {
            "valid": False,
            "error_type": "answer_format",
            "error": ["答卷不是有效 JSON 数组。"],
        }
    if not isinstance(calls, list) or len(calls) != 1:
        return {"valid": False, "error_type": "call_count", "error": ["本类别要求恰好一个调用。"]}
    call = calls[0]
    if (
        not isinstance(call, dict)
        or set(call) != {"name", "arguments"}
        or not isinstance(call["name"], str)
        or not isinstance(call["arguments"], dict)
    ):
        return {
            "valid": False,
            "error_type": "answer_format",
            "error": ["每个调用必须只包含 name 字符串和 arguments 对象。"],
        }
    return simple_function_checker(
        functions[0], {call["name"]: call["arguments"]}, expected[0], "python", "niuma"
    )

import argparse
import hashlib
import json
from pathlib import Path

from app.resources.knowledge.samples import TECHNICAL

DATASET = Path(__file__).resolve().parents[1] / "datasets/travel-expense"


def generate(output: Path) -> dict:
    """仅复制清单中的教学原件，不引入评分答案。"""
    source = json.loads((DATASET / "manifest.json").read_text())
    libraries = []
    travel_files = []
    for item in source["documents"]:
        path = DATASET / item["path"]
        data = path.read_bytes()
        target = output / "差旅报销" / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        travel_files.append({"path": str(target), "sha256": hashlib.sha256(data).hexdigest()})
    libraries.append(
        {
            "name": "差旅报销",
            "description": "虚构教学资料：交通、住宿、报销材料与办理流程。",
            "files": travel_files,
        }
    )
    tech_files = []
    for name, body in TECHNICAL.items():
        target = output / "项目技术文档" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        data = body.encode()
        target.write_bytes(data)
        tech_files.append({"path": str(target), "sha256": hashlib.sha256(data).hexdigest()})
    libraries.append(
        {
            "name": "项目技术文档",
            "description": "虚构星桥项目：发布回滚、接口错误、备份恢复与开发约定。",
            "files": tech_files,
        }
    )
    manifest = {"fictional": True, "libraries": libraries}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="生成两组虚构演示原件，不自动写入用户知识库")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = generate(args.output.resolve())
    print(
        json.dumps(
            {
                "manifest": str(args.output.resolve() / "manifest.json"),
                "libraries": [
                    {"name": item["name"], "documents": len(item["files"])}
                    for item in manifest["libraries"]
                ],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

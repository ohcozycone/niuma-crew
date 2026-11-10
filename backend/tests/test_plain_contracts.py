import json
import subprocess
import sys


def test_ordinary_runtime_contracts_do_not_load_storage_or_sdk():
    code = """
import json, sys
import app.runtime.contracts.agent
import app.runtime.contracts.content
import app.runtime.contracts.runs
import app.runtime.contracts.tools
import app.runtime.usage
print(json.dumps(sorted(sys.modules)))
"""
    result = subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, text=True
    )
    modules = json.loads(result.stdout)
    forbidden = (
        "sqlalchemy",
        "langchain",
        "langgraph",
        "deepagents",
        "fastapi",
        "app.agent",
        "app.execution",
        "app.bootstrap",
        "app.infrastructure.database",
    )
    assert not [
        name for name in modules if any(name == p or name.startswith(p + ".") for p in forbidden)
    ]

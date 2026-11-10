"""目标架构契约：目录、真实依赖、只读例外与普通类型隔离。"""

import ast
import hashlib
import json
import subprocess
import sys
from importlib.util import resolve_name
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND / "app"
CONTRACT = json.loads((BACKEND / "tests/architecture_contract.json").read_text())
MODULES = {
    ".".join(("app", *p.relative_to(ROOT).with_suffix("").parts)).removesuffix(".__init__"): p
    for p in ROOT.rglob("*.py")
}


def imports(source, package):
    """解析所有作用域、相对导入、包聚合和字面量动态导入。"""
    result = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            result.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = (
                resolve_name("." * node.level + (node.module or ""), package)
                if node.level
                else node.module or ""
            )
            result.add(base)
            result.update(base + "." + a.name for a in node.names if base + "." + a.name in MODULES)
        elif (
            isinstance(node, ast.Call)
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else ""
            )
            if name in {"import_module", "__import__"}:
                result.add(node.args[0].value)
    return result


def dependency_graph():
    graph = {}
    for module, path in MODULES.items():
        package = module if path.name == "__init__.py" else module.rpartition(".")[0]
        graph[module] = imports(path.read_text(), package)
        parts = module.split(".")
        graph[module].update(
            ".".join(parts[:i]) for i in range(1, len(parts)) if ".".join(parts[:i]) in MODULES
        )
        graph[module].discard(module)
    return graph


def under(name, prefix):
    return name == prefix or name.startswith(prefix + ".")


def closure(graph, origin):
    visited = set()
    pending = [origin]
    while pending:
        for target in graph.get(pending.pop(), ()):
            if target not in visited:
                visited.add(target)
                pending.append(target)
    return visited


def test_complete_source_disposition_and_exact_target_tree():
    sources = CONTRACT["source_files"]
    assert len(sources) == CONTRACT["baseline_source_count"] == 195
    assert len({s["source"] for s in sources}) == len(sources)
    expected = {name for name in CONTRACT["required_targets"] if not name.endswith("__init__.py")}
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*.py") if p.name != "__init__.py"}
    assert actual == expected, {
        "missing": sorted(expected - actual),
        "unexpected": sorted(actual - expected),
    }
    for source in sources:
        assert source["action"] in {"retain", "move", "split", "merge", "delete"}
        assert len(source["sha256"]) == 64 and source["targets"]
        assert all((ROOT / path).is_file() for path in source["targets"])
        if source["source"] not in source["targets"]:
            assert not (ROOT / source["source"]).exists(), source["source"]
    allowed = set(CONTRACT["allowed_top_level_packages"])
    assert {p.name for p in ROOT.iterdir() if p.is_dir() and p.name != "__pycache__"} <= allowed
    for item in CONTRACT["supporting_python_files"]:
        assert (BACKEND.parent / item["target"]).is_file(), item


def test_target_modules_have_responsibilities_and_no_facade_forwarders():
    for name in CONTRACT["required_targets"]:
        if name.endswith("__init__.py"):
            continue
        path = ROOT / name
        tree = ast.parse(path.read_text())
        body = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom, ast.Expr))]
        assert body, name
        assert "KnowledgeService" not in path.read_text(), name
    for path in (ROOT / "resources/knowledge").glob("*.py"):
        assert not any(
            isinstance(n, ast.Attribute) and n.attr in {"knowledge", "_knowledge"}
            for n in ast.walk(ast.parse(path.read_text()))
        ), path


def test_normal_module_graph_has_no_cycles_or_service_locator_backedges():
    graph = dependency_graph()
    state = {}
    stack = []

    def visit(node):
        assert state.get(node) != "active", stack + [node]
        if state.get(node) == "done":
            return
        state[node] = "active"
        stack.append(node)
        for target in graph[node]:
            if target in graph:
                visit(target)
        stack.pop()
        state[node] = "done"

    for module in graph:
        visit(module)
    for module, dependencies in graph.items():
        if under(module, "app.bootstrap") or module in {
            "app.main",
            "app.config",
            "app.runtime.assembly",
        }:
            continue
        assert not any(
            under(name, "app.bootstrap") or name == "app.runtime.assembly" for name in dependencies
        ), module


def test_dependency_rules_and_named_orm_exceptions():
    graph = dependency_graph()
    exceptions = {
        key: {"app." + value for value in values}
        for key, values in {
            **CONTRACT["readonly_projections"],
            **CONTRACT["legacy_metadata"],
        }.items()
    }
    for module, targets in graph.items():
        path = MODULES[module].relative_to(ROOT).as_posix()
        for target in targets:
            if under(module, "app.runtime.execution"):
                assert not any(
                    under(target, p)
                    for p in (
                        "app.applications",
                        "app.runtime.agent",
                        "app.runtime.tools",
                        "app.api",
                    )
                ), (module, target)
            if under(module, "app.runtime.agent"):
                assert not any(
                    under(target, p)
                    for p in (
                        "app.applications",
                        "app.runtime.execution",
                        "app.api",
                        "app.auth",
                        "app.infrastructure.database",
                    )
                ), (module, target)
            if under(module, "app.runtime.tools"):
                assert not any(
                    under(target, p)
                    for p in (
                        "app.runtime.execution",
                        "app.runtime.agent",
                        "app.applications",
                        "app.auth",
                        "app.api",
                        "app.infrastructure.database",
                    )
                ), (module, target)
                if under(target, "app.resources"):
                    assert target.endswith((".contracts", ".schemas")), (module, target)
            if under(module, "app.applications"):
                assert not any(
                    under(target, p)
                    for p in (
                        "app.runtime.agent",
                        "app.runtime.tools",
                        "app.runtime.execution.store",
                        "app.api",
                    )
                ), (module, target)
            if under(module, "app.api") or under(module, "app.cli"):
                assert not any(
                    under(target, p)
                    for p in (
                        "app.runtime.agent",
                        "app.runtime.tools",
                        "app.runtime.execution.store",
                        "langchain",
                        "langchain_core",
                        "langgraph",
                        "deepagents",
                    )
                ), (module, target)
            if under(module, "app.resources"):
                assert not any(
                    under(target, p)
                    for p in ("app.applications", "app.runtime", "app.api", "app.bootstrap")
                ), (module, target)
                if under(target, "app.resources") and len(target.split(".")) > 2:
                    owner = module.split(".")[2]
                    other = target.split(".")[2]
                    assert (
                        owner == other
                        or other in CONTRACT["resource_dependencies"].get(owner, ())
                        or target in exceptions.get(path, ())
                    ), (module, target)
            if any(under(module, p) for p in ("app.common", "app.infrastructure", "app.auth")):
                assert not any(
                    under(target, p)
                    for p in (
                        "app.resources",
                        "app.applications",
                        "app.runtime",
                        "app.bootstrap",
                        "app.api",
                    )
                ), (module, target)
            # Mutable business models remain inside their owner, apart from named read-only projections.
            if (
                target.endswith(".models")
                and target.startswith("app.")
                and not under(module, "app.bootstrap")
            ):
                owner = target.rpartition(".")[0]
                if not under(module, owner):
                    assert target in exceptions.get(path, ()), (module, target)
    for path in CONTRACT["readonly_projections"]:
        tree = ast.parse((ROOT / path).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {
                    "add",
                    "add_all",
                    "merge",
                    "delete",
                    "commit",
                    "rollback",
                    "flush",
                }, (path, node.func.attr)
            if isinstance(node, ast.ImportFrom):
                assert not ({a.name for a in node.names} & {"insert", "update", "delete"}), path


def test_plain_contracts_and_low_level_modules_have_safe_transitive_dependencies():
    graph = dependency_graph()
    for origin in graph:
        if not under(origin, "app.runtime.contracts") and not under(origin, "app.common"):
            continue
        dependencies = closure(graph, origin)
        forbidden = (
            "sqlalchemy",
            "langchain",
            "langchain_core",
            "langgraph",
            "deepagents",
            "opensandbox",
            "fastapi",
            "app.runtime.agent",
            "app.runtime.execution",
            "app.infrastructure.database",
        )
        assert not any(under(name, p) for name in dependencies for p in forbidden), origin


def test_model_registry_import_only_registers_models():
    code = """
import json, sys
from app.bootstrap.model_registry import Base
print(json.dumps({'tables': sorted(Base.metadata.tables), 'modules': sorted(sys.modules)}))
"""
    result = subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, text=True
    )
    data = json.loads(result.stdout)
    assert len(data["tables"]) == 31
    assert not any(
        under(name, p)
        for name in data["modules"]
        for p in (
            "app.bootstrap.services",
            "app.api",
            "app.runtime.agent",
            "langchain",
            "langchain_core",
            "langgraph",
            "deepagents",
            "fastapi",
        )
    )


@pytest.mark.parametrize("item", CONTRACT["preserved_data"], ids=lambda item: item["source"])
def test_datasets_and_assessment_samples_preserved(item):
    path = BACKEND.parent / item["target"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]


def test_original_definitions_have_owners_or_explicit_replacements():
    for source in CONTRACT["source_files"]:
        defined = {
            node.name
            for target in source["targets"]
            for node in ast.walk(ast.parse((ROOT / target).read_text()))
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for original in source["symbols"]:
            replacements = CONTRACT["symbol_replacements"].get(
                source["source"] + ":" + original, [original]
            )
            assert set(replacements) <= defined, (source["source"], original, replacements)

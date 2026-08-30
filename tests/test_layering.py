"""分层依赖约束测试。"""

from __future__ import annotations

import ast
from pathlib import Path


def test_api_and_infra_do_not_import_core() -> None:
    violations: list[str] = []
    for layer in ("api", "infra"):
        root = Path("src/scaffold") / layer
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("scaffold.core"):
                    violations.append(f"{path}:{node.lineno}")
                elif isinstance(node, ast.Import) and any(
                    alias.name.startswith("scaffold.core") for alias in node.names
                ):
                    violations.append(f"{path}:{node.lineno}")

    assert violations == []

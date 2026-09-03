"""계층 규칙을 테스트로 강제한다. 문서에만 적으면 3주 뒤에 깨진다."""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "chika"

#: domain이 써도 되는 표준 라이브러리. 이 밖의 import는 위반이다.
_ALLOWED_STDLIB = {
    "abc", "collections", "dataclasses", "enum", "functools", "hashlib",
    "itertools", "math", "random", "statistics", "types", "typing", "__future__",
}


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def _modules(layer: str) -> list[Path]:
    return sorted((SRC / layer).rglob("*.py"))


def test_domain_layer_exists() -> None:
    assert _modules("domain"), "domain 모듈이 하나도 없다"


def test_domain_imports_nothing_but_stdlib_and_itself() -> None:
    violations: list[str] = []
    for path in _modules("domain"):
        for root in _imported_roots(path):
            if root == "chika" or root in _ALLOWED_STDLIB:
                continue
            violations.append(f"{path.relative_to(SRC)} imports {root}")
    assert not violations, f"domain 계층의 외부 의존: {violations}"


def test_domain_does_not_import_outer_layers() -> None:
    forbidden = ("chika.application", "chika.infrastructure", "chika.interface", "chika.etl")
    violations: list[str] = []
    for path in _modules("domain"):
        source = path.read_text(encoding="utf-8")
        violations.extend(
            f"{path.relative_to(SRC)} -> {name}" for name in forbidden if name in source
        )
    assert not violations, f"의존 방향 위반: {violations}"


def test_application_imports_only_domain() -> None:
    forbidden = ("chika.infrastructure", "chika.interface", "chika.etl")
    violations: list[str] = []
    for path in _modules("application"):
        source = path.read_text(encoding="utf-8")
        violations.extend(
            f"{path.relative_to(SRC)} -> {name}" for name in forbidden if name in source
        )
    assert not violations, f"의존 방향 위반: {violations}"


def test_openai_sdk_never_appears_in_domain_or_application() -> None:
    violations: list[str] = []
    for layer in ("domain", "application"):
        for path in _modules(layer):
            roots = _imported_roots(path)
            if "agents" in roots or "openai" in roots or "pydantic" in roots:
                violations.append(str(path.relative_to(SRC)))
    assert not violations, f"LLM/pydantic 의존이 안쪽 계층에 있다: {violations}"

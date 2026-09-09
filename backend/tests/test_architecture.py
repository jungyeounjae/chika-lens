"""계층 규칙을 테스트로 강제한다. 문서에만 적으면 3주 뒤에 깨진다."""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "chika"

#: domain/application이 써도 되는 표준 라이브러리. 이 밖의 import는 위반이다.
_ALLOWED_STDLIB = {
    "abc", "collections", "dataclasses", "enum", "functools", "hashlib",
    "itertools", "math", "random", "statistics", "types", "typing", "__future__",
}

#: interface 계층에서 유일하게 infrastructure를 알아도 되는 파일.
#: Phase 0 데모/합성 루트(README "Phase 0 데모" 절)로, 구체 구현체를 조립해
#: UseCases에 주입하는 역할이다. 다른 interface 코드(agent/*)는 절대
#: infrastructure를 몰라야 한다 — 알면 실제 구현이 바뀔 때 LLM 어댑터까지
#: 흔들린다.
_COMPOSITION_ROOT = SRC / "interface" / "cli.py"


def _imported_roots(path: Path) -> set[str]:
    """각 import의 최상위 패키지 이름만 (예: "chika.application.x" -> "chika")."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def _imported_modules(path: Path) -> set[str]:
    """각 import의 전체 점 표기 모듈 경로 (레벨 0, 즉 절대 임포트만)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def _modules(layer: str) -> list[Path]:
    return sorted((SRC / layer).rglob("*.py"))


def _forbidden_hits(modules: set[str], forbidden_prefixes: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for module in modules:
        for prefix in forbidden_prefixes:
            if module == prefix or module.startswith(prefix + "."):
                hits.append(module)
    return hits


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
        for hit in _forbidden_hits(_imported_modules(path), forbidden):
            violations.append(f"{path.relative_to(SRC)} -> {hit}")
    assert not violations, f"의존 방향 위반: {violations}"


def test_application_imports_only_domain_and_stdlib() -> None:
    """application은 domain과 표준 라이브러리만 쓸 수 있다 (스펙 §4).

    domain 계층에 적용하는 것과 동일한 stdlib 허용 목록 검사다. 이게 없으면
    유스케이스 안에 `import requests`나 외부 API 클라이언트가 섞여도 아키텍처
    테스트가 통과한다 — 유스케이스는 포트(Protocol)로만 인프라를 알아야 한다.
    """
    violations: list[str] = []
    for path in _modules("application"):
        for root in _imported_roots(path):
            if root == "chika" or root in _ALLOWED_STDLIB:
                continue
            violations.append(f"{path.relative_to(SRC)} imports {root}")
    assert not violations, f"application 계층의 외부 의존: {violations}"


def test_application_imports_only_domain() -> None:
    forbidden = ("chika.infrastructure", "chika.interface", "chika.etl")
    violations: list[str] = []
    for path in _modules("application"):
        for hit in _forbidden_hits(_imported_modules(path), forbidden):
            violations.append(f"{path.relative_to(SRC)} -> {hit}")
    assert not violations, f"의존 방향 위반: {violations}"


def test_infrastructure_does_not_import_interface() -> None:
    """infrastructure -> interface는 의존 방향 역행이다 (README "계층 규칙").

    infrastructure는 domain의 포트(Protocol)만 구현하면 되고, interface(에이전트
    툴, CLI, 나중의 FastAPI)를 알 이유가 전혀 없다.
    """
    violations: list[str] = []
    for path in _modules("infrastructure"):
        for hit in _forbidden_hits(_imported_modules(path), ("chika.interface",)):
            violations.append(f"{path.relative_to(SRC)} -> {hit}")
    assert not violations, f"의존 방향 위반: {violations}"


def test_interface_does_not_import_infrastructure_outside_the_composition_root() -> None:
    """interface -> infrastructure도 반대 방향 위반이다.

    유일한 예외는 `_COMPOSITION_ROOT`(interface/cli.py) 하나뿐이다 — 구체
    리포지토리를 조립해 UseCases에 주입하는 합성 루트이기 때문이다. 그 밖의
    interface 코드(특히 agent/*, LLM 어댑터)는 infrastructure를 몰라야 한다 —
    몰라야 리포지토리 구현을 바꿔도(Fake -> File, 또는 다른 어댑터) 에이전트
    쪽 코드가 흔들리지 않는다.
    """
    violations: list[str] = []
    for path in _modules("interface"):
        if path == _COMPOSITION_ROOT:
            continue
        for hit in _forbidden_hits(_imported_modules(path), ("chika.infrastructure",)):
            violations.append(f"{path.relative_to(SRC)} -> {hit}")
    assert not violations, f"의존 방향 위반: {violations}"


def test_openai_sdk_never_appears_in_domain_or_application() -> None:
    violations: list[str] = []
    for layer in ("domain", "application"):
        for path in _modules(layer):
            roots = _imported_roots(path)
            if "agents" in roots or "openai" in roots or "pydantic" in roots:
                violations.append(str(path.relative_to(SRC)))
    assert not violations, f"LLM/pydantic 의존이 안쪽 계층에 있다: {violations}"


def test_domain_and_application_use_absolute_imports_only() -> None:
    """상대 임포트는 위의 가드들을 통째로 우회한다.

    `_imported_roots`는 `level != 0`인 ImportFrom을 건너뛰고, 바깥 계층 검사들은
    "chika.infrastructure" 같은 리터럴을 찾는데 `from ..infrastructure import x`에는
    그 문자열이 없다. 두 계층은 이미 절대 임포트만 쓰므로 아예 금지한다.
    """
    violations: list[str] = []
    for layer in ("domain", "application"):
        for path in _modules(layer):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            violations.extend(
                f"{path.relative_to(SRC)}:{node.lineno}"
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.level > 0
            )
    assert not violations, f"상대 임포트 금지 (가드를 우회한다): {violations}"

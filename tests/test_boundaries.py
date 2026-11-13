"""Import-boundary test: enforces the standalone rules in Architecture.md section 5."""

import ast
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

REPO_PACKAGES = {"training", "guard", "client", "demo_rag", "gateway", "evals", "scripts", "tests"}

# Allowed in-repo import prefixes per package. Anything else in REPO_PACKAGES is a violation.
ALLOWED_REPO_IMPORTS: dict[str, set[str]] = {
    "guard": {"guard", "training.normalize"},
    "client": {"client"},
    "demo_rag": {"demo_rag", "client"},
    "gateway": {"gateway", "client"},
    "evals": {"evals", "client", "training"},
    "training": {"training"},
    "scripts": {"scripts", "training"},
}

# Third-party top-level modules from the PRD section 12 whitelist (plus their import names).
# Adding a name here means the owner approved the dependency.
THIRD_PARTY = {
    "fastapi", "starlette", "pydantic", "uvicorn", "httpx", "yaml", "pytest",
    "pandas", "numpy", "matplotlib", "seaborn",
    "langchain_core", "langgraph", "chromadb", "tiktoken", "mcp",
    "transformers", "peft", "trl", "bitsandbytes", "unsloth", "torch", "datasets", "vllm",
    "slowapi", "presidio_analyzer", "presidio_anonymizer", "opentelemetry",
}


def _module_names(path: Path, root: Path) -> list[str]:
    """Return absolute module names imported by one file (relative imports resolved)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    pkg_parts = list(path.relative_to(root).with_suffix("").parts[:-1])
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg_parts[: len(pkg_parts) - node.level + 1]
                mod = ".".join(base + ([node.module] if node.module else []))
            else:
                mod = node.module or ""
            names.extend(f"{mod}.{alias.name}" if mod else alias.name for alias in node.names)
    return [n for n in names if n]


def _allowed(name: str, prefixes: set[str]) -> bool:
    """True if module name equals or sits under one of the prefixes."""
    return any(name == p or name.startswith(p + ".") for p in prefixes)


def find_violations(root: Path) -> list[str]:
    """Scan every package under root and list boundary violations."""
    violations: list[str] = []
    for pkg, allowed in ALLOWED_REPO_IMPORTS.items():
        for path in sorted((root / pkg).rglob("*.py")):
            if ".venv" in path.parts:
                continue
            rel = path.relative_to(root).as_posix()
            is_test = "tests" in path.parts
            for name in _module_names(path, root):
                top = name.split(".")[0]
                if top in REPO_PACKAGES:
                    if not _allowed(name, allowed):
                        violations.append(f"{rel}: imports {name}")
                elif top in sys.stdlib_module_names or top in THIRD_PARTY:
                    continue
                elif is_test and top == "conftest":
                    continue
                else:
                    violations.append(f"{rel}: imports unknown module {name} (other project or unapproved dependency)")
    return violations


def test_repo_respects_boundaries() -> None:
    """The real repo has no boundary violations."""
    assert find_violations(REPO) == []


def _write(root: Path, rel: str, code: str) -> None:
    """Create a file (and parent dirs) under root."""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(code, encoding="utf-8")


@pytest.mark.parametrize(
    "rel,code",
    [
        ("guard/a.py", "from training.schemas import DataRow\n"),
        ("guard/b.py", "import demo_rag.graph\n"),
        ("guard/c.py", "from client import ruguard_client\n"),
        ("client/d.py", "from guard.scanner import StubScanner\n"),
        ("demo_rag/e.py", "from guard import scanner\n"),
        ("gateway/f.py", "import some_other_project\n"),
        ("guard/app/g.py", "from ...training import schemas\n"),
    ],
)
def test_detects_violation(tmp_path: Path, rel: str, code: str) -> None:
    """Each forbidden import is reported."""
    _write(tmp_path, rel, code)
    assert len(find_violations(tmp_path)) == 1


def test_allows_permitted_imports(tmp_path: Path) -> None:
    """Allowed imports are not reported."""
    _write(tmp_path, "guard/ok.py", "import os\nfrom fastapi import FastAPI\nfrom training.normalize import normalize_text\n")
    _write(tmp_path, "guard/app/ok2.py", "from ..scanner import StubScanner\n")
    _write(tmp_path, "guard/ok4.py", "from training import normalize\n")
    _write(tmp_path, "demo_rag/ok3.py", "from client.ruguard_client import x\n")
    assert find_violations(tmp_path) == []

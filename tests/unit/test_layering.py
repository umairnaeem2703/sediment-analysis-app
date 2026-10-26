"""NFR-05: the layering rules of B2 hold (src/core is pure maths; src/services has no Tk)."""

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).parents[2] / "src"
CORE_FILES = sorted((SRC / "core").glob("*.py"))
SERVICE_FILES = sorted((SRC / "services").glob("*.py"))

THIRD_PARTY_IN_CORE = {"numpy", "pandas"}
FILE_STDLIB = {"argparse", "io", "os", "pathlib", "shutil", "tempfile"}
FILE_CALLS = {"open", "read_csv", "read_excel", "read_table", "to_csv", "to_excel", "savefig"}


def _imports(path: Path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            yield node.module


def _calls(path: Path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call):
            function = node.func
            yield function.id if isinstance(function, ast.Name) else getattr(function, "attr", "")


@pytest.mark.parametrize("path", CORE_FILES, ids=lambda path: path.name)
def test_x_nfr_05_core_imports_only_the_standard_library_numpy_pandas_and_itself(path):
    for module in _imports(path):
        root = module.split(".")[0]
        assert root in sys.stdlib_module_names | THIRD_PARTY_IN_CORE | {"src"}, f"{path.name} imports {module}"
        assert root not in FILE_STDLIB, f"{path.name} imports {module}"
        if root == "src":
            assert module.startswith("src.core"), f"{path.name} imports {module}"


@pytest.mark.parametrize("path", CORE_FILES, ids=lambda path: path.name)
def test_x_nfr_05_core_does_no_file_io(path):
    assert not FILE_CALLS & set(_calls(path))


@pytest.mark.parametrize("path", SERVICE_FILES, ids=lambda path: path.name)
def test_x_nfr_05_services_never_import_tk_or_the_ui(path):
    for module in _imports(path):
        assert module.split(".")[0] != "tkinter" and not module.startswith("src.ui"), f"{path.name} imports {module}"

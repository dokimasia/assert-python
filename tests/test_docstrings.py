"""Every public callable documents itself.

An assertion library is read through its docstrings more than through
its source, so a missing Args entry is a defect like any other. These
cases are what stop the documentation drifting from the signatures
after the next parameter is added.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
import re
from typing import Any

import pytest

SOURCE = pathlib.Path(__file__).resolve().parent.parent / "src" / "dokimi_assert"

#: Either kind of function definition; a coroutine is documented
#: exactly like any other callable.
Function = ast.FunctionDef | ast.AsyncFunctionDef

#: Parameters that carry no meaning of their own.
SKIPPED = {"self", "cls"}

#: Modules whose contents are re-exported and documented elsewhere.
RE_EXPORTS = {"__init__.py"}


def _public_functions() -> list[tuple[str, str, Function]]:
    """Answer every public function in the package, with where it lives.

    Only what a caller can reach: functions at module level and methods
    on a public class. A function defined inside another is a local
    helper, and documenting it would say nothing to anyone outside.
    """
    found: list[tuple[str, str, Function]] = []
    for path in sorted(SOURCE.rglob("*.py")):
        if path.name in RE_EXPORTS:
            continue
        where = str(path.relative_to(SOURCE))
        module = ast.parse(path.read_text())

        for node in module.body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                if not node.name.startswith("_"):
                    found.append((where, node.name, node))
            elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                for member in node.body:
                    if not isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef):
                        continue
                    if member.name.startswith("_") and member.name != "__init__":
                        continue
                    found.append((where, f"{node.name}.{member.name}", member))
    return found


FUNCTIONS = _public_functions()
IDS = [f"{where}::{name}" for where, name, _ in FUNCTIONS]


def _documented_args(docstring: str) -> set[str]:
    """Answer the parameter names an Args section names."""
    match = re.search(
        r"\n\s*Args:\n(.*?)(?:\n\s*\n\s*[A-Z][a-z]+:|\Z)", docstring, re.S
    )
    if match is None:
        return set()
    return {
        m.group(1)
        for m in re.finditer(r"^\s{4}(\*{0,2}[a-z_][a-z0-9_]*):", match.group(1), re.M)
    }


def _declared_args(node: Any) -> set[str]:
    """Answer the parameter names a signature declares."""
    a = node.args
    names = {p.arg for p in [*a.posonlyargs, *a.args, *a.kwonlyargs]}
    if a.vararg:
        names.add(f"*{a.vararg.arg}")
    if a.kwarg:
        names.add(f"**{a.kwarg.arg}")
    return names - SKIPPED


@pytest.mark.parametrize(("where", "name", "node"), FUNCTIONS, ids=IDS)
def test_every_public_function_has_a_docstring(
    where: str, name: str, node: Any
) -> None:
    """A public callable with no docstring cannot be used from help()."""
    assert ast.get_docstring(node), f"{where}::{name} has no docstring"


@pytest.mark.parametrize(("where", "name", "node"), FUNCTIONS, ids=IDS)
def test_every_parameter_is_documented(where: str, name: str, node: Any) -> None:
    """A parameter with no Args entry is one nobody can use correctly."""
    doc = ast.get_docstring(node) or ""
    declared = _declared_args(node)
    if not declared:
        return

    missing = declared - _documented_args(doc)
    assert not missing, f"{where}::{name} does not document {sorted(missing)}"


@pytest.mark.parametrize(("where", "name", "node"), FUNCTIONS, ids=IDS)
def test_a_returning_function_says_what_it_returns(
    where: str, name: str, node: Any
) -> None:
    """A caller cannot use a return value nobody described."""
    doc = ast.get_docstring(node) or ""
    returns = node.returns
    answers = returns is not None and not (
        isinstance(returns, ast.Constant) and returns.value is None
    )
    if not answers:
        return

    assert "Returns:" in doc, f"{where}::{name} returns a value it does not describe"


@pytest.mark.parametrize(("where", "name", "node"), FUNCTIONS, ids=IDS)
def test_no_restructured_text_markup(where: str, name: str, node: Any) -> None:
    """This package builds no Sphinx, so a role is noise wherever it is read."""
    doc = ast.get_docstring(node) or ""

    roles = re.findall(r":[a-z]+:`[^`]+`", doc)
    assert not roles, f"{where}::{name} carries RST roles: {roles}"
    assert "``" not in doc, f"{where}::{name} carries RST literals"


@pytest.mark.parametrize(("where", "name", "node"), FUNCTIONS, ids=IDS)
def test_every_section_body_is_indented(where: str, name: str, node: Any) -> None:
    """A body flush with its header is not a section any tool will read."""
    doc = ast.get_docstring(node) or ""
    lines = doc.split("\n")

    for index, line in enumerate(lines[:-1]):
        if not re.fullmatch(r"(Args|Returns|Raises):", line.strip()):
            continue
        body = lines[index + 1]
        assert body.startswith("    "), (
            f"{where}::{name} has {line.strip()} with an unindented body: {body!r}"
        )


@pytest.mark.parametrize(("where", "name", "node"), FUNCTIONS, ids=IDS)
def test_no_placeholder_text(where: str, name: str, node: Any) -> None:
    """Generated filler reads as documentation and says nothing."""
    doc = ast.get_docstring(node) or ""

    for filler in ("See above.", "Do the thing.", "The result described above."):
        assert filler not in doc, f"{where}::{name} carries placeholder text"


MODULES = sorted(SOURCE.rglob("*.py"))
MODULE_IDS = [str(p.relative_to(SOURCE)) for p in MODULES]


@pytest.mark.parametrize("path", MODULES, ids=MODULE_IDS)
def test_every_module_documents_itself(path: pathlib.Path) -> None:
    """A module with no docstring gives help() nothing to show."""
    doc = ast.get_docstring(ast.parse(path.read_text()))
    assert doc, f"{path.name} has no module docstring"


@pytest.mark.parametrize("path", MODULES, ids=MODULE_IDS)
def test_no_module_carries_markup(path: pathlib.Path) -> None:
    """A role in a module docstring is read literally, like any other."""
    doc = ast.get_docstring(ast.parse(path.read_text())) or ""

    roles = re.findall(r":[a-z]+:`[^`]+`", doc)
    assert not roles, f"{path.name} carries RST roles: {roles}"
    assert "``" not in doc, f"{path.name} carries RST literals"


def test_the_two_surfaces_document_the_same_assertions() -> None:
    """A name documented on one surface and not the other is a gap."""
    from dokimi_assert import check, expect

    for name in sorted(set(check.__all__) & set(expect.__all__)):
        assert inspect.getdoc(getattr(check, name)), f"check.{name}"
        assert inspect.getdoc(getattr(expect, name)), f"expect.{name}"


def test_the_readme_api_reference_matches_the_code() -> None:
    """A signature list that drifts from the code misleads every reader.

    The README's reference is generated. Run
    ``python tools/api_reference.py --write`` after changing a
    signature, and commit what it produces.
    """
    import subprocess
    import sys

    root = pathlib.Path(__file__).resolve().parent.parent
    generated = subprocess.run(
        [sys.executable, str(root / "tools" / "api_reference.py")],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    readme = (root / "README.md").read_text()
    start, end = "<!-- api-reference:start -->", "<!-- api-reference:end -->"
    assert start in readme and end in readme, "README.md has no api-reference block"

    published = readme.split(start, 1)[1].split(end, 1)[0].strip()
    assert published == generated, (
        "README.md is out of date; run python tools/api_reference.py --write"
    )

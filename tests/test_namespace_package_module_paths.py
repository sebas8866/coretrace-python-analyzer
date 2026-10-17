"""PEP 420 namespace directories nested inside regular Python packages."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from coretrace_python.frontend import build_hir
from coretrace_python.interprocedural.modulegraph import (
    _import_root,
    build_module_graph,
    name_modules,
)
from coretrace_python.semantic.imports import analyze_imports
from coretrace_python.semantic.scopes import analyze_scopes
from coretrace_python.source import SourceManager


class NamespacePackageModulePaths(unittest.TestCase):
    def test_relative_import_from_implicit_subpackage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "pkg"
            (package / "sub").mkdir(parents=True)
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "config.py").write_text("VALUE = 1\n", encoding="utf-8")
            module = package / "sub" / "app.py"
            module.write_text("from ..config import VALUE\n", encoding="utf-8")

            manager = SourceManager()
            source = manager.load_file(module)
            self.assertEqual(source.module_name, "pkg.sub.app")
            self.assertEqual(_import_root(source), root)
            hir = build_hir(source)
            scopes = analyze_scopes(hir)
            table = analyze_imports(hir, scopes)
            self.assertEqual(
                tuple(str(s) for s in table.all_symbols()), ("python.pkg.config.VALUE",)
            )
            named = name_modules(
                root,
                (
                    manager.load_file(package / "__init__.py"),
                    manager.load_file(package / "config.py"),
                    source,
                ),
            )
            self.assertEqual(set(named), {"pkg", "pkg.config", "pkg.sub.app"})
            modules = {name: build_hir(item) for name, item in named.items()}
            imports = {
                name: analyze_imports(item, analyze_scopes(item))
                for name, item in modules.items()
            }
            graph = build_module_graph(named, modules, imports)
            self.assertEqual(graph.imports("pkg.sub.app"), frozenset({"pkg.config"}))

            result = subprocess.run(
                [sys.executable, "-m", "coretrace_python", "--check", str(root)],
                capture_output=True,
                text=True,
                timeout=25,
                check=False,
                env=os.environ.copy(),
            )
            self.assertEqual(result.returncode, 0, result.stderr[-1000:])
            self.assertNotIn("relative import beyond top-level package", result.stderr)

    def test_nested_namespace_portions_and_regular_subpackage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "pkg"
            (package / "nested" / "implicit" / "regular").mkdir(parents=True)
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "nested" / "implicit" / "regular" / "__init__.py").write_text(
                "", encoding="utf-8"
            )
            module = package / "nested" / "implicit" / "regular" / "view.py"
            module.write_text("value = 1\n", encoding="utf-8")
            source = SourceManager().load_file(module)
            self.assertEqual(source.module_name, "pkg.nested.implicit.regular.view")
            self.assertEqual(_import_root(source), root)

    def test_standalone_script_under_nonpackage_stays_top_level(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module = root / "scripts" / "tools" / "run.py"
            module.parent.mkdir(parents=True)
            module.write_text("value = 1\n", encoding="utf-8")
            source = SourceManager().load_file(module)
            self.assertEqual(source.module_name, "run")
            self.assertEqual(_import_root(source), module.parent)

    def test_regular_package_init_and_module_names_remain_stable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "pkg" / "sub"
            package.mkdir(parents=True)
            (package.parent / "__init__.py").write_text("", encoding="utf-8")
            (package / "__init__.py").write_text("", encoding="utf-8")
            module = package / "view.py"
            module.write_text("value = 1\n", encoding="utf-8")
            manager = SourceManager()
            self.assertEqual(manager.load_file(module).module_name, "pkg.sub.view")
            self.assertEqual(manager.load_file(package / "__init__.py").module_name, "pkg.sub")
            self.assertEqual(_import_root(manager.load_file(module)), root)


if __name__ == "__main__":
    unittest.main()

"""Clean Architecture, CI-enforced: presentation → application → domain; infrastructure → application/domain.

domain imports no framework at all; application never imports infrastructure or presentation; only
infrastructure touches Google/Supabase/HTTP/ML libraries; nothing below presentation prints.
"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAYERS = ("domain", "application", "infrastructure", "presentation")
ALLOWED_INTERNAL = {
    "domain": set(),
    "application": {"domain"},
    "infrastructure": {"domain", "application"},
    "presentation": {"domain", "application", "infrastructure"},
}
THIRD_PARTY_ONLY_IN_INFRA = {"requests", "supabase", "googleapiclient", "numpy", "sentence_transformers",
                             "matplotlib", "httpx", "postgrest"}
STDLIB = set(__import__("sys").stdlib_module_names)


def imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def files(layer: str):
    return sorted((ROOT / layer).rglob("*.py"))


class DependencyRuleTest(unittest.TestCase):
    def test_layers_only_import_inward(self):
        for layer in LAYERS:
            for path in files(layer):
                bad = (imports_of(path) & set(LAYERS)) - ALLOWED_INTERNAL[layer] - {layer}
                self.assertEqual(bad, set(), f"{path.relative_to(ROOT)} imports {bad}")

    def test_domain_and_application_are_stdlib_only(self):
        for layer in ("domain", "application"):
            for path in files(layer):
                third = {n for n in imports_of(path) if n not in STDLIB and n not in LAYERS}
                self.assertEqual(third, set(), f"{path.relative_to(ROOT)} imports {third}")

    def test_framework_libraries_live_in_infrastructure(self):
        for layer in ("domain", "application", "presentation"):
            for path in files(layer):
                bad = imports_of(path) & THIRD_PARTY_ONLY_IN_INFRA
                self.assertEqual(bad, set(), f"{path.relative_to(ROOT)} imports {bad}")

    def test_nothing_below_presentation_prints(self):
        for layer in ("domain", "application", "infrastructure"):
            for path in files(layer):
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                            and node.func.id in ("print", "input")):
                        self.fail(f"{path.relative_to(ROOT)}:{node.lineno} prints")

    def test_only_the_composition_root_wires_adapters(self):
        for layer in ("domain", "application", "infrastructure"):
            for path in files(layer):
                self.assertNotIn("composition_root", imports_of(path), str(path))

    def test_secrets_are_not_hardcoded(self):
        for layer in LAYERS:
            for path in files(layer):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("AIzaSy", text, str(path))
                self.assertNotRegex(text, r"eyJ[A-Za-z0-9_-]{20,}", str(path))


if __name__ == "__main__":
    unittest.main()

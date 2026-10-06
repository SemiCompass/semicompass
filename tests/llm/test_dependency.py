import re
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
IMPORT = re.compile(r"^\s*(?:import|from)\s+anthropic\b", re.MULTILINE)


class DependencyTest(unittest.TestCase):
    def test_only_scripts_llm_imports_anthropic(self):
        """AIを呼び出せるのは scripts/llm/ だけ（アーキテクチャ設計書 4.2、CLAUDE.md 9章）。"""
        offenders = [p.relative_to(SCRIPTS).as_posix() for p in SCRIPTS.rglob("*.py")
                     if p.relative_to(SCRIPTS).parts[0] != "llm" and IMPORT.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(offenders, [])

    def test_the_llm_layer_does_import_it(self):
        self.assertTrue(IMPORT.search((SCRIPTS / "llm" / "agent_call.py").read_text(encoding="utf-8")))

    def test_client_is_created_without_arguments_and_no_api_key(self):
        code = "\n".join(l for l in (SCRIPTS / "llm" / "agent_call.py").read_text(encoding="utf-8").splitlines()
                         if not l.lstrip().startswith(("#", '"""', "*")))
        self.assertIn("anthropic.Anthropic()", code)
        self.assertNotIn("api_key=", code)
        self.assertNotIn("ANTHROPIC_API_KEY", code)


if __name__ == "__main__":
    unittest.main()

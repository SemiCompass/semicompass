import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "factcheck"))
import claims  # noqa: E402
import factcheck as fc  # noqa: E402
import morph  # noqa: E402

DICT = {claims.normalize(w) for w in ("アクセル", "アドバンテスト")}


class CommonWordTest(unittest.TestCase):
    def test_near_word_is_a_claim_without_a_predicate(self):
        found = [c.text for c in claims.extract_claims("アクセスログを記録する。", DICT)]
        self.assertIn("アクセス", found)

    def test_predicate_removes_a_common_word_but_not_a_misspelling(self):
        common = lambda w: w == "アクセス"  # noqa: E731
        found = [c.text for c in claims.extract_claims("アクセスログを記録する。アドバンテスド社が作る。", DICT, common)]
        self.assertNotIn("アクセス", found)
        self.assertIn("アドバンテスド", found)

    def test_check_claims_accepts_a_predicate(self):
        results = fc.check_claims("アクセスログを記録する。", [], DICT, set(), None, lambda w: w == "アクセス")
        self.assertEqual(results, [])

    @unittest.skipUnless(morph.available(), "SudachiPy がない")
    def test_sudachi_marks_general_nouns_only(self):
        self.assertTrue(morph.is_common_word("アクセス"))
        self.assertFalse(morph.is_common_word("東京エレクトロン"))  # 固有名詞
        self.assertFalse(morph.is_common_word("アドバンテスド"))  # 書き間違い（未知の語）
        self.assertFalse(morph.is_common_word("アクセスログを"))  # 複数の語

    @unittest.skipUnless(morph.available(), "SudachiPy がない")
    def test_default_check_ignores_access_but_still_catches_misspelling(self):
        self.assertEqual([r for r in fc.check_claims("アクセスログを記録する。", [], DICT, set())], [])
        bad = fc.check_claims("アドバンテスド社が作る。", [], DICT, set())
        self.assertTrue(any(r.result == fc.CONTRADICTION for r in bad))


if __name__ == "__main__":
    unittest.main()

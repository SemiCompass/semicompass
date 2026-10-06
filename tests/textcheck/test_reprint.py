import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "textcheck"))

import reprint  # noqa: E402


def kana(n, start=0x3041):
    return "".join(chr(start + i % 80) for i in range(n))


def kanji(n, start=0x4E00):
    return "".join(chr(start + i) for i in range(n))


class ReprintTest(unittest.TestCase):
    def check(self, source, draft, min_run=30):
        results = reprint.check_reprint([source], {"overview": draft}, min_run)
        return results, reprint.failures(results, min_run)

    def test_no_overlap_passes(self):
        results, failed = self.check(kana(500), kanji(300))
        self.assertEqual(failed, [])
        self.assertLess(results[0].longest, 30)

    def test_boundary_29_passes_30_fails(self):
        shared = kanji(40, 0x5000)
        for n, fails in ((29, False), (30, True), (31, True)):
            with self.subTest(n=n):
                results, failed = self.check(kana(100) + shared[:n] + kana(100, 0x30A1), kanji(50) + shared[:n] + kanji(50, 0x6000))
                self.assertEqual(results[0].longest, n)
                self.assertEqual(bool(failed), fails)

    def test_whitespace_and_width_differences_are_ignored(self):
        shared = "半導体 製造装置の ＡＢＣ　工程 を 説明 する 文章 であり ます 合成 の 文 です 以上 の 通り で ある"
        results, failed = self.check(kana(50) + shared + kana(50), kanji(20) + shared.replace(" ", "").replace("ＡＢＣ", "ABC") + kanji(20, 0x5000))
        self.assertTrue(failed)
        self.assertGreaterEqual(results[0].longest, 30)

    def test_citation_numbers_inserted_mid_sentence_do_not_hide_a_match(self):
        shared = kanji(40, 0x5000)
        draft = kanji(20) + shared[:15] + "[S1]" + shared[15:] + kanji(20, 0x6000)
        results, failed = self.check(kana(50) + shared + kana(50), draft)
        self.assertEqual(results[0].longest, 40)
        self.assertTrue(failed)
        spread = kanji(20) + shared[:10] + "[S1]" + shared[10:20] + "[S12]" + shared[20:30] + "［Ｓ３］" + shared[30:] + kanji(20, 0x6000)
        self.assertTrue(self.check(kana(50) + shared + kana(50), spread)[1])

    def test_citation_numbers_in_the_source_are_ignored_too(self):
        shared = kanji(40, 0x5000)
        self.assertTrue(self.check(shared[:15] + "[S1]" + shared[15:], shared)[1])

    def test_only_citation_pattern_is_removed(self):
        self.assertEqual(reprint.normalize("あ[S1]い[S12]う[Sx]え[S]お"), "あいう[Sx]え[S]お")

    def test_match_does_not_cross_section_boundaries(self):
        shared = kanji(40, 0x5000)
        results = reprint.check_reprint([kana(50) + shared[:20], shared[20:] + kana(50)], {"overview": shared}, 30)
        self.assertEqual(results[0].longest, 20)

    def test_each_field_is_reported_by_name(self):
        shared = kanji(35, 0x5000)
        results = reprint.check_reprint([shared], {"overview": kanji(40), "segments[0].note": shared}, 30)
        failed = reprint.failures(results, 30)
        self.assertEqual([r.field for r in failed], ["segments[0].note"])
        self.assertEqual(reprint.longest_overall(results), 35)

    def test_results_hold_no_text(self):
        results = reprint.check_reprint([kanji(60)], {"overview": kanji(60)}, 30)
        for r in results:
            self.assertEqual(set(vars(r)), {"field", "longest", "failed"})
            self.assertNotIn(kanji(10), repr(r))

    def test_empty_inputs(self):
        self.assertEqual(reprint.check_reprint([], {"a": "あ"}, 30)[0].longest, 0)
        self.assertEqual(reprint.check_reprint(["あ"], {"a": ""}, 30)[0].longest, 0)
        self.assertEqual(reprint.longest_overall([]), 0)

    def test_long_source_is_fast_enough(self):
        import time
        started = time.time()
        reprint.check_reprint([kana(120_000)], {"overview": kana(700)}, 30)
        self.assertLess(time.time() - started, 10)

    def test_shipped_config_is_30(self):
        self.assertEqual(reprint.load_min_run(), 30)

    def test_config_loading_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            for text in ("min_run_chars: 0\n", "min_run_chars: x\n", "other: 1\n", "[\n"):
                path = Path(tmp) / "c.yaml"
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    reprint.load_min_run(path)
            with self.assertRaises(ValueError):
                reprint.load_min_run(Path(tmp) / "nope.yaml")
            (Path(tmp) / "ok.yaml").write_text("min_run_chars: 12\n", encoding="utf-8")
            self.assertEqual(reprint.load_min_run(Path(tmp) / "ok.yaml"), 12)


if __name__ == "__main__":
    unittest.main()

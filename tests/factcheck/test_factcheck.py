"""事実確認（scripts/factcheck/）のテスト。AT-12：わざと誤りを入れた下書きで、見逃さないことを確かめる。合成の語だけを使う。"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "factcheck"))

import claims  # noqa: E402
import factcheck as fc  # noqa: E402

SOURCE = (
    "架空製作所の2025年12月期の連結売上収益は9,582.9億円であった。2026年3月23日に有価証券報告書を提出した。"
    "精密・電子セグメントの売上収益は342,270百万円で、全体の35.7%を占める。従業員数は1,234人である。"
    "半導体の製造にはCMP装置を使う。"
)
LISTED = {"https://example.org/report"}

GOOD = (
    "架空製作所の連結売上収益は、2025年12月期に9,582.9億円であった[S1]。精密・電子の売上収益は3,422.7億円で、全体の35.7%を占める[S1]。"
    "従業員数は1,234人である[S1]。有価証券報告書は2026年3月23日に提出された[S1]。出典：https://example.org/report"
)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        (self.tmp / "data" / "companies").mkdir(parents=True)
        (self.tmp / "data" / "companies" / "kakuu.yaml").write_text(yaml.safe_dump({"slug": "kakuu", "name": "架空製作所", "short_names": ["架空"]}, allow_unicode=True), encoding="utf-8")
        self.dictionary = fc.load_dictionary(self.tmp)
        self.sources = [fc.make_source("S1", SOURCE)]

    def check(self, text, fetcher=None, listed=LISTED):
        return fc.check_claims(text, self.sources, self.dictionary, listed, fetcher)

    def results_of(self, text, kind=None, **kw):
        return [(r.claim.text, r.result) for r in self.check(text, **kw) if kind is None or r.claim.kind == kind]


class ExtractTest(unittest.TestCase):
    def test_numbers_dates_urls_and_names(self):
        found = {(c.kind, c.text) for c in claims.extract_claims(GOOD)}
        for expected in [("number", "9,582.9億円"), ("number", "3,422.7億円"), ("number", "35.7%"), ("number", "1,234人"),
                         ("date", "2025年12月"), ("date", "2026年3月23日"), ("url", "https://example.org/report"), ("proper", "架空製作所")]:
            self.assertIn(expected, found)

    def test_citations_and_full_width_are_normalized(self):
        found = [(c.kind, c.text) for c in claims.extract_claims("売上は１，２３４億円[S1]である。")]
        self.assertEqual(found, [("number", "1,234億円")])


class GroundedTest(Base):
    def test_good_draft_passes(self):
        results = self.check(GOOD, fetcher=lambda u: 200)
        self.assertEqual([r for r in results if r.result != fc.GROUNDED], [])

    def test_unit_conversion_and_rounding_are_allowed(self):
        # 342,270百万円 = 3,422.7億円。桁の丸め（3,423億円）も、表示の桁の範囲で認める
        self.assertEqual(self.results_of("精密・電子の売上収益は3,423億円である。", "number"), [("3,423億円", fc.GROUNDED)])
        self.assertEqual(self.results_of("精密・電子の売上収益は342,270百万円である。", "number"), [("342,270百万円", fc.GROUNDED)])


class ErrorInjectionTest(Base):
    """AT-12：検出すべき誤りを見逃さない。"""

    def not_grounded(self, text, **kw):
        return {t for t, r in self.results_of(text, **kw) if r != fc.GROUNDED}

    def test_changed_number_is_detected(self):
        bad = GOOD.replace("3,422.7億円", "3,842.7億円")
        self.assertIn("3,842.7億円", self.not_grounded(bad, fetcher=lambda u: 200))

    def test_changed_number_near_same_label_is_a_contradiction(self):
        self.assertEqual(dict(self.results_of("精密・電子セグメントの売上収益は3,842.7億円である。", "number"))["3,842.7億円"], fc.CONTRADICTION)

    def test_changed_unit_is_detected(self):
        self.assertIn("1,234社", self.not_grounded("従業員数は1,234社である。"))

    def test_changed_percent_is_detected(self):
        self.assertIn("53.7%", self.not_grounded(GOOD.replace("35.7%", "53.7%"), fetcher=lambda u: 200))

    def test_changed_date_is_detected(self):
        self.assertIn("2026年3月24日", self.not_grounded(GOOD.replace("2026年3月23日", "2026年3月24日"), fetcher=lambda u: 200))

    def test_unlisted_url_is_detected(self):
        self.assertIn("https://example.org/other", self.not_grounded(GOOD + " https://example.org/other", fetcher=lambda u: 200))

    def test_missing_url_is_a_contradiction(self):
        self.assertEqual(dict(self.results_of("出典：https://example.org/report", fetcher=lambda u: 404))["https://example.org/report"], fc.CONTRADICTION)

    def test_connection_failure_is_unverifiable(self):
        def boom(url):
            raise OSError("timeout")
        self.assertEqual(dict(self.results_of("出典：https://example.org/report", fetcher=boom))["https://example.org/report"], fc.UNVERIFIABLE)

    def test_url_not_checked_is_unverifiable(self):
        self.assertEqual(dict(self.results_of("出典：https://example.org/report"))["https://example.org/report"], fc.UNVERIFIABLE)

    def test_misspelled_company_is_a_contradiction(self):
        self.assertEqual(dict(self.results_of("架空製作書は装置を作る。", "proper"))["架空製作書"], fc.CONTRADICTION)

    def test_nonexistent_company_is_detected(self):
        self.assertEqual(dict(self.results_of("未来電子は装置を作る。", "proper"))["未来電子"], fc.UNSUPPORTED)

    def test_dictionary_company_is_grounded(self):
        self.assertEqual(self.results_of("架空製作所は装置を作る。", "proper"), [("架空製作所", fc.GROUNDED)])


class JudgeTest(Base):
    def test_failures_and_acknowledgement(self):
        results = self.check(GOOD.replace("35.7%", "53.7%"), fetcher=lambda u: 200)
        bad = fc.failures(results, set())
        self.assertEqual([r.claim.text for r in bad], ["53.7%"])
        self.assertEqual(fc.failures(results, {fc.fingerprint(bad[0].claim)}), [])

    def test_report_does_not_contain_source_text(self):
        results = self.check(GOOD.replace("35.7%", "53.7%"), fetcher=lambda u: 200)
        report = fc.report(results, set())
        self.assertIn("不合格", report)
        self.assertIn("53.7%", report)
        for phrase in ("精密・電子セグメントの売上収益は", "有価証券報告書を提出した", "CMP装置を使う"):
            self.assertNotIn(phrase, report)

    def test_cli_exit_codes(self):
        draft = self.tmp / "draft.md"
        src = self.tmp / "s1.txt"
        src.write_text(SOURCE, encoding="utf-8")
        front = {"sources": [{"id": "S1", "url": "https://example.org/report"}]}
        draft.write_text("---\n" + yaml.safe_dump(front) + "---\n\n" + GOOD.replace("出典：https://example.org/report", ""), encoding="utf-8")
        self.assertEqual(fc.main(["--draft", str(draft), "--source", f"S1={src}", "--root", str(self.tmp)]), 0)
        draft.write_text("---\n" + yaml.safe_dump(front) + "---\n\n" + GOOD.replace("35.7%", "53.7%"), encoding="utf-8")
        out = self.tmp / "r.json"
        self.assertEqual(fc.main(["--draft", str(draft), "--source", f"S1={src}", "--root", str(self.tmp), "--json", str(out)]), 1)
        bad = [r["fingerprint"] for r in json.loads(out.read_text(encoding="utf-8")) if r["result"] != fc.GROUNDED]
        ack = self.tmp / "ack.json"
        ack.write_text(json.dumps(bad), encoding="utf-8")
        self.assertEqual(fc.main(["--draft", str(draft), "--source", f"S1={src}", "--root", str(self.tmp), "--ack", str(ack)]), 0)
        self.assertEqual(fc.main(["--draft", str(self.tmp / "none.md"), "--root", str(self.tmp)]), 2)


if __name__ == "__main__":
    unittest.main()

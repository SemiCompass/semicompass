"""AG-12 の出力の検査と、IR重要ポイントのファイルへの書き直し（scripts/draft/ir_point.py）のテスト。"""
import copy
import json
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "draft"))
sys.path.insert(0, str(ROOT / "scripts" / "llm"))
sys.path.insert(0, str(ROOT / "tests" / "validate"))
sys.path.insert(0, str(ROOT / "scripts" / "validate"))

import agent_call  # noqa: E402
import ir_point  # noqa: E402

GOOD = {
    "performance_summary": {"text": "2027年3月期第2四半期累計の売上高は1,200.0億円で前年同期比＋10.0%、営業利益は150.0億円で＋5.0%だった。",
                            "source_ids": ["S1"]},
    "outlook": {"text": "会社は、2027年3月期の通期の業績予想を据え置いた。", "source_ids": ["S1"]},
    "highlights": {"text": "装置事業で新しい洗浄装置の出荷を始め、国内工場の生産能力を増やす。", "source_ids": ["S1", "S2"]},
    "uses_quarterly_figures": False,
}
META = {"company": "advantest", "fiscal_period_end": "2027-03", "quarter": 2, "announced_on": "2026-10-28",
        "published_at": "2026-10-29",
        "sources": [{"id": "S1", "title": "決算短信", "publisher": "取引所", "url": "https://www.release.tdnet.info/a.pdf",
                     "accessed_on": "2026-10-29"},
                    {"id": "S2", "title": "決算説明資料", "publisher": "取引所", "url": "https://www.release.tdnet.info/b.pdf",
                     "accessed_on": "2026-10-29"}]}


class CheckOutputTest(unittest.TestCase):
    def test_good_output_passes(self):
        errors, warnings = ir_point.check_output(GOOD, ["S1", "S2"])
        self.assertEqual((errors, warnings), ([], []))

    def test_agent_files_load(self):
        prompt, schema = agent_call.load_agent("AG-12")
        self.assertIn("IR重要ポイント", prompt)
        self.assertEqual(ir_point.check_output(GOOD, ["S1", "S2"], schema)[0], [])

    def test_schema_violation(self):
        bad = copy.deepcopy(GOOD)
        del bad["outlook"]
        errors, _ = ir_point.check_output(bad, ["S1"])
        self.assertTrue(errors and "形式" in errors[0])

    def test_limits_follow_fr307(self):
        bad = copy.deepcopy(GOOD)
        bad["highlights"]["text"] = "あ" * 71  # スキーマの上限も70字
        errors, _ = ir_point.check_output(bad, ["S1", "S2"])
        self.assertTrue(errors)

    def test_unknown_source_id(self):
        bad = copy.deepcopy(GOOD)
        bad["outlook"]["source_ids"] = ["S9"]
        errors, _ = ir_point.check_output(bad, ["S1", "S2"])
        self.assertIn("S9", errors[0])

    def test_investment_words_fail_but_sales_is_fine(self):
        bad = copy.deepcopy(GOOD)
        bad["highlights"]["text"] = "新製品の出荷は株価の買い材料になる。"
        errors, _ = ir_point.check_output(bad, ["S1", "S2"])
        self.assertTrue(any("株価" in e and "買い材料" in e for e in errors))
        ok = copy.deepcopy(GOOD)
        ok["performance_summary"]["text"] = "売上高と売り上げの総利益が増えた。"
        self.assertEqual(ir_point.check_output(ok, ["S1", "S2"])[0], [])

    def test_citations_and_markup_are_not_allowed_in_text(self):
        bad = copy.deepcopy(GOOD)
        bad["outlook"]["text"] = "会社は、通期の予想を据え置いた。[S1]"
        errors, _ = ir_point.check_output(bad, ["S1", "S2"])
        self.assertTrue(any("出典の番号" in e for e in errors))

    def test_warning_words(self):
        warn = copy.deepcopy(GOOD)
        warn["highlights"]["text"] = "次世代の洗浄装置の出荷を始めた。"
        errors, warnings = ir_point.check_output(warn, ["S1", "S2"])
        self.assertEqual(errors, [])
        self.assertIn("次世代", warnings[0])

    def test_error_messages_do_not_contain_the_text(self):
        bad = copy.deepcopy(GOOD)
        bad["highlights"]["text"] = "固有の文章ゼータは株価に効く。"
        errors, _ = ir_point.check_output(bad, ["S1", "S2"])
        self.assertTrue(errors)
        self.assertFalse(any("ゼータ" in e for e in errors))

    def test_reprint_check(self):
        source = "新しい洗浄装置の出荷を開始した。国内工場の生産能力を増強する。"
        copied = copy.deepcopy(GOOD)
        copied["highlights"]["text"] = source
        errors, longest = ir_point.reprint_check(copied, [source], 20)
        self.assertTrue(errors)
        self.assertGreaterEqual(longest, 20)


class RenderTest(unittest.TestCase):
    def test_render_passes_file_schema_and_site_checks(self):
        text = ir_point.render(GOOD, META)
        front_text, body = text.split("---\n", 2)[1:]
        front = yaml.safe_load(front_text)
        self.assertEqual(ir_point.check_file(front), [])
        self.assertEqual((front["draft"], front["ai_generated"]), (True, True))
        self.assertEqual([line for line in body.splitlines() if line.startswith("#")], ["## 業績の要点", "## 今期見通し", "## 注目材料"])
        self.assertIn("[S1][S2]", body)

    def test_file_path(self):
        self.assertEqual(ir_point.file_path("advantest", "2027-03", 2), "content/ir-points/advantest/2027-03-q2.md")

    def test_rendered_file_passes_validate_data(self):
        from test_ir_points import SOURCES_YAML  # noqa: E402
        from test_validate_data import Base  # noqa: E402

        class Probe(Base):
            def runTest(self):
                pass

        probe = Probe()
        probe.setUp()
        try:
            (probe.root / "config" / "sources.yaml").write_text(yaml.safe_dump(SOURCES_YAML, allow_unicode=True), encoding="utf-8")
            rel = ir_point.file_path(META["company"], META["fiscal_period_end"], META["quarter"])
            path = probe.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(ir_point.render(GOOD, META), encoding="utf-8")
            errors = [str(p) for p in probe.check() if p.file == rel and p.severity == "error"]
            self.assertEqual(errors, [])
        finally:
            probe.tearDown()


class ExampleTest(unittest.TestCase):
    def test_example_is_fictional_and_well_formed(self):
        data = json.loads((ROOT / "agents" / "AG-12" / "examples" / "01-basic.json").read_text(encoding="utf-8"))
        self.assertEqual(set(data), {"description", "input", "expect"})
        ids = [s["id"] for s in data["input"]["task"]["sources"]]
        self.assertEqual(sorted(data["input"]["materials"]), sorted(ids))
        self.assertTrue(all("架空" in v for v in data["input"]["materials"].values()))


if __name__ == "__main__":
    unittest.main()

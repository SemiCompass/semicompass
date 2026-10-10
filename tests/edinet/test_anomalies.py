import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "edinet"))
import check_anomalies as ca  # noqa: E402

CFG = ca.load_config()


def money(v):
    return {"value": v, "unit": "million_yen"}


def fin(end, sales, op=100, ni=80, seg=None, doc="D1", ptype="annual"):
    return {"fiscal_period_end": end[:7], "period_type": ptype, "period_end": end, "doc_id": doc,
            "net_sales": money(sales), "operating_income": money(op), "net_income": money(ni),
            "segments": seg if seg is not None else [{"net_sales_external": money(sales)}]}


def company(*fins, filings=()):
    return {"company": "x", "financials": list(fins), "filings": list(filings)}


class AnomalyTest(unittest.TestCase):
    def check(self, before, after):
        return ca.check_company("x", before, after, CFG)

    def base(self):
        return company(fin("2025-03-31", 1000, doc="D0"))

    def test_normal_change_passes(self):
        before = self.base()
        after = company(fin("2025-03-31", 1000, doc="D0"), fin("2026-03-31", 1100, 120, 90))
        self.assertEqual(self.check(before, after), [])

    def test_sales_jump(self):
        after = company(fin("2025-03-31", 1000, doc="D0"), fin("2026-03-31", 1600))
        self.assertTrue(any("急変" in m and "売上高" in m for m in self.check(self.base(), after)))

    def test_profit_sign_change(self):
        after = company(fin("2025-03-31", 1000, doc="D0"), fin("2026-03-31", 1000, op=-5))
        self.assertTrue(any("符号" in m for m in self.check(self.base(), after)))

    def test_unit_error(self):
        after = company(fin("2025-03-31", 1000, doc="D0"), fin("2026-03-31", 1_000_000, op=100_000, ni=80_000,
                                                              seg=[{"net_sales_external": money(1_000_000)}]))
        self.assertTrue(any("単位" in m for m in self.check(self.base(), after)))

    def test_missing_field(self):
        broken = fin("2026-03-31", 1000)
        del broken["operating_income"]
        after = company(fin("2025-03-31", 1000, doc="D0"), broken)
        self.assertTrue(any("欠け" in m and "営業利益" in m for m in self.check(self.base(), after)))

    def test_segment_sum_mismatch(self):
        after = company(fin("2025-03-31", 1000, doc="D0"), fin("2026-03-31", 1000, seg=[{"net_sales_external": money(800)}]))
        self.assertTrue(any("合計の不一致" in m for m in self.check(self.base(), after)))

    def test_new_failed_filing_only(self):
        f = {"doc_id": "D9", "status": "failed"}
        before = company(filings=[f])
        self.assertEqual(self.check(before, company(filings=[f])), [])
        self.assertTrue(any("取得の失敗" in m for m in self.check(company(), company(filings=[f]))))

    def test_old_entries_are_not_rechecked(self):
        weird = company(fin("2025-03-31", 1000, doc="D0"), fin("2026-03-31", 9000))
        self.assertEqual(self.check(copy.deepcopy(weird), weird), [])

    def test_half_year_compares_with_same_type(self):
        before = company(fin("2025-09-30", 500, ptype="half", doc="H0"), fin("2025-03-31", 1000, doc="D0"))
        after = copy.deepcopy(before)
        after["financials"].append(fin("2026-09-30", 520, ptype="half", doc="H1"))
        self.assertEqual(self.check(before, after), [])


class CliTest(unittest.TestCase):
    def test_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            b, a = Path(d, "b"), Path(d, "a")
            b.mkdir(); a.mkdir()
            old = company(fin("2025-03-31", 1000, doc="D0"))
            (b / "x.json").write_text(json.dumps(old), encoding="utf-8")
            (a / "x.json").write_text(json.dumps(company(fin("2025-03-31", 1000, doc="D0"), fin("2026-03-31", 1050))), encoding="utf-8")
            self.assertEqual(ca.main(["--before", str(b), "--after", str(a)]), 0)
            (a / "x.json").write_text(json.dumps(company(fin("2025-03-31", 1000, doc="D0"), fin("2026-03-31", 5000))), encoding="utf-8")
            self.assertEqual(ca.main(["--before", str(b), "--after", str(a)]), 10)
            self.assertEqual(ca.main(["--before", str(b), "--after", str(Path(d, "none"))]), 0)


class RealDataTest(unittest.TestCase):
    def test_existing_data_has_no_surprises_when_everything_is_new(self):
        """全社の既存データを「新しい」として流して、誤検知の様子を見る（異常として出るものは、実データの事実）。"""
        with tempfile.TemporaryDirectory() as d:
            result = ca.run(Path(d), ROOT / "data" / "auto", CFG)
        for slug, msgs in result.items():
            for m in msgs:
                self.assertNotIn("単位の誤り", m, f"{slug}: {m}")


if __name__ == "__main__":
    unittest.main()

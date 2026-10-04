"""config/xbrl-map.yaml の段階2の更新（実際の書類で確かめた内容）の確認。"""

import json
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "xbrl-map.yaml"
SCHEMA = ROOT / "schemas" / "config" / "xbrl-map.schema.json"
TEXT = CONFIG.read_text(encoding="utf-8")
DATA = yaml.safe_load(TEXT)
CONFIRMED = "確認済み（東京エレクトロン、SUMCO、ソニー、レゾナックの実際の書類、2026年10月）"

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None


class XbrlMapStage2Test(unittest.TestCase):
    def test_passes_the_schema(self):
        if Draft202012Validator is None:
            self.skipTest("jsonschema がない")
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual([e.message for e in Draft202012Validator(schema).iter_errors(DATA)], [])

    def test_jgaap_items(self):
        jgaap = DATA["standards"]["jgaap"]
        self.assertEqual(jgaap["items"], {
            "net_sales": ["jppfs_cor:NetSales", "jppfs_cor:OperatingRevenue1",
                          "jpcrp_cor:NetSalesSummaryOfBusinessResults"],
            "operating_income": ["jppfs_cor:OperatingIncome"],
            "ordinary_income": ["jppfs_cor:OrdinaryIncome", "jpcrp_cor:OrdinaryIncomeLossSummaryOfBusinessResults"],
            "net_income": ["jppfs_cor:ProfitLossAttributableToOwnersOfParent",
                           "jpcrp_cor:ProfitLossAttributableToOwnersOfParentSummaryOfBusinessResults"],
        })
        self.assertEqual(jgaap["expected_absent"], [])
        for key in ("segment", "region"):  # 日本基準のセグメント・地域は、項目を置かない
            self.assertFalse([k for k in jgaap["items"] if key in k])

    def test_ifrs_items(self):
        ifrs = DATA["standards"]["ifrs"]
        self.assertEqual(ifrs["items"], {
            "net_sales": ["jpigp_cor:RevenueIFRS", "jpigp_cor:NetSalesIFRS",
                          "jpcrp_cor:RevenueIFRSSummaryOfBusinessResults"],
            "operating_income": ["jpigp_cor:OperatingProfitLossIFRS"],
            "net_income": ["jpigp_cor:ProfitLossAttributableToOwnersOfParentIFRS",
                           "jpcrp_cor:ProfitLossAttributableToOwnersOfParentIFRSSummaryOfBusinessResults"],
            "segment_external_sales": ["jpigp_cor:RevenueFromExternalCustomersIFRS",
                                       "jpigp_cor:SalesToExternalCustomersIFRS"],
        })
        self.assertEqual(ifrs["expected_absent"], ["ordinary_income"])

    def test_usgaap_is_unchanged(self):
        self.assertEqual(DATA["standards"]["usgaap"], {
            "items": {
                "net_sales": ["jpcrp_cor:RevenuesUSGAAPSummaryOfBusinessResults"],
                "operating_income": ["jpcrp_cor:OperatingIncomeLossUSGAAPSummaryOfBusinessResults"],
                "net_income": ["jpcrp_cor:NetIncomeLossAttributableToOwnersOfParentUSGAAPSummaryOfBusinessResults"],
            },
            "expected_absent": ["ordinary_income"],
        })

    def test_employees(self):
        self.assertEqual(DATA["employees"], {
            "employees_consolidated": ["jpcrp_cor:NumberOfEmployees"],
            "employees_non_consolidated": ["jpcrp_cor:NumberOfEmployees"],
            "average_age": ["jpcrp_cor:AverageAgeYearsInformationAboutReportingCompanyInformationAboutEmployees"],
            "average_length_of_service": [
                "jpcrp_cor:AverageLengthOfServiceYearsInformationAboutReportingCompanyInformationAboutEmployees"],
            "average_annual_salary": [
                "jpcrp_cor:AverageAnnualSalaryInformationAboutReportingCompanyInformationAboutEmployees"],
        })

    def test_doc_types_are_unchanged(self):
        self.assertEqual(list(DATA["doc_types"]), ["120", "130", "160", "170"])

    def test_header_has_the_rules_for_stage_3(self):
        header = "\n".join(line for line in TEXT.splitlines() if line.startswith("#")).split("schema_version")[0]
        for phrase in ("UTF-16LE（BOMあり）", "jpcrp030000-asr", "jpcrp040300-ssr", "jpaud",
                       "CurrentYearDuration", "CurrentYearInstant", "InterimDuration", "InterimInstant",
                       "Prior1YearDuration", "Prior1InterimDuration",
                       "_NonConsolidatedMember", "「連結・個別」の列は", "「その他」",
                       "セグメントの member", "期間", "regions は空にする"):
            self.assertIn(phrase, header)

    def test_confirmation_notes(self):
        lines = TEXT.splitlines()
        self.assertIn(CONFIRMED, lines[2] + lines[3])  # 確認の状況の説明が、先頭にある
        self.assertIn("未確認", "\n".join(lines[:6]))

        def line_of(element):
            return next(line for line in lines if element in line and not line.lstrip().startswith("#") and line.lstrip().startswith("- "))

        # 指示で確認済みとされた要素
        for element in ("jppfs_cor:NetSales ", "jpcrp_cor:NetSalesSummaryOfBusinessResults"):
            self.assertIn(CONFIRMED, line_of(element), msg=element)
        self.assertIn("確認済み（レゾナックの実際の書類、2026年10月）", line_of("jpigp_cor:RevenueIFRS"))
        self.assertIn("確認済み（ソニーの実際の書類、2026年10月）", line_of("jpigp_cor:NetSalesIFRS"))
        self.assertIn("確認済み（レゾナックとソニーの実際の書類、2026年10月）", TEXT)
        # 未確認とされた要素
        self.assertIn("未確認", line_of("jppfs_cor:OperatingRevenue1"))
        self.assertNotIn("確認済み", line_of("jppfs_cor:OperatingRevenue1"))
        for element in DATA["standards"]["usgaap"]["items"].values():
            for name in element:
                self.assertIn("未確認", line_of(name))
        self.assertIn("日本基準では未確認", TEXT)
        # 確認済みと書いた行は、確認済みの要素だけ（未確認の要素に「確認済み」の印を付けない）
        for line in lines:
            if line.lstrip().startswith("- ") and "確認済み" in line:
                self.assertTrue(re.search(r"NetSales |NetSalesSummaryOfBusinessResults|RevenueIFRS|NetSalesIFRS", line), msg=line)


if __name__ == "__main__":
    unittest.main()

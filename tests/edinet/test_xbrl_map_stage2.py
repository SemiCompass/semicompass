"""config/xbrl-map.yaml の確定版（実際の書類8件で確かめた内容）の確認。"""

import json
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "xbrl-map.yaml"
SCHEMA = ROOT / "schemas" / "config" / "xbrl-map.schema.json"
TEXT = CONFIG.read_text(encoding="utf-8")
LINES = TEXT.splitlines()
DATA = yaml.safe_load(TEXT)
HEADER = "\n".join(line for line in LINES if line.startswith("#")).split("schema_version")[0]

JGAAP = "（東京エレクトロン、SUMCO、富士電機）"
IFRS = "（ソニー、レゾナック、京セラ、アドバンテスト）"

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None


def line_of(element, after=0):
    """要素名の行（コメントでない、`- ` で始まる行）を返す。同じ要素が複数あるときは after 番目以降の最初。"""
    found = [(i, line) for i, line in enumerate(LINES)
             if line.lstrip().startswith("- ") and re.search(re.escape(element) + r"(\s|$)", line)]
    return next(line for i, line in found if i >= after)


def standard_block(name):
    start = next(i for i, line in enumerate(LINES) if line.startswith(f"  {name}:"))
    end = next((i for i in range(start + 1, len(LINES)) if re.match(r"^  (\w+):|^\S", LINES[i])), len(LINES))
    return LINES[start:end]


class FinalXbrlMapTest(unittest.TestCase):
    def test_passes_the_schema(self):
        if Draft202012Validator is None:
            self.skipTest("jsonschema がない")
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        self.assertEqual([e.message for e in Draft202012Validator(schema).iter_errors(DATA)], [])

    def test_doc_types_are_unchanged(self):
        self.assertEqual(DATA["doc_types"], {"120": "annual_report", "130": "amended_annual_report",
                                             "160": "semiannual_report", "170": "amended_semiannual_report"})

    def test_jgaap(self):
        jgaap = DATA["standards"]["jgaap"]
        self.assertEqual(jgaap["items"], {
            "net_sales": ["jppfs_cor:NetSales", "jpcrp_cor:NetSalesSummaryOfBusinessResults",
                          "jppfs_cor:OperatingRevenue1"],  # OperatingRevenue1 は末尾
            "operating_income": ["jppfs_cor:OperatingIncome"],
            "ordinary_income": ["jppfs_cor:OrdinaryIncome", "jpcrp_cor:OrdinaryIncomeLossSummaryOfBusinessResults"],
            "net_income": ["jppfs_cor:ProfitLossAttributableToOwnersOfParent",
                           "jpcrp_cor:ProfitLossAttributableToOwnersOfParentSummaryOfBusinessResults"],
            "segment_external_sales": ["jpcrp_cor:RevenuesFromExternalCustomers"],
            "segment_total_sales": ["jppfs_cor:NetSales"],
            "segment_profit": ["jppfs_cor:OperatingIncome"],
        })
        self.assertEqual(jgaap["expected_absent"], [])
        self.assertFalse([k for k in jgaap["items"] if "region" in k])  # 地域別は、項目を置かない

    def test_ifrs(self):
        ifrs = DATA["standards"]["ifrs"]
        self.assertEqual(ifrs["items"], {
            "net_sales": ["jpigp_cor:NetSalesIFRS", "jpigp_cor:RevenueIFRS",
                          "jpcrp_cor:RevenueIFRSSummaryOfBusinessResults"],
            "operating_income": ["jpigp_cor:OperatingProfitLossIFRS"],
            "net_income": ["jpigp_cor:ProfitLossAttributableToOwnersOfParentIFRS",
                           "jpcrp_cor:ProfitLossAttributableToOwnersOfParentIFRSSummaryOfBusinessResults"],
            "segment_external_sales": ["jpigp_cor:SalesToExternalCustomersIFRS",
                                       "jpigp_cor:RevenueFromExternalCustomersIFRS",
                                       "*:SalesAndFinancialServicesRevenueToCustomersIFRS"],
            "segment_total_sales": ["jpigp_cor:NetSalesIFRS", "jpigp_cor:RevenueIFRS",
                                    "*:SalesAndFinancialServicesRevenueIFRS"],
            "segment_profit": ["jpigp_cor:SegmentProfitLossIFRS", "jpigp_cor:OperatingProfitLossIFRS"],
        })
        self.assertEqual(ifrs["expected_absent"], ["ordinary_income"])

    def test_usgaap_has_only_sales_and_net_income(self):
        usgaap = DATA["standards"]["usgaap"]
        self.assertEqual(usgaap["items"], {
            "net_sales": ["jpcrp_cor:RevenuesUSGAAPSummaryOfBusinessResults"],
            "net_income": ["jpcrp_cor:NetIncomeLossAttributableToOwnersOfParentUSGAAPSummaryOfBusinessResults"],
        })
        self.assertEqual(usgaap["expected_absent"], ["operating_income", "ordinary_income"])

    def test_ordinary_income_only_in_jgaap(self):
        self.assertIn("ordinary_income", DATA["standards"]["jgaap"]["items"])
        for name in ("ifrs", "usgaap"):
            self.assertNotIn("ordinary_income", DATA["standards"][name]["items"])
            self.assertIn("ordinary_income", DATA["standards"][name]["expected_absent"])

    def test_employees_are_unchanged(self):
        self.assertEqual(DATA["employees"], {
            "employees_consolidated": ["jpcrp_cor:NumberOfEmployees"],
            "employees_non_consolidated": ["jpcrp_cor:NumberOfEmployees"],
            "average_age": ["jpcrp_cor:AverageAgeYearsInformationAboutReportingCompanyInformationAboutEmployees"],
            "average_length_of_service": [
                "jpcrp_cor:AverageLengthOfServiceYearsInformationAboutReportingCompanyInformationAboutEmployees"],
            "average_annual_salary": [
                "jpcrp_cor:AverageAnnualSalaryInformationAboutReportingCompanyInformationAboutEmployees"],
        })

    def test_dei(self):
        self.assertEqual(DATA["dei"], {
            "elements": {
                "accounting_standard": "jpdei_cor:AccountingStandardsDEI",
                "consolidated": "jpdei_cor:WhetherConsolidatedFinancialStatementsArePreparedDEI",
                "period_type": "jpdei_cor:TypeOfCurrentPeriodDEI",
                "fiscal_year_start": "jpdei_cor:CurrentFiscalYearStartDateDEI",
                "period_end": "jpdei_cor:CurrentPeriodEndDateDEI",
                "fiscal_year_end": "jpdei_cor:CurrentFiscalYearEndDateDEI",
            },
            "accounting_standards": {"Japan GAAP": "jgaap", "IFRS": "ifrs", "US GAAP": "usgaap"},
            "period_types": {"FY": "annual", "HY": "half", "Q2": "half"},  # Q2 は docTypeCode 160 のときだけ有効（extract.py）
        })
        # YAMLの値が、文字列として読まれる（真偽値などにならない）
        self.assertTrue(all(isinstance(k, str) for k in DATA["dei"]["period_types"]))
        # DEIの会計基準の値は、standards のキーに対応する
        self.assertEqual(set(DATA["dei"]["accounting_standards"].values()), set(DATA["standards"]))

    def test_header_keeps_the_existing_rules(self):
        for phrase in ("UTF-16LE（BOMあり）", "jpcrp030000-asr", "jpcrp040300-ssr", "jpaud",
                       "CurrentYearDuration", "CurrentYearInstant", "InterimDuration", "InterimInstant",
                       "Prior1YearDuration", "Prior1InterimDuration", "_NonConsolidatedMember"):
            self.assertIn(phrase, HEADER)

    def test_header_has_the_new_rules(self):
        flat = re.sub(r"\s*\n#\s*", "", "\n" + HEADER)  # 折り返しをつなげる
        for phrase in (
            "会計基準、連結の有無、期間は、DEI（下の dei）から読む",
            "DEIの連結財務諸表の作成の有無と、コンテキストで行う",
            "CSV の「連結・個別」の列は使わない",
            "IFRS の連結の行は「その他」になる",
            "fiscal_period_end は、DEIの fiscal_year_end の年月",
            "データ定義書 2.4.3",
            "FY → annual", "HY → half",
            "period_start は、DEIの fiscal_year_start", "period_end は、DEIの period_end（半期は、その半期の末日）",
            "CurrentYearInstant（連結）、CurrentYearInstant_NonConsolidatedMember（単体）に完全に一致する行だけ",
            "セグメント別の従業員数の行（Member を含むコンテキスト）は使わない",
            "TotalOfReportableSegmentsAndOthersMember（合計。セグメントではない）",
            "ReconcilingItemsMember（調整額。segment_adjustment に使う）",
            "NonConsolidatedMember（単体の文脈。セグメントではない）",
            "最初の _ の後）の部分から、会社固有の前置き",
            "jpcrp030000-asr_E01740-000 のような形",
            "自動取得のデータの name には、この名前（前置きを除いたメンバー名）を入れる",
            "セグメント対応表（data/segments/）から表示する",
            "地域別の売上は、8つの書類のどれにも数値の項目がなかった。regions は空にする",
            "米国基準（キヤノン）は、売上と純利益だけ。営業利益は null、segments は [] にする",
        ):
            self.assertIn(phrase, flat, msg=phrase)
        self.assertNotIn("4つの書類では", HEADER)  # 古い記述は残さない

    def test_unconfirmed_items_are_listed_and_marked(self):
        self.assertIn("未確認のまま残すもの", HEADER)
        for phrase in ("jppfs_cor:OperatingRevenue1", "半期報告書での米国基準", "日本基準の半期のセグメント"):
            self.assertIn(phrase, HEADER)
        # 未確認と書いた行は、この1つだけ（要素の行）。それ以外の要素の行に「未確認」はない
        marked = [line for line in LINES if line.lstrip().startswith("- ") and "未確認" in line]
        self.assertEqual(len(marked), 1)
        self.assertIn("jppfs_cor:OperatingRevenue1", marked[0])
        self.assertNotIn("確認済み", marked[0])
        # 日本基準の中で、末尾に置かれている
        block = standard_block("jgaap")
        net_sales = block[block.index(next(line for line in block if "net_sales:" in line)) + 1:][:3]
        self.assertIn("OperatingRevenue1", net_sales[-1])
        # 半期のセグメント、半期の米国基準は、コメントに「未確認」とある
        self.assertTrue(any("半期報告書のセグメント" in line and "未確認" in line for line in LINES if line.startswith("  #")))
        self.assertTrue(any("半期報告書での米国基準" in line and "未確認" in line for line in LINES if line.startswith("  #")))

    def test_confirmed_items_name_the_companies(self):
        for element in ("jppfs_cor:NetSales", "jpcrp_cor:NetSalesSummaryOfBusinessResults", "jppfs_cor:OperatingIncome",
                        "jppfs_cor:OrdinaryIncome", "jpcrp_cor:OrdinaryIncomeLossSummaryOfBusinessResults",
                        "jppfs_cor:ProfitLossAttributableToOwnersOfParent",
                        "jpcrp_cor:ProfitLossAttributableToOwnersOfParentSummaryOfBusinessResults"):
            self.assertIn("確認済み" + JGAAP, line_of(element), msg=element)
        for element in ("jpcrp_cor:RevenuesFromExternalCustomers",):
            self.assertIn("確認済み（富士電機）", line_of(element))
        start = next(i for i, line in enumerate(LINES) if "segment_total_sales:" in line)
        self.assertIn("確認済み（富士電機）", line_of("jppfs_cor:NetSales", after=start))
        start = next(i for i, line in enumerate(LINES) if "segment_profit:" in line)
        self.assertIn("確認済み（富士電機）", line_of("jppfs_cor:OperatingIncome", after=start))
        for element in ("jpigp_cor:NetSalesIFRS", "jpigp_cor:RevenueIFRS", "jpcrp_cor:RevenueIFRSSummaryOfBusinessResults",
                        "jpigp_cor:OperatingProfitLossIFRS", "jpigp_cor:ProfitLossAttributableToOwnersOfParentIFRS",
                        "jpcrp_cor:ProfitLossAttributableToOwnersOfParentIFRSSummaryOfBusinessResults",
                        "jpigp_cor:SalesToExternalCustomersIFRS", "jpigp_cor:RevenueFromExternalCustomersIFRS"):
            self.assertIn("確認済み" + IFRS, line_of(element), msg=element)
        self.assertIn("確認済み（京セラ、アドバンテスト）", line_of("jpigp_cor:SegmentProfitLossIFRS"))
        start = next(i for i, line in enumerate(LINES) if "- jpigp_cor:SegmentProfitLossIFRS" in line) + 1
        self.assertIn("確認済み（ソニー）", line_of("jpigp_cor:OperatingProfitLossIFRS", after=start))
        for element in DATA["standards"]["usgaap"]["items"].values():
            self.assertIn("確認済み（キヤノン）", line_of(element[0]))
        self.assertIn("確認済み（東京エレクトロン、ソニー、キヤノン）", TEXT)
        self.assertIn("半期報告書には、従業員の項目がない", TEXT)

    def test_header_states_the_q2_and_wildcard_rules(self):
        self.assertIn('"Q2"', HEADER)
        self.assertIn("160（半期報告書）のときだけ", HEADER)
        self.assertIn("先頭が「*:」の候補", HEADER)
        self.assertIn("EDINETCodeDEI", HEADER)
        self.assertIn("確認済み：ソニーの2024年3月期の書類", HEADER)
        for element in ("*:SalesAndFinancialServicesRevenueToCustomersIFRS", "*:SalesAndFinancialServicesRevenueIFRS"):
            self.assertIn("確認済み（ソニーの2024年3月期の書類）", next(line for line in LINES if element in line and line.lstrip().startswith("- ")))
        self.assertIn("160（半期報告書）のときだけ有効", next(line for line in LINES if line.lstrip().startswith('"Q2": half')))

    def test_header_states_the_eight_documents(self):
        for company in ("東京エレクトロン", "SUMCO", "ソニー", "レゾナック", "富士電機", "京セラ", "アドバンテスト", "キヤノン"):
            self.assertIn(company, HEADER)
        self.assertIn("実際の書類8件、2026年10月", HEADER)


if __name__ == "__main__":
    unittest.main()

import copy
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import yaml

import edinet_fakes as fk
from test_comparative import (CODE, DOC_TYPES, EXT, JST, OPI, T1, T2, XMAP, build, doc, emp_rows, ext, fin_rows, fy2025,
                              fy2026, listing, money, prior_fin, seg_rows, state)
from test_extract import HEADER, dei, r
from test_inspect_document import csv_text, zip_response

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "validate"))
import validate_data  # noqa: E402

build_auto = __import__("build_auto")
extract = __import__("extract")
ingest_company = __import__("ingest_company")
LATER = datetime(2026, 10, 9, 9, 0, tzinfo=JST)
SONY = "E01777"
SONY_PFX = "jpcrp030000-asr_E01777-000"
CUR, PRI = "CurrentYearDuration", "Prior1YearDuration"


def emp_all(inst, ec=1000, es=500):
    return emp_rows(inst, ec, es, 40) + [
        r("jpcrp_cor:AverageLengthOfServiceYearsInformationAboutReportingCompanyInformationAboutEmployees",
          inst + "_NonConsolidatedMember", "10", "", "年"),
        r("jpcrp_cor:AverageAnnualSalaryInformationAboutReportingCompanyInformationAboutEmployees",
          inst + "_NonConsolidatedMember", "7000000")]


def ifrs_fin(dur, ns, oi, ni):
    return [money("jpigp_cor:RevenueIFRS", dur, ns, "売上収益（IFRS）"),
            money("jpigp_cor:OperatingProfitLossIFRS", dur, oi, "営業利益（IFRS）"),
            money("jpigp_cor:ProfitLossAttributableToOwnersOfParentIFRS", dur, ni, "当期利益（IFRS）")]


def ifrs_segs(dur, members, adjustment=None, pfx="jpcrp030000-asr_E01950-000"):
    """members: {名前: (外部売上, 利益)}。ソニーの形：利益は OperatingProfitLossIFRS のメンバー付きの行。"""
    out = []
    for name, (external, profit) in members.items():
        out.append(money("jpigp_cor:SalesToExternalCustomersIFRS", f"{dur}_{pfx}{name}", external))
        out.append(money("jpigp_cor:OperatingProfitLossIFRS", f"{dur}_{pfx}{name}", profit))
    if adjustment is not None:
        out.append(money("jpigp_cor:OperatingProfitLossIFRS", f"{dur}_{pfx}ReconcilingItemsMember", adjustment))
    return out


def usgaap_doc(doc_id="S100AAA1", ns=1_000_000_000, submitted="2025-06-20 15:00"):
    rows = dei("US GAAP", start="2024-04-01", end="2025-03-31", fy_end="2025-03-31", code=CODE) + [
        r("jpcrp_cor:RevenuesUSGAAPSummaryOfBusinessResults", CUR, str(ns), "売上高（US GAAP）、経営指標等"),
        r("jpcrp_cor:NetIncomeLossAttributableToOwnersOfParentUSGAAPSummaryOfBusinessResults", CUR, "20000000")] + \
        emp_all("CurrentYearInstant")
    return doc(doc_id, rows, submitted=submitted)


def ifrs_doc26(doc_id="S100AAA2", prior=(), segs=(), submitted="2026-06-20 15:00", doc_code="120", code=CODE):
    rows = dei("IFRS", start="2025-04-01", end="2026-03-31", fy_end="2026-03-31", code=code) + \
        ifrs_fin(CUR, 1_200_000_000, 600_000_000, 300_000_000) + list(segs) + emp_all("CurrentYearInstant") + list(prior)
    return doc(doc_id, rows, doc_code=doc_code, start="2025-04-01", end="2026-03-31", submitted=submitted)


def check_all(testcase, data):
    """スキーマ（jsonschema＋FormatChecker）と、scripts/validate/validate_data.py に合格する。"""
    testcase.assertEqual(ingest_company.validate(data), [])
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "data" / "companies").mkdir(parents=True)
        (root / "data" / "auto").mkdir()
        (root / "config").mkdir()
        shutil.copy(ROOT / "data" / "supply-chain.yaml", root / "data" / "supply-chain.yaml")
        shutil.copy(ROOT / "config" / "xbrl-map.yaml", root / "config" / "xbrl-map.yaml")
        shutil.copy(ROOT / "data" / "companies" / "advantest.yaml", root / "data" / "companies" / "advantest.yaml")
        import json
        (root / "data" / "auto" / "advantest.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        testcase.assertEqual([str(p) for p in validate_data.validate(root)], [])


class Q2Test(unittest.TestCase):
    def rows(self, period):
        return dei(period=period, end="2025-09-30", code=CODE) + fin_rows("InterimDuration", 500_000_000, 100_000_000,
                                                                           ordinary=1, ni=2)

    def test_q2_is_half_only_for_doc_type_160(self):
        result = ext_with(self.rows("Q2"), "160")
        self.assertFalse(result["stopped"])
        self.assertEqual((result["financial"]["period_type"], result["financial"]["net_sales"]["context"]),
                         ("half", "InterimDuration"))
        self.assertEqual(result["anomalies"], [])
        self.assertIsNone(result["employee"])

    def test_q2_with_other_doc_type_is_anomaly(self):
        for code in ("120", "130", "170", None):
            result = ext_with(self.rows("Q2"), code)
            self.assertTrue(result["stopped"], msg=code)
            self.assertEqual([a["code"] for a in result["anomalies"]], ["dei_unknown_period_type"], msg=code)
            self.assertIn("160", result["anomalies"][0]["message"])

    def test_hy_and_fy_are_as_before(self):
        for code in ("160", "170", "120", None):
            self.assertEqual(ext_with(self.rows("HY"), code)["financial"]["period_type"], "half")
        annual = dei(code=CODE) + fin_rows("CurrentYearDuration", 1, 1, ordinary=1, ni=1)
        self.assertEqual(ext_with(annual, None)["financial"]["period_type"], "annual")

    def test_unknown_value_is_still_anomaly(self):
        result = ext_with(self.rows("Q3"), "160")
        self.assertEqual(result["anomalies"][0]["code"], "dei_unknown_period_type")

    def test_q2_document_is_ingested_as_semiannual_report(self):
        rows = self.rows("Q2")
        row = {**listing("S100AAH1", "160", start="2025-04-01", end="2025-09-30", submitted="2025-11-14 15:00")}
        got = fetch(rows, row)
        self.assertIsNone(got["error"])
        data, _ = build_auto.build("advantest", CODE, None, [got], T1, DOC_TYPES)
        f = data["filings"][0]
        self.assertEqual((f["status"], f["doc_type"], f["period_type"], f["fiscal_period_end"]),
                         ("ingested", "semiannual_report", "half", "2026-03"))
        check_all(self, data)

    def test_q2_document_with_other_doc_type_code_fails(self):
        row = {**listing("S100AAH1", "120", start="2025-04-01", end="2025-09-30", submitted="2025-11-14 15:00")}
        data, _ = build_auto.build("advantest", CODE, None, [fetch(self.rows("Q2"), row)], T1, DOC_TYPES)
        self.assertEqual((data["filings"][0]["status"], data["filings"][0]["error"]),
                         ("failed", "anomaly:dei_unknown_period_type"))
        self.assertEqual(data["financials"], [])
        check_all(self, data)


def ext_with(rows, doc_type_code):
    return extract.extract([dict(zip(HEADER, x)) for x in rows], "S100AAA1", "2026-10-04T10:00:00+09:00", XMAP,
                           doc_type_code=doc_type_code)


class FakeEdinet:
    def __init__(self, raw):
        self.raw = raw

    def get_document(self, doc_id):
        return self.raw


def fetch(rows, row):
    raw = zip_response(csv_text(rows)).read()
    return ingest_company.fetch_one(FakeEdinet(raw), row, "2026-10-04T10:00:00+09:00", XMAP, "KEY", CODE)


class SameAmountTest(unittest.TestCase):
    def test_boundaries_and_units(self):
        same = build_auto.same_amount
        self.assertTrue(same("million_yen", 90378.818, 90378))
        self.assertTrue(same("million_yen", 100, 100.999))
        self.assertFalse(same("million_yen", 100, 101))           # ちょうど1は、同じとみなさない
        self.assertFalse(same("million_yen", 100, 99))
        self.assertTrue(same("million_yen", -100.5, -100))
        self.assertFalse(same("million_yen", 100, None))
        self.assertTrue(same("million_yen", None, None))
        for unit in ("yen", "persons", "years"):
            self.assertFalse(same(unit, 1000, 1000.5), msg=unit)
            self.assertFalse(same(unit, 1000, 1001), msg=unit)
            self.assertTrue(same(unit, 1000, 1000), msg=unit)


class RoundingTest(unittest.TestCase):
    def first(self, ns=90_378_818_000, oi=500_000_000, **kw):
        return state(fy2025(ns=ns, oi=oi, **kw))

    def test_difference_below_one_is_not_replaced(self):
        first = self.first()
        data, changes = build(first, [fy2026(prior=prior_fin(ns=90_378_000_000))], T2)
        self.assertEqual(data["financials"][0]["net_sales"]["value"], 90378.818)
        self.assertEqual(data["financials"][0], first["financials"][0])
        self.assertEqual(data["revisions"], [])
        self.assertEqual([c["kind"] for c in changes], ["added"])
        check_all(self, data)

    def test_difference_of_one_or_more_is_replaced(self):
        first = self.first(ns=100_000_000)
        data, _ = build(first, [fy2026(prior=prior_fin(ns=101_000_000))], T2)  # 100 → 101（ちょうど1）
        self.assertEqual(data["financials"][0]["net_sales"]["value"], 101)
        self.assertEqual([(v["path"], v["old"], v["new"]) for v in data["revisions"]],
                         [("/financials/0/net_sales/value", 100, 101)])
        again = self.first(ns=100_000_000)
        data, _ = build(again, [fy2026(prior=prior_fin(ns=100_999_000))], T2)  # 100 → 100.999（1未満）
        self.assertEqual((data["financials"][0]["net_sales"]["value"], data["revisions"]), (100, []))
        data, _ = build(again, [fy2026(prior=prior_fin(ns=102_500_000))], T2)
        self.assertEqual(data["financials"][0]["net_sales"]["value"], 102.5)

    def test_persons_are_compared_strictly(self):
        first = state(fy2025(ec=1000, es=500))
        data, _ = build(first, [fy2026(prior=prior_fin() + emp_rows("Prior1YearInstant", 1001, 500))], T2)
        self.assertEqual([(v["path"], v["old"], v["new"]) for v in data["revisions"]],
                         [("/employees/0/consolidated/employees/value", 1000, 1001)])

    def test_amended_report_uses_the_same_rule(self):
        first = self.first()
        near = fy2025("S100AAA7", ns=90_378_000_000, doc_code="130", submitted="2025-12-01 10:00", parentDocID="S100AAA1")
        data, _ = build(first, [near], T2)
        self.assertEqual(data["financials"][0]["net_sales"], first["financials"][0]["net_sales"])  # 精度のある値を残す
        self.assertEqual(data["revisions"], [])
        self.assertEqual(data["financials"][0]["doc_id"], "S100AAA7")
        self.assertEqual({f["doc_id"]: f["status"] for f in data["filings"]},
                         {"S100AAA1": "superseded", "S100AAA7": "ingested"})
        far = fy2025("S100AAA8", ns=91_500_000_000, doc_code="130", submitted="2025-12-01 10:00", parentDocID="S100AAA1")
        data, _ = build(first, [far], T2)
        self.assertEqual(data["financials"][0]["net_sales"]["value"], 91500)
        self.assertEqual([(v["path"], v["old"], v["new"]) for v in data["revisions"]],
                         [("/financials/0/net_sales/value", 90378.818, 91500)])
        check_all(self, data)

    def test_segment_values_within_rounding_keep_the_precise_value(self):
        segs = {"AMember": (600_400_000, 40_000_000), "BMember": (400_000_000, 10_000_000)}
        first = state(fy2025(segs=segs))
        same_but_rounded = {"AMember": (600_000_000, 40_000_000), "BMember": (400_000_000, 10_000_000)}
        data, _ = build(first, [fy2026(prior=prior_fin() + seg_rows(PRI, same_but_rounded))], T2)
        self.assertEqual((data["revisions"], data["financials"][0]["segments"]), ([], first["financials"][0]["segments"]))
        # 別のメンバーの値が違って、丸ごと置き換えるとき、丸めだけの違いの値は、精度のある値を残す
        changed = {"AMember": (600_000_000, 40_000_000), "BMember": (450_000_000, 10_000_000)}
        data, _ = build(first, [fy2026(prior=prior_fin() + seg_rows(PRI, changed))], T2)
        a, b = data["financials"][0]["segments"]
        self.assertEqual((a["net_sales_external"]["value"], a["net_sales_external"]["doc_id"]), (600.4, "S100AAA1"))
        self.assertEqual((b["net_sales_external"]["value"], b["net_sales_external"]["doc_id"]), (450, "S100AAA2"))
        self.assertEqual([(v["path"], v["old"], v["new"]) for v in data["revisions"]],
                         [("/financials/0/segments/1/net_sales_external/value", 400, 450)])
        check_all(self, data)


class AccountingStandardSwitchTest(unittest.TestCase):
    PRIOR_SEGS = {"GameMember": (500_000_000, 50_000_000), "MusicMember": (300_000_000, 30_000_000)}

    def prior(self, ns=1_000_000_000, oi=450_000_000, ni=200_000_000, segs=True, adj=-20_000_000):
        rows = ifrs_fin(PRI, ns, oi, ni)
        if segs:
            rows += ifrs_segs(PRI, self.PRIOR_SEGS, adj)
        return rows

    def test_sony_shape_usgaap_to_ifrs(self):
        first = state(usgaap_doc())
        row = first["financials"][0]
        self.assertEqual((row["accounting_standard"], row["operating_income"]["value"], row["segments"]), ("usgaap", None, []))
        data, changes = build(first, [ifrs_doc26(prior=self.prior())], T2)
        check_all(self, data)
        row = data["financials"][0]
        self.assertEqual((row["accounting_standard"], row["net_sales_label"], row["doc_id"], row["consolidated"]),
                         ("ifrs", "売上収益", "S100AAA2", True))
        self.assertEqual((row["net_sales"]["value"], row["net_sales"]["element"], row["net_sales"]["context"],
                          row["net_sales"]["doc_id"]), (1000, "jpigp_cor:RevenueIFRS", PRI, "S100AAA2"))
        self.assertEqual((row["operating_income"]["value"], row["net_income"]["value"]), (450, 200))
        self.assertEqual([s["member"] for s in row["segments"]], ["GameMember", "MusicMember"])
        self.assertEqual(row["segment_adjustment"]["value"], -20)
        self.assertNotIn("ordinary_income", row)
        self.assertEqual(list(row)[:9], ["fiscal_period_end", "period_type", "period_start", "period_end",
                                         "accounting_standard", "consolidated", "doc_id", "net_sales_label", "net_sales"])
        revs = {v["path"]: (v["old"], v["new"], v["supersedes"]) for v in data["revisions"]}
        self.assertEqual(revs["/financials/0/operating_income/value"], (None, 450, "S100AAA1"))
        self.assertNotIn("/financials/0/net_sales/value", revs)  # 値が同じ（1000）なので revisions なし
        kinds = [c["kind"] for c in changes]
        self.assertIn("accounting_standard_changed", kinds)
        message = next(c["message"] for c in changes if c["kind"] == "accounting_standard_changed")
        self.assertIn("会計基準が変わった（usgaap → ifrs）", message)
        self.assertIn("segments_changed", kinds)
        self.assertEqual(data["filings"][0]["status"], "ingested")

    def test_resonac_shape_jgaap_to_ifrs_removes_ordinary_income(self):
        first = state(fy2025(ns=1_000_000_000, oi=500_000_000))
        self.assertIn("ordinary_income", first["financials"][0])
        data, changes = build(first, [ifrs_doc26(prior=self.prior(ns=1_000_000_000, oi=480_000_000, segs=False))], T2)
        check_all(self, data)  # 取り除いた ordinary_income の履歴（new が null）も、validate_data に合格する
        row = data["financials"][0]
        self.assertNotIn("ordinary_income", row)
        self.assertEqual((row["accounting_standard"], row["net_sales_label"]), ("ifrs", "売上収益"))
        revs = {v["path"]: (v["old"], v["new"]) for v in data["revisions"]}
        self.assertEqual(revs["/financials/0/ordinary_income/value"], (1, None))
        self.assertEqual(revs["/financials/0/operating_income/value"], (500, 480))
        self.assertEqual(revs["/financials/0/net_income/value"], (2, 200))
        self.assertNotIn("/financials/0/net_sales/value", revs)
        self.assertEqual(row["segments"], [])
        self.assertIn("会計基準が変わった（jgaap → ifrs）", next(c["message"] for c in changes
                                                       if c["kind"] == "accounting_standard_changed"))

    def test_same_values_still_update_standard_and_label(self):
        first = state(usgaap_doc())
        rows = ifrs_fin(PRI, 1_000_000_000, 450_000_000, 20_000_000)
        first["financials"][0]["operating_income"] = {**first["financials"][0]["operating_income"], "value": 450}
        data, _ = build(first, [ifrs_doc26(prior=rows)], T2)
        row = data["financials"][0]
        self.assertEqual((row["accounting_standard"], row["net_sales_label"], row["doc_id"]), ("ifrs", "売上収益", "S100AAA2"))
        self.assertEqual(data["revisions"], [])
        check_all(self, data)

    def test_same_standard_keeps_the_previous_rules(self):
        first = state(fy2025())
        data, changes = build(first, [fy2026(prior=prior_fin(oi=400_000_000))], T2)
        row = data["financials"][0]
        self.assertEqual((row["accounting_standard"], row["net_sales_label"], row["doc_id"]), ("jgaap", "売上高", "S100AAA1"))
        self.assertEqual([v["path"] for v in data["revisions"]], ["/financials/0/operating_income/value"])
        self.assertNotIn("accounting_standard_changed", [c["kind"] for c in changes])

    def test_older_document_ingested_later_does_not_override(self):
        first = state(fy2025())
        second, _ = build(first, [ifrs_doc26(prior=self.prior())], T2)
        self.assertEqual(second["financials"][0]["accounting_standard"], "ifrs")
        amended = fy2025("S100AAA7", ns=1_100_000_000, doc_code="130", submitted="2025-12-01 10:00", parentDocID="S100AAA1")
        data, _ = build(second, [amended], LATER)
        row = data["financials"][0]
        self.assertEqual((row["accounting_standard"], row["doc_id"], row["net_sales"]["doc_id"]), ("ifrs", "S100AAA2", "S100AAA2"))
        self.assertEqual(data["revisions"], second["revisions"])
        self.assertEqual({f["doc_id"]: f["status"] for f in data["filings"]}["S100AAA7"], "superseded")
        check_all(self, data)

    def test_newer_leaf_values_block_the_switch(self):
        first = state(fy2025())
        newest = fy2026("S100AAA9", prior=prior_fin(oi=300_000_000), submitted="2026-09-01 10:00")
        second, _ = build(first, [newest], T2)
        data, _ = build(second, [ifrs_doc26("S100AAA2", prior=self.prior(), submitted="2026-06-20 10:00")], LATER)
        self.assertEqual(data["financials"][0]["accounting_standard"], "jgaap")
        self.assertEqual(data["financials"][0]["operating_income"]["value"], 300)

    def test_second_run_gives_the_same_result(self):
        first = state(usgaap_doc())
        second, _ = build(first, [ifrs_doc26(prior=self.prior())], T2)
        third, changes = build(second, [ifrs_doc26(prior=self.prior()), usgaap_doc()], LATER)
        self.assertEqual(third, second)
        self.assertEqual(changes, [])
        a, _ = build(None, [ifrs_doc26(prior=self.prior()), usgaap_doc()])
        b, _ = build(None, [usgaap_doc(), ifrs_doc26(prior=self.prior())])
        self.assertEqual(a, b)

    def test_row_rounding_is_kept_on_switch(self):
        first = state(usgaap_doc(ns=90_378_818_000))
        data, _ = build(first, [ifrs_doc26(prior=self.prior(ns=90_378_000_000))], T2)
        self.assertEqual(data["financials"][0]["net_sales"]["value"], 90378.818)


class SegmentsMissingTest(unittest.TestCase):
    def test_existing_segments_are_kept_when_comparative_has_none(self):
        segs = {"AMember": (600_000_000, 40_000_000)}
        first = state(fy2025(segs=segs, adj=-10_000_000))
        data, changes = build(first, [fy2026(prior=prior_fin(oi=400_000_000))], T2)
        row = data["financials"][0]
        self.assertEqual(row["segments"], first["financials"][0]["segments"])
        self.assertEqual(row["segment_adjustment"], first["financials"][0]["segment_adjustment"])
        self.assertEqual(row["operating_income"]["value"], 400)  # 財務の値は、これまでどおり置き換える
        missing = [c for c in changes if c["kind"] == "segments_missing_in_comparative"]
        self.assertEqual(len(missing), 1)
        self.assertIn("前期の列にセグメントがない（既存を残した）", missing[0]["message"])
        check_all(self, data)

    def test_no_notice_when_existing_has_no_segments(self):
        first = state(fy2025())
        _, changes = build(first, [fy2026(prior=prior_fin())], T2)
        self.assertNotIn("segments_missing_in_comparative", [c["kind"] for c in changes])

    def test_switch_replaces_whole_row_even_without_comparative_segments(self):
        first = state(fy2025(segs={"AMember": (600_000_000, 40_000_000)}, adj=-10_000_000))
        data, changes = build(first, [ifrs_doc26(prior=ifrs_fin(PRI, 1_000_000_000, 450_000_000, 200_000_000))], T2)
        row = data["financials"][0]
        self.assertEqual(row["segments"], [])
        self.assertNotIn("segment_adjustment", row)
        kinds = [c["kind"] for c in changes]
        self.assertNotIn("segments_missing_in_comparative", kinds)
        self.assertIn("segments_changed", kinds)
        self.assertEqual(row["accounting_standard"], "ifrs")
        check_all(self, data)


class CompanySpecificElementTest(unittest.TestCase):
    EXT_L = "SalesAndFinancialServicesRevenueToCustomersIFRS"
    TOT_L = "SalesAndFinancialServicesRevenueIFRS"

    def sony_rows(self, dur=CUR, pfx=SONY_PFX, code=SONY, members=None, with_code=True, common_first=False):
        members = members or {"GameMember": (4_000_000_000, 5_000_000_000, 400_000_000),
                              "MusicMember": (2_000_000_000, 2_500_000_000, 250_000_000)}
        rows = dei("IFRS", code=code) if with_code else [x for x in dei("IFRS") if "EDINETCode" not in x[0]]
        rows += ifrs_fin(dur, 9_000_000_000, 800_000_000, 500_000_000)
        for name, (external, total, profit) in members.items():
            context = f"{dur}_{pfx}{name}"
            rows += [money(f"{pfx}:{self.EXT_L}", context, external), money(f"{pfx}:{self.TOT_L}", context, total),
                     money("jpigp_cor:OperatingProfitLossIFRS", context, profit)]
        rows += [money("jpigp_cor:OperatingProfitLossIFRS", f"{dur}_{pfx}ReconcilingItemsMember", -100_000_000),
                 money("jpigp_cor:OperatingProfitLossIFRS", f"{dur}_{pfx}ReportableSegmentsMember", 650_000_000)]
        return rows + emp_all("CurrentYearInstant")

    def segments_of(self, rows, dur=CUR):
        return ext(rows, "S100TS7P")

    def test_sony_shape_segments_are_taken_from_company_specific_elements(self):
        res = self.segments_of(self.sony_rows())
        f = res["financial"]
        self.assertEqual(res["anomalies"], [])
        self.assertEqual([s["member"] for s in f["segments"]], ["GameMember", "MusicMember"])
        game = f["segments"][0]
        self.assertEqual((game["net_sales_external"]["value"], game["net_sales_total"]["value"], game["profit"]["value"]),
                         (4000, 5000, 400))
        self.assertEqual(game["net_sales_external"]["element"], f"{SONY_PFX}:{self.EXT_L}")
        self.assertEqual(game["profit"]["element"], "jpigp_cor:OperatingProfitLossIFRS")
        self.assertEqual(f["segment_adjustment"]["value"], -100)
        self.assertEqual(res["financial"]["net_sales"]["value"], 9000)

    def test_other_company_prefix_is_not_taken(self):
        other = self.sony_rows(pfx="jpcrp030000-asr_E99999-000")
        # 会社固有の前置きの要素は E99999 のもの。この書類の企業は E01777
        res = self.segments_of(other)
        self.assertEqual(res["financial"]["segments"], [])

    def test_common_namespaces_are_not_taken(self):
        rows = [x for x in self.sony_rows() if self.EXT_L not in x[0]]
        rows += [money(f"jpigp_cor:{self.EXT_L}", f"{CUR}_{SONY_PFX}GameMember", 1_000_000_000),
                 money(f"jppfs_cor:{self.EXT_L}", f"{CUR}_{SONY_PFX}GameMember", 1_000_000_000),
                 money(f"jpcrp_cor:{self.EXT_L}", f"{CUR}_{SONY_PFX}GameMember", 1_000_000_000)]
        self.assertEqual(self.segments_of(rows)["financial"]["segments"], [])

    def test_prefix_form_and_company_code_are_checked_exactly(self):
        for bad_prefix in ("jpcrp030000-xyz_E01777-000", "jpcrp_E01777-000", "jpcrp030000-asr_E1777-000",
                           "jpcrp030000-asr_E01777-00", "jpcrp030000-asr_e01777-000", "xjpcrp030000-asr_E01777-000"):
            rows = [x for x in self.sony_rows(pfx="jpcrp030000-asr_E01777-000")]
            rows = [[x[0].replace("jpcrp030000-asr_E01777-000:", bad_prefix + ":") if ":" in x[0] else x[0], *x[1:]]
                    for x in rows]
            res = self.segments_of(rows)
            self.assertEqual(res["financial"]["segments"], [], msg=bad_prefix)

    def test_no_edinet_code_in_dei_means_no_wildcard_match(self):
        res = self.segments_of(self.sony_rows(with_code=False))
        self.assertEqual(res["financial"]["segments"], [])

    def test_common_name_candidates_come_first_and_results_do_not_change(self):
        common = ifrs_segs(CUR, {"GameMember": (4_100_000_000, 410_000_000)})
        with_wildcard = self.sony_rows() + common
        res = self.segments_of(with_wildcard)
        self.assertEqual([s["member"] for s in res["financial"]["segments"]], ["GameMember"])
        self.assertEqual(res["financial"]["segments"][0]["net_sales_external"]["value"], 4100)
        self.assertEqual(res["financial"]["segments"][0]["net_sales_external"]["element"],
                         "jpigp_cor:SalesToExternalCustomersIFRS")
        # 共通の名前が使える書類（会社固有の要素がない）は、これまでと同じ結果
        plain = dei("IFRS", code=SONY) + ifrs_fin(CUR, 9_000_000_000, 800_000_000, 500_000_000) + common + \
            emp_all("CurrentYearInstant")
        before = [s["net_sales_external"]["value"] for s in self.segments_of(plain)["financial"]["segments"]]
        self.assertEqual(before, [4100])

    def test_prior_column_uses_the_same_rule(self):
        rows = self.sony_rows() + self.sony_rows(dur=PRI, members={"GameMember": (3_000_000_000, 3_500_000_000, 300_000_000)})[
            len(dei("IFRS")):-len(emp_all("CurrentYearInstant"))]
        res = self.segments_of(rows)
        prior = res["comparative"]["financial"]
        self.assertEqual([s["member"] for s in prior["segments"]], ["GameMember"])
        self.assertEqual((prior["segments"][0]["net_sales_external"]["value"], prior["segments"][0]["net_sales_external"]["context"]),
                         (3000, f"{PRI}_{SONY_PFX}GameMember"))
        self.assertEqual(prior["segment_adjustment"]["value"], -100)

    def test_half_report_ssr_prefix(self):
        pfx = "jpcrp040300-ssr_E01777-000"
        dur = "InterimDuration"
        rows = dei("IFRS", period="HY", end="2025-09-30", code=SONY) + ifrs_fin(dur, 4_000_000_000, 300_000_000, 200_000_000)
        rows += [money(f"{pfx}:{self.EXT_L}", f"{dur}_{pfx}GameMember", 1_500_000_000),
                 money("jpigp_cor:OperatingProfitLossIFRS", f"{dur}_{pfx}GameMember", 100_000_000)]
        res = ext(rows, "S100TS7Q")
        self.assertEqual(res["anomalies"], [])
        self.assertEqual([s["member"] for s in res["financial"]["segments"]], ["GameMember"])
        self.assertEqual(res["financial"]["segments"][0]["net_sales_external"]["value"], 1500)

    def test_matches_function(self):
        work = extract._Extraction("S100AAA1", "t", "E01777")
        self.assertTrue(work.matches("*:A", "jpcrp030000-asr_E01777-000:A"))
        self.assertTrue(work.matches("*:A", "jpcrp040300-ssr_E01777-000:A"))
        self.assertFalse(work.matches("*:A", "jpcrp030000-asr_E01778-000:A"))
        self.assertFalse(work.matches("*:A", "jpcrp030000-asr_E01777-000:AB"))
        self.assertFalse(work.matches("*:A", "jpcrp030000-asr_E01777-000"))
        self.assertFalse(work.matches("*:A", "jpigp_cor:A"))
        self.assertTrue(work.matches("jpigp_cor:A", "jpigp_cor:A"))
        self.assertFalse(work.matches("jpigp_cor:A", "jpcrp030000-asr_E01777-000:A"))
        self.assertFalse(extract._Extraction("S100AAA1", "t").matches("*:A", "jpcrp030000-asr_E01777-000:A"))

    def test_built_data_with_company_specific_segments_passes_checks(self):
        rows = self.sony_rows(code=CODE, pfx="jpcrp030000-asr_E01950-000")
        data, _ = build(None, [doc("S100AAA1", rows)])
        self.assertEqual(len(data["financials"][0]["segments"]), 2)
        check_all(self, data)


class SummaryAndScreenTest(unittest.TestCase):
    def test_new_kinds_appear_in_summary_and_screen(self):
        ia = __import__("ingest_all")
        first = state(usgaap_doc(), )
        data, changes = build(first, [ifrs_doc26(prior=ifrs_fin(PRI, 1_000_000_000, 450_000_000, 200_000_000))], T2)
        seg_first = state(fy2025(segs={"AMember": (600_000_000, 40_000_000)}))
        seg_data, seg_changes = build(seg_first, [fy2026(prior=prior_fin(oi=400_000_000))], T2)
        results = [{"slug": "advantest", "edinet_code": CODE, "skipped": None, "changes": changes, "data": data},
                   {"slug": "other-co", "edinet_code": CODE, "skipped": None, "changes": seg_changes, "data": seg_data}]
        text = ia.render_summary(results, {"total": 2, "list": 1, "fetch": 1}, "KEY")
        self.assertIn("会計基準が変わった（前期の列による置き換え）", text)
        self.assertIn("会計基準が変わった（usgaap → ifrs）", text)
        self.assertIn("前期の列にセグメントがない（既存を残した）", text)
        screen = ingest_company.render_changes("advantest", changes + seg_changes, 2)
        self.assertIn("[会計基準の変更]", screen)
        self.assertIn("[前期の列にセグメントなし]", screen)


if __name__ == "__main__":
    unittest.main()

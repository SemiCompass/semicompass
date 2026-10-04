import copy
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

import edinet_fakes as fk
from edinet_fakes import FakeResponse
from test_extract import EMP_E, HEADER, PFX, dei, r

build_auto = __import__("build_auto")
extract = __import__("extract")
ingest_company = __import__("ingest_company")

ROOT = Path(__file__).resolve().parents[2]
XMAP = yaml.safe_load((ROOT / "config" / "xbrl-map.yaml").read_text(encoding="utf-8"))
DOC_TYPES = {str(k): v for k, v in XMAP["doc_types"].items()}
JST = ZoneInfo("Asia/Tokyo")
T1 = datetime(2026, 10, 4, 10, 0, tzinfo=JST)
T2 = datetime(2026, 10, 5, 11, 30, tzinfo=JST)
CODE, SLUG = "E01950", "advantest"
EXT = "jpcrp_cor:RevenuesFromExternalCustomers"
OPI = "jppfs_cor:OperatingIncome"
AGE = "jpcrp_cor:AverageAgeYearsInformationAboutReportingCompanyInformationAboutEmployees"


def money(element, ctx, yen, label=""):
    return r(element, ctx, str(yen), label)


def fin_rows(dur, ns, oi, ordinary=None, ni=None):
    out = [money("jppfs_cor:NetSales", dur, ns, "売上高"), money(OPI, dur, oi, "営業利益")]
    if ordinary is not None:
        out.append(money("jppfs_cor:OrdinaryIncome", dur, ordinary))
    if ni is not None:
        out.append(money("jppfs_cor:ProfitLossAttributableToOwnersOfParent", dur, ni))
    return out


def seg_rows(dur, members, adjustment=None):
    """members: {名前: (外部売上, 利益)}（円）。adjustment: 調整額の利益（円）。"""
    out = []
    for name, (ext, profit) in members.items():
        out.append(money(EXT, f"{dur}_{PFX}{name}", ext))
        if profit is not None:
            out.append(money(OPI, f"{dur}_{PFX}{name}", profit))
    if adjustment is not None:
        out.append(money(OPI, f"{dur}_{PFX}ReconcilingItemsMember", adjustment))
    return out


def emp_rows(inst, consolidated, single, age=None):
    out = [r(EMP_E, inst, str(consolidated), "", ""), r(EMP_E, inst + "_NonConsolidatedMember", str(single), "", "")]
    if age is not None:
        out.append(r(AGE, inst + "_NonConsolidatedMember", str(age), "", "年"))
    return out


def full_current(dur, inst, ns, oi, segs=None, adj=None, ec=1000, es=500, half=False):
    rows = fin_rows(dur, ns, oi, ordinary=1_000_000, ni=2_000_000) + seg_rows(dur, segs or {}, adj)
    if not half:
        rows += emp_rows(inst, ec, es, 40) + [
            r("jpcrp_cor:AverageLengthOfServiceYearsInformationAboutReportingCompanyInformationAboutEmployees",
              inst + "_NonConsolidatedMember", "10", "", "年"),
            r("jpcrp_cor:AverageAnnualSalaryInformationAboutReportingCompanyInformationAboutEmployees",
              inst + "_NonConsolidatedMember", "7000000")]
    return rows


def ext(rows, doc_id):
    return extract.extract([dict(zip(HEADER, x)) for x in rows], doc_id, "2026-10-04T10:00:00+09:00", XMAP)


def listing(doc_id, doc_code="120", start="2024-04-01", end="2025-03-31", submitted="2025-06-20 15:00", **kw):
    row = fk.row(doc_id, CODE, doc_code, periodStart=start, periodEnd=end, submitDateTime=submitted, **kw)
    row["slug"] = SLUG
    return row


def doc(doc_id, rows, doc_code="120", **kw):
    return {"filing": listing(doc_id, doc_code, **kw), "result": ext(rows, doc_id), "error": None}


def fy2025(doc_id="S100AAA1", ns=1_000_000_000, oi=500_000_000, segs=None, adj=None, ec=1000, es=500, **kw):
    kw.setdefault("submitted", "2025-06-20 15:00")
    rows = dei(start="2024-04-01", end="2025-03-31", fy_end="2025-03-31", code=CODE) + \
        full_current("CurrentYearDuration", "CurrentYearInstant", ns, oi, segs, adj, ec, es)
    return doc(doc_id, rows, **kw)


def fy2026(doc_id="S100AAA2", prior=None, segs=None, adj=None, ec=None, es=None, doc_code="120", **kw):
    """2026-03期。prior は、前期の列の rows（なければ前期の列なし）。"""
    kw.setdefault("submitted", "2026-06-20 15:00")
    rows = dei(start="2025-04-01", end="2026-03-31", fy_end="2026-03-31", code=CODE) + \
        full_current("CurrentYearDuration", "CurrentYearInstant", 1_200_000_000, 600_000_000, segs, adj) + (prior or [])
    return doc(doc_id, rows, doc_code=doc_code, start="2025-04-01", end="2026-03-31", **kw)


def build(existing, docs, now=T1):
    return build_auto.build(SLUG, CODE, existing, docs, now, DOC_TYPES)


def state(*docs):
    data, _ = build(None, list(docs))
    return data


def prior_fin(ns=1_000_000_000, oi=500_000_000):
    return fin_rows("Prior1YearDuration", ns, oi)


class ExtractComparativeTest(unittest.TestCase):
    def comp(self, rows):
        res = ext(dei() + rows, "S100AAA2")
        return res, res["comparative"]

    def test_prior_columns_are_read_with_prior_contexts(self):
        rows = fin_rows("CurrentYearDuration", 9_000_000_000, 1) + fin_rows("Prior1YearDuration", 3_000_000_000, 400_000_000,
                                                                          ordinary=7_000_000, ni=8_000_000)
        rows += seg_rows("Prior1YearDuration", {"AMember": (2_000_000_000, 100_000_000)}, adjustment=-5_000_000)
        rows += emp_rows("Prior1YearInstant", 111, 22, 41) + emp_rows("CurrentYearInstant", 999, 888)
        res, comp = self.comp(rows)
        f = comp["financial"]
        self.assertEqual((f["fiscal_period_end"], f["period_type"]), ("2025-03", "annual"))
        self.assertEqual((f["net_sales"]["value"], f["net_sales"]["context"], f["operating_income"]["value"],
                          f["ordinary_income"]["value"], f["net_income"]["value"]), (3000, "Prior1YearDuration", 400, 7, 8))
        self.assertEqual((f["segments"][0]["member"], f["segments"][0]["net_sales_external"]["value"],
                          f["segments"][0]["profit"]["value"], f["segment_adjustment"]["value"]), ("AMember", 2000, 100, -5))
        self.assertEqual((f["net_sales"]["doc_id"], f["net_sales"]["unit"]), ("S100AAA2", "million_yen"))
        e = comp["employee"]
        self.assertEqual((e["consolidated"]["employees"]["value"], e["non_consolidated"]["employees"]["value"]), (111, 22))
        self.assertEqual(list(e["non_consolidated"]), ["employees"])  # 従業員数だけ（平均年齢などは使わない）
        self.assertEqual(res["financial"]["net_sales"]["value"], 9000)  # 当期の取り出しは変わらない

    def test_missing_items_are_omitted_without_anomaly(self):
        res, comp = self.comp(fin_rows("CurrentYearDuration", 9_000_000_000, 1) + fin_rows("Prior1YearDuration", 3_000_000_000, 4)[:1])
        self.assertEqual(set(comp["financial"]), {"fiscal_period_end", "period_type", "net_sales"})
        self.assertIsNone(comp["employee"])
        self.assertEqual([a for a in res["anomalies"] if "前期" in a["message"]], [])

    def test_no_prior_columns(self):
        _, comp = self.comp(fin_rows("CurrentYearDuration", 9_000_000_000, 1))
        self.assertEqual(comp["financial"], {"fiscal_period_end": "2025-03", "period_type": "annual"})

    def test_half_uses_prior_interim_contexts(self):
        rows = dei(period="HY", end="2025-09-30") + fin_rows("InterimDuration", 9_000_000_000, 1) + \
            fin_rows("Prior1InterimDuration", 4_000_000_000, 2_000_000) + fin_rows("Prior1YearDuration", 1, 1)
        comp = ext(rows, "S100AAA2")["comparative"]
        self.assertEqual((comp["financial"]["period_type"], comp["financial"]["net_sales"]["value"],
                          comp["financial"]["net_sales"]["context"]), ("half", 4000, "Prior1InterimDuration"))
        self.assertIsNone(comp["employee"])

    def test_unconvertible_item_is_left_out_with_note(self):
        rows = fin_rows("CurrentYearDuration", 9_000_000_000, 1)
        rows.append(["jppfs_cor:NetSales", "売上高", "Prior1YearDuration", "前期", "連結", "期間", "USD", "ドル", "5"])
        res, comp = self.comp(rows)
        self.assertNotIn("net_sales", comp["financial"])
        self.assertTrue(comp["notes"])

    def test_usgaap_and_ifrs(self):
        rows = dei("IFRS") + [r("jpigp_cor:RevenueIFRS", "Prior1YearDuration", "3000000000", "売上収益（IFRS）"),
                              r("jpigp_cor:OperatingProfitLossIFRS", "Prior1YearDuration", "100000000")]
        comp = ext(rows, "S100AAA2")["comparative"]["financial"]
        self.assertEqual((comp["net_sales"]["value"], comp["operating_income"]["value"]), (3000, 100))
        self.assertNotIn("ordinary_income", comp)
        rows = dei("US GAAP") + [r("jpcrp_cor:RevenuesUSGAAPSummaryOfBusinessResults", "Prior1YearDuration", "3000000000")]
        self.assertEqual(ext(rows, "S100AAA2")["comparative"]["financial"]["net_sales"]["value"], 3000)

    def test_stopped_result_has_no_comparative(self):
        self.assertNotIn("comparative", ext(dei(standard="Other") + prior_fin(), "S100AAA2"))


class ApplyComparativeTest(unittest.TestCase):
    def valid(self, data):
        self.assertEqual(ingest_company.validate(data), [])

    def test_same_prior_changes_nothing(self):
        first = state(fy2025())
        data, changes = build(first, [fy2026(prior=prior_fin())], T2)
        self.valid(data)
        self.assertEqual(data["revisions"], [])
        self.assertEqual(data["financials"][0], first["financials"][0])
        self.assertEqual([c["kind"] for c in changes], ["added"])

    def test_operating_income_only_differs_sony_shape(self):
        first = state(fy2025(oi=1_407_163_000_000, ns=11_000_000_000_000))
        data, changes = build(first, [fy2026(prior=prior_fin(11_000_000_000_000, 1_276_635_000_000))], T2)
        self.valid(data)
        row = data["financials"][0]
        self.assertEqual(row["operating_income"], {"value": 1276635, "unit": "million_yen", "original_unit": "yen",
                                                    "element": OPI, "context": "Prior1YearDuration",
                                                    "doc_id": "S100AAA2", "ingested_at": "2026-10-05T11:30:00+09:00"})
        self.assertEqual((row["net_sales"]["doc_id"], row["net_sales"]["context"]), ("S100AAA1", "CurrentYearDuration"))
        self.assertEqual((row["net_sales_label"], row["accounting_standard"], row["consolidated"], row["doc_id"]),
                         ("売上高", "jgaap", True, "S100AAA1"))
        self.assertEqual(data["revisions"], [{"at": "2026-10-05T11:30:00+09:00", "doc_id": "S100AAA2",
                                              "supersedes": "S100AAA1", "path": "/financials/0/operating_income/value",
                                              "old": 1407163, "new": 1276635}])
        self.assertEqual(data["financials"][1]["fiscal_period_end"], "2026-03")
        self.assertEqual(sorted(c["kind"] for c in changes), ["added", "replaced"])
        self.assertEqual(data["filings"][0]["status"], "ingested")  # 前期の書類は superseded にしない

    def test_segment_members_and_values_change_advantest_shape(self):
        first = state(fy2025(segs={"AMember": (600_000_000, 40_000_000), "BMember": (400_000_000, 10_000_000)},
                             adj=-10_000_000))
        prior = prior_fin() + seg_rows("Prior1YearDuration", {"AMember": (550_000_000, 40_000_000),
                                                              "CMember": (450_000_000, 20_000_000)}, -20_000_000)
        data, changes = build(first, [fy2026(prior=prior)], T2)
        self.valid(data)
        row = data["financials"][0]
        self.assertEqual([s["member"] for s in row["segments"]], ["AMember", "CMember"])
        self.assertEqual({s["net_sales_external"]["doc_id"] for s in row["segments"]}, {"S100AAA2"})
        self.assertEqual(row["segment_adjustment"]["value"], -20)
        self.assertEqual(row["segment_adjustment"]["doc_id"], "S100AAA2")
        self.assertEqual([(v["path"], v["old"], v["new"], v["supersedes"]) for v in data["revisions"]],
                         [("/financials/0/segments/0/net_sales_external/value", 600, 550, "S100AAA1"),
                          ("/financials/0/segment_adjustment/value", -10, -20, "S100AAA1")])
        moved = [c for c in changes if c["kind"] == "segments_changed"]
        self.assertEqual(len(moved), 1)
        self.assertIn("セグメントの区分が変わった（追加：CMember、削除：BMember）", moved[0]["message"])
        self.assertEqual(list(row)[-3:], ["segments", "segment_adjustment", "regions"])

    def test_only_segment_values_change(self):
        first = state(fy2025(segs={"AMember": (600_000_000, 40_000_000)}))
        prior = prior_fin() + seg_rows("Prior1YearDuration", {"AMember": (600_000_000, 45_000_000)})
        data, changes = build(first, [fy2026(prior=prior)], T2)
        self.assertEqual([(v["path"], v["old"], v["new"]) for v in data["revisions"]],
                         [("/financials/0/segments/0/profit/value", 40, 45)])
        self.assertNotIn("segments_changed", [c["kind"] for c in changes])
        self.valid(data)

    def test_adjustment_only_changes(self):
        first = state(fy2025(segs={"AMember": (600_000_000, 40_000_000)}, adj=-10_000_000))
        prior = prior_fin() + seg_rows("Prior1YearDuration", {"AMember": (600_000_000, 40_000_000)}, -30_000_000)
        data, _ = build(first, [fy2026(prior=prior)], T2)
        self.assertEqual([(v["path"], v["old"], v["new"]) for v in data["revisions"]],
                         [("/financials/0/segment_adjustment/value", -10, -30)])
        self.valid(data)

    def test_same_segments_change_nothing(self):
        segs = {"AMember": (600_000_000, 40_000_000)}
        first = state(fy2025(segs=segs, adj=-10_000_000))
        prior = prior_fin() + seg_rows("Prior1YearDuration", segs, -10_000_000)
        data, _ = build(first, [fy2026(prior=prior)], T2)
        self.assertEqual(data["revisions"], [])
        self.assertEqual(data["financials"][0], first["financials"][0])

    def test_no_prior_row_does_nothing(self):
        data, _ = build(None, [fy2026(prior=prior_fin(1, 2))])
        self.assertEqual(len(data["financials"]), 1)
        self.assertEqual((data["financials"][0]["fiscal_period_end"], data["revisions"]), ("2026-03", []))
        self.valid(data)

    def test_second_run_changes_nothing(self):
        first = state(fy2025())
        second, _ = build(first, [fy2026(prior=prior_fin(oi=400_000_000))], T2)
        again, changes = build(second, [fy2026(prior=prior_fin(oi=400_000_000)), fy2025()],
                               datetime(2026, 10, 9, 9, 0, tzinfo=JST))
        self.assertEqual(again, second)
        self.assertEqual(changes, [])
        self.assertEqual(again["updated_at"], "2026-10-05T11:30:00+09:00")

    def test_same_batch_in_either_order_gives_the_same_result(self):
        a, _ = build(None, [fy2026(prior=prior_fin(oi=400_000_000)), fy2025()])
        b, _ = build(None, [fy2025(), fy2026(prior=prior_fin(oi=400_000_000))])
        self.assertEqual(a, b)
        self.assertEqual(a["financials"][0]["operating_income"]["value"], 400)

    def test_older_document_ingested_later_does_not_override_newer_value(self):
        first = state(fy2025())
        second, _ = build(first, [fy2026(prior=prior_fin(oi=400_000_000))], T2)
        # 2025-06 と 2026-06 の間に提出された訂正が、あとから届く（営業利益は元のまま、売上高だけ違う）
        amended = fy2025("S100AAA7", ns=1_100_000_000, oi=500_000_000, doc_code="130", submitted="2025-12-01 10:00",
                         parentDocID="S100AAA1")
        data, _ = build(second, [amended], datetime(2026, 10, 9, 9, 0, tzinfo=JST))
        self.valid(data)
        row = data["financials"][0]
        self.assertEqual((row["operating_income"]["value"], row["operating_income"]["doc_id"]), (400, "S100AAA2"))
        self.assertEqual((row["net_sales"]["value"], row["net_sales"]["doc_id"]), (1100, "S100AAA7"))
        paths = [(v["path"], v["old"], v["new"], v["doc_id"]) for v in data["revisions"]]
        self.assertEqual(paths, [("/financials/0/operating_income/value", 500, 400, "S100AAA2"),
                                 ("/financials/0/net_sales/value", 1000, 1100, "S100AAA7")])

    def test_older_segments_are_not_restored_by_a_later_older_document(self):
        segs = {"AMember": (600_000_000, 40_000_000)}
        first = state(fy2025(segs=segs))
        prior = prior_fin() + seg_rows("Prior1YearDuration", {"ZMember": (700_000_000, 50_000_000)})
        second, _ = build(first, [fy2026(prior=prior)], T2)
        amended = fy2025("S100AAA7", segs={"AMember": (650_000_000, 41_000_000)}, doc_code="130",
                         submitted="2025-12-01 10:00", parentDocID="S100AAA1")
        data, _ = build(second, [amended], datetime(2026, 10, 9, 9, 0, tzinfo=JST))
        self.assertEqual([s["member"] for s in data["financials"][0]["segments"]], ["ZMember"])
        self.valid(data)

    def test_newer_amended_report_overrides_the_comparative(self):
        first = state(fy2025())
        second, _ = build(first, [fy2026(prior=prior_fin(oi=400_000_000))], T2)
        later = fy2026("S100AAA9", prior=prior_fin(oi=300_000_000), doc_code="130", submitted="2026-08-01 10:00",
                       parentDocID="S100AAA2")
        data, _ = build(second, [later], datetime(2026, 10, 9, 9, 0, tzinfo=JST))
        self.valid(data)
        self.assertEqual(data["financials"][0]["operating_income"]["value"], 300)
        last = data["revisions"][-1]
        self.assertEqual((last["path"], last["old"], last["new"], last["supersedes"], last["doc_id"]),
                         ("/financials/0/operating_income/value", 400, 300, "S100AAA2", "S100AAA9"))

    def test_half_prior_column(self):
        half25 = doc("S100AAH1", dei(period="HY", start="2024-04-01", end="2024-09-30", fy_end="2025-03-31", code=CODE) +
                     fin_rows("InterimDuration", 400_000_000, 100_000_000, ordinary=1, ni=2),
                     doc_code="160", start="2024-04-01", end="2024-09-30", submitted="2024-11-14 15:00")
        first = state(half25)
        half26 = doc("S100AAH2", dei(period="HY", start="2025-04-01", end="2025-09-30", fy_end="2026-03-31", code=CODE) +
                     fin_rows("InterimDuration", 500_000_000, 120_000_000, ordinary=1, ni=2) +
                     fin_rows("Prior1InterimDuration", 400_000_000, 90_000_000), doc_code="160", start="2025-04-01",
                     end="2025-09-30", submitted="2025-11-14 15:00")
        data, _ = build(first, [half26], T2)
        self.valid(data)
        self.assertEqual([(f["fiscal_period_end"], f["period_type"]) for f in data["financials"]],
                         [("2025-03", "half"), ("2026-03", "half")])
        self.assertEqual(data["financials"][0]["operating_income"]["value"], 90)
        self.assertEqual(data["revisions"][0]["path"], "/financials/0/operating_income/value")
        self.assertEqual(data["employees"], [])

    def test_half_does_not_touch_annual_row(self):
        first = state(fy2025())
        half26 = doc("S100AAH2", dei(period="HY", start="2025-04-01", end="2025-09-30", fy_end="2026-03-31", code=CODE) +
                     fin_rows("InterimDuration", 500_000_000, 120_000_000, ordinary=1, ni=2) +
                     fin_rows("Prior1InterimDuration", 1, 1), doc_code="160", start="2025-04-01", end="2025-09-30",
                     submitted="2025-11-14 15:00")
        data, _ = build(first, [half26], T2)
        self.assertEqual(data["revisions"], [])
        self.assertEqual(data["financials"][0], first["financials"][0])

    def test_employees_prior_column(self):
        first = state(fy2025(ec=1000, es=500))
        data, _ = build(first, [fy2026(prior=prior_fin() + emp_rows("Prior1YearInstant", 1100, 480, 39))], T2)
        self.valid(data)
        e = data["employees"][0]
        self.assertEqual((e["consolidated"]["employees"]["value"], e["consolidated"]["employees"]["doc_id"]), (1100, "S100AAA2"))
        self.assertEqual((e["non_consolidated"]["employees"]["value"], e["non_consolidated"]["employees"]["context"]),
                         (480, "Prior1YearInstant_NonConsolidatedMember"))
        self.assertEqual((e["non_consolidated"]["average_age"]["value"], e["non_consolidated"]["average_age"]["doc_id"]),
                         (40, "S100AAA1"))  # 平均年齢などは置き換えない
        self.assertEqual(e["doc_id"], "S100AAA1")
        self.assertEqual([(v["path"], v["old"], v["new"]) for v in data["revisions"]],
                         [("/employees/0/consolidated/employees/value", 1000, 1100),
                          ("/employees/0/non_consolidated/employees/value", 500, 480)])

    def test_failed_document_does_not_apply_comparative(self):
        first = state(fy2025())
        bad_rows = [x for x in dei(start="2025-04-01", end="2026-03-31", fy_end="2026-03-31", code=CODE) +
                    full_current("CurrentYearDuration", "CurrentYearInstant", 1, 1) + prior_fin(oi=1)
                    if "OperatingIncome" not in x[0] or "Prior" in x[2]]
        data, _ = build(first, [doc("S100AAA2", bad_rows, start="2025-04-01", end="2026-03-31",
                                    submitted="2026-06-20 15:00")], T2)
        self.assertEqual(data["filings"][1]["status"], "failed")
        self.assertEqual(data["financials"][0], first["financials"][0])

    def test_order_independence_of_replacement_decision_uses_submitted_at_not_ingest_order(self):
        # 新しい書類（S3）の前期の列で置き換えた値は、あとから取り込む S2（S1 と S3 の間の提出）の前期の列では戻らない
        first = state(fy2025())
        s3 = fy2026("S100AAA3", prior=prior_fin(oi=300_000_000), submitted="2026-09-01 10:00")
        second, _ = build(first, [s3], T2)
        s2 = fy2026("S100AAA2", prior=prior_fin(oi=400_000_000), submitted="2026-06-20 10:00")
        data, _ = build(second, [s2], datetime(2026, 10, 9, 9, 0, tzinfo=JST))
        self.assertEqual(data["financials"][0]["operating_income"]["value"], 300)

    def test_older_comparative_segments_do_not_replace_newer_ones(self):
        first = state(fy2025(segs={"AMember": (600_000_000, 40_000_000)}))
        s3 = fy2026("S100AAA3", prior=prior_fin() + seg_rows("Prior1YearDuration", {"ZMember": (700_000_000, None)}),
                    submitted="2026-09-01 10:00")
        second, _ = build(first, [s3], T2)
        s2 = fy2026("S100AAA2", prior=prior_fin() + seg_rows("Prior1YearDuration", {"YMember": (800_000_000, None)}),
                    submitted="2026-06-20 10:00")
        data, _ = build(second, [s2], datetime(2026, 10, 9, 9, 0, tzinfo=JST))
        self.assertEqual([s["member"] for s in data["financials"][0]["segments"]], ["ZMember"])
        self.assertEqual(data["financials"][0]["segments"][0]["net_sales_external"]["doc_id"], "S100AAA3")
        self.assertEqual(data["revisions"], [])  # メンバーの追加・削除は revisions に書けない


class SummaryTest(unittest.TestCase):
    def test_segments_changed_is_in_summary_and_screen(self):
        ia = __import__("ingest_all")
        first = state(fy2025(segs={"AMember": (600_000_000, None)}))
        prior = prior_fin() + seg_rows("Prior1YearDuration", {"CMember": (450_000_000, None)})
        data, changes = build(first, [fy2026(prior=prior)], T2)
        results = [{"slug": SLUG, "edinet_code": CODE, "skipped": None, "changes": changes, "data": data}]
        text = ia.render_summary(results, {"total": 1, "list": 1, "fetch": 0}, "KEY")
        self.assertIn("セグメントの区分が変わった（前期の列による置き換え）", text)
        self.assertIn("追加：CMember、削除：AMember", text)
        self.assertIn("置き換えた値：", text)
        screen = ingest_company.render_changes(SLUG, changes, 1)
        self.assertIn("[セグメントの区分]", screen)


if __name__ == "__main__":
    unittest.main()

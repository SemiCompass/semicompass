import copy
import itertools
import unittest

from test_comparative import (CODE, DOC_TYPES, T1, T2, XMAP, build, doc, ext, fin_rows, fy2025, listing, money, seg_rows,
                              state)
from test_extract import HEADER, dei, r
from test_ingest_rules import (LATER, SONY, SONY_PFX, check_all, emp_all, fetch, ifrs_fin, ifrs_segs)
from test_inspect_document import csv_text

build_auto = __import__("build_auto")
extract = __import__("extract")
ingest_company = __import__("ingest_company")
validate_data = __import__("validate_data")
YTD, QI, PYTD = "CurrentYTDDuration", "CurrentQuarterInstant", "Prior1YTDDuration"


def q2_dei(standard="Japan GAAP", code=CODE):
    # 実書類（S100UPNV、S100URKY、S100UQ07）と同じ期間：2024-04-01〜2024-09-30、fiscal_year_end は 2025-03-31
    return dei(standard, period="Q2", start="2024-04-01", end="2024-09-30", fy_end="2025-03-31", code=code)


def jg_q2(dur=YTD, ns=500_000_000, oi=100_000_000):
    return fin_rows(dur, ns, oi, ordinary=30_000_000, ni=20_000_000)


def q2_doc(doc_id, rows, submitted="2024-11-14 15:00", start="2024-04-01", end="2024-09-30", doc_code="160", **kw):
    """Q2 の書類は、取り込みと同じく、docTypeCode（160 か 170）を渡して取り出す。"""
    result = extract.extract([dict(zip(HEADER, x)) for x in rows], doc_id, "2026-10-04T10:00:00+09:00", XMAP,
                             doc_type_code=doc_code)
    return {"filing": listing(doc_id, doc_code, start=start, end=end, submitted=submitted, **kw), "result": result,
            "error": None}


class Q2ContextsTest(unittest.TestCase):
    def run_q2(self, rows, doc_type_code="160"):
        return extract.extract([dict(zip(HEADER, x)) for x in rows], "S100UPNV", "2026-10-04T10:00:00+09:00", XMAP,
                               doc_type_code=doc_type_code)

    def test_contexts_for_each_period_type(self):
        c = extract.contexts_for
        self.assertEqual(c({"period_type_raw": "FY", "period_type": "annual"}),
                         ("CurrentYearDuration", "CurrentYearInstant", "Prior1YearDuration", "Prior1YearInstant"))
        self.assertEqual(c({"period_type_raw": "HY", "period_type": "half"}),
                         ("InterimDuration", "InterimInstant", "Prior1InterimDuration", "Prior1InterimInstant"))
        self.assertEqual(c({"period_type_raw": "Q2", "period_type": "half"}),
                         (YTD, QI, PYTD, "Prior1QuarterInstant"))

    def test_japan_gaap_consolidated_without_segments(self):
        decoys = [money("jppfs_cor:NetSales", "CurrentYearDuration", 1), money("jppfs_cor:NetSales", "InterimDuration", 2),
                  money("jppfs_cor:NetSales", "CurrentYTDDuration_NonConsolidatedMember", 3),
                  money("jppfs_cor:NetSales", "Prior1YTDDuration", 4)]
        res = self.run_q2(q2_dei() + decoys + jg_q2())
        f = res["financial"]
        self.assertEqual(res["anomalies"], [])
        self.assertEqual((f["period_type"], f["fiscal_period_end"], f["period_start"], f["period_end"], f["consolidated"],
                          f["accounting_standard"]), ("half", "2025-03", "2024-04-01", "2024-09-30", True, "jgaap"))
        self.assertEqual((f["net_sales"]["value"], f["net_sales"]["context"], f["operating_income"]["context"]),
                         (500, YTD, YTD))
        self.assertEqual((f["ordinary_income"]["value"], f["net_income"]["value"]), (30, 20))
        self.assertEqual((f["segments"], f["regions"]), ([], []))
        self.assertNotIn("segment_adjustment", f)

    def test_no_employee_row_even_if_instant_rows_exist(self):
        rows = q2_dei() + jg_q2() + emp_all(QI) + emp_all("CurrentYearInstant")
        res = self.run_q2(rows)
        self.assertIsNone(res["employee"])
        self.assertIsNone(res["comparative"]["employee"])

    def test_ifrs_with_segments_including_company_specific_elements(self):
        rows = q2_dei("IFRS", code=SONY) + ifrs_fin(YTD, 4_000_000_000, 300_000_000, 200_000_000)
        ext_l, tot_l = "SalesAndFinancialServicesRevenueToCustomersIFRS", "SalesAndFinancialServicesRevenueIFRS"
        for name, (external, total, profit) in {"GameMember": (1_500_000_000, 1_700_000_000, 100_000_000),
                                                "MusicMember": (800_000_000, 900_000_000, 90_000_000)}.items():
            context = f"{YTD}_{SONY_PFX}{name}"
            rows += [money(f"{SONY_PFX}:{ext_l}", context, external), money(f"{SONY_PFX}:{tot_l}", context, total),
                     money("jpigp_cor:OperatingProfitLossIFRS", context, profit)]
        rows += [money("jpigp_cor:OperatingProfitLossIFRS", f"{YTD}_{SONY_PFX}ReconcilingItemsMember", -30_000_000),
                 money("jpigp_cor:OperatingProfitLossIFRS", f"{YTD}_{SONY_PFX}ReportableSegmentsMember", 190_000_000),
                 money(f"{SONY_PFX}:{ext_l}", f"CurrentYearDuration_{SONY_PFX}DecoyMember", 7)]
        res = self.run_q2(rows)
        f = res["financial"]
        self.assertEqual(res["anomalies"], [])
        self.assertEqual([s["member"] for s in f["segments"]], ["GameMember", "MusicMember"])
        game = f["segments"][0]
        self.assertEqual((game["net_sales_external"]["value"], game["net_sales_total"]["value"], game["profit"]["value"],
                          game["net_sales_external"]["context"]), (1500, 1700, 100, f"{YTD}_{SONY_PFX}GameMember"))
        self.assertEqual(f["segment_adjustment"]["value"], -30)
        self.assertEqual(f["accounting_standard"], "ifrs")

    def test_prior_column_uses_prior_ytd_contexts(self):
        rows = q2_dei() + jg_q2() + jg_q2(PYTD, 400_000_000, 90_000_000) + \
            seg_rows(PYTD, {"AMember": (300_000_000, 50_000_000)}, adjustment=-5_000_000) + \
            [money("jppfs_cor:NetSales", "Prior1InterimDuration", 1), money("jppfs_cor:NetSales", "Prior1YearDuration", 2)]
        comp = self.run_q2(rows)["comparative"]["financial"]
        self.assertEqual((comp["fiscal_period_end"], comp["period_type"], comp["net_sales"]["value"],
                          comp["net_sales"]["context"]), ("2024-03", "half", 400, PYTD))
        self.assertEqual((comp["segments"][0]["member"], comp["segments"][0]["profit"]["value"],
                          comp["segment_adjustment"]["value"]), ("AMember", 50, -5))

    def test_other_doc_type_codes_are_still_anomalies(self):
        for code in ("120", "130", None):  # 170（訂正半期報告書）は、半期として読む（TestQ2AmendedHalf）
            res = self.run_q2(q2_dei() + jg_q2(), code)
            self.assertTrue(res["stopped"], msg=code)
            self.assertEqual(res["anomalies"][0]["code"], "dei_unknown_period_type", msg=code)

    def test_fy_and_hy_results_do_not_change(self):
        hy = dei(period="HY", start="2024-04-01", end="2024-09-30", fy_end="2025-03-31", code=CODE) + jg_q2("InterimDuration") \
            + jg_q2(YTD, 1, 1)
        res = self.run_q2(hy, "160")
        self.assertEqual((res["financial"]["net_sales"]["value"], res["financial"]["net_sales"]["context"]),
                         (500, "InterimDuration"))
        fy = dei(code=CODE) + fin_rows("CurrentYearDuration", 700_000_000, 1, ordinary=1, ni=1) + emp_all("CurrentYearInstant") \
            + jg_q2(YTD, 1, 1)
        res = self.run_q2(fy, "120")
        self.assertEqual((res["financial"]["net_sales"]["value"], res["financial"]["net_sales"]["context"]),
                         (700, "CurrentYearDuration"))
        self.assertIsNotNone(res["employee"])


class Q2IngestTest(unittest.TestCase):
    def test_japan_gaap_q2_document_is_ingested_and_passes_checks(self):
        data, _ = build(None, [q2_doc("S100UPNV", q2_dei() + jg_q2())])
        f = data["filings"][0]
        self.assertEqual((f["status"], f["doc_type"], f["period_type"], f["fiscal_period_end"], f["period_start"], f["period_end"]),
                         ("ingested", "semiannual_report", "half", "2025-03", "2024-04-01", "2024-09-30"))
        row = data["financials"][0]
        self.assertEqual((row["period_type"], row["fiscal_period_end"], row["period_end"]), ("half", "2025-03", "2024-09-30"))
        self.assertEqual(data["employees"], [])
        check_all(self, data)

    def test_ifrs_q2_document_with_segments_passes_checks(self):
        rows = q2_dei("IFRS") + ifrs_fin(YTD, 4_000_000_000, 300_000_000, 200_000_000) + \
            ifrs_segs(YTD, {"AMember": (1_500_000_000, 100_000_000)}, -30_000_000)
        data, _ = build(None, [q2_doc("S100UQ07", rows)])
        self.assertEqual(data["filings"][0]["status"], "ingested")
        self.assertEqual(len(data["financials"][0]["segments"]), 1)
        check_all(self, data)

    def test_q2_prior_column_replaces_the_prior_half_row(self):
        old_rows = dei(period="HY", start="2023-04-01", end="2023-09-30", fy_end="2024-03-31", code=CODE) + \
            jg_q2("InterimDuration", 400_000_000, 100_000_000)
        first = state(doc("S100OLD1", old_rows, doc_code="160", start="2023-04-01", end="2023-09-30",
                          submitted="2023-11-14 15:00"))
        new = q2_doc("S100UPNV", q2_dei() + jg_q2() + jg_q2(PYTD, 400_000_000, 120_000_000))
        data, changes = build(first, [new], T2)
        old = data["financials"][0]
        self.assertEqual((old["fiscal_period_end"], old["period_type"]), ("2024-03", "half"))
        self.assertEqual((old["operating_income"]["value"], old["operating_income"]["context"],
                          old["operating_income"]["doc_id"]), (120, PYTD, "S100UPNV"))
        self.assertEqual([(v["path"], v["old"], v["new"], v["supersedes"]) for v in data["revisions"]],
                         [("/financials/0/operating_income/value", 100, 120, "S100OLD1")])
        check_all(self, data)

    def test_q2_document_with_other_doc_type_code_fails_without_values(self):
        row = listing("S100UPNV", "120", start="2024-04-01", end="2024-09-30", submitted="2024-11-14 15:00")
        got = fetch(q2_dei() + jg_q2(), row)
        data, _ = build_auto.build("advantest", CODE, None, [got], T1, DOC_TYPES)
        self.assertEqual((data["filings"][0]["status"], data["filings"][0]["error"]),
                         ("failed", "anomaly:dei_unknown_period_type"))
        self.assertEqual((data["financials"], data["employees"]), ([], []))
        check_all(self, data)


class Q2AmendedHalfTest(unittest.TestCase):
    """旧様式（Q2）の訂正半期報告書（docTypeCode 170）。SUMCO の S100UH1H（元の半期報告書は S100U5NK）の形。"""

    def dei(self):  # 決算期が12月の会社：半期は 2024-01-01〜2024-06-30、fiscal_year_end は 2024-12-31
        return dei("Japan GAAP", period="Q2", start="2024-01-01", end="2024-06-30", fy_end="2024-12-31", code=CODE)

    def original(self, ns=500_000_000, oi=100_000_000):
        return q2_doc("S100U5NK", self.dei() + jg_q2(YTD, ns, oi), submitted="2024-08-09 15:00",
                      start="2024-01-01", end="2024-06-30")

    def amended(self, ns=500_000_000, oi=90_000_000, doc_id="S100UH1H", **kw):
        return q2_doc(doc_id, self.dei() + jg_q2(YTD, ns, oi), submitted="2024-09-20 10:00", start="2024-01-01",
                      end="2024-06-30", doc_code="170", **kw)

    def test_amended_half_report_is_read_as_half(self):
        data, changes = build(None, [self.original(), self.amended(parentDocID="S100U5NK")])
        self.assertNotIn("not_recorded", [c["kind"] for c in changes])
        f = {x["doc_id"]: x for x in data["filings"]}["S100UH1H"]
        self.assertEqual((f["doc_type"], f["edinet_doc_type_code"], f["period_type"], f["fiscal_period_end"],
                          f["period_start"], f["period_end"]),
                         ("amended_semiannual_report", "170", "half", "2024-12", "2024-01-01", "2024-06-30"))
        self.assertEqual(data["employees"], [])
        self.assertEqual(len(data["financials"]), 1)
        self.assertEqual((data["financials"][0]["period_type"], data["financials"][0]["net_sales"]["context"]),
                         ("half", YTD))
        check_all(self, data)

    def test_original_is_superseded_and_values_are_replaced_with_revisions(self):
        first, _ = build(None, [self.original()])
        data, changes = build(first, [self.amended(ns=500_000_000, oi=90_000_000, parentDocID="S100U5NK")], T2)
        status = {f["doc_id"]: (f["status"], f.get("supersedes")) for f in data["filings"]}
        self.assertEqual(status, {"S100U5NK": ("superseded", None), "S100UH1H": ("ingested", "S100U5NK")})
        row = data["financials"][0]
        self.assertEqual((row["doc_id"], row["operating_income"]["value"], row["net_sales"]["value"]), ("S100UH1H", 90, 500))
        self.assertEqual([(v["path"], v["old"], v["new"], v["doc_id"], v["supersedes"]) for v in data["revisions"]],
                         [("/financials/0/operating_income/value", 100, 90, "S100UH1H", "S100U5NK")])
        self.assertIn("superseded", [c["kind"] for c in changes])
        check_all(self, data)

    def test_supersedes_follows_the_rule_even_without_parent_doc_id(self):
        first, _ = build(None, [self.original()])
        data, _ = build(first, [self.amended()], T2)  # parentDocID なし
        self.assertEqual({f["doc_id"]: f.get("supersedes") for f in data["filings"]}["S100UH1H"], "S100U5NK")
        self.assertEqual(data["filings"][0]["status"], "superseded")
        # parentDocID が別の書類を指しても、前に提出された書類のうち最も新しいものが優先される
        data, _ = build(first, [self.amended(parentDocID="S100ZZZZ")], T2)
        self.assertEqual({f["doc_id"]: f.get("supersedes") for f in data["filings"]}["S100UH1H"], "S100U5NK")

    def test_unchanged_values_add_no_revisions(self):
        first, _ = build(None, [self.original()])
        data, _ = build(first, [self.amended(oi=100_000_000)], T2)
        self.assertEqual(data["revisions"], [])
        self.assertEqual({f["doc_id"]: f["status"] for f in data["filings"]},
                         {"S100U5NK": "superseded", "S100UH1H": "ingested"})
        check_all(self, data)

    def test_rounding_difference_is_ignored(self):
        first, _ = build(None, [self.original(ns=90_378_818_000)])
        data, _ = build(first, [self.amended(ns=90_378_000_000, oi=100_000_000)], T2)
        self.assertEqual((data["financials"][0]["net_sales"]["value"], data["revisions"]), (90378.818, []))

    def test_second_run_changes_nothing_and_order_does_not_matter(self):
        docs = [self.original(), self.amended()]
        a, _ = build(None, docs)
        b, _ = build(None, list(reversed(docs)))
        self.assertEqual(a, b)
        again, changes = build(a, docs, LATER)
        self.assertEqual((again, changes), (a, []))

    def test_amended_half_without_an_original_is_not_recorded_as_a_new_kind_of_failure(self):
        data, changes = build(None, [self.amended()])
        self.assertEqual(data["filings"], [])
        self.assertEqual([(c["kind"], c["reason"]) for c in changes], [("not_recorded", "supersedes_unknown")])

    def test_ingest_passes_the_doc_type_code_170(self):
        row = listing("S100UH1H", "170", start="2024-01-01", end="2024-06-30", submitted="2024-09-20 10:00")
        got = fetch(self.dei() + jg_q2(YTD, 500_000_000, 90_000_000), row)
        self.assertIsNone(got["error"])
        self.assertFalse(got["result"]["stopped"])
        self.assertEqual(got["result"]["financial"]["period_type"], "half")

    def test_q2_in_annual_report_types_is_still_an_anomaly(self):
        for code in ("120", "130"):
            result = extract.extract([dict(zip(HEADER, x)) for x in self.dei() + jg_q2()], "S100UH1H",
                                     "2026-10-04T10:00:00+09:00", XMAP, doc_type_code=code)
            self.assertTrue(result["stopped"], msg=code)
            self.assertEqual(result["anomalies"][0]["code"], "dei_unknown_period_type", msg=code)
        # 120 は、取り込みでは failed（値は入らない）
        row = listing("S100UH1H", "120", start="2024-01-01", end="2024-06-30", submitted="2024-09-20 10:00")
        data, _ = build_auto.build("advantest", CODE, None, [fetch(self.dei() + jg_q2(), row)], T1, DOC_TYPES)
        self.assertEqual((data["filings"][0]["status"], data["filings"][0]["error"]),
                         ("failed", "anomaly:dei_unknown_period_type"))
        self.assertEqual(data["financials"], [])

    def test_q2_in_semiannual_report_160_is_as_before(self):
        data, _ = build(None, [self.original()])
        self.assertEqual((data["filings"][0]["doc_type"], data["filings"][0]["status"], data["filings"][0]["period_type"]),
                         ("semiannual_report", "ingested", "half"))
        check_all(self, data)


class ChainTest(unittest.TestCase):
    def doc_amended(self, doc_id, ns, submitted, parent="S100AAA1"):
        extra = {"parentDocID": parent} if parent else {}
        return fy2025(doc_id, ns=ns, doc_code="130", submitted=submitted, **extra)

    def ebara(self):
        """荏原の形：元の書類と、訂正報告書が2つ。2つ目の parentDocID が、元の書類を指す。"""
        return [fy2025("S100AAA1", ns=1_000_000_000, submitted="2024-03-28 15:00"),
                self.doc_amended("S100AAA2", 1_500_000_000, "2024-06-01 10:00"),
                self.doc_amended("S100AAA3", 1_600_000_000, "2024-09-01 10:00", parent="S100AAA1")]

    def chain(self, data):
        return {f["doc_id"]: (f["status"], f.get("supersedes")) for f in data["filings"]}

    def test_two_amendments_form_a_chain(self):
        data, _ = build(None, self.ebara())
        self.assertEqual(self.chain(data), {"S100AAA1": ("superseded", None), "S100AAA2": ("superseded", "S100AAA1"),
                                            "S100AAA3": ("ingested", "S100AAA2")})
        self.assertEqual(data["financials"][0]["net_sales"]["value"], 1600)
        # revisions の supersedes は、置き換える前の値の書類のまま
        self.assertEqual([(v["doc_id"], v["supersedes"], v["old"], v["new"]) for v in data["revisions"]],
                         [("S100AAA2", "S100AAA1", 1000, 1500), ("S100AAA3", "S100AAA2", 1500, 1600)])
        check_all(self, data)

    def test_one_amendment(self):
        data, _ = build(None, [fy2025("S100AAA1", submitted="2024-03-28 15:00"),
                               self.doc_amended("S100AAA2", 1_500_000_000, "2024-06-01 10:00")])
        self.assertEqual(self.chain(data), {"S100AAA1": ("superseded", None), "S100AAA2": ("ingested", "S100AAA1")})
        check_all(self, data)

    def test_parent_doc_id_pointing_at_the_original_loses_to_the_rule(self):
        data, changes = build(None, self.ebara())
        self.assertEqual(self.chain(data)["S100AAA3"][1], "S100AAA2")  # parentDocID は S100AAA1
        # 前の書類が filings にないときだけ、parentDocID を使う
        alone, _ = build(None, [self.doc_amended("S100AAA3", 1_600_000_000, "2024-09-01 10:00", parent="S100AAA1")])
        self.assertEqual(self.chain(alone), {"S100AAA3": ("ingested", "S100AAA1")})

    def test_any_order_gives_the_same_result(self):
        docs = self.ebara()
        results = [build(None, list(p))[0] for p in itertools.permutations(docs)]
        for other in results[1:]:
            self.assertEqual(other, results[0])

    def test_arrival_order_across_runs_gives_the_same_chain(self):
        docs = self.ebara()
        expected = self.chain(build(None, docs)[0])
        for first, second in ((docs[:2], docs[2:]), ([docs[0], docs[2]], [docs[1]]), (docs[:1], docs[1:]),
                              ([docs[2]], [docs[0], docs[1]])):
            state_one, _ = build(None, first)
            final, _ = build(state_one, second, T2)
            self.assertEqual(self.chain(final), expected)
            check_all(self, final)

    def test_second_run_changes_nothing(self):
        first, _ = build(None, self.ebara())
        again, changes = build(first, self.ebara(), LATER)
        self.assertEqual(again, first)
        self.assertEqual(changes, [])

    def legacy(self):
        """今の取り込みの結果（荏原）：S100AAA3 の supersedes が、元の書類を指している。"""
        data, _ = build(None, self.ebara())
        broken = copy.deepcopy(data)
        for f in broken["filings"]:
            if f["doc_id"] == "S100AAA3":
                f["supersedes"] = "S100AAA1"
        return broken

    def test_existing_file_is_fixed_on_rerun_and_stays_fixed(self):
        broken = self.legacy()
        fixed, changes = build(broken, self.ebara(), T2)
        self.assertEqual(self.chain(fixed)["S100AAA3"], ("ingested", "S100AAA2"))
        self.assertEqual([c["kind"] for c in changes], ["supersedes_fixed"])
        self.assertIn("S100AAA1 から S100AAA2", changes[0]["message"])
        self.assertEqual(fixed["updated_at"], "2026-10-05T11:30:00+09:00")
        self.assertEqual(fixed["revisions"], broken["revisions"])  # revisions は変えない
        again, changes = build(fixed, self.ebara(), LATER)
        self.assertEqual((again, changes), (fixed, []))
        check_all(self, fixed)

    def test_failed_amendment_is_fixed_but_does_not_supersede(self):
        first, _ = build(None, [fy2025("S100AAA1", submitted="2024-03-28 15:00"),
                                self.doc_amended("S100AAA2", 1_500_000_000, "2024-06-01 10:00")])
        failed = {"filing": listing("S100AAA3", "130", submitted="2024-09-01 10:00", parentDocID="S100AAA1"),
                  "result": None, "error": "zip_format"}
        data, _ = build(first, [failed], T2)
        c = self.chain(data)
        self.assertEqual(c["S100AAA3"], ("failed", "S100AAA2"))
        self.assertEqual(c["S100AAA2"], ("ingested", "S100AAA1"))  # failed は、前の版を superseded にしない
        check_all(self, data)

    def test_failed_documents_are_not_counted_as_previous_versions(self):
        failed = {"filing": listing("S100AAA2", "130", submitted="2024-06-01 10:00", parentDocID="S100AAA1"),
                  "result": None, "error": "zip_format"}
        data, _ = build(None, [fy2025("S100AAA1", submitted="2024-03-28 15:00"), failed,
                               self.doc_amended("S100AAA3", 1_600_000_000, "2024-09-01 10:00", parent="S100AAA2")])
        c = self.chain(data)
        self.assertEqual(c["S100AAA3"], ("ingested", "S100AAA1"))  # failed の S100AAA2 は、前の版にならない
        self.assertEqual(c["S100AAA2"], ("failed", "S100AAA1"))
        self.assertEqual(c["S100AAA1"][0], "superseded")
        check_all(self, data)

    def test_half_and_annual_chains_are_separate(self):
        half = lambda doc_id, ns, submitted, code="160": doc(  # noqa: E731
            doc_id, dei(period="HY", start="2024-04-01", end="2024-09-30", fy_end="2025-03-31", code=CODE) +
            jg_q2("InterimDuration", ns, 1), doc_code=code, start="2024-04-01", end="2024-09-30", submitted=submitted)
        docs = [fy2025("S100AAA1", submitted="2024-12-01 15:00"), half("S100AAH1", 400_000_000, "2024-11-14 15:00"),
                half("S100AAH2", 450_000_000, "2024-12-20 15:00", "170")]
        data, _ = build(None, docs)
        self.assertEqual(self.chain(data), {"S100AAA1": ("ingested", None), "S100AAH1": ("superseded", None),
                                            "S100AAH2": ("ingested", "S100AAH1")})
        check_all(self, data)


class ValidatorChainTest(unittest.TestCase):
    def test_validator_reports_a_broken_chain_as_an_error_and_passes_after_fix(self):
        import contextlib
        import io
        import json
        import shutil
        import tempfile
        from pathlib import Path
        helper = ChainTest()
        broken = helper.legacy()
        fixed, _ = build(broken, helper.ebara(), T2)
        root_dir = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data" / "companies").mkdir(parents=True)
            (root / "data" / "auto").mkdir()
            (root / "config").mkdir()
            shutil.copy(root_dir / "data" / "supply-chain.yaml", root / "data" / "supply-chain.yaml")
            shutil.copy(root_dir / "config" / "xbrl-map.yaml", root / "config" / "xbrl-map.yaml")
            shutil.copy(root_dir / "data" / "companies" / "advantest.yaml", root / "data" / "companies" / "advantest.yaml")
            target = root / "data" / "auto" / "advantest.json"
            # 切れた連鎖（S100AAA2 が superseded なのに、どこからも指されていない）
            target.write_text(json.dumps(broken), encoding="utf-8")
            problems = validate_data.validate(root)
            errors = [p for p in problems if p.severity == "error"]
            self.assertEqual([p.path for p in errors], ["/filings/1/status"])
            self.assertIn("S100AAA2", errors[0].message)
            self.assertEqual([p for p in problems if p.severity == "warning"], [])
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(validate_data.main([], root=root), 1)  # エラーなので、終了コード 1
                self.assertEqual(validate_data.main(["--strict"], root=root), 1)
            self.assertIn("エラー 1件 / 警告 0件", out.getvalue())
            # 直した結果は、エラーも警告も出ない
            target.write_text(json.dumps(fixed), encoding="utf-8")
            self.assertEqual(validate_data.validate(root), [])
            # failed の書類の supersedes だけが指している superseded は、エラーのまま
            only_failed = copy.deepcopy(fixed)
            for f in only_failed["filings"]:
                if f["doc_id"] == "S100AAA3":
                    f["status"] = "failed"
                    f["error"] = "zip_format"
                    f.pop("ingested_at", None)
            target.write_text(json.dumps(only_failed), encoding="utf-8")
            self.assertTrue([p for p in validate_data.validate(root) if p.severity == "error"])


if __name__ == "__main__":
    unittest.main()

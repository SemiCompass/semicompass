import contextlib
import io
import json
import os
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import yaml
from jsonschema import Draft202012Validator

import edinet_fakes as fk
from edinet_fakes import KEY, Clock
from test_client_document import DocServer
from test_inspect_document import CSV_NAME, HEADER, Base, csv_text, zip_response

extract = __import__("extract")
extract_document = __import__("extract_document")
csv_reader = __import__("csv_reader")
insp = __import__("inspect_document")

ROOT = Path(__file__).resolve().parents[2]
XMAP = yaml.safe_load((ROOT / "config" / "xbrl-map.yaml").read_text(encoding="utf-8"))
SCHEMA = json.loads((ROOT / "schemas" / "data" / "auto-company.schema.json").read_text(encoding="utf-8"))
AT = "2026-10-04T10:00:00+09:00"
DOC = "S100AAA1"
CUR, INST = "CurrentYearDuration", "CurrentYearInstant"
NC = "_NonConsolidatedMember"
PFX = "jpcrp030000-asr_E99999-000"


def validator(name):
    return Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": SCHEMA["$defs"]})


def r(element, context, value, label="", unit="円"):
    return [element, label, context, "当期", "連結", "期間", "JPY", unit, value]


def dei(standard="Japan GAAP", consolidated="true", period="FY", start="2025-04-01", end="2026-03-31",
        fy_end="2026-03-31", code="E99999"):
    d = "jpdei_cor:"
    return [r(d + "AccountingStandardsDEI", CUR, standard, unit=""),
            r(d + "WhetherConsolidatedFinancialStatementsArePreparedDEI", CUR, consolidated, unit=""),
            r(d + "TypeOfCurrentPeriodDEI", CUR, period, unit=""),
            r(d + "CurrentFiscalYearStartDateDEI", CUR, start, unit=""),
            r(d + "CurrentPeriodEndDateDEI", CUR, end, unit=""),
            r(d + "CurrentFiscalYearEndDateDEI", CUR, fy_end, unit=""),
            r(d + "EDINETCodeDEI", CUR, code, unit="")]


JG = [r("jppfs_cor:NetSales", CUR, "1000000000", "売上高"),
      r("jppfs_cor:OperatingIncome", CUR, "-50000000", "営業利益"),
      r("jppfs_cor:OrdinaryIncome", CUR, "30000000", "経常利益"),
      r("jppfs_cor:ProfitLossAttributableToOwnersOfParent", CUR, "20000000", "当期純利益")]
EMP_E = "jpcrp_cor:NumberOfEmployees"
EMP = [r(EMP_E, INST, "5000", "従業員数", ""), r(EMP_E, INST + NC, "1200", "従業員数", ""),
       r(EMP_E, INST + "_" + PFX + "SegAMember", "999", "従業員数", ""),
       r("jpcrp_cor:AverageAgeYearsInformationAboutReportingCompanyInformationAboutEmployees", INST + NC, "41.5", "", "年"),
       r("jpcrp_cor:AverageLengthOfServiceYearsInformationAboutReportingCompanyInformationAboutEmployees", INST + NC, "15.3", "", "年"),
       r("jpcrp_cor:AverageAnnualSalaryInformationAboutReportingCompanyInformationAboutEmployees", INST + NC, "7500000", "", "円")]


def seg(member, ext, total=None, profit=None, std="jppfs_cor"):
    c = f"{CUR}_{PFX}{member}" if member else CUR
    out = [r("jpcrp_cor:RevenuesFromExternalCustomers", c, ext)]
    if total:
        out.append(r("jppfs_cor:NetSales", c, total))
    if profit:
        out.append(r("jppfs_cor:OperatingIncome", c, profit))
    return out


def run(rows, **kw):
    res = extract.extract([dict(zip(HEADER, x)) for x in rows], DOC, AT, XMAP)
    for key, name in (("financial", "financial"), ("employee", "employee")):
        if res[key] is not None:
            errors = list(validator(name).iter_errors(res[key]))
            assert not errors, [e.message for e in errors]
    return res


class JgaapTest(unittest.TestCase):
    def test_consolidated_annual(self):
        res = run(dei() + JG + EMP)
        f = res["financial"]
        self.assertEqual(res["anomalies"], [])
        self.assertEqual((f["fiscal_period_end"], f["period_type"], f["period_start"], f["period_end"]),
                         ("2026-03", "annual", "2025-04-01", "2026-03-31"))
        self.assertEqual((f["accounting_standard"], f["consolidated"], f["net_sales_label"]), ("jgaap", True, "売上高"))
        self.assertEqual(f["net_sales"], {"value": 1000, "unit": "million_yen", "original_unit": "yen",
                                           "element": "jppfs_cor:NetSales", "context": CUR, "doc_id": DOC, "ingested_at": AT})
        self.assertEqual(f["operating_income"]["value"], -50)
        self.assertEqual(f["ordinary_income"]["value"], 30)
        self.assertEqual((f["segments"], f["regions"]), ([], []))

    def test_ordinary_income_missing_is_anomaly(self):
        res = run(dei() + [x for x in JG if "Ordinary" not in x[0]] + EMP)
        self.assertIsNone(res["financial"]["ordinary_income"]["value"])
        self.assertEqual([a["item"] for a in res["anomalies"] if a["code"] == "item_not_found"], ["ordinary_income"])

    def test_item_missing_is_anomaly_and_null(self):
        res = run(dei() + [x for x in JG if "OperatingIncome" not in x[0]] + EMP)
        self.assertIsNone(res["financial"]["operating_income"]["value"])
        self.assertEqual([a["item"] for a in res["anomalies"]], ["operating_income"])

    def test_candidate_order_and_second_candidate(self):
        rows = [r("jpcrp_cor:NetSalesSummaryOfBusinessResults", CUR, "7000000", "売上高、経営指標等")]
        res = run(dei() + rows + JG[1:])
        self.assertEqual(res["financial"]["net_sales"]["element"], "jpcrp_cor:NetSalesSummaryOfBusinessResults")
        self.assertEqual(res["financial"]["net_sales_label"], "売上高")

    def test_only_exact_current_context_is_used(self):
        rows = [r("jppfs_cor:NetSales", "Prior1YearDuration", "1", "売上高"),
                r("jppfs_cor:NetSales", CUR + NC, "2", "売上高"),
                r("jppfs_cor:NetSales", f"{CUR}_{PFX}SegAMember", "3", "売上高"),
                r("jppfs_cor:NetSales", "InterimDuration", "4", "売上高")]
        res = run(dei() + rows + JG[1:])
        self.assertIsNone(res["financial"]["net_sales"]["value"])

    def test_conflicting_duplicate_values(self):
        res = run(dei() + JG + [r("jppfs_cor:NetSales", CUR, "999000000", "売上高")])
        self.assertEqual(res["financial"]["net_sales"]["value"], 1000)
        self.assertIn("duplicate_conflict", [a["code"] for a in res["anomalies"]])


class OtherStandardsTest(unittest.TestCase):
    def test_ifrs(self):
        rows = dei("IFRS") + [r("jpigp_cor:RevenueIFRS", CUR, "2000000000", "売上収益（IFRS）"),
                              r("jpigp_cor:OperatingProfitLossIFRS", CUR, "100000000", "営業利益（IFRS）"),
                              r("jpigp_cor:ProfitLossAttributableToOwnersOfParentIFRS", CUR, "80000000", "親会社の所有者に帰属する当期利益（IFRS）")]
        res = run(rows + EMP)
        f = res["financial"]
        self.assertEqual(res["anomalies"], [])
        self.assertEqual((f["accounting_standard"], f["net_sales_label"], f["net_sales"]["value"]), ("ifrs", "売上収益", 2000))
        self.assertNotIn("ordinary_income", f)

    def test_ifrs_half_has_no_employee(self):
        rows = dei("IFRS", period="HY", end="2025-09-30") + [
            r("jpigp_cor:RevenueIFRS", "InterimDuration", "500000000", "売上収益（IFRS）"),
            r("jpigp_cor:OperatingProfitLossIFRS", "InterimDuration", "10000000"),
            r("jpigp_cor:ProfitLossAttributableToOwnersOfParentIFRS", "InterimDuration", "8000000"),
            r("jpigp_cor:RevenueIFRS", CUR, "9", "売上収益（IFRS）")] + EMP
        res = run(rows)
        self.assertIsNone(res["employee"])
        f = res["financial"]
        self.assertEqual((f["period_type"], f["period_end"], f["fiscal_period_end"]), ("half", "2025-09-30", "2026-03"))
        self.assertEqual(f["net_sales"]["context"], "InterimDuration")

    def test_usgaap(self):
        rows = dei("US GAAP") + [r("jpcrp_cor:RevenuesUSGAAPSummaryOfBusinessResults", CUR, "300000000", "売上高（US GAAP）、経営指標等"),
                                 r("jpcrp_cor:NetIncomeLossAttributableToOwnersOfParentUSGAAPSummaryOfBusinessResults", CUR, "5000000"),
                                 *seg("SegAMember", "100000000"), *EMP]
        res = run(rows)
        f = res["financial"]
        self.assertEqual(res["anomalies"], [])
        self.assertIsNone(f["operating_income"]["value"])
        self.assertEqual((f["segments"], f["net_sales_label"], f["net_sales"]["value"]), ([], "売上高", 300))
        self.assertNotIn("ordinary_income", f)


class SegmentTest(unittest.TestCase):
    def test_multi_segment(self):
        rows = dei() + JG + [
            *seg("EnergyReportableSegmentsMember", "600000000", "650000000", "40000000"),
            *seg("OtherMember", "400000000", None, "-3000000"),
            *seg("TotalOfReportableSegmentsAndOthersMember", "1000000000", "1100000000", "37000000"),
            *seg("ReconcilingItemsMember", "", None, "-87000000")[1:],
            r("jpcrp_cor:RevenuesFromExternalCustomers", f"{CUR}_{PFX}EnergyReportableSegmentsMember{NC}", "5"),
            r("jpcrp_cor:RevenuesFromExternalCustomers", f"{CUR}{NC}_{PFX}XMember", "6"),
            r("jpcrp_cor:RevenuesFromExternalCustomers", "Prior1YearDuration_" + PFX + "OldMember", "7")]
        res = run(rows)
        f = res["financial"]
        self.assertEqual([s["member"] for s in f["segments"]], ["EnergyReportableSegmentsMember", "OtherMember"])
        e = f["segments"][0]
        self.assertEqual((e["name"], e["net_sales_external"]["value"], e["net_sales_total"]["value"], e["profit"]["value"]),
                         ("EnergyReportableSegmentsMember", 600, 650, 40))
        self.assertNotIn("net_sales_total", f["segments"][1])
        self.assertEqual(f["segment_adjustment"]["value"], -87)
        self.assertTrue(res["notes"])


class EmployeeTest(unittest.TestCase):
    def test_not_mixed(self):
        res = run(dei() + JG + EMP)
        e = res["employee"]
        self.assertEqual((e["fiscal_period_end"], e["as_of"]), ("2026-03", "2026-03-31"))
        self.assertEqual(e["consolidated"]["employees"]["value"], 5000)
        n = e["non_consolidated"]
        self.assertEqual((n["employees"]["value"], n["average_age"]["value"], n["average_length_of_service"]["value"]),
                         (1200, 41.5, 15.3))
        self.assertEqual(n["average_age"]["unit"], "years")
        self.assertEqual(n["employees"]["context"], INST + NC)
        self.assertEqual(e["consolidated"]["employees"]["context"], INST)

    def test_salary_stays_yen(self):
        s = run(dei() + JG + EMP)["employee"]["non_consolidated"]["average_annual_salary"]
        self.assertEqual((s["value"], s["unit"], s["original_unit"]), (7500000, "yen", "yen"))

    def test_missing_rows_are_anomalies(self):
        res = run(dei() + JG + [x for x in EMP if "Average" not in x[0]])
        self.assertEqual(len([a for a in res["anomalies"] if a["code"] == "item_not_found"]), 3)

    def test_no_consolidated_row_for_non_consolidated_company(self):
        res = run(dei(consolidated="false") + JG + [x for x in EMP if x[2] != INST])
        self.assertNotIn("consolidated", res["employee"])
        self.assertFalse(res["financial"]["consolidated"])
        self.assertEqual(res["anomalies"], [])


class DeiTest(unittest.TestCase):
    def test_unknown_values_stop(self):
        for kw, code in ((dict(standard="Other GAAP"), "dei_unknown_accounting_standard"),
                         (dict(period="Q1"), "dei_unknown_period_type"),
                         (dict(consolidated="maybe"), "dei_unknown_consolidated"),
                         (dict(start="2025/04/01"), "dei_bad_date")):
            res = run(dei(**kw) + JG)
            self.assertTrue(res["stopped"], kw)
            self.assertIsNone(res["financial"])
            self.assertIn(code, [a["code"] for a in res["anomalies"]])

    def test_missing_dei_stops(self):
        res = run(JG)
        self.assertTrue(res["stopped"])
        self.assertEqual({a["code"] for a in res["anomalies"]}, {"dei_missing"})

    def test_period_mismatch_is_anomaly(self):
        res = run(dei(end="2025-12-31") + JG)
        self.assertIn("period_mismatch", [a["code"] for a in res["anomalies"]])

    def test_missing_column_raises(self):
        with self.assertRaises(ValueError):
            extract.extract([{"a": "1"}], DOC, AT, XMAP)


class ConversionTest(unittest.TestCase):
    def conv(self, value, unit="円", element="jppfs_cor:NetSales"):
        rows = [r("jppfs_cor:NetSales", CUR, value, "売上高", unit)]
        res = run(dei() + rows + JG[1:] + EMP)
        return res["financial"]["net_sales"], res

    def test_no_rounding_and_json_integer(self):
        v, res = self.conv("1234567")
        self.assertEqual(v["value"], 1.234567)
        self.assertEqual(res["anomalies"], [])
        v, _ = self.conv("2000000")
        self.assertIsInstance(v["value"], int)

    def test_big_and_negative(self):
        v, _ = self.conv("12345678900000000000")
        self.assertEqual(v["value"], 12345678900000)
        self.assertIsInstance(v["value"], int)
        self.assertEqual(self.conv("-3500000")[0]["value"], -3.5)
        self.assertEqual(self.conv("1,000,000")[0]["value"], 1)

    def test_original_units(self):
        v, _ = self.conv("5000", "千円")
        self.assertEqual((v["value"], v["original_unit"]), (5, "thousand_yen"))
        v, _ = self.conv("5", "百万円")
        self.assertEqual((v["value"], v["original_unit"]), (5, "million_yen"))

    def test_unknown_unit_is_anomaly_null(self):
        v, res = self.conv("5", "ドル")
        self.assertIsNone(v["value"])
        self.assertIn("unit_unknown", [a["code"] for a in res["anomalies"]])

    def test_empty_unit_uses_unit_id(self):
        v, _ = self.conv("5000000", "")
        self.assertEqual(v["value"], 5)

    def test_unrepresentable_precision_is_anomaly(self):
        v, res = self.conv("1" + "0" * 5 + "1234567890123456789")
        self.assertIn("precision_loss", [a["code"] for a in res["anomalies"]])


class ReaderTest(unittest.TestCase):
    def test_column_aliases_match_inspector(self):
        for role, aliases in insp.COLUMN_ALIASES.items():
            mine = extract.COLUMN_ALIASES.get("consolidated_column" if role == "consolidated" else role)
            self.assertEqual(mine, aliases, role)

    def test_dei_text_rows_are_kept_and_textblock_dropped(self):
        rows = dei() + JG + [r("jpcrp_cor:XTextBlock", CUR, "123", unit=""), r("jpcrp_cor:Other", CUR, "text")]
        got = csv_reader.document_rows(fk_zip(rows))
        self.assertEqual(len(got), len(dei()) + len(JG))

    def test_two_csv_with_dei_is_error(self):
        z = zip_bytes(dei() + JG, extra=[("XBRL_TO_CSV/second.csv", enc(csv_text(dei())))])
        with self.assertRaises(ValueError):
            csv_reader.document_rows(z)


def enc(text):
    return fk.__dict__.get("x") or ("﻿" + text).encode("utf-16-le")


def zip_bytes(rows, extra=()):
    from test_inspect_document import make_zip
    return make_zip(enc(csv_text(rows)), extra=extra)


def fk_zip(rows):
    return zip_bytes(rows)


class CliTest(Base):
    NOW = datetime(2026, 10, 4, 10, 0, 30, 123, tzinfo=ZoneInfo("Asia/Tokyo"))

    def go(self, argv=(), rows=None, env=None, response=None):
        rows = dei() + JG + EMP if rows is None else rows
        server = DocServer(response or zip_response(csv_text(rows)))
        clock = Clock()
        out, err = io.StringIO(), io.StringIO()
        environ = {extract_document.ENV_KEY: KEY} if env is None else env
        with mock.patch.dict(os.environ, environ, clear=True), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            code = extract_document.main(["--doc-id", DOC, *argv], open_url=server, sleep=clock.sleep,
                                         monotonic=clock.monotonic, now=self.NOW)
        return code, out.getvalue(), err.getvalue(), server

    def test_screen_and_json(self):
        path = self.tmp / "out.json"
        code, out, err, server = self.go(["--out", str(path)])
        self.assertEqual(code, 0, msg=err)
        for text in ("jppfs_cor:NetSales", CUR, "1000000000", "異常なし", "元の値", "換算後の値", "E99999"):
            self.assertIn(text, out)
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["financial"]["net_sales"]["ingested_at"], "2026-10-04T10:00:30+09:00")
        self.assertEqual(payload["edinet_code"], "E99999")
        self.assertEqual(len(server.requests), 1)
        for text in (out, err, path.read_text(encoding="utf-8")):
            self.assertNotIn(KEY, text)

    def test_company_match_and_mismatch(self):
        code, _, err, _ = self.go(["--company", "advantest"], rows=dei(code="E01950") + JG + EMP)
        self.assertEqual(code, 0, msg=err)
        code, out, err, _ = self.go(["--company", "advantest"])
        self.assertEqual(code, 2)
        self.assertIn("E01950", err)
        self.assertEqual(out, "")

    def test_unknown_company(self):
        self.assertEqual(self.go(["--company", "no-such-company"])[0], 2)

    def test_out_under_data_auto_is_rejected(self):
        code, out, err, server = self.go(["--out", str(ROOT / "data" / "auto" / "x.json")])
        self.assertEqual(code, 2)
        self.assertEqual(server.requests, [])
        self.assertFalse((ROOT / "data" / "auto" / "x.json").exists())

    def test_bad_doc_id_and_missing_key(self):
        with mock.patch.dict(os.environ, {extract_document.ENV_KEY: KEY}, clear=True), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(extract_document.main(["--doc-id", "bad"]), 2)
        self.assertEqual(self.go(env={})[0], 2)

    def test_stopped_exit_1_and_json_written(self):
        path = self.tmp / "o.json"
        code, out, _, _ = self.go(["--out", str(path)], rows=dei(standard="X") + JG)
        self.assertEqual(code, 1)
        self.assertTrue(json.loads(path.read_text(encoding="utf-8"))["stopped"])
        self.assertIn("取り出しを止めた", out)

    def test_http_error_never_prints_key(self):
        server = DocServer(lambda req: (_ for _ in ()).throw(fk.http_error(req, 500)))
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {extract_document.ENV_KEY: KEY}, clear=True), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = extract_document.main(["--doc-id", DOC], open_url=server, sleep=lambda s: None,
                                         monotonic=Clock().monotonic)
        self.assertEqual(code, 1)
        self.assertNotIn(KEY, out.getvalue() + err.getvalue())

    def test_not_a_zip_fails_without_traceback(self):
        code, _, err, _ = self.go(response=fk.FakeResponse(b"PK not really"))
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)


if __name__ == "__main__":
    unittest.main()

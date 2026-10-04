import contextlib
import copy
import io
import json
import os
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import yaml

import edinet_fakes as fk
from edinet_fakes import KEY, Clock, FakeResponse
from test_client_document import DocServer
from test_extract import EMP, HEADER, JG, dei, r
from test_inspect_document import Base, csv_text, zip_response

build_auto = __import__("build_auto")
ingest = __import__("ingest_company")
extract = __import__("extract")

ROOT = Path(__file__).resolve().parents[2]
XMAP = yaml.safe_load((ROOT / "config" / "xbrl-map.yaml").read_text(encoding="utf-8"))
DOC_TYPES = {str(k): v for k, v in XMAP["doc_types"].items()}
JST = ZoneInfo("Asia/Tokyo")
T1 = datetime(2026, 10, 4, 10, 0, tzinfo=JST)
T2 = datetime(2026, 10, 5, 11, 30, tzinfo=JST)
CODE = "E01950"
SLUG = "advantest"
CUR = "CurrentYearDuration"


def rows_for(net_sales="1000000000", fy_end="2026-03-31", period="FY", start="2025-04-01", end=None, code=CODE,
             employees=100):
    end = end or fy_end
    jg = [x[:] for x in JG]
    jg[0] = r("jppfs_cor:NetSales", CUR if period == "FY" else "InterimDuration", net_sales, "売上高")
    if period == "HY":
        for x in jg[1:]:
            x[2] = "InterimDuration"
    emp = [x[:] for x in EMP]
    emp[0][8] = str(employees)
    return dei(period=period, start=start, end=end, fy_end=fy_end, code=code) + jg + (emp if period == "FY" else [])


def ext(rows, doc_id):
    return extract.extract([dict(zip(HEADER, x)) for x in rows], doc_id, "2026-10-04T10:00:00+09:00", XMAP)


def listing(doc_id, doc_code="120", start="2025-04-01", end="2026-03-31", submitted="2026-06-20 15:00", code=CODE, **kw):
    row = fk.row(doc_id, code, doc_code, periodStart=start, periodEnd=end, submitDateTime=submitted, **kw)
    row["slug"] = SLUG
    return row


def doc(doc_id, rows=None, doc_code="120", **kw):
    rows = rows if rows is not None else rows_for()
    return {"filing": listing(doc_id, doc_code, **kw), "result": ext(rows, doc_id), "error": None}


def build(existing, docs, now=T1):
    return build_auto.build(SLUG, CODE, existing, docs, now, DOC_TYPES)


def errors(data):
    return ingest.validate(data)


class NewCompanyTest(unittest.TestCase):
    def test_new_company(self):
        data, changes = build(None, [doc("S100AAA1")])
        self.assertEqual(errors(data), [])
        self.assertEqual(list(data), list(build_auto.TOP_KEYS))
        self.assertEqual((data["company"], data["edinet_code"], data["updated_at"]), (SLUG, CODE, "2026-10-04T10:00:00+09:00"))
        f = data["filings"][0]
        self.assertEqual(list(f), ["doc_id", "doc_type", "edinet_doc_type_code", "fiscal_period_end", "period_type",
                                   "period_start", "period_end", "submitted_at", "url", "status", "ingested_at"])
        self.assertEqual((f["doc_type"], f["edinet_doc_type_code"], f["fiscal_period_end"], f["period_type"]),
                         ("annual_report", "120", "2026-03", "annual"))
        self.assertEqual((f["submitted_at"], f["status"], f["ingested_at"]),
                         ("2026-06-20T15:00:00+09:00", "ingested", "2026-10-04T10:00:00+09:00"))
        self.assertEqual(f["url"], "https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/S100AAA1.pdf")
        self.assertEqual(len(data["financials"]), 1)
        self.assertEqual(data["employees"][0]["fiscal_period_end"], "2026-03")
        self.assertEqual((data["announcements"], data["revisions"]), ([], []))
        self.assertEqual([c["kind"] for c in changes], ["added"])

    def test_second_run_changes_nothing(self):
        first, _ = build(None, [doc("S100AAA1")])
        again, changes = build(first, [doc("S100AAA1")], T2)
        self.assertEqual(again, first)
        self.assertEqual(again["updated_at"], "2026-10-04T10:00:00+09:00")
        self.assertEqual(changes, [])
        self.assertEqual(json.dumps(again), json.dumps(first))

    def test_existing_for_other_company_is_error(self):
        first, _ = build(None, [doc("S100AAA1")])
        first["edinet_code"] = "E00001"
        with self.assertRaises(ValueError):
            build(first, [])


class PeriodsTest(unittest.TestCase):
    def test_new_period_added_in_order_and_updated_at(self):
        first, _ = build(None, [doc("S100AAA2", rows_for("2000000000", "2027-03-31", start="2026-04-01"),
                                    start="2026-04-01", end="2027-03-31", submitted="2027-06-20 15:00")])
        data, changes = build(first, [doc("S100AAA1")], T2)
        self.assertEqual(errors(data), [])
        self.assertEqual([f["fiscal_period_end"] for f in data["financials"]], ["2026-03", "2027-03"])
        self.assertEqual([f["doc_id"] for f in data["filings"]], ["S100AAA1", "S100AAA2"])  # submitted_at の古い順
        self.assertEqual([e["fiscal_period_end"] for e in data["employees"]], ["2026-03", "2027-03"])
        self.assertEqual(data["updated_at"], "2026-10-05T11:30:00+09:00")

    def test_half_and_annual_mixed(self):
        half = doc("S100AAA3", rows_for("400000000", "2026-03-31", "HY", "2025-04-01", "2025-09-30"), doc_code="160",
                   start="2025-04-01", end="2025-09-30", submitted="2025-11-14 15:00")
        data, _ = build(None, [doc("S100AAA1"), half])
        self.assertEqual(errors(data), [])
        self.assertEqual([(f["fiscal_period_end"], f["period_type"]) for f in data["financials"]],
                         [("2026-03", "half"), ("2026-03", "annual")])
        self.assertEqual(len(data["employees"]), 1)
        self.assertEqual([f["doc_type"] for f in data["filings"]], ["semiannual_report", "annual_report"])


class AmendmentTest(unittest.TestCase):
    def amended(self, net_sales, doc_id="S100AAA9", parent="S100AAA1", submitted="2026-07-10 10:00"):
        extra = {"parentDocID": parent} if parent else {}
        return doc(doc_id, rows_for(net_sales), doc_code="130", submitted=submitted, **extra)

    def test_amended_replaces_value_with_history(self):
        first, _ = build(None, [doc("S100AAA1")])
        data, changes = build(first, [self.amended("1500000000")], T2)
        self.assertEqual(errors(data), [])
        statuses = {f["doc_id"]: f["status"] for f in data["filings"]}
        self.assertEqual(statuses, {"S100AAA1": "superseded", "S100AAA9": "ingested"})
        amended = next(f for f in data["filings"] if f["doc_id"] == "S100AAA9")
        self.assertEqual((amended["supersedes"], amended["doc_type"]), ("S100AAA1", "amended_annual_report"))
        self.assertNotIn("supersedes", data["filings"][0])
        self.assertEqual(data["financials"][0]["net_sales"]["value"], 1500)
        self.assertEqual(data["financials"][0]["doc_id"], "S100AAA9")
        self.assertEqual(data["revisions"], [{"at": "2026-10-05T11:30:00+09:00", "doc_id": "S100AAA9",
                                              "supersedes": "S100AAA1", "path": "/financials/0/net_sales/value",
                                              "old": 1000, "new": 1500}])
        self.assertEqual(sorted(c["kind"] for c in changes), ["added", "replaced", "superseded"])

    def test_same_values_make_no_revision(self):
        first, _ = build(None, [doc("S100AAA1")])
        data, _ = build(first, [self.amended("1000000000")], T2)
        self.assertEqual(data["revisions"], [])
        self.assertEqual(data["filings"][0]["status"], "superseded")
        self.assertEqual(data["financials"][0]["doc_id"], "S100AAA9")

    def test_without_parent_uses_previous_ingested(self):
        first, _ = build(None, [doc("S100AAA1")])
        data, _ = build(first, [self.amended("1500000000", parent=None)], T2)
        self.assertEqual(next(f for f in data["filings"] if f["doc_id"] == "S100AAA9")["supersedes"], "S100AAA1")
        self.assertEqual(data["filings"][0]["status"], "superseded")

    def test_second_amendment_supersedes_first(self):
        first, _ = build(None, [doc("S100AAA1"), self.amended("1500000000", parent=None)])
        data, _ = build(first, [self.amended("1600000000", "S100AAB1", parent=None, submitted="2026-08-01 10:00")], T2)
        statuses = {f["doc_id"]: f["status"] for f in data["filings"]}
        self.assertEqual(statuses, {"S100AAA1": "superseded", "S100AAA9": "superseded", "S100AAB1": "ingested"})
        self.assertEqual([(v["supersedes"], v["old"], v["new"]) for v in data["revisions"]],
                         [("S100AAA1", 1000, 1500), ("S100AAA9", 1500, 1600)])

    def test_amended_in_same_run_as_original(self):
        data, _ = build(None, [self.amended("1500000000", parent=None), doc("S100AAA1")])
        self.assertEqual(errors(data), [])
        self.assertEqual(data["financials"][0]["net_sales"]["value"], 1500)
        self.assertEqual(len(data["revisions"]), 1)

    def test_amended_without_known_original_is_not_recorded(self):
        data, changes = build(None, [self.amended("1500000000", parent=None)])
        self.assertEqual((data["filings"], data["financials"]), ([], []))
        self.assertEqual([c["kind"] for c in changes], ["not_recorded"])

    def test_late_arriving_original_does_not_override(self):
        first, _ = build(None, [self.amended("1500000000", parent="S100AAA1")])
        data, _ = build(first, [doc("S100AAA1")], T2)
        self.assertEqual(data["financials"][0]["net_sales"]["value"], 1500)
        self.assertEqual({f["doc_id"]: f["status"] for f in data["filings"]},
                         {"S100AAA1": "superseded", "S100AAA9": "ingested"})
        self.assertEqual(data["revisions"], [])

    def test_revision_paths_follow_row_after_earlier_period_is_inserted(self):
        later = doc("S100AAA2", rows_for("2000000000", "2027-03-31", start="2026-04-01"), start="2026-04-01",
                    end="2027-03-31", submitted="2027-06-20 15:00")
        amended = doc("S100AAA8", rows_for("2500000000", "2027-03-31", start="2026-04-01"), doc_code="130",
                      start="2026-04-01", end="2027-03-31", submitted="2027-07-20 15:00", parentDocID="S100AAA2")
        state, _ = build(None, [later, amended])
        self.assertEqual(state["revisions"][0]["path"], "/financials/0/net_sales/value")
        data, _ = build(state, [doc("S100AAA1")], T2)
        self.assertEqual(data["revisions"][0]["path"], "/financials/1/net_sales/value")
        self.assertEqual(data["financials"][1]["net_sales"]["value"], 2500)

    def test_segment_value_change_path(self):
        seg = [r("jpcrp_cor:RevenuesFromExternalCustomers", f"{CUR}_jpcrp030000-asr_E01950-000AMember", "100000000")]
        first, _ = build(None, [doc("S100AAA1", rows_for() + seg)])
        seg2 = [r("jpcrp_cor:RevenuesFromExternalCustomers", f"{CUR}_jpcrp030000-asr_E01950-000AMember", "300000000")]
        data, _ = build(first, [self.amended_rows(rows_for() + seg2)], T2)
        self.assertEqual([(v["path"], v["old"], v["new"]) for v in data["revisions"]],
                         [("/financials/0/segments/0/net_sales_external/value", 100, 300)])

    def amended_rows(self, rows):
        return doc("S100AAA9", rows, doc_code="130", submitted="2026-07-10 10:00", parentDocID="S100AAA1")


class FailureTest(unittest.TestCase):
    def test_anomaly_doc_is_failed_and_has_no_values(self):
        rows = [x for x in rows_for() if "OperatingIncome" not in x[0]]
        data, changes = build(None, [doc("S100AAA1", rows)])
        f = data["filings"][0]
        self.assertEqual((f["status"], f["error"]), ("failed", "anomaly:operating_income_not_found"))
        self.assertNotIn("ingested_at", f)
        self.assertEqual((data["financials"], data["employees"]), ([], []))
        self.assertEqual(errors(data), [])
        self.assertIn("failed", [c["kind"] for c in changes])
        self.assertIn("anomaly", [c["kind"] for c in changes])

    def test_stopped_dei_is_failed(self):
        data, _ = build(None, [doc("S100AAA1", rows_for() and dei(standard="Other") + JG)])
        f = data["filings"][0]
        self.assertEqual((f["status"], f["error"]), ("failed", "anomaly:dei_unknown_accounting_standard"))
        self.assertEqual((f["fiscal_period_end"], f["period_type"], f["period_start"]), ("2026-03", "annual", "2025-04-01"))
        self.assertEqual(errors(data), [])

    def test_failed_does_not_block_good_docs(self):
        bad = doc("S100AAA2", [x for x in rows_for("1", "2027-03-31", start="2026-04-01") if "OperatingIncome" not in x[0]],
                  start="2026-04-01", end="2027-03-31", submitted="2027-06-20 15:00")
        data, _ = build(None, [doc("S100AAA1"), bad])
        self.assertEqual([f["status"] for f in data["filings"]], ["ingested", "failed"])
        self.assertEqual(len(data["financials"]), 1)

    def test_fetch_failure_uses_listing_period(self):
        failed = {"filing": listing("S100AAA5", "160", start="2025-04-01", end="2025-09-30", submitted="2025-11-14 15:00"),
                  "result": None, "error": "fetch_failed"}
        data, changes = build(None, [failed])
        f = data["filings"][0]
        self.assertEqual((f["status"], f["error"], f["doc_type"]), ("failed", "fetch_failed", "semiannual_report"))
        self.assertEqual((f["fiscal_period_end"], f["period_type"], f["period_end"]), ("2026-03", "half", "2025-09-30"))
        self.assertEqual(errors(data), [])
        self.assertEqual(changes[0]["kind"], "failed")

    def test_fetch_failure_without_period_is_not_recorded(self):
        row = {**listing("S100AAA5"), "periodStart": None, "periodEnd": None}
        data, changes = build(None, [{"filing": row, "result": None, "error": "zip_format"}])
        self.assertEqual(data["filings"], [])
        self.assertEqual(changes[0]["kind"], "not_recorded")

    def test_doc_type_mismatch_is_failed(self):
        data, _ = build(None, [doc("S100AAA1", rows_for("1", "2026-03-31", "HY", "2025-04-01", "2025-09-30"))])
        self.assertEqual(data["filings"][0]["error"], "anomaly:doc_type_mismatch")


class SelectionTest(unittest.TestCase):
    def test_other_company_and_withdrawn_rows_are_excluded(self):
        other = {"filing": listing("S100AAA2", code="E00001"), "result": ext(rows_for(code="E00001"), "S100AAA2"), "error": None}
        gone = doc("S100AAA3", withdrawalStatus="1")
        unknown = doc("S100AAA4", doc_code="999")
        data, changes = build(None, [doc("S100AAA1"), other, gone, unknown])
        self.assertEqual([f["doc_id"] for f in data["filings"]], ["S100AAA1"])
        self.assertEqual(sorted(c["doc_id"] for c in changes if c["kind"] == "anomaly"),
                         ["S100AAA2", "S100AAA3", "S100AAA4"])

    def test_known_doc_is_not_ingested_twice(self):
        first, _ = build(None, [doc("S100AAA1")])
        data, _ = build(first, [doc("S100AAA1", rows_for("9"))], T2)
        self.assertEqual(data, first)

    def test_announcements_are_kept(self):
        first, _ = build(None, [doc("S100AAA1")])
        first["announcements"] = [{"fiscal_period_end": "2026-03", "quarter": 4, "announced_on": "2026-05-12",
                                   "detected_at": "2026-05-12T16:00:00+09:00",
                                   "documents": [{"type": "tanshin", "title": "決算短信", "url": "https://example.com/a.pdf",
                                                  "published_at": "2026-05-12T15:00:00+09:00"}]}]
        data, _ = build(first, [doc("S100AAA2", rows_for("2", "2027-03-31", start="2026-04-01"), start="2026-04-01",
                                    end="2027-03-31", submitted="2027-06-20 15:00")], T2)
        self.assertEqual(data["announcements"], first["announcements"])
        self.assertEqual(errors(data), [])


class SchemaTest(unittest.TestCase):
    def test_bad_data_fails_with_format_check(self):
        data, _ = build(None, [doc("S100AAA1")])
        bad = copy.deepcopy(data)
        bad["filings"][0]["period_start"] = "2025-13-45"
        self.assertTrue(any("period_start" in e for e in errors(bad)))
        bad = copy.deepcopy(data)
        bad["updated_at"] = "2026-13-45T10:00:00+09:00"
        self.assertTrue(errors(bad))
        bad = copy.deepcopy(data)
        bad["extra"] = 1
        self.assertTrue(errors(bad))


class CliTest(Base):
    NOW = datetime(2026, 10, 4, 10, 0, 30, tzinfo=JST)

    def listing_file(self, rows):
        path = self.tmp / "filings.json"
        path.write_text(json.dumps({"generated_at": "x", "filings": rows}, ensure_ascii=False), encoding="utf-8")
        return path

    def go(self, argv, server=None, env=None):
        server = server or DocServer(zip_response(csv_text(rows_for())))
        out, err = io.StringIO(), io.StringIO()
        environ = {ingest.ENV_KEY: KEY} if env is None else env
        with mock.patch.dict(os.environ, environ, clear=True), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            code = ingest.main(argv, open_url=server, sleep=lambda s: None, monotonic=Clock().monotonic, now=self.NOW)
        return code, out.getvalue(), err.getvalue(), server

    def args(self, rows, *extra):
        out_dir = self.tmp / "out"
        out_dir.mkdir(exist_ok=True)
        return ["--company", SLUG, "--filings-json", str(self.listing_file(rows)), "--out-dir", str(out_dir), *extra]

    def test_end_to_end_and_idempotent(self):
        rows = [listing("S100AAA1"), {**listing("S100AAA7"), "slug": "disco", "edinetCode": "E02000"}]
        code, out, err, server = self.go(self.args(rows))
        self.assertEqual(code, 0, msg=err)
        path = self.tmp / "out" / f"{SLUG}.json"
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.endswith("}\n"))
        self.assertEqual(text, json.dumps(json.loads(text), ensure_ascii=False, indent=2) + "\n")
        data = json.loads(text)
        self.assertEqual(ingest.validate(data), [])
        self.assertEqual(data["updated_at"], "2026-10-04T10:00:30+09:00")
        self.assertEqual(len(server.requests), 1)
        self.assertIn("S100AAA1", out)
        self.assertIn("取り込み", out)
        # 2回目：既存を渡すと、取得せず、書かない
        server2 = DocServer(zip_response(csv_text(rows_for())))
        before = path.stat().st_mtime_ns
        code, out, err, _ = self.go([*self.args(rows), "--existing", str(path)], server2)
        self.assertEqual(code, 0, msg=err)
        self.assertEqual(server2.requests, [])
        self.assertIn("変更がない", out)
        self.assertEqual(path.stat().st_mtime_ns, before)
        for t in (out, err, text):
            self.assertNotIn(KEY, t)

    def test_failed_documents_are_recorded(self):
        server = DocServer(FakeResponse(b"PK not really"))
        code, out, err, _ = self.go(self.args([listing("S100AAA1")]), server)
        self.assertEqual(code, 0, msg=err)
        data = json.loads((self.tmp / "out" / f"{SLUG}.json").read_text(encoding="utf-8"))
        self.assertEqual((data["filings"][0]["status"], data["filings"][0]["error"]), ("failed", "zip_format"))
        self.assertIn("失敗", out)

    def test_http_error_is_failed_but_auth_error_aborts(self):
        server = DocServer(lambda req: (_ for _ in ()).throw(fk.http_error(req, 500)))
        code, _, err, _ = self.go(self.args([listing("S100AAA1")]), server)
        self.assertEqual(code, 0, msg=err)
        data = json.loads((self.tmp / "out" / f"{SLUG}.json").read_text(encoding="utf-8"))
        self.assertEqual(data["filings"][0]["error"], "fetch_failed")
        (self.tmp / "out" / f"{SLUG}.json").unlink()
        server = DocServer(lambda req: (_ for _ in ()).throw(fk.http_error(req, 401)))
        code, out, err, _ = self.go(self.args([listing("S100AAA1")]), server)
        self.assertEqual(code, 1)
        self.assertFalse((self.tmp / "out" / f"{SLUG}.json").exists())
        for t in (out, err):
            self.assertNotIn(KEY, t)

    def test_document_of_other_company_is_failed(self):
        server = DocServer(zip_response(csv_text(rows_for(code="E00001"))))
        code, _, err, _ = self.go(self.args([listing("S100AAA1")]), server)
        data = json.loads((self.tmp / "out" / f"{SLUG}.json").read_text(encoding="utf-8"))
        self.assertEqual(data["filings"][0]["error"], "edinet_code_mismatch")

    def test_out_dir_under_data_auto_is_rejected(self):
        # data/auto/ が実在しなくても検査が働くことを確かめるため、実在するフォルダを禁止の場所に差し替える
        auto = self.tmp / "auto"
        (auto / "sub").mkdir(parents=True)
        listing_path = str(self.listing_file([listing("S100AAA1")]))
        with mock.patch.object(ingest, "FORBIDDEN_OUT_DIR", auto.resolve()):
            for target in (auto, auto / "sub"):
                code, _, err, server = self.go(["--company", SLUG, "--filings-json", listing_path,
                                                "--out-dir", str(target)])
                self.assertEqual(code, 2)
                self.assertIn("data/auto/", err)
                self.assertEqual(server.requests, [])
                self.assertEqual(list(target.glob("*.json")), [])
        code, _, err, _ = self.go(["--company", SLUG, "--filings-json", listing_path,
                                   "--out-dir", str(ROOT / "data" / "auto")])
        self.assertEqual(code, 2)

    def test_max_requests_exceeded_before_any_fetch(self):
        rows = [listing(f"S100AA{i}{i}") for i in range(3)]
        code, _, err, server = self.go(self.args(rows, "--max-requests", "2"))
        self.assertEqual(code, 2)
        self.assertEqual(server.requests, [])
        self.assertIn("--max-requests", err)

    def test_missing_key_when_fetch_is_needed(self):
        code, _, err, _ = self.go(self.args([listing("S100AAA1")]), env={})
        self.assertEqual(code, 2)

    def test_no_documents_and_no_existing_writes_nothing(self):
        code, out, _, _ = self.go(self.args([]), env={})
        self.assertEqual(code, 0)
        self.assertEqual(list((self.tmp / "out").iterdir()), [])

    def test_unknown_company_and_bad_files(self):
        argv = self.args([listing("S100AAA1")])
        argv[1] = "no-such-company"
        self.assertEqual(self.go(argv)[0], 2)
        argv = self.args([listing("S100AAA1")])
        argv[3] = str(self.tmp / "missing.json")
        self.assertEqual(self.go(argv)[0], 2)

    def test_schema_failure_writes_nothing(self):
        with mock.patch.object(ingest, "validate", return_value=["x: bad"]):
            code, _, err, _ = self.go(self.args([listing("S100AAA1")]))
        self.assertEqual(code, 1)
        self.assertFalse((self.tmp / "out" / f"{SLUG}.json").exists())


if __name__ == "__main__":
    unittest.main()

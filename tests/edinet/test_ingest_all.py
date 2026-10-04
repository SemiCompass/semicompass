import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import edinet_fakes as fk
from edinet_fakes import KEY, Clock, FakeResponse, ok_body
from test_build_auto import rows_for
from test_inspect_document import csv_text, zip_response

ia = __import__("ingest_all")
ingest_company = __import__("ingest_company")
build_auto = __import__("build_auto")

JST = ZoneInfo("Asia/Tokyo")
NOW = datetime(2026, 10, 6, 10, 0, tzinfo=JST)
DAY = "2026-06-19"  # 金曜日
ROOT = Path(__file__).resolve().parents[2]
A, B = "alpha-co", "beta-co"
CA, CB = "E00001", "E00002"


def entry(doc_id, code, doc_code="120", day=DAY, **kw):
    return fk.row(doc_id, code, doc_code, submitDateTime=f"{day} 15:00", **kw)


def doc_zip(code, net_sales="1000000000", drop=None):
    rows = rows_for(net_sales, code=code)
    if drop:
        rows = [x for x in rows if drop not in x[0]]
    return zip_response(csv_text(rows))


class Router:
    """書類一覧（documents.json）と書類取得（documents/{docID}）の模擬。"""

    def __init__(self, listing=None, docs=None):
        self.listing = listing or {}
        self.docs = docs or {}
        self.list_requests = []
        self.doc_requests = []

    def __call__(self, request, timeout):
        from urllib.parse import parse_qs, urlparse
        url = urlparse(request.full_url)
        if url.path.endswith("documents.json"):
            day = parse_qs(url.query)["date"][0]
            self.list_requests.append(day)
            step = self.listing.get(day, ok_body([]))
        else:
            doc_id = url.path.rsplit("/", 1)[1]
            self.doc_requests.append(doc_id)
            step = self.docs[doc_id]
        if isinstance(step, Exception):
            raise step
        if callable(step):
            return step(request)
        return step if isinstance(step, FakeResponse) else FakeResponse(step)


def raise_http(code):
    return lambda request: (_ for _ in ()).throw(fk.http_error(request, code))


class Base(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.tmp = Path(directory.name)
        self.companies = self.tmp / "companies"
        self.companies.mkdir()
        for slug, code in ((A, CA), (B, CB)):
            (self.companies / f"{slug}.yaml").write_text(f"slug: {slug}\nedinet_code: {code}\n", encoding="utf-8")
        (self.companies / "no-code.yaml").write_text("slug: no-code\n", encoding="utf-8")
        self.auto = self.tmp / "auto"
        self.out = self.tmp / "out"
        self.out.mkdir()
        self.summary = self.tmp / "summary.md"
        patcher = mock.patch.object(ia, "AUTO_DIR", self.auto)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_all(self, router, extra=(), companies=(A, B), env=None, out_dir=None, days=(DAY, DAY)):
        argv = []
        for c in companies:
            argv += ["--company", c]
        argv += ["--from", days[0], "--to", days[1], "--out-dir", str(out_dir or self.out),
                 "--summary", str(self.summary), *extra]
        out, err = io.StringIO(), io.StringIO()
        environ = {ia.ENV_KEY: KEY} if env is None else env
        with mock.patch.dict(os.environ, environ, clear=True), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            code = ia.main(argv, open_url=router, sleep=lambda s: None, monotonic=Clock().monotonic, now=NOW,
                           companies_dir=self.companies)
        return code, out.getvalue(), err.getvalue()

    def two_company_router(self, **docs):
        listing = {DAY: ok_body([entry("S100AAA1", CA), entry("S100BBB1", CB)])}
        base = {"S100AAA1": doc_zip(CA), "S100BBB1": doc_zip(CB, "2000000000")}
        base.update(docs)
        return Router(listing, base)

    def written(self):
        return sorted(p.name for p in self.out.iterdir())

    def load(self, slug, folder=None):
        return json.loads(((folder or self.out) / f"{slug}.json").read_text(encoding="utf-8"))

    def no_key(self, *texts):
        for t in texts:
            self.assertNotIn(KEY, t)


class IngestTest(Base):
    def test_two_companies_in_one_scan(self):
        router = self.two_company_router()
        code, out, err = self.run_all(router)
        self.assertEqual(code, 0, msg=err)
        self.assertEqual(router.list_requests, [DAY])          # 一覧は1回の走査
        self.assertEqual(sorted(router.doc_requests), ["S100AAA1", "S100BBB1"])
        self.assertEqual(self.written(), [f"{A}.json", f"{B}.json"])
        for slug, code_ in ((A, CA), (B, CB)):
            data = self.load(slug)
            self.assertEqual((data["company"], data["edinet_code"]), (slug, code_))
            self.assertEqual(ingest_company.validate(data), [])
            self.assertEqual(data["filings"][0]["status"], "ingested")
        self.assertEqual(self.load(B)["financials"][0]["net_sales"]["value"], 2000)
        text = (self.out / f"{A}.json").read_text(encoding="utf-8")
        self.assertEqual(text, json.dumps(json.loads(text), ensure_ascii=False, indent=2) + "\n")
        self.no_key(out, err, text, self.summary.read_text(encoding="utf-8"))

    def test_one_company_failing_does_not_stop_the_other(self):
        router = self.two_company_router(S100AAA1=FakeResponse(b"PK not really"))
        code, _, err = self.run_all(router)
        self.assertEqual(code, 0, msg=err)
        self.assertEqual((self.load(A)["filings"][0]["status"], self.load(A)["filings"][0]["error"]),
                         ("failed", "zip_format"))
        self.assertEqual(self.load(A)["financials"], [])
        self.assertEqual(self.load(B)["filings"][0]["status"], "ingested")

    def test_unexpected_error_in_one_company_skips_only_that_company(self):
        real = build_auto.build

        def flaky(slug, *a, **kw):
            if slug == A:
                raise RuntimeError("boom")
            return real(slug, *a, **kw)

        with mock.patch.object(build_auto, "build", flaky):
            code, out, err = self.run_all(self.two_company_router())
        self.assertEqual(code, 0, msg=err)
        self.assertEqual(self.written(), [f"{B}.json"])
        self.assertIn("飛ばした", out)
        self.assertIn(f"## {A}", self.summary.read_text(encoding="utf-8"))

    def test_second_run_with_same_input_changes_nothing(self):
        self.run_all(self.two_company_router())
        self.auto.mkdir()
        for slug in (A, B):
            (self.auto / f"{slug}.json").write_text((self.out / f"{slug}.json").read_text(encoding="utf-8"), encoding="utf-8")
        second = self.tmp / "out2"
        second.mkdir()
        router = self.two_company_router()
        code, out, err = self.run_all(router, out_dir=second)
        self.assertEqual(code, 0, msg=err)
        self.assertEqual(router.doc_requests, [])
        self.assertEqual(list(second.iterdir()), [])
        self.assertIn("変更なし", self.summary.read_text(encoding="utf-8"))

    def test_unchanged_company_is_not_written_but_changed_one_is(self):
        self.run_all(self.two_company_router())
        self.auto.mkdir()
        (self.auto / f"{A}.json").write_text((self.out / f"{A}.json").read_text(encoding="utf-8"), encoding="utf-8")
        second = self.tmp / "out2"
        second.mkdir()
        code, _, err = self.run_all(self.two_company_router(), out_dir=second)
        self.assertEqual(code, 0, msg=err)
        self.assertEqual(sorted(p.name for p in second.iterdir()), [f"{B}.json"])  # A は既存と同じ
        self.assertEqual(json.loads((second / f"{B}.json").read_text(encoding="utf-8"))["updated_at"],
                         "2026-10-06T10:00:00+09:00")

    def test_existing_file_of_other_company_is_skipped_and_reported(self):
        self.auto.mkdir()
        (self.auto / f"{A}.json").write_text(json.dumps({"company": A, "edinet_code": "E99999"}), encoding="utf-8")
        before = (self.auto / f"{A}.json").read_text(encoding="utf-8")
        code, _, err = self.run_all(self.two_company_router())
        self.assertEqual(code, 0, msg=err)
        self.assertEqual(self.written(), [f"{B}.json"])
        self.assertEqual((self.auto / f"{A}.json").read_text(encoding="utf-8"), before)
        self.assertIn("一致しない", self.summary.read_text(encoding="utf-8"))

    def test_broken_existing_file_is_skipped(self):
        self.auto.mkdir()
        (self.auto / f"{A}.json").write_text("{ not json", encoding="utf-8")
        code, _, _ = self.run_all(self.two_company_router())
        self.assertEqual((code, self.written()), (0, [f"{B}.json"]))

    def test_rows_of_unlisted_company_are_ignored(self):
        router = Router({DAY: ok_body([entry("S100AAA1", CA), entry("S100ZZZ1", "E77777")])},
                        {"S100AAA1": doc_zip(CA)})
        code, _, _ = self.run_all(router, companies=(A,))
        self.assertEqual((code, router.doc_requests), (0, ["S100AAA1"]))

    def test_retry_failed(self):
        router = self.two_company_router(S100AAA1=FakeResponse(b"PK not really"))
        self.run_all(router)
        self.auto.mkdir()
        (self.auto / f"{A}.json").write_text((self.out / f"{A}.json").read_text(encoding="utf-8"), encoding="utf-8")
        second = self.tmp / "out2"
        second.mkdir()
        router = self.two_company_router()
        self.run_all(router, out_dir=second)
        self.assertEqual(router.doc_requests, ["S100BBB1"])  # 指定なしでは、failed の A を再取得しない（B は既存がないので取得）
        third = self.tmp / "out3"
        third.mkdir()
        router = self.two_company_router()
        code, _, err = self.run_all(router, ["--retry-failed"], out_dir=third)
        self.assertEqual(code, 0, msg=err)
        self.assertEqual(sorted(router.doc_requests), ["S100AAA1", "S100BBB1"])
        data = json.loads((third / f"{A}.json").read_text(encoding="utf-8"))
        self.assertEqual([(f["doc_id"], f["status"]) for f in data["filings"]], [("S100AAA1", "ingested")])

    def test_transient_failure_is_not_recorded(self):
        router = self.two_company_router(S100AAA1=TimeoutError("timed out"))
        code, out, err = self.run_all(router)
        self.assertEqual((code, self.written()), (0, [f"{B}.json"]))
        self.assertIn("transient", self.summary.read_text(encoding="utf-8"))


class StopTest(Base):
    def test_auth_error_stops_everything_and_writes_nothing(self):
        router = self.two_company_router(S100AAA1=raise_http(401))
        code, out, err = self.run_all(router)
        self.assertEqual(code, 1)
        self.assertEqual(list(self.out.iterdir()), [])
        self.assertFalse(self.summary.exists())
        self.no_key(out, err)

    def test_listing_failure_stops_everything(self):
        router = Router({DAY: raise_http(500)}, {})
        code, out, err = self.run_all(router)
        self.assertEqual((code, list(self.out.iterdir())), (1, []))
        self.assertFalse(self.summary.exists())
        self.no_key(out, err)

    def test_schema_failure_writes_nothing(self):
        real = ingest_company.validate
        with mock.patch.object(ingest_company, "validate",
                               lambda data: ["x: bad"] if data["company"] == B else real(data)):
            code, _, err = self.run_all(self.two_company_router())
        self.assertEqual(code, 1)
        self.assertEqual(list(self.out.iterdir()), [])  # A も書かない
        self.assertFalse(self.summary.exists())
        self.assertIn("何も書かない", err)

    def test_real_schema_check_catches_bad_date_time(self):
        real = build_auto.build

        def bad(*a, **kw):
            data, changes = real(*a, **kw)
            data["updated_at"] = "2026-13-45T10:00:00+09:00"
            return data, changes

        with mock.patch.object(build_auto, "build", bad):
            code, _, _ = self.run_all(self.two_company_router())
        self.assertEqual((code, list(self.out.iterdir())), (1, []))

    def test_max_requests_exceeded_by_days(self):
        router = self.two_company_router()
        code, _, err = self.run_all(router, ["--max-requests", "1", "--include-weekends"], days=("2026-06-18", "2026-06-19"))
        self.assertEqual(code, 2)
        self.assertEqual((router.list_requests, router.doc_requests), ([], []))
        self.assertIn("--max-requests", err)

    def test_max_requests_exceeded_by_total_before_any_fetch_or_write(self):
        router = self.two_company_router()
        code, _, err = self.run_all(router, ["--max-requests", "2"])  # 一覧1回＋取得2回＝3回
        self.assertEqual(code, 2)
        self.assertEqual(router.doc_requests, [])
        self.assertEqual(list(self.out.iterdir()), [])
        self.assertIn("合計 3 回", err)

    def test_missing_key_and_bad_companies(self):
        self.assertEqual(self.run_all(self.two_company_router(), env={})[0], 2)
        self.assertEqual(self.run_all(self.two_company_router(), companies=("no-such",))[0], 2)
        self.assertEqual(self.run_all(self.two_company_router(), companies=("no-code",))[0], 2)


class WriteDataAutoTest(Base):
    def test_conditions(self):
        router = self.two_company_router
        # GITHUB_ACTIONS が true でない
        for env in ({ia.ENV_KEY: KEY}, {ia.ENV_KEY: KEY, "GITHUB_ACTIONS": "false"},
                    {ia.ENV_KEY: KEY, "GITHUB_ACTIONS": "True"}):
            code, _, err = self.run_all(router(), ["--write-data-auto"], env=env, out_dir=self.auto)
            self.assertEqual(code, 2, msg=env)
            self.assertIn("GITHUB_ACTIONS", err)
        self.assertFalse(self.auto.exists())
        actions = {ia.ENV_KEY: KEY, "GITHUB_ACTIONS": "true"}
        # --out-dir が data/auto と一致しない
        code, _, err = self.run_all(router(), ["--write-data-auto"], env=actions, out_dir=self.out)
        self.assertEqual(code, 2)
        self.assertIn("一致", err)
        # フラグなしで data/auto（とその下）を指定
        self.auto.mkdir()
        (self.auto / "sub").mkdir()
        for target in (self.auto, self.auto / "sub"):
            code, _, err = self.run_all(router(), env=actions, out_dir=target)
            self.assertEqual(code, 2)
            self.assertIn("data/auto/", err)
        code, _, _ = self.run_all(router(), ["--write-data-auto"], env=actions, out_dir=self.auto / "sub")
        self.assertEqual(code, 2)
        self.assertEqual(list(self.auto.glob("*.json")), [])
        self.assertEqual(list(self.out.iterdir()), [])

    def test_writes_to_data_auto_when_allowed(self):
        actions = {ia.ENV_KEY: KEY, "GITHUB_ACTIONS": "true"}
        code, _, err = self.run_all(self.two_company_router(), ["--write-data-auto"], env=actions, out_dir=self.auto)
        self.assertEqual(code, 0, msg=err)  # data/auto が無くても、作って書く
        self.assertEqual(sorted(p.name for p in self.auto.glob("*.json")), [f"{A}.json", f"{B}.json"])
        self.assertEqual(list(self.out.iterdir()), [])

    def test_real_data_auto_is_rejected_without_flag(self):
        # 差し替えずに、リポジトリの data/auto を指定する
        def snapshot():
            real = ROOT / "data" / "auto"
            return sorted((p.name, p.stat().st_mtime_ns) for p in real.iterdir()) if real.exists() else None

        before = snapshot()
        with mock.patch.object(ia, "AUTO_DIR", ROOT / "data" / "auto"):
            code, _, err = self.run_all(self.two_company_router(), out_dir=ROOT / "data" / "auto")
        self.assertEqual(code, 2)
        self.assertEqual(snapshot(), before)  # data/auto は、何も変わらない

    def test_summary_under_data_auto_is_rejected(self):
        self.auto.mkdir()
        self.summary = self.auto / "s.md"
        self.assertEqual(self.run_all(self.two_company_router())[0], 2)


class SummaryTest(Base):
    def test_summary_content(self):
        bad_rows = [x for x in rows_for("3000000000", code=CB) if "OperatingIncome" not in x[0]]
        router = Router({DAY: ok_body([entry("S100AAA1", CA), entry("S100BBB1", CB),
                                       entry("S100BBB2", CB, "130", parentDocID="S100BBB1", day=DAY)])},
                        {"S100AAA1": doc_zip(CA), "S100BBB1": zip_response(csv_text(bad_rows)),
                         "S100BBB2": FakeResponse(b"PK not really")})
        code, _, err = self.run_all(router)
        self.assertEqual(code, 0, msg=err)
        text = self.summary.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# 取り込みの概要"))
        for expected in ("追加した書類：1件", "置き換えた値：0件", "failed の書類：2件", "not_recorded の書類：0件",
                         "APIの呼び出し：4回（書類の一覧 1回、書類の取得 3回）",
                         f"## {A}（{CA}）", f"## {B}（{CB}）",
                         "S100AAA1：annual_report、決算期 2026-03（annual）",
                         "S100BBB1：anomaly:operating_income_not_found", "S100BBB2：zip_format",
                         "**異常**", "operating_income"):
            self.assertIn(expected, text)
        self.no_key(text)

    def test_replaced_values_in_summary(self):
        self.run_all(self.two_company_router())
        self.auto.mkdir()
        (self.auto / f"{A}.json").write_text((self.out / f"{A}.json").read_text(encoding="utf-8"), encoding="utf-8")
        second = self.tmp / "out2"
        second.mkdir()
        router = Router({DAY: ok_body([entry("S100AAA1", CA), entry("S100AAA9", CA, "130", parentDocID="S100AAA1",
                                                                    day="2026-06-19")])},
                        {"S100AAA9": doc_zip(CA, "1500000000")})
        # 訂正の提出が元より後になるよう、時刻を上書き
        router.listing[DAY]["results"][1]["submitDateTime"] = "2026-06-19 16:00"
        code, _, err = self.run_all(router, out_dir=second, companies=(A,))
        self.assertEqual(code, 0, msg=err)
        text = self.summary.read_text(encoding="utf-8")
        self.assertIn("置き換えた値：1件", text)
        self.assertIn("/financials/0/net_sales/value", text)
        data = json.loads((second / f"{A}.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data["revisions"]), 1)

    def test_no_document_text_in_summary(self):
        # 数値以外の本文の行は、取り込みの対象外で、概要にも出ない
        rows = rows_for(code=CA) + [["jpcrp_cor:DescriptionOfBusiness", "事業の内容", "CurrentYearDuration", "当期", "連結",
                                     "期間", "", "", "本文の秘密の文章"]]
        router = Router({DAY: ok_body([entry("S100AAA1", CA)])}, {"S100AAA1": zip_response(csv_text(rows))})
        code, out, err = self.run_all(router, companies=(A,))
        self.assertNotIn("本文の秘密の文章", self.summary.read_text(encoding="utf-8") + out + err)
        self.assertNotIn("本文の秘密の文章", (self.out / f"{A}.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

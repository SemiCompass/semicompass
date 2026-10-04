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
from edinet_fakes import KEY, Clock, DayServer, http_error, ok_body, row

lf = fk.list_filings
JST = ZoneInfo("Asia/Tokyo")
NOW = datetime(2026, 10, 6, 10, 0, tzinfo=JST)  # 火曜日。前日は月曜日 2026-10-05
LATER = datetime(2026, 10, 12, 10, 0, tzinfo=JST)  # 範囲が未来にならない日

COMPANIES = {
    "advantest": "E01950",
    "disco": "E02000",
    "no-edinet": None,   # 外資系日本法人など。edinet_code がない
}


class Base(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.tmp = Path(directory.name)
        self.companies = self.tmp / "companies"
        self.companies.mkdir()
        for slug, code in COMPANIES.items():
            text = f"schema_version: 1\nslug: {slug}\n" + (f"edinet_code: {code}\n" if code else "")
            (self.companies / f"{slug}.yaml").write_text(text, encoding="utf-8")

    def run_main(self, argv, server=None, *, env=None, now=NOW, config_path=None, clock=None):
        clock = clock or Clock()
        server = server or DayServer(clock=clock)
        out, err = io.StringIO(), io.StringIO()
        environ = {lf.ENV_KEY: KEY} if env is None else env
        with mock.patch.dict(os.environ, environ, clear=True), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            code = lf.main(argv, open_url=server, sleep=clock.sleep, monotonic=clock.monotonic, now=now,
                           companies_dir=self.companies, config_path=config_path or lf.XBRL_MAP_PATH)
        return code, out.getvalue(), err.getvalue(), server, clock


class DateRangeTest(Base):
    def test_weekends_are_skipped_by_default(self):
        # 10/2(金)〜10/6(火)。土日（10/3、10/4）は呼ばない
        code, out, err, server, _ = self.run_main(
            ["--company", "advantest", "--from", "2026-10-02", "--to", "2026-10-06"])
        self.assertEqual(code, 0, msg=err)
        self.assertEqual(server.days, ["2026-10-02", "2026-10-05", "2026-10-06"])
        self.assertEqual({t for _, t, _ in server.requests}, {"2"})  # type=2（提出書類の一覧）

    def test_include_weekends(self):
        _, _, _, server, _ = self.run_main(
            ["--company", "advantest", "--from", "2026-10-02", "--to", "2026-10-06", "--include-weekends"])
        self.assertEqual(server.days, ["2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05", "2026-10-06"])

    def test_range_includes_both_ends_and_single_day(self):
        _, _, _, server, _ = self.run_main(["--company", "advantest", "--from", "2026-10-05", "--to", "2026-10-05"])
        self.assertEqual(server.days, ["2026-10-05"])

    def test_default_is_yesterday_in_japan(self):
        _, _, _, server, _ = self.run_main(["--company", "advantest"])  # 10/6(火) の前日は 10/5(月)
        self.assertEqual(server.days, ["2026-10-05"])
        # 日本時間の日付が変わった直後（UTCではまだ前日）でも、日本時間で数える
        now = datetime(2026, 10, 6, 0, 30, tzinfo=JST)
        _, _, _, server, _ = self.run_main(["--company", "advantest"], now=now)
        self.assertEqual(server.days, ["2026-10-05"])

    def test_default_yesterday_on_weekend_makes_no_request(self):
        now = datetime(2026, 10, 5, 10, 0, tzinfo=JST)  # 月曜日。前日は日曜日
        code, out, _, server, _ = self.run_main(["--company", "advantest"], now=now)
        self.assertEqual(code, 0)
        self.assertEqual(server.requests, [])
        self.assertIn("対象の日がない", out)
        _, _, _, server, _ = self.run_main(["--company", "advantest", "--include-weekends"], now=now)
        self.assertEqual(server.days, ["2026-10-04"])

    def test_invalid_ranges(self):
        for argv in (["--from", "2026-10-02"], ["--to", "2026-10-02"],
                     ["--from", "2026-10-06", "--to", "2026-10-02"],
                     ["--from", "2026-10-02", "--to", "2026-10-07"]):  # 未来
            code, out, err, server, _ = self.run_main(["--company", "advantest", *argv])
            self.assertEqual(code, 2, msg=argv)
            self.assertEqual(server.requests, [])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            lf.parse_args(["--company", "advantest", "--from", "2026/10/02", "--to", "2026/10/03"])
        self.assertEqual(raised.exception.code, 2)


class MaxRequestsTest(Base):
    RANGE = ["--from", "2026-09-21", "--to", "2026-10-02"]  # 平日10日

    def test_exceeding_max_requests_fails_before_any_request(self):
        code, out, err, server, _ = self.run_main(["--company", "advantest", *self.RANGE, "--max-requests", "9"])
        self.assertEqual(code, 2)
        self.assertEqual(server.requests, [])
        self.assertIn("--max-requests", err)
        self.assertIn("超える", err)

    def test_exactly_max_requests_is_allowed(self):
        code, _, _, server, _ = self.run_main(["--company", "advantest", *self.RANGE, "--max-requests", "10"])
        self.assertEqual(code, 0)
        self.assertEqual(len(server.requests), 10)

    def test_default_is_400(self):
        self.assertEqual(lf.parse_args(["--company", "x"]).max_requests, 400)
        # 400日を超える範囲（土日を含む）は、既定では実行前に止まる
        code, _, err, server, _ = self.run_main(
            ["--company", "advantest", "--from", "2025-01-01", "--to", "2026-10-02", "--include-weekends"])
        self.assertEqual(code, 2)
        self.assertEqual(server.requests, [])

    def test_retries_also_count_toward_the_limit(self):
        limited = {"2026-10-05": [http_error_for(429)]}
        code, out, err, server, _ = self.run_main(
            ["--company", "advantest", "--from", "2026-10-05", "--to", "2026-10-05", "--max-requests", "1"],
            DayServer(limited))
        self.assertEqual(code, 1)
        self.assertEqual(len(server.requests), 1)  # 再試行の2回目は、上限で止まる
        self.assertIn("上限", err)

    def test_invalid_max_requests_value(self):
        for value in ("0", "-1", "abc"):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                lf.parse_args(["--company", "x", "--max-requests", value])


def http_error_for(code):
    def raiser(request):
        raise http_error(request, code, {"StatusCode": code, "message": "x"})
    return raiser


class FilteringTest(Base):
    DAY = "2026-10-05"

    def results(self):
        return [
            row("S100AAA1", "E01950", "120"),                                   # 対象
            row("S100AAA2", "E01950", "130", docDescription="訂正有価証券報告書"),  # 対象（訂正）
            row("S100AAA3", "E01950", "160"),                                   # 対象
            row("S100AAA4", "E01950", "170"),                                   # 対象（訂正）
            row("S100AAA5", "E01950", "350"),                                   # 対象外の書類の種類
            row("S100AAA6", "E01950", "030"),                                   # 対象外の書類の種類
            row("S100BBB1", "E99999", "120"),                                   # 別の企業
            row("S100BBB2", None, "120"),                                       # edinetCode なし
            row("S100CCC1", "E02000", "120"),                                   # 別の対象の企業
        ]

    def run_day(self, results, companies=("advantest",), extra=()):
        argv = []
        for c in companies:
            argv += ["--company", c]
        server = DayServer({self.DAY: [ok_body(results)]})
        return self.run_main([*argv, "--from", self.DAY, "--to", self.DAY, "--out", str(self.tmp / "o.json"), *extra],
                             server)

    def filings(self):
        return json.loads((self.tmp / "o.json").read_text(encoding="utf-8"))["filings"]

    def test_doc_type_code_filter(self):
        code, out, err, _, _ = self.run_day(self.results())
        self.assertEqual(code, 0, msg=err)
        ids = [f["docID"] for f in self.filings()]
        self.assertEqual(sorted(ids), ["S100AAA1", "S100AAA2", "S100AAA3", "S100AAA4"])
        self.assertNotIn("S100AAA5", out)
        self.assertNotIn("S100AAA6", out)

    def test_doc_types_come_from_config(self):
        config = self.tmp / "xbrl-map.yaml"
        config.write_text('doc_types:\n  "120": annual_report\n', encoding="utf-8")
        server = DayServer({self.DAY: [ok_body(self.results())]})
        code, _, _, _, _ = self.run_main(["--company", "advantest", "--from", self.DAY, "--to", self.DAY,
                                          "--out", str(self.tmp / "o.json")], server, config_path=config)
        self.assertEqual(code, 0)
        self.assertEqual([f["docID"] for f in self.filings()], ["S100AAA1"])

    def test_missing_or_empty_doc_types_in_config_fails(self):
        config = self.tmp / "xbrl-map.yaml"
        config.write_text("doc_types: {}\n", encoding="utf-8")
        code, _, err, server, _ = self.run_main(["--company", "advantest"], config_path=config)
        self.assertEqual(code, 2)
        self.assertEqual(server.requests, [])

    def test_edinet_code_match_and_slug(self):
        code, out, _, _, _ = self.run_day(self.results(), companies=("advantest", "disco"))
        by_id = {f["docID"]: f["slug"] for f in self.filings()}
        self.assertEqual(by_id["S100AAA1"], "advantest")
        self.assertEqual(by_id["S100CCC1"], "disco")
        self.assertNotIn("S100BBB1", by_id)  # 指定していない edinetCode
        self.assertNotIn("S100BBB2", by_id)
        # 1社だけ指定すると、もう1社の書類は出ない
        self.run_day(self.results(), companies=("disco",))
        self.assertEqual([f["docID"] for f in self.filings()], ["S100CCC1"])

    def test_withdrawn_filings_are_excluded_and_counted(self):
        results = [row("S100AAA1", "E01950", "120"),
                   row("S100AAA7", "E01950", "120", withdrawalStatus="1"),
                   row("S100AAA8", "E01950", "160", withdrawalStatus="2"),
                   row("S100BBB9", "E99999", "120", withdrawalStatus="1")]  # 対象外の企業は数えない
        code, out, _, _, _ = self.run_day(results)
        self.assertEqual([f["docID"] for f in self.filings()], ["S100AAA1"])
        self.assertNotIn("S100AAA7", out)
        self.assertIn("取り下げ（除外）2件", out)
        self.assertEqual(json.loads((self.tmp / "o.json").read_text(encoding="utf-8"))["withdrawn_count"], 2)

    def test_withdrawal_status_as_number_zero_is_not_withdrawn(self):
        self.run_day([row("S100AAA1", "E01950", "120", withdrawalStatus=0)])
        self.assertEqual(len(self.filings()), 1)

    def test_json_keeps_api_field_names_and_adds_slug(self):
        self.run_day([row("S100AAA1", "E01950", "120")])
        data = json.loads((self.tmp / "o.json").read_text(encoding="utf-8"))
        filing = data["filings"][0]
        self.assertEqual(filing, {
            "slug": "advantest", "docID": "S100AAA1", "edinetCode": "E01950", "docTypeCode": "120",
            "periodStart": "2025-04-01", "periodEnd": "2026-03-31", "submitDateTime": "2026-06-20 15:00",
            "docDescription": "有価証券報告書", "withdrawalStatus": "0", "docInfoEditStatus": "0"})
        self.assertNotIn("fiscal_period_end", json.dumps(data))  # 変換はしない
        self.assertEqual(data["parameters"]["companies"], ["advantest"])
        self.assertEqual(data["parameters"]["api_requests"], 1)

    def test_table_has_slug_kind_doc_id_period_and_submit_time(self):
        code, out, _, _, _ = self.run_day([row("S100AAA2", "E01950", "130")])
        line = [ln for ln in out.splitlines() if "S100AAA2" in ln][0]
        for text in ("advantest", "訂正有価証券報告書", "S100AAA2", "2025-04-01〜2026-03-31", "2026-06-20 15:00"):
            self.assertIn(text, line)
        self.assertIn("該当 1件", out)

    def test_no_results_key_and_empty_results(self):
        for body in (ok_body(None), ok_body([])):
            server = DayServer({self.DAY: [body]})
            code, out, _, _, _ = self.run_main(["--company", "advantest", "--from", self.DAY, "--to", self.DAY], server)
            self.assertEqual(code, 0)
            self.assertIn("該当する書類はない", out)

    def test_rows_are_sorted_by_submit_time(self):
        results = [row("S100AAA3", "E01950", "160", submitDateTime="2026-11-13 15:00"),
                   row("S100AAA1", "E01950", "120", submitDateTime="2026-06-20 09:00")]
        self.run_day(results)
        self.assertEqual([f["docID"] for f in self.filings()], ["S100AAA1", "S100AAA3"])


class CompanyTest(Base):
    def test_unknown_slug_fails_without_request(self):
        code, out, err, server, _ = self.run_main(["--company", "not-in-master"])
        self.assertEqual(code, 2)
        self.assertIn("企業マスタにない slug: not-in-master", err)
        self.assertEqual(server.requests, [])

    def test_unknown_slug_among_valid_ones_fails(self):
        code, _, err, server, _ = self.run_main(["--company", "advantest", "--company", "typo"])
        self.assertEqual(code, 2)
        self.assertEqual(server.requests, [])

    def test_slug_with_path_characters_is_rejected(self):
        for slug in ("../advantest", "advantest/../x", "Advantest", "a b", ""):
            code, _, err, server, _ = self.run_main(["--company", slug])
            self.assertEqual(code, 2, msg=slug)
            self.assertEqual(server.requests, [])

    def test_company_without_edinet_code_fails(self):
        code, _, err, server, _ = self.run_main(["--company", "no-edinet"])
        self.assertEqual(code, 2)
        self.assertIn("edinet_code", err)
        self.assertEqual(server.requests, [])

    def test_multiple_companies_and_duplicates(self):
        code, out, _, _, _ = self.run_main(["--company", "advantest", "--company", "disco", "--company", "advantest"])
        self.assertEqual(code, 0)
        self.assertIn("企業: advantest, disco", out)

    def test_company_is_required(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            lf.parse_args([])
        self.assertEqual(raised.exception.code, 2)

    def test_real_company_master_has_edinet_code_for_advantest(self):
        codes = lf.load_companies(["advantest"], lf.COMPANIES_DIR)
        self.assertEqual(codes, {"E01950": "advantest"})


class RetryAndIntervalTest(Base):
    def test_429_is_retried_with_widening_intervals_then_succeeds(self):
        day = "2026-10-05"
        steps = [http_error_for(429), {"StatusCode": 429, "message": "Rate limit"}, ok_body([row("S100AAA1", "E01950", "120")])]
        clock = Clock()
        server = DayServer({day: steps}, clock)
        code, out, err, _, clock = self.run_main(["--company", "advantest", "--from", day, "--to", day], server, clock=clock)
        self.assertEqual(code, 0, msg=err)
        self.assertEqual(len(server.requests), 3)
        self.assertEqual(clock.sleeps, [30, 60])  # 間隔を広げる
        self.assertIn("S100AAA1", out)

    def test_429_gives_up_after_three_retries(self):
        day = "2026-10-05"
        clock = Clock()
        server = DayServer({day: [http_error_for(429)]}, clock)
        code, _, err, _, clock = self.run_main(["--company", "advantest", "--from", day, "--to", day], server, clock=clock)
        self.assertEqual(code, 1)
        self.assertEqual(len(server.requests), 4)  # 最初の1回 + 再試行3回
        self.assertEqual(clock.sleeps, [30, 60, 120])
        self.assertIn("アクセスが多すぎる", err)

    def test_calls_are_at_least_one_second_apart(self):
        clock = Clock()
        server = DayServer(clock=clock)
        self.run_main(["--company", "advantest", "--from", "2026-10-05", "--to", "2026-10-09"], server, clock=clock, now=LATER)
        times = [t for _, _, t in server.requests]
        self.assertEqual(len(times), 5)
        gaps = [b - a for a, b in zip(times, times[1:])]
        self.assertTrue(all(g >= 1.0 for g in gaps), msg=gaps)
        self.assertEqual(clock.sleeps, [1.0] * 4)

    def test_timeout_is_30_seconds(self):
        server = DayServer()
        self.run_main(["--company", "advantest", "--from", "2026-10-05", "--to", "2026-10-06"], server)
        self.assertEqual(server.timeouts, [30, 30])

    def test_auth_error_fails_without_retry(self):
        day = "2026-10-05"
        server = DayServer({day: [{"StatusCode": 401, "message": "Access denied due to invalid subscription key."}]})
        code, _, err, _, _ = self.run_main(["--company", "advantest", "--from", day, "--to", day], server)
        self.assertEqual(code, 1)
        self.assertEqual(len(server.requests), 1)
        self.assertIn("認証に失敗", err)

    def test_failure_on_a_later_day_stops_and_writes_no_file(self):
        out = self.tmp / "o.json"
        server = DayServer({"2026-10-06": [{"metadata": {"status": "500", "message": "x"}}]})
        code, _, err, _, _ = self.run_main(
            ["--company", "advantest", "--from", "2026-10-05", "--to", "2026-10-07", "--out", str(out)], server,
            now=LATER)
        self.assertEqual(code, 1)
        self.assertEqual(server.days, ["2026-10-05", "2026-10-06"])
        self.assertFalse(out.exists())


class SecretTest(Base):
    def leaking_errors(self):
        url = f"https://api.edinet-fsa.go.jp/api/v2/documents.json?date=2026-10-05&type=2&Subscription-Key={KEY}"
        return [urllib.error.URLError(f"failed {url}"), OSError(f"cannot connect {url}"),
                ValueError(f"unexpected {url.replace(KEY, fk.ENCODED_KEY)}"), RuntimeError(f"key={KEY}")]

    def test_key_never_appears_in_output_or_json(self):
        out_file = self.tmp / "o.json"
        for error in self.leaking_errors():
            server = DayServer({"2026-10-05": [error]})
            code, out, err, _, _ = self.run_main(
                ["--company", "advantest", "--from", "2026-10-05", "--to", "2026-10-05", "--out", str(out_file)], server)
            self.assertEqual(code, 1, msg=repr(error))
            fk.assert_no_key(self, out, err)
            self.assertNotIn("Traceback", err)
            self.assertFalse(out_file.exists())
        # 成功のときも、標準出力とJSONにキーがない
        server = DayServer({"2026-10-05": [ok_body([row("S100AAA1", "E01950", "120")])]})
        code, out, err, _, _ = self.run_main(
            ["--company", "advantest", "--from", "2026-10-05", "--to", "2026-10-05", "--out", str(out_file)], server)
        self.assertEqual(code, 0)
        fk.assert_no_key(self, out, err, out_file.read_text(encoding="utf-8"))

    def test_server_message_with_key_is_masked(self):
        body = {"StatusCode": 400, "message": f"bad request Subscription-Key={KEY} and {KEY}"}
        code, out, err, _, _ = self.run_main(
            ["--company", "advantest", "--from", "2026-10-05", "--to", "2026-10-05"],
            DayServer({"2026-10-05": [body]}))
        self.assertEqual(code, 1)
        fk.assert_no_key(self, out, err)

    def test_missing_key(self):
        code, out, err, server, _ = self.run_main(["--company", "advantest"], env={})
        self.assertEqual(code, 2)
        self.assertIn("EDINET_API_KEY", err)
        self.assertEqual(server.requests, [])

    def test_key_cannot_be_passed_as_argument(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            lf.parse_args(["--company", "advantest", "--key", KEY])


class OutputFileTest(Base):
    def test_nothing_is_written_without_out(self):
        cwd = os.getcwd()
        work = self.tmp / "work"
        work.mkdir()
        os.chdir(work)
        try:
            self.run_main(["--company", "advantest", "--from", "2026-10-05", "--to", "2026-10-06"],
                          DayServer({"2026-10-05": [ok_body([row("S100AAA1", "E01950", "120")])]}))
            self.assertEqual(os.listdir(work), [])
        finally:
            os.chdir(cwd)

    def test_out_under_data_auto_is_refused(self):
        target = lf.REPO_ROOT / "data" / "auto" / "result.json"
        for path in (target, lf.REPO_ROOT / "data" / "auto" / "sub" / "r.json"):
            code, _, err, server, _ = self.run_main(["--company", "advantest", "--out", str(path)])
            self.assertEqual(code, 2)
            self.assertIn("data/auto/", err)
            self.assertEqual(server.requests, [])
        self.assertFalse(target.exists())

    def test_out_with_missing_folder_or_directory_is_refused(self):
        for path in (self.tmp / "nope" / "o.json", self.tmp):
            code, _, _, server, _ = self.run_main(["--company", "advantest", "--out", str(path)])
            self.assertEqual(code, 2, msg=str(path))
            self.assertEqual(server.requests, [])

    def test_out_is_utf8_json_with_newline(self):
        out = self.tmp / "o.json"
        self.run_main(["--company", "advantest", "--from", "2026-10-05", "--to", "2026-10-05", "--out", str(out)],
                      DayServer({"2026-10-05": [ok_body([row("S100AAA1", "E01950", "120")])]}))
        text = out.read_text(encoding="utf-8")
        self.assertTrue(text.endswith("\n"))
        self.assertIn("有価証券報告書", text)  # ensure_ascii=False
        self.assertEqual(json.loads(text)["parameters"]["from"], "2026-10-05")


if __name__ == "__main__":
    unittest.main()

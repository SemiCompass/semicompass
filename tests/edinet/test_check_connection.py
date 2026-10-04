import contextlib
import importlib.util
import io
import json
import os
import socket
import tempfile
import traceback
import unittest
import urllib.error
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "edinet" / "check_connection.py"
spec = importlib.util.spec_from_file_location("check_connection", MODULE_PATH)
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)

# キーは、URLに入れると形が変わる文字（+ / =）を含める
KEY = "SECRET+key/0123=ABCDEF"
SUCCESS = {
    "metadata": {
        "title": "提出された書類を把握するためのAPI",
        "parameter": {"date": "2026-10-03", "type": "1"},
        "resultset": {"count": 123},
        "processDateTime": "2026-10-04 13:01",
        "status": "200",
        "message": "OK",
    }
}


class FakeResponse:
    def __init__(self, body, status=200):
        self._raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.status = status

    def read(self):
        return self._raw

    def getcode(self):
        return self.status

    def close(self):
        pass


def http_error(request, code, body=None, headers=None):
    """HTTPエラー。URL（キー入り）を持つ本物の例外と同じ形にする。"""
    raw = body if isinstance(body, bytes) else json.dumps(body or {}).encode("utf-8")
    message = f"HTTP Error {code}"
    return urllib.error.HTTPError(
        request.full_url, code, message, headers or {}, io.BytesIO(raw)
    )


class Server:
    """open_url の模擬。応答を順に返し、呼び出しを記録する。"""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.requests = []
        self.timeouts = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        self.timeouts.append(timeout)
        step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        if callable(step):
            return step(request)
        return step


def run_main(argv, server, *, env=None, sleeps=None):
    out, err = io.StringIO(), io.StringIO()
    environ = {cc.ENV_KEY: KEY} if env is None else env
    sleeps = [] if sleeps is None else sleeps
    with mock.patch.dict(os.environ, environ, clear=True), contextlib.redirect_stdout(
        out
    ), contextlib.redirect_stderr(err):
        code = cc.main(argv, open_url=server, sleep=sleeps.append)
    return code, out.getvalue(), err.getvalue()


def assert_no_key(testcase, *texts):
    for text in texts:
        for form in (KEY, "SECRET%2Bkey%2F0123%3DABCDEF", "SECRET+key/0123=ABCDEF"):
            testcase.assertNotIn(form, text)
        testcase.assertNotIn("Subscription-Key=SECRET", text)


class SuccessTest(unittest.TestCase):
    def test_prints_count_process_time_and_status(self):
        server = Server(FakeResponse(SUCCESS))
        code, out, err = run_main(["--date", "2026-10-03"], server)
        self.assertEqual(code, 0)
        self.assertIn("件数: 123", out)
        self.assertIn("更新日時: 2026-10-04 13:01", out)
        self.assertIn("ステータス: 200", out)
        self.assertEqual(err, "")
        assert_no_key(self, out, err)

    def test_request_has_expected_url_and_timeout(self):
        server = Server(FakeResponse(SUCCESS))
        run_main(["--date", "2026-10-03"], server)
        self.assertEqual(len(server.requests), 1)
        url = urlparse(server.requests[0].full_url)
        self.assertEqual((url.scheme, url.netloc, url.path), ("https", "api.edinet-fsa.go.jp", "/api/v2/documents.json"))
        query = parse_qs(url.query)
        self.assertEqual(query["date"], ["2026-10-03"])
        self.assertEqual(query["type"], ["1"])
        self.assertEqual(query["Subscription-Key"], [KEY])  # 送るのは正しいキー（出力には出さない）
        self.assertEqual(server.timeouts, [30])

    def test_default_date_is_yesterday_in_japan(self):
        # 2026-10-03 16:00 UTC は、日本時間では 10-04 01:00。前日は 10-03
        now = datetime(2026, 10, 3, 16, 0, tzinfo=timezone.utc)
        self.assertEqual(cc.default_date(now), date(2026, 10, 3))
        now = datetime(2026, 10, 3, 14, 59, tzinfo=timezone.utc)  # 日本時間 10-03 23:59
        self.assertEqual(cc.default_date(now), date(2026, 10, 2))

    def test_main_uses_default_date_when_omitted(self):
        server = Server(FakeResponse(SUCCESS))
        with mock.patch.object(cc, "default_date", return_value=date(2026, 1, 2)):
            run_main([], server)
        self.assertEqual(parse_qs(urlparse(server.requests[0].full_url).query)["date"], ["2026-01-02"])


class FailureStatusTest(unittest.TestCase):
    def test_401_in_json_with_http_200(self):
        body = {"StatusCode": 401, "message": "Access denied due to invalid subscription key."}
        server = Server(FakeResponse(body, status=200))
        code, out, err = run_main(["--date", "2026-10-03"], server)
        self.assertEqual(code, 1)
        self.assertIn("認証に失敗", err)
        self.assertEqual(out, "")
        self.assertEqual(len(server.requests), 1)  # 401は再試行しない
        assert_no_key(self, out, err)

    def test_401_as_http_status(self):
        server = Server(lambda request: (_ for _ in ()).throw(http_error(request, 401, {"StatusCode": 401, "message": "denied"})))
        code, out, err = run_main(["--date", "2026-10-03"], server)
        self.assertEqual(code, 1)
        self.assertIn("認証に失敗", err)
        assert_no_key(self, out, err)

    def test_metadata_status_not_200(self):
        body = {"metadata": {"status": "404", "message": "Not Found"}}
        code, out, err = run_main(["--date", "2026-10-03"], Server(FakeResponse(body)))
        self.assertEqual(code, 1)
        self.assertIn("404", err)
        self.assertEqual(out, "")

    def test_http_200_without_status_is_not_success(self):
        code, out, err = run_main(["--date", "2026-10-03"], Server(FakeResponse({"metadata": {}})))
        self.assertEqual(code, 1)
        self.assertEqual(out, "")

    def test_non_json_response(self):
        code, out, err = run_main(["--date", "2026-10-03"], Server(FakeResponse(b"<html>oops</html>")))
        self.assertEqual(code, 1)
        self.assertIn("JSON", err)
        self.assertNotIn("oops", err)

    def test_500_is_reported_as_possible_outage_without_retry(self):
        server = Server(lambda request: (_ for _ in ()).throw(http_error(request, 500, b"Internal Server Error")))
        sleeps = []
        code, out, err = run_main(["--date", "2026-10-03"], server, sleeps=sleeps)
        self.assertEqual(code, 1)
        self.assertIn("停止している可能性", err)
        self.assertEqual(len(server.requests), 1)
        self.assertEqual(sleeps, [])
        assert_no_key(self, out, err)

    def test_500_in_json(self):
        body = {"StatusCode": 500, "message": "Unexpected error."}
        code, _, err = run_main(["--date", "2026-10-03"], Server(FakeResponse(body)))
        self.assertEqual(code, 1)
        self.assertIn("停止している可能性", err)


class RetryTest(unittest.TestCase):
    def too_many(self, request):
        raise http_error(request, 429, {"StatusCode": 429, "message": "Rate limit is exceeded."})

    def test_retries_up_to_three_times_then_fails(self):
        server = Server(self.too_many)
        sleeps = []
        code, out, err = run_main(["--date", "2026-10-03"], server, sleeps=sleeps)
        self.assertEqual(code, 1)
        self.assertEqual(len(server.requests), 4)  # 最初の1回 + 再試行3回
        self.assertEqual(len(sleeps), 3)
        self.assertEqual(sleeps, sorted(sleeps))  # 間隔は広がる
        self.assertTrue(all(wait >= 30 for wait in sleeps))  # 十分に間隔を空ける
        self.assertIn("アクセスが多すぎる", err)
        assert_no_key(self, out, err)

    def test_succeeds_after_retry(self):
        server = Server(self.too_many, self.too_many, FakeResponse(SUCCESS))
        sleeps = []
        code, out, _ = run_main(["--date", "2026-10-03"], server, sleeps=sleeps)
        self.assertEqual(code, 0)
        self.assertEqual(len(server.requests), 3)
        self.assertEqual(len(sleeps), 2)
        self.assertIn("件数: 123", out)

    def test_429_in_json_with_http_200_is_retried(self):
        body = {"StatusCode": 429, "message": "Rate limit is exceeded."}
        server = Server(FakeResponse(body), FakeResponse(SUCCESS))
        sleeps = []
        code, _, _ = run_main(["--date", "2026-10-03"], server, sleeps=sleeps)
        self.assertEqual(code, 0)
        self.assertEqual(len(sleeps), 1)

    def test_retry_after_header_is_respected_and_capped(self):
        def limited(request):
            raise http_error(request, 429, {}, headers={"Retry-After": "90"})

        sleeps = []
        run_main(["--date", "2026-10-03"], Server(limited), sleeps=sleeps)
        self.assertEqual(sleeps[0], 90)
        self.assertLessEqual(max(sleeps), cc.RETRY_MAX_SECONDS)
        self.assertEqual(cc._retry_wait(0, "99999"), cc.RETRY_MAX_SECONDS)


class ConfigTest(unittest.TestCase):
    def test_missing_env_var(self):
        server = Server(FakeResponse(SUCCESS))
        code, out, err = run_main(["--date", "2026-10-03"], server, env={})
        self.assertEqual(code, 2)
        self.assertIn("EDINET_API_KEY", err)
        self.assertEqual(server.requests, [])  # 接続しない

    def test_blank_env_var(self):
        server = Server(FakeResponse(SUCCESS))
        code, _, _ = run_main(["--date", "2026-10-03"], server, env={cc.ENV_KEY: "  "})
        self.assertEqual(code, 2)
        self.assertEqual(server.requests, [])

    def test_invalid_date_is_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            cc.parse_args(["--date", "2026/10/03"])
        self.assertEqual(raised.exception.code, 2)

    def test_key_cannot_be_passed_as_argument(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cc.parse_args(["--key", KEY])


class TimeoutTest(unittest.TestCase):
    def test_timeout_is_30_seconds(self):
        self.assertEqual(cc.TIMEOUT_SECONDS, 30)

    def test_timeout_error_is_reported(self):
        for error in (TimeoutError("timed out"), socket.timeout("timed out"), urllib.error.URLError(TimeoutError("timed out"))):
            def raise_timeout(request, error=error):
                raise error

            code, out, err = run_main(["--date", "2026-10-03"], Server(raise_timeout))
            self.assertEqual(code, 1)
            self.assertIn("タイムアウト", err)
            self.assertIn("30秒", err)
            assert_no_key(self, out, err)


class SecretLeakTest(unittest.TestCase):
    """キーとキー入りのURLを、出力、エラー文、例外に出さない。"""

    def leaking_errors(self):
        url = f"https://api.edinet-fsa.go.jp/api/v2/documents.json?date=2026-10-03&type=1&Subscription-Key={KEY}"
        encoded = "SECRET%2Bkey%2F0123%3DABCDEF"
        return [
            urllib.error.URLError(f"failed to reach {url}"),
            urllib.error.URLError(OSError(f"connection reset for {url}")),
            OSError(f"cannot connect: {url}"),
            ConnectionResetError(f"reset {url.replace(KEY, encoded)}"),
            ValueError(f"unexpected: {url}"),
            RuntimeError(f"key={KEY}"),
        ]

    def test_main_never_prints_key_for_any_exception(self):
        for error in self.leaking_errors():
            def raise_error(request, error=error):
                raise error

            code, out, err = run_main(["--date", "2026-10-03"], Server(raise_error))
            self.assertEqual(code, 1, msg=repr(error))
            assert_no_key(self, out, err)
            self.assertNotIn("Traceback", err)
            self.assertIn("error:", err)

    def test_raised_exception_and_traceback_do_not_contain_key(self):
        for error in self.leaking_errors():
            def raise_error(request, error=error):
                raise error

            with self.assertRaises(cc.EdinetError) as raised:
                cc.fetch_document_list(date(2026, 10, 3), KEY, open_url=Server(raise_error), sleep=lambda s: None)
            exception = raised.exception
            text = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
            assert_no_key(self, str(exception), repr(exception), text)
            self.assertIsNone(exception.__cause__)  # キーを含む元の例外を引き継がない
            self.assertTrue(exception.__suppress_context__)

    def test_http_error_message_with_key_is_masked(self):
        body = {"StatusCode": 400, "message": f"bad request: Subscription-Key={KEY} and {KEY}"}
        code, out, err = run_main(["--date", "2026-10-03"], Server(FakeResponse(body)))
        self.assertEqual(code, 1)
        assert_no_key(self, out, err)
        self.assertIn("***", err)

    def test_redact(self):
        self.assertEqual(cc.redact("a Subscription-Key=abc123&x=1 b"), "a Subscription-Key=***&x=1 b")
        self.assertEqual(cc.redact(f"k={KEY}", KEY), "k=***")
        self.assertEqual(cc.redact("k=SECRET%2Bkey%2F0123%3DABCDEF", KEY), "k=***")
        self.assertEqual(cc.redact("k=SECRET+key/0123=ABCDEF", KEY), "k=***")
        self.assertEqual(cc.redact("no secret here", KEY), "no secret here")

    def test_no_redirect_is_followed(self):
        # リダイレクトは追わない（キー入りのURLを別の送信先へ送らない）
        handler = cc._NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, "Found", {}, "https://example.com/"))


class NoFileWriteTest(unittest.TestCase):
    def test_no_files_are_written(self):
        with tempfile.TemporaryDirectory() as directory:
            cwd = os.getcwd()
            os.chdir(directory)
            try:
                run_main(["--date", "2026-10-03"], Server(FakeResponse(SUCCESS)))
                run_main(["--date", "2026-10-03"], Server(FakeResponse({"StatusCode": 401, "message": "x"})))
                self.assertEqual(os.listdir(directory), [])
            finally:
                os.chdir(cwd)

    def test_script_source_has_no_file_writes(self):
        import ast

        source = MODULE_PATH.read_text(encoding="utf-8")
        forbidden_methods = {"write_text", "write_bytes", "mkdir", "touch", "write", "writelines", "unlink", "rename"}
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call):
                func = node.func
                self.assertFalse(isinstance(func, ast.Name) and func.id == "open", msg="open() を呼んでいる")
                self.assertFalse(
                    isinstance(func, ast.Attribute) and func.attr in forbidden_methods,
                    msg=f"{getattr(func, 'attr', '')} を呼んでいる",
                )
        self.assertNotIn("data/auto", source)


if __name__ == "__main__":
    unittest.main()

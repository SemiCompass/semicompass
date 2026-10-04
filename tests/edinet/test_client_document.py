import json
import unittest
import urllib.error
from datetime import date
from urllib.parse import parse_qs, urlparse

import edinet_fakes as fk
from edinet_fakes import KEY, Clock, FakeResponse, http_error

client = fk.client
ZIP = b"PK\x03\x04dummy-zip-bytes"


class DocServer:
    """書類取得API（documents/{docID}?type=5）の模擬。"""

    def __init__(self, *steps, clock=None):
        self.steps = list(steps)
        self.requests = []
        self.clock = clock

    def __call__(self, request, timeout):
        url = urlparse(request.full_url)
        self.requests.append((url.netloc, url.path, parse_qs(url.query), self.clock.now if self.clock else None, request.headers))
        step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        if isinstance(step, Exception):
            raise step
        if callable(step):
            return step(request)
        return step


def make(server, clock=None, **kwargs):
    clock = clock or server.clock or Clock()
    return client.EdinetClient(KEY, open_url=server, sleep=clock.sleep, monotonic=clock.monotonic, **kwargs), clock


class GetDocumentTest(unittest.TestCase):
    def test_returns_zip_bytes_and_sends_type_5(self):
        server = DocServer(FakeResponse(ZIP))
        edinet, _ = make(server)
        self.assertEqual(edinet.get_document("S100AAA1"), ZIP)
        host, path, query, _, headers = server.requests[0]
        self.assertEqual((host, path), ("api.edinet-fsa.go.jp", "/api/v2/documents/S100AAA1"))
        self.assertEqual(query["type"], ["5"])
        self.assertEqual(query["Subscription-Key"], [KEY])  # 送るのは正しいキー（出力には出さない）

    def test_json_error_with_http_200_is_a_failure(self):
        for body, expect in (({"metadata": {"status": "404", "message": "Not Found"}}, "404"),
                             ({"StatusCode": 401, "message": "Access denied"}, "認証に失敗")):
            edinet, _ = make(DocServer(FakeResponse(body)))
            with self.assertRaises(client.EdinetError) as raised:
                edinet.get_document("S100AAA1")
            self.assertIn(expect, str(raised.exception))

    def test_json_success_marker_without_zip_is_not_success(self):
        edinet, _ = make(DocServer(FakeResponse({"metadata": {"status": "200", "message": "OK"}})))
        with self.assertRaises(client.EdinetError) as raised:
            edinet.get_document("S100AAA1")
        self.assertIn("ZIPではなくJSON", str(raised.exception))

    def test_neither_zip_nor_json(self):
        edinet, _ = make(DocServer(FakeResponse(b"<html>oops</html>")))
        with self.assertRaises(client.EdinetError) as raised:
            edinet.get_document("S100AAA1")
        self.assertIn("ZIPでもJSONでもなかった", str(raised.exception))
        self.assertNotIn("oops", str(raised.exception))

    def test_http_error_status_is_used_when_body_is_not_json(self):
        def raiser(request):
            raise urllib.error.HTTPError(request.full_url, 500, "x", {}, None)
        edinet, _ = make(DocServer(raiser))
        with self.assertRaises(client.EdinetError) as raised:
            edinet.get_document("S100AAA1")
        self.assertIn("停止している可能性", str(raised.exception))

    def test_429_is_retried_up_to_three_times(self):
        def limited(request):
            raise http_error(request, 429)
        clock = Clock()
        server = DocServer(limited, clock=clock)
        edinet, _ = make(server, clock)
        with self.assertRaises(client.EdinetError):
            edinet.get_document("S100AAA1")
        self.assertEqual(len(server.requests), 4)
        self.assertEqual(clock.sleeps, [30, 60, 120])

    def test_429_in_json_with_http_200_then_success(self):
        clock = Clock()
        server = DocServer(FakeResponse({"StatusCode": 429, "message": "x"}), FakeResponse(ZIP), clock=clock)
        edinet, _ = make(server, clock)
        self.assertEqual(edinet.get_document("S100AAA1"), ZIP)
        self.assertEqual(clock.sleeps, [30])

    def test_calls_share_the_one_second_interval_with_the_list_api(self):
        clock = Clock()
        server = DocServer(FakeResponse(ZIP), clock=clock)
        edinet, _ = make(server, clock)
        edinet.get_document("S100AAA1")
        edinet.get_document("S100AAA2")
        edinet.get_document("S100AAA3")
        self.assertEqual(clock.sleeps, [1.0, 1.0])
        self.assertEqual(edinet.request_count, 3)

    def test_max_requests_applies(self):
        edinet, _ = make(DocServer(FakeResponse(ZIP)), max_requests=1)
        edinet.get_document("S100AAA1")
        with self.assertRaises(client.EdinetError):
            edinet.get_document("S100AAA2")

    def test_response_larger_than_limit_fails(self):
        edinet, _ = make(DocServer(FakeResponse(b"PK" + b"x" * 100)))
        with self.assertRaises(client.EdinetError) as raised:
            edinet.get_document("S100AAA1", max_bytes=50)
        self.assertIn("大きすぎる", str(raised.exception))
        edinet, _ = make(DocServer(FakeResponse(b"PK" + b"x" * 100)))
        self.assertEqual(len(edinet.get_document("S100AAA1", max_bytes=102)), 102)  # ちょうどは通る

    def test_invalid_doc_id_makes_no_request(self):
        server = DocServer(FakeResponse(ZIP))
        edinet, _ = make(server)
        for doc_id in ("../x", "S100AAA1/../x", "s100aaa1", "S100AAA", "S100AAA11", "S100AAA1?type=1", ""):
            with self.assertRaises(client.EdinetError) as raised:
                edinet.get_document(doc_id)
            self.assertEqual(raised.exception.exit_code, 2)
        self.assertEqual(server.requests, [])

    def test_key_is_masked_in_every_failure(self):
        import traceback
        url = f"https://x/?Subscription-Key={KEY}"
        for error in (OSError(url), ValueError(url), RuntimeError(KEY), urllib.error.URLError(url)):
            edinet, _ = make(DocServer(error))
            with self.assertRaises(client.EdinetError) as raised:
                edinet.get_document("S100AAA1")
            exc = raised.exception
            text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            fk.assert_no_key(self, str(exc), repr(exc), text)
            self.assertIsNone(exc.__cause__)

    def test_server_message_with_key_is_masked(self):
        body = {"StatusCode": 400, "message": f"bad Subscription-Key={KEY} {KEY}"}
        edinet, _ = make(DocServer(FakeResponse(body)))
        with self.assertRaises(client.EdinetError) as raised:
            edinet.get_document("S100AAA1")
        fk.assert_no_key(self, str(raised.exception))

    def test_list_api_accept_header_is_unchanged(self):
        seen = []

        def spy(request, timeout):
            seen.append(request.get_header("Accept"))
            return FakeResponse(fk.ok_body([]))
        edinet = client.EdinetClient(KEY, open_url=spy)
        edinet.get_documents(date(2026, 10, 5), 2)
        self.assertEqual(seen, ["application/json"])


if __name__ == "__main__":
    unittest.main()

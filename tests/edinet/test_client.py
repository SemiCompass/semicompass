import unittest
from datetime import date

import edinet_fakes as fk
from edinet_fakes import KEY, Clock, DayServer, http_error, ok_body, row

client = fk.client
D = date(2026, 10, 5)


def make(server, clock=None, **kwargs):
    clock = clock or server.clock or Clock()
    return client.EdinetClient(KEY, open_url=server, sleep=clock.sleep, monotonic=clock.monotonic, **kwargs), clock


class ClientTest(unittest.TestCase):
    def test_returns_whole_body_with_results(self):
        server = DayServer({"2026-10-05": [ok_body([row("S100AAA1", "E01950", "120")])]})
        edinet, _ = make(server)
        body = edinet.get_documents(D, 2)
        self.assertEqual(body["metadata"]["status"], "200")
        self.assertEqual(body["results"][0]["docID"], "S100AAA1")

    def test_type_parameter_is_sent(self):
        server = DayServer()
        edinet, _ = make(server)
        edinet.get_documents(D, 1)
        edinet.get_documents(D, 2)
        self.assertEqual([t for _, t, _ in server.requests], ["1", "2"])

    def test_first_call_does_not_wait_and_later_calls_are_one_second_apart(self):
        clock = Clock()
        server = DayServer(clock=clock)
        edinet, _ = make(server, clock)
        for _ in range(3):
            edinet.get_documents(D, 2)
        self.assertEqual(clock.sleeps, [1.0, 1.0])
        times = [t for _, _, t in server.requests]
        self.assertTrue(all(b - a >= 1.0 for a, b in zip(times, times[1:])))

    def test_min_interval_can_be_longer_and_already_elapsed_time_counts(self):
        clock = Clock()
        server = DayServer(clock=clock)
        edinet, _ = make(server, clock, min_interval=2.5)
        edinet.get_documents(D, 2)
        clock.now += 1.0  # 1秒たってから、次の呼び出し
        edinet.get_documents(D, 2)
        self.assertEqual(clock.sleeps, [1.5])

    def test_retry_wait_replaces_the_interval(self):
        clock = Clock()

        def limited(request):
            raise http_error(request, 429)

        server = DayServer({"2026-10-05": [limited, ok_body([])]}, clock)
        edinet, _ = make(server, clock)
        edinet.get_documents(D, 2)
        self.assertEqual(clock.sleeps, [30])  # 再試行の待ちだけ。間隔の1秒は足さない
        self.assertEqual(edinet.request_count, 2)

    def test_429_retries_at_most_three_times(self):
        def limited(request):
            raise http_error(request, 429)
        clock = Clock()
        edinet, _ = make(DayServer({"2026-10-05": [limited]}, clock), clock)
        with self.assertRaises(client.EdinetError):
            edinet.get_documents(D, 2)
        self.assertEqual(edinet.request_count, 4)
        self.assertEqual(clock.sleeps, [30, 60, 120])

    def test_max_requests_counts_every_call(self):
        edinet, _ = make(DayServer(), max_requests=2)
        edinet.get_documents(D, 2)
        edinet.get_documents(D, 2)
        with self.assertRaises(client.EdinetError) as raised:
            edinet.get_documents(D, 2)
        self.assertIn("上限（2回）", str(raised.exception))
        self.assertEqual(edinet.request_count, 2)

    def test_timeout_default_is_30_seconds(self):
        server = DayServer()
        edinet, _ = make(server)
        edinet.get_documents(D, 2)
        self.assertEqual(server.timeouts, [30])
        self.assertEqual(client.TIMEOUT_SECONDS, 30)

    def test_repr_does_not_show_key(self):
        edinet, _ = make(DayServer())
        fk.assert_no_key(self, repr(edinet), str(edinet))
        self.assertIn("***", repr(edinet))

    def test_key_not_in_error_messages_or_exception_chain(self):
        import traceback
        url = f"https://x/?Subscription-Key={KEY}"
        for error in (OSError(url), ValueError(url), RuntimeError(KEY)):
            def raiser(request, error=error):
                raise error
            edinet, _ = make(DayServer({"2026-10-05": [raiser]}))
            with self.assertRaises(client.EdinetError) as raised:
                edinet.get_documents(D, 2)
            exc = raised.exception
            text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            fk.assert_no_key(self, str(exc), repr(exc), text)
            self.assertIsNone(exc.__cause__)

    def test_non_200_metadata_status_and_status_code_fail(self):
        for body in ({"metadata": {"status": "404", "message": "Not Found"}},
                     {"StatusCode": 401, "message": "Access denied"},
                     {"metadata": {}}):
            edinet, _ = make(DayServer({"2026-10-05": [body]}))
            with self.assertRaises(client.EdinetError):
                edinet.get_documents(D, 2)

    def test_check_connection_still_uses_the_same_parts(self):
        import check_connection as cc
        self.assertIs(cc.EdinetError, client.EdinetError)
        self.assertIs(cc.redact, client.redact)
        self.assertEqual(cc.TIMEOUT_SECONDS, 30)


if __name__ == "__main__":
    unittest.main()

"""EDINET関連のテストで使う、HTTPと時計の模擬。"""

import io
import json
import sys
import urllib.error
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "edinet"))

import client  # noqa: E402
import list_filings  # noqa: E402

KEY = "SECRET+key/0123=ABCDEF"  # URLに入れると形が変わる文字（+ / =）を含める
ENCODED_KEY = "SECRET%2Bkey%2F0123%3DABCDEF"


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
    raw = json.dumps(body or {}).encode("utf-8")
    return urllib.error.HTTPError(request.full_url, code, f"HTTP Error {code}", headers or {}, io.BytesIO(raw))


class Clock:
    """sleep で進む、模擬の時計。"""

    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def monotonic(self):
        return self.now


def ok_body(results=None, count=None):
    body = {"metadata": {"title": "提出された書類を把握するためのAPI", "status": "200", "message": "OK",
                         "processDateTime": "2026-10-06 13:01",
                         "resultset": {"count": len(results) if results is not None else 0}}}
    if results is not None:
        body["results"] = results
    return body


def row(doc_id, edinet_code, doc_type, **extra):
    base = {"docID": doc_id, "edinetCode": edinet_code, "docTypeCode": doc_type,
            "periodStart": "2025-04-01", "periodEnd": "2026-03-31",
            "submitDateTime": "2026-06-20 15:00", "docDescription": "有価証券報告書",
            "withdrawalStatus": "0", "docInfoEditStatus": "0"}
    base.update(extra)
    return base


class DayServer:
    """日付ごとに応答を返す、open_url の模擬。呼び出しを記録する。

    responses: {"YYYY-MM-DD": [応答, ...]}。応答は、辞書（JSON）、例外、または request を受ける関数。
    応答の並びの最後を、以降も返す。書いていない日は、結果なしの応答。
    """

    def __init__(self, responses=None, clock=None):
        self.responses = {k: list(v) for k, v in (responses or {}).items()}
        self.clock = clock
        self.requests = []   # (日付, type, 呼び出しの時刻)
        self.timeouts = []

    def __call__(self, request, timeout):
        query = parse_qs(urlparse(request.full_url).query)
        day = query["date"][0]
        self.requests.append((day, query["type"][0], self.clock.now if self.clock else None))
        self.timeouts.append(timeout)
        steps = self.responses.get(day)
        if not steps:
            return FakeResponse(ok_body([]))
        step = steps.pop(0) if len(steps) > 1 else steps[0]
        if isinstance(step, Exception):
            raise step
        if callable(step):
            return step(request)
        return FakeResponse(step)

    @property
    def days(self):
        return [d for d, _, _ in self.requests]


def assert_no_key(testcase, *texts):
    for text in texts:
        for form in (KEY, ENCODED_KEY):
            testcase.assertNotIn(form, text)
        testcase.assertNotIn("Subscription-Key=SECRET", text)

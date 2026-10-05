"""原資料束のテストで使う、合成のCSV・ZIP・HTTP・R2の模擬。実際の書類の文章は使わない。"""

import io
import json
import sys
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "bundle"))
sys.path.insert(0, str(ROOT / "scripts" / "edinet"))
sys.path.insert(0, str(ROOT / "tests" / "edinet"))

from edinet_fakes import KEY, Clock, FakeResponse  # noqa: E402,F401

HEADER = ["要素ID", "項目名", "コンテキストID", "相対年度", "連結・個別", "期間・時点", "ユニットID", "単位", "値"]
CSV_NAME = "XBRL_TO_CSV/jpcrp030000-asr-001_E99999-000_2026-03-31_01_2026-06-20.csv"
EDINET_CODE = "E99999"
DOC_ID = "S100TEST"
ELEM_A = "test_cor:AlphaSectionTextBlock"
ELEM_B = "test_cor:BetaSectionTextBlock"
ELEM_C = "test_cor:GammaSectionTextBlock"

# 合成の語。本文が出力に漏れていないかを、この語で確かめる
WORD_A = "ゼータ合成語アルファ"
WORD_B = "イータ合成語ベータ"
HTML_A = f"<p>{WORD_A}　です。</p><ul><li>項目一</li><li>項目二</li></ul>"
HTML_B = f"<div>{WORD_B} &amp; 記号 &lt;と&gt;</div><table><tr><td>見出し</td><td>値</td></tr></table>"


def row(element, label, context, value):
    return [element, label, context, "当期", "連結", "期間", "", "", value]


BASE_ROWS = [
    row("jpdei_cor:EDINETCodeDEI", "EDINETコード", "FilingDateInstant", EDINET_CODE),
    row("jppfs_cor:NetSales", "売上高", "CurrentYearDuration", "1000"),
    row(ELEM_A, "節A（合成）", "FilingDateInstant", HTML_A),
    row(ELEM_B, "節B（合成）", "CurrentYearDuration", HTML_B),
    row("test_cor:NotTextBlockElement", "文章だが対象外", "CurrentYearDuration", "<p>対象外の文章</p>"),
    row(ELEM_C, "節C（空）", "FilingDateInstant", "<p> </p>"),
]


def csv_bytes(rows=BASE_ROWS, header=HEADER):
    def line(cells):
        return "\t".join('"' + c.replace('"', '""') + '"' for c in cells)
    text = "\r\n".join(line(c) for c in [header, *rows]) + "\r\n"
    return b"\xff\xfe" + text.encode("utf-16-le")


def make_zip(rows=BASE_ROWS, name=CSV_NAME):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, csv_bytes(rows))
    return buffer.getvalue()


class DocServer:
    """書類取得API（documents/{docID}）の模擬。ZIPを返す。"""

    def __init__(self, body=None):
        self.body = make_zip() if body is None else body
        self.requests = []

    def __call__(self, request, timeout):
        url = urlparse(request.full_url)
        self.requests.append((url.path, parse_qs(url.query)))
        return FakeResponse(self.body)


class FakeR2:
    """put_object だけを持つ、R2（S3互換）のクライアントの模擬。"""

    def __init__(self, response=None, error=None):
        self.puts = []
        self.response = response if response is not None else {"ResponseMetadata": {"HTTPStatusCode": 200}}
        self.error = error

    def put_object(self, **kwargs):
        if self.error:
            raise self.error
        self.puts.append(kwargs)
        return self.response


def write_auto(directory: Path, slug="testco", filings=None, edinet_code=EDINET_CODE):
    filings = filings if filings is not None else [filing(DOC_ID)]
    (directory / f"{slug}.json").write_text(
        json.dumps({"company": slug, "edinet_code": edinet_code, "filings": filings}), encoding="utf-8")


def filing(doc_id, doc_type="annual_report", status="ingested", period="2026-03", submitted="2026-06-20T13:00:00+09:00"):
    return {"doc_id": doc_id, "doc_type": doc_type, "status": status, "fiscal_period_end": period,
            "submitted_at": submitted, "period_type": "annual"}


R2_ACCOUNT = "0123456789abcdef0123456789abcdef"
R2_ACCESS = "AKIAFAKEACCESSKEY0001"
R2_SECRET = "FAKE+secret/key=0000zzzz"
R2_ENV = {
    "EDINET_API_KEY": KEY,
    "R2_ACCOUNT_ID": R2_ACCOUNT,
    "R2_ACCESS_KEY_ID": R2_ACCESS,
    "R2_SECRET_ACCESS_KEY": R2_SECRET,
    "R2_BUCKET": "semicompass-bundles",
}

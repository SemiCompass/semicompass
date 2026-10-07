"""工程・用語の解説のテストで使う、HTTP・R2・時計・PDFの模擬。実際の資料の文章は使わない（合成の語だけ）。"""

import io
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
for sub in ("bundle", "validate", "draft", "llm", "textcheck", "edinet"):
    sys.path.insert(0, str(ROOT / "scripts" / sub))
sys.path.insert(0, str(ROOT / "tests" / "llm"))

import make_explainer_bundle as meb  # noqa: E402

ENV = {"R2_ACCOUNT_ID": "0123456789abcdef0123456789abcdef", "R2_ACCESS_KEY_ID": "AKIAFAKEACCESSKEY0001",
       "R2_SECRET_ACCESS_KEY": "FAKE+secret/key=0000zzzz", "R2_BUCKET": "semicompass-bundles"}
SECRETS = tuple(ENV.values())
WORD = "ゼータ合成語"  # 資料の本文にだけある語。出力のどこにも出ない
TARGET = "架空研磨"  # 対象の語

APPROVED = "https://a.example.org/page1.html"
APPROVED2 = "https://a.example.org/page2.html"
OTHER_HOST = "https://b.example.net/doc.html"
CANDIDATE = "https://c.example.org/candidate.html"
REJECTED = "https://d.example.org/rejected.html"


def source(url, status="approved", role="primary", kind="web", title="資料", publisher="架空協会"):
    return {"status": status, "role": role, "kind": kind, "publisher": publisher, "title": title, "url": url}


def make_config(path: Path, term_sources, slug="test-term", name="架空研磨", extra=None) -> Path:
    """本物の設定（工程10件、用語30件）に、試験用の用語 test-term を足した設定を、path に書く。"""
    config = yaml.safe_load((ROOT / "config" / "explainer-sources.yaml").read_text(encoding="utf-8"))
    config["terms"][slug] = {"term": name, "sources": term_sources, **(extra or {})}
    path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def html_page(*paragraphs, nav="メニュー項目", footer="フッターの文", extra_head=""):
    body = "".join(f"<p>{p}</p>" for p in paragraphs)
    return (f"<html><head><title>題</title>{extra_head}<script>var x='スクリプトの文';</script></head><body>"
            f"<nav>{nav}</nav><header class='site-header'>ヘッダーの文</header>"
            f"<main>{body}</main><footer>{footer}</footer></body></html>").encode("utf-8")


def ok(body: bytes, content_type="text/html; charset=utf-8", **headers):
    return meb.HttpResponse(200, {"content-type": content_type, **headers}, body)


def redirect(location, status=301):
    return meb.HttpResponse(status, {"location": location}, b"")


ROBOTS_OK = meb.HttpResponse(200, {"content-type": "text/plain"}, b"User-agent: *\nAllow: /\n")


class Clock:
    def __init__(self):
        self.t = 1000.0
        self.sleeps = []

    def monotonic(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += seconds


class FakeTransport:
    """url → 応答（HttpResponse、例外、またはその一覧）。robots.txt は、指定がなければ「すべて可」を返す。呼び出しを記録する。"""

    def __init__(self, responses, clock=None):
        self.responses = dict(responses)
        self.calls = []  # (url, headers)
        self.clock = clock

    def __call__(self, url, headers, timeout, max_bytes):
        self.calls.append((url, headers, self.clock.t if self.clock else None))
        step = self.responses.get(url)
        if step is None and url.endswith("/robots.txt"):
            step = ROBOTS_OK
        if step is None:
            return meb.HttpResponse(404, {}, b"")
        if isinstance(step, list):
            step = step.pop(0) if len(step) > 1 else step[0]
        if isinstance(step, Exception):
            raise step
        return step

    def urls(self):
        return [c[0] for c in self.calls]


class FakeR2:
    def __init__(self, objects=None, error=None):
        self.objects = dict(objects or {})
        self.error = error
        self.puts = []
        self.gets = []

    def put_object(self, Bucket, Key, Body, ContentType=None):  # noqa: N803
        self.puts.append((Bucket, Key, Body))
        self.objects[Key] = Body
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def get_object(self, Bucket, Key):  # noqa: N803
        self.gets.append((Bucket, Key))
        if self.error:
            raise self.error
        if Key not in self.objects:
            raise NoSuchKey()
        return {"Body": io.BytesIO(self.objects[Key])}


class NoSuchKey(Exception):
    response = {"Error": {"Code": "NoSuchKey", "Message": WORD}}


def make_pdf(pages):
    """ASCII の文字列だけを持つ、最小の PDF（1ページ1文字列）。"""
    objects = []
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    font_id = 3 + 2 * len(pages)
    for i, text in enumerate(pages):
        content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
                       f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode())
        objects.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()

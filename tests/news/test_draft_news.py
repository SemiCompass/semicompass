"""ニュース解説の下書き（scripts/news/draft_news.py、fetch_source.py）の単体テスト。AIと通信は模擬。合成の語だけを使う。"""

import copy
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "news"))
sys.path.insert(0, str(ROOT / "tests" / "llm"))

import draft_news  # noqa: E402
import fetch_source  # noqa: E402
from llm_fakes import FakeClient, reply  # noqa: E402

NOW = datetime(2026, 10, 10, 9, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
SOURCE_URL = "https://stats.example.org/release.html"
SOURCE_TEXT = "架空統計機構の発表。" + "世界の半導体の売上は架空の四半期に増えたと機構は伝えた。" * 12


def para(seed: str, n: int) -> str:
    """出典の番号つきの、合成の段落（資料とは、30字以上連続して重ならない）。"""
    base = f"{seed}の説明として、別の言い回しで事実を整理して述べる文章がここに続く。[S1]"
    return (base * 3)[: max(n, len(base))] if n else base


def draft_output(**kw) -> dict:
    out = {
        "slug": "global-chip-sales-record", "title": "架空の世界市場が過去最高になった", "description": "架空の統計機構が、世界の半導体の売上が過去最高になったと公表した。日本の装置企業にも波及しうる。",
        "what_happened": "架空統計機構は2026年10月、世界の半導体の売上が2026年8月までの累計で過去最高になったと公表した。[S1]" + "売上の増加は、複数の用途の需要が同時に伸びたことによる。" * 3,
        "why_important": "過去の水準と比べると、今回の累計は大きな節目にあたる。[S1]" + "市場の拡大は、装置や材料への投資の判断に影響する。" * 4,
        "position": "試験の工程を担うアドバンテストなど、検査に関わる企業の事業にも関係する。[S1]" + "最終検査（テスト）の需要は、出荷の増加に連動する。" * 3,
        "source_title": "架空統計機構の発表", "source_publisher": "架空統計機構", "source_published_on": "2026-10-08", "reporting": "primary",
        "companies": ["advantest"], "unlisted_companies": [], "processes": ["final-test"],
        "x_text": "世界の半導体の売上が過去最高に。検査の工程とアドバンテストに関わる。", "uncertain": [],
    }
    out.update(kw)
    return out


def candidate(**kw) -> dict:
    c = {"id": "c11", "title": "世界半導体市場が過去最高に", "url": "https://press.example.org/a", "publisher": "架空媒体", "kind": "press",
         "published_on": "2026-10-08", "category": "supply_demand", "overseas": True, "priority_hit": False,
         "score": {"impact": 1, "supply_chain": 2, "novelty": 3, "reliability": 2}, "reporting": "press", "semiconductor_related": True}
    c.update(kw)
    return c


def review(*issues):
    return reply({"issues": list(issues)})


ERR = {"part": "what_happened", "kind": "unsupported", "severity": "error", "note": "資料にない数値がある"}
WARN = {"part": "title", "kind": "tone", "severity": "warning", "note": "空疎な言葉がある"}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.out = self.tmp / "out"
        self.scored = self.tmp / "scored.json"
        self.scored.write_text(json.dumps({"ranked": [candidate()], "observed": []}, ensure_ascii=False), encoding="utf-8")
        self.summary = []

    def run_draft(self, *replies, url=SOURCE_URL, cid="c11", fetcher=None, operations=None):
        client = FakeClient(*replies)
        argv = ["--scored", str(self.scored), "--id", cid, "--out-dir", str(self.out), "--ledger-dir", str(self.tmp / "ledger"), "--run-id", "r1"]
        if url:
            argv += ["--url", url]
        kwargs = {}
        if operations:
            kwargs["operations_path"] = operations
        code = draft_news.main(argv, now=lambda: NOW, client_factory=lambda: client,
                               fetcher=fetcher or (lambda u: {"url": u, "title": "架空統計機構の発表", "text": SOURCE_TEXT}), **kwargs)
        return code, client

    def front(self):
        files = list((self.out / "content" / "news").glob("*.md"))
        self.assertEqual(len(files), 1)
        text = files[0].read_text(encoding="utf-8")
        return files[0], yaml.safe_load(text.split("---\n")[1]), text.split("---\n", 2)[2]


class DraftTest(Base):
    def test_success_creates_file_and_pr_body(self):
        code, client = self.run_draft(reply(draft_output()), review())
        self.assertEqual(code, 0)
        path, front, body = self.front()
        self.assertEqual(path.name, "2026-10-global-chip-sales-record.md")
        self.assertFalse(front["draft"])
        self.assertTrue(front["ai_generated"])
        self.assertEqual(front["category"], "supply_demand")
        self.assertTrue(front["overseas"])
        self.assertEqual(front["score"]["reliability"], 3)  # 一次情報
        self.assertEqual(front["source_article"]["url"], SOURCE_URL)
        self.assertTrue(front["x_post"].endswith("https://semicompass.com/news/2026/10/global-chip-sales-record/"))
        self.assertEqual([l for l in body.splitlines() if l.startswith("## ")], ["## " + h for h in draft_news.HEADINGS])
        pr = (self.out / "pr-body.md").read_text(encoding="utf-8")
        self.assertIn("取り込む前に", pr)
        self.assertTrue(list((self.out / "ledger").glob("*.jsonl")))
        # AI へは、資料の区画に元記事を入れる。コメントや候補の見出しは、資料の外
        sent = json.dumps(client.calls[0]["messages"], ensure_ascii=False)
        self.assertIn("【S1 本文】", sent)
        self.assertIn("tagline", sent)  # 企業の一言の説明と工程を渡す（本サイトの見方で企業を選ぶ材料）

    def test_unresolved_review_error_makes_draft_true(self):
        code, _ = self.run_draft(reply(draft_output()), review(ERR), reply(draft_output(title="別の架空の見出しで書き直した")), review(ERR, WARN))
        self.assertEqual(code, 0)
        _, front, _ = self.front()
        self.assertTrue(front["draft"])
        self.assertIn("校閲（AG-13）の指摘が残っている", (self.out / "pr-body.md").read_text(encoding="utf-8"))

    def test_review_error_fixed_by_rewrite(self):
        code, client = self.run_draft(reply(draft_output()), review(ERR), reply(draft_output(title="書き直した架空の見出しである")), review(WARN))
        self.assertEqual(code, 0)
        _, front, _ = self.front()
        self.assertFalse(front["draft"])
        self.assertEqual(front["title"], "書き直した架空の見出しである")

    def test_reprint_triggers_one_rewrite(self):
        copied = draft_output(what_happened="世界の半導体の売上は架空の四半期に増えたと機構は伝えた。世界の半導体の売上は架空の四半期に増えたと機構は伝えた。[S1]" + "売上の増加は、複数の用途の需要が同時に伸びたことによる。" * 2)
        code, client = self.run_draft(reply(copied), reply(draft_output()), review())
        self.assertEqual(code, 0)
        self.assertEqual(len(client.calls), 3)

    def test_invalid_company_twice_fails(self):
        bad = draft_output(companies=["no-such-company"])
        code, _ = self.run_draft(reply(bad), reply(bad))
        self.assertEqual(code, 1)
        self.assertFalse((self.out / "content").exists())

    def test_overseas_requires_companies(self):
        bad = draft_output(companies=[])
        code, _ = self.run_draft(reply(bad), reply(bad))
        self.assertEqual(code, 1)

    def test_press_candidate_without_url_is_refused_without_calling_ai(self):
        code, client = self.run_draft(reply(draft_output()), url=None)
        self.assertEqual(code, 2)
        self.assertEqual(client.calls, [])

    def test_primary_candidate_uses_its_own_url(self):
        self.scored.write_text(json.dumps({"ranked": [candidate(kind="company", url="https://corp.example.org/n1")], "observed": []}, ensure_ascii=False), encoding="utf-8")
        code, _ = self.run_draft(reply(draft_output()), review(), url=None)
        self.assertEqual(code, 0)
        self.assertEqual(self.front()[1]["source_article"]["url"], "https://corp.example.org/n1")

    def test_fetch_failure_exits_2(self):
        def boom(url):
            raise fetch_source.FetchError("取得を断られた、または見つからない（HTTP 403）")
        code, client = self.run_draft(reply(draft_output()), fetcher=boom)
        self.assertEqual(code, 2)
        self.assertEqual(client.calls, [])

    def test_unknown_id_and_bad_id(self):
        self.assertEqual(self.run_draft(reply(draft_output()), cid="c99")[0], 2)
        self.assertEqual(self.run_draft(reply(draft_output()), cid="x1; rm")[0], 2)

    def test_paused_skips(self):
        ops = self.tmp / "operations.yaml"
        data = yaml.safe_load((ROOT / "config" / "operations.yaml").read_text(encoding="utf-8"))
        data["status"] = "paused"
        ops.write_text(yaml.safe_dump(data), encoding="utf-8")
        code, client = self.run_draft(reply(draft_output()), operations=ops)
        self.assertEqual(code, 3)
        self.assertEqual(client.calls, [])


class FetchTest(unittest.TestCase):
    PUBLIC = staticmethod(lambda host, port, **kw: [(2, 1, 6, "", ("93.184.216.34", port))])

    class Resp:
        def __init__(self, body, ctype="text/html; charset=utf-8"):
            self.body, self.headers = body, {"Content-Type": ctype}

        def read(self, n):
            return self.body[:n]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Opener:
        def __init__(self, resp):
            self.resp = resp

        def open(self, request, timeout):
            return self.resp

    def test_html_to_text(self):
        page = ("<html><head><title>架空の発表</title><script>var a=1;</script></head><body><nav>メニュー</nav><article><p>" + "本文の一文である。" * 40 + "</p></article></body></html>").encode()
        doc = fetch_source.fetch_text("https://a.example.org/x", opener=self.Opener(self.Resp(page)), resolver=self.PUBLIC)
        self.assertEqual(doc["title"], "架空の発表")
        self.assertNotIn("var a", doc["text"])
        self.assertNotIn("メニュー", doc["text"])

    def test_refuses_http_and_internal(self):
        with self.assertRaises(fetch_source.FetchError):
            fetch_source.fetch_text("http://a.example.org/x")
        with self.assertRaises(fetch_source.FetchError):
            fetch_source.fetch_text("https://internal.example.org/x", resolver=lambda h, p, **kw: [(2, 1, 6, "", ("169.254.169.254", p))])

    def test_short_page_is_refused(self):
        with self.assertRaises(fetch_source.FetchError):
            fetch_source.fetch_text("https://a.example.org/x", opener=self.Opener(self.Resp("<html><body>JavaScriptを有効にしてください</body></html>".encode())), resolver=self.PUBLIC)


if __name__ == "__main__":
    unittest.main()

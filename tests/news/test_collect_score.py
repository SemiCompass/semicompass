"""ニュース候補の収集（scripts/news/collect.py）と点付け（score.py）の単体テスト。通信とAIは模擬。合成の見出しだけを使う。"""

import json
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "news"))
sys.path.insert(0, str(ROOT / "tests" / "llm"))

import collect  # noqa: E402
import score  # noqa: E402
from llm_fakes import FakeClient, NOW, reply  # noqa: E402

RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>架空の設備投資の発表</title><link>https://a.example.org/1?utm_source=x#top</link><pubDate>Tue, 06 Oct 2026 09:00:00 +0900</pubDate></item>
<item><title>古い発表</title><link>https://a.example.org/old</link><pubDate>Tue, 01 Sep 2026 09:00:00 +0900</pubDate></item>
<item><title>httpのリンク</title><link>http://a.example.org/h</link><pubDate>Tue, 06 Oct 2026 09:00:00 +0900</pubDate></item>
</channel></rss>""".encode()
ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>架空の政策の決定</title><link rel="alternate" href="https://b.example.org/2"/><updated>2026-10-07T01:00:00+09:00</updated></entry>
<entry><title>重複</title><link href="https://a.example.org/1"/><updated>2026-10-07T01:00:00+09:00</updated></entry>
</feed>""".encode()
PAGE = """<html><body><ul><li><span>2026.10.05</span><a href="/topics/3.html">架空協会の統計の公表について</a></li>
<li><a href="/x.html">短い</a></li></ul></body></html>""".encode("utf-8")

CONFIG = {"candidate_limit": 30, "daily_limit": 2, "weekly_max_per_category": 1, "priority_rules": {"investment": "国内の新設"},
          "sources": [
              {"id": "s-rss", "name": "架空企業", "kind": "company", "reliability": "high", "feed_url": "https://a.example.org/rss"},
              {"id": "s-atom", "name": "架空省", "kind": "government", "reliability": "high", "feed_url": "https://b.example.org/atom"},
              {"id": "s-page", "name": "架空協会", "kind": "association", "reliability": "high", "page_url": "https://c.example.org/list"},
              {"id": "s-bad", "name": "壊れた", "kind": "press", "reliability": "medium", "feed_url": "https://d.example.org/rss"},
          ]}
TODAY = date(2026, 10, 7)


def fetcher(url):
    bodies = {"https://a.example.org/rss": RSS, "https://b.example.org/atom": ATOM, "https://c.example.org/list": PAGE}
    if url not in bodies:
        raise ValueError("取得できない")
    return bodies[url]


class CheckSourcesTest(unittest.TestCase):
    def test_reports_feed_page_and_failure(self):
        import check_sources
        import urllib.error

        def fetch(url):
            if url.endswith("bad"):
                raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
            return RSS if url.endswith("rss") else b'<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml"></head></html>'

        self.assertTrue(check_sources.check("https://a.example.org/rss", fetch).startswith("OK  https://a.example.org/rss  フィード  "))
        self.assertIn("HTTP 403", check_sources.check("https://a.example.org/bad", fetch))
        self.assertIn("https://a.example.org/feed.xml", check_sources.check("https://a.example.org/top", fetch))


class CollectTest(unittest.TestCase):
    def run_collect(self, seen=frozenset()):
        return collect.collect(CONFIG, today=TODAY, days=3, seen=set(seen), fetcher=fetcher)

    def test_collects_dedupes_and_orders(self):
        r = self.run_collect()
        urls = [c["url"] for c in r["candidates"]]
        self.assertEqual(urls, ["https://b.example.org/2", "https://a.example.org/1?utm_source=x#top", "https://c.example.org/topics/3.html"])
        self.assertEqual([c["id"] for c in r["candidates"]], ["c01", "c02", "c03"])  # 古い発表、httpのリンク、重複は入らない
        self.assertEqual(r["failed"], [{"source": "s-bad", "reason": "ValueError"}])
        self.assertEqual(r["candidates"][0]["reporting_hint"], "primary")

    def test_seen_urls_are_skipped(self):
        r = self.run_collect({collect.normalize_url("https://a.example.org/1")})
        self.assertNotIn("https://a.example.org/1?utm_source=x#top", [c["url"] for c in r["candidates"]])

    def test_candidate_limit(self):
        config = {**CONFIG, "candidate_limit": 1}
        r = collect.collect(config, today=TODAY, days=3, seen=set(), fetcher=fetcher)
        self.assertEqual(len(r["candidates"]), 1)

    def test_seen_from_content_and_file(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / "2026-10-x.md").write_text("---\nsource_article:\n  url: https://a.example.org/1\n---\n本文\n", encoding="utf-8")
        seen_file = tmp / "seen.txt"
        seen_file.write_text("https://b.example.org/2 2026-10-07\n", encoding="utf-8")
        urls = collect.seen_urls(tmp, [seen_file])
        self.assertEqual(urls, {"https://a.example.org/1", "https://b.example.org/2"})

    def test_page_with_spaced_japanese_dates(self):
        page = ("<dl><dt>2026年10月 9日</dt><dd>リリース</dd><dd><a href='/japanese/topics/2026/1009.pdf'>架空のガイドを公開</a></dd>"
                "<dt>2026年10月 6日</dt><dd>リリース</dd><dd><a href='/japanese/topics/2026/1006.pdf'>架空の賞が決定しました</a></dd></dl>").encode()
        items = collect.parse_page(page, "https://c.example.org/cgi-bin/list.cgi")
        self.assertEqual([(i["published_on"], i["url"]) for i in items],
                         [("2026-10-09", "https://c.example.org/japanese/topics/2026/1009.pdf"),
                          ("2026-10-06", "https://c.example.org/japanese/topics/2026/1006.pdf")])

    def test_page_with_date_inside_link_text(self):
        page = ("<p><a href='/news/event/20261007_001.html'>2026.10.07<b>架空展示会 2026</b>に出展します</a></p>"
                "<ul><li><a href='https://x.example.org/a.pdf'>2026/09/30 投資家の皆様へ 架空の株式処分のお知らせ</a></li></ul>").encode()
        items = collect.parse_page(page, "https://c.example.org/news/")
        self.assertEqual([i["published_on"] for i in items], ["2026-10-07", "2026-09-30"])
        self.assertTrue(items[0]["title"].startswith("架空展示会 2026"))
        self.assertNotIn("2026", items[1]["title"][:5])

    def test_category_labels_at_the_end_are_removed(self):
        page = "<p><a href='/n/1.html'>2026.10.07 架空展示会 2026 会場 架空センター トピックス 製品・サービス IR イベント お知らせ</a></p>".encode()
        items = collect.parse_page(page, "https://c.example.org/news/")
        self.assertEqual(items[0]["title"], "架空展示会 2026 会場 架空センター")

    def test_rejects_non_https_fetch(self):
        with self.assertRaises(ValueError):
            collect.fetch("http://example.org/")


def ag10_item(cid, **kw):
    item = {"id": cid, "semiconductor_related": True, "category": "investment", "impact": 2, "supply_chain": 2, "novelty": 2,
            "reporting": "press", "overseas": False, "priority_hit": False, "listed_companies": [], "reason": "架空の理由である。"}
    item.update(kw)
    return item


class ScoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        result = collect.collect(CONFIG, today=TODAY, days=3, seen=set(), fetcher=fetcher)
        self.data = result
        self.cand = tmp_cand = self.tmp / "candidates.json"
        tmp_cand.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        cfg = self.tmp / "news.yaml"
        import yaml
        cfg.write_text(yaml.safe_dump({**CONFIG}, allow_unicode=True), encoding="utf-8")
        self.cfg = cfg

    def run_score(self, items, extra=()):
        client = FakeClient(reply({"items": items}))
        out = self.tmp / "out"
        code = score.main(["--candidates", str(self.cand), "--out-dir", str(out), "--ledger-dir", str(self.tmp / "ledger"), "--run-id", "r1",
                           "--config", str(self.cfg), "--content-dir", str(self.tmp / "none"), "--companies-dir", str(self.tmp / "none"), *extra],
                          client_factory=lambda: client, now=lambda: NOW)
        return code, out, client

    def test_ranks_and_builds_issue(self):
        code, out, client = self.run_score([
            ag10_item("c01", impact=1, supply_chain=1, novelty=1),
            ag10_item("c02", priority_hit=True, impact=0, supply_chain=0, novelty=0, category="policy"),
            ag10_item("c03", semiconductor_related=False, impact=0, supply_chain=0, novelty=0),
        ])
        self.assertEqual(code, 0)
        scored = json.loads((out / "scored.json").read_text(encoding="utf-8"))
        self.assertEqual([s["id"] for s in scored["ranked"]], ["c02", "c01"])  # 優先の基準に当たるものが先
        self.assertEqual(scored["excluded"], 1)
        c02 = scored["ranked"][0]
        self.assertEqual(c02["score"]["reliability"], 3)  # 政府の情報源は primary
        body = (out / "issue-body.md").read_text(encoding="utf-8")
        self.assertIn("/draft c01 c03", body)
        self.assertIn("★政策・規制", body)
        self.assertIn("☑ 推奨", body)
        self.assertTrue(list((out / "ledger").glob("*.jsonl")))
        # 候補の見出しは「資料」の区画に入る
        sent = json.dumps(client.calls[0]["messages"], ensure_ascii=False)
        self.assertIn("<資料>", sent)
        self.assertIn("架空の政策の決定", sent)

    def test_speculative_press_goes_to_observed(self):
        cands = json.loads(self.cand.read_text(encoding="utf-8"))
        cands["candidates"][0]["kind"] = "press"
        self.cand.write_text(json.dumps(cands, ensure_ascii=False), encoding="utf-8")
        code, out, _ = self.run_score([ag10_item("c01", reporting="speculative"), ag10_item("c02"), ag10_item("c03")])
        scored = json.loads((out / "scored.json").read_text(encoding="utf-8"))
        self.assertEqual([s["id"] for s in scored["observed"]], ["c01"])
        self.assertEqual(scored["observed"][0]["score"]["reliability"], 1)

    def test_weekly_category_cap_pushes_down(self):
        content = self.tmp / "content"
        content.mkdir()
        (content / "2026-10-a.md").write_text("---\npublished_at: '2026-10-06'\ncategory: investment\n---\n", encoding="utf-8")
        cfg_args = ["--content-dir", str(content)]
        client = FakeClient(reply({"items": [ag10_item("c01", impact=3, supply_chain=3, novelty=3), ag10_item("c02", category="policy", impact=0, supply_chain=0, novelty=0), ag10_item("c03", category="policy", impact=0, supply_chain=0, novelty=0)]}))
        out = self.tmp / "out2"
        code = score.main(["--candidates", str(self.cand), "--out-dir", str(out), "--ledger-dir", str(self.tmp / "ledger"), "--run-id", "r2",
                           "--config", str(self.cfg), "--companies-dir", str(self.tmp / "none"), *cfg_args],
                          client_factory=lambda: client, now=lambda: NOW)
        scored = json.loads((out / "scored.json").read_text(encoding="utf-8"))
        self.assertTrue(scored["ranked"][-1]["category_full"])  # 週の上限（このテストでは1件）に達した種別は下げる
        self.assertEqual(scored["ranked"][-1]["id"], "c01")

    def test_no_candidates_makes_notice_without_ai(self):
        self.cand.write_text(json.dumps({"collected_on": "2026-10-07", "candidates": [], "per_source": {}, "failed": []}), encoding="utf-8")
        out = self.tmp / "out3"
        code = score.main(["--candidates", str(self.cand), "--out-dir", str(out), "--ledger-dir", str(self.tmp), "--run-id", "r3", "--config", str(self.cfg)])
        self.assertEqual(code, 0)
        self.assertIn("新しい候補はなかった", (out / "issue-body.md").read_text(encoding="utf-8"))

    def test_unknown_ids_are_dropped(self):
        code, out, _ = self.run_score([ag10_item("c01"), ag10_item("c99")])
        scored = json.loads((out / "scored.json").read_text(encoding="utf-8"))
        self.assertEqual([s["id"] for s in scored["ranked"]], ["c01"])


if __name__ == "__main__":
    unittest.main()

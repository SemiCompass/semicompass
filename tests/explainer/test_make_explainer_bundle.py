import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import explainer_fakes as fk
import make_explainer_bundle as meb

redirect = fk.redirect
NOW = datetime(2026, 10, 7, 9, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo"))


def filler(n, start=0x4E00):
    return "".join(chr(start + i % 2000) for i in range(n))


class ExtractTest(unittest.TestCase):
    def test_html_keeps_the_main_text_only(self):
        page = fk.html_page(f"{fk.TARGET}は、表面を平らにする処理である。", "二つ目の段落である。").decode("utf-8")
        texts = [p["text"] for p in meb.html_paragraphs(page)]
        self.assertEqual(texts, [f"{fk.TARGET}は、表面を平らにする処理である。", "二つ目の段落である。"])

    def test_html_without_main_drops_navigation_ads_and_scripts(self):
        page = ("<html><body><nav>ナビの文</nav><div class='global-nav'>グローバルの文</div><div id='cookie-banner'>同意の文</div>"
                "<div class='content'><h1>見出し</h1><p>本文の一つ目の段落である。</p><p>本文の二つ目<br>改行を含む。</p></div>"
                "<aside>横の文</aside><script>alert(1)</script><style>.a{}</style><footer>末尾の文</footer></body></html>")
        texts = [p["text"] for p in meb.html_paragraphs(page)]
        joined = "".join(texts)
        for dropped in ("ナビ", "グローバル", "同意", "横の文", "alert", "末尾の文"):
            self.assertNotIn(dropped, joined)
        self.assertIn("本文の一つ目の段落である。", texts)
        self.assertIn("見出し", texts)

    def test_html_keeps_headings_inside_header_and_whitespace_between_cjk_is_removed(self):
        page = "<main><header><h1>題</h1></header><p>日本語の\n  文章が、\n  続く。 English  words</p></main>"
        texts = [p["text"] for p in meb.html_paragraphs(page)]
        self.assertIn("日本語の文章が、続く。 English words", texts)

    def test_decodes_shift_jis(self):
        body = "<html><head><meta charset='Shift_JIS'></head><body><p>日本語の本文である。</p></body></html>".encode("cp932")
        response = fk.ok(body, content_type="text/html")
        fmt, paragraphs = meb.extract_paragraphs(response, "https://a.example.org/x")
        self.assertEqual((fmt, paragraphs[0]["text"]), ("html", "日本語の本文である。"))

    def test_pdf_keeps_page_numbers(self):
        pdf = fk.make_pdf(["First page text about polishing", "Second page text about etching", "Third page text"])
        fmt, paragraphs = meb.extract_paragraphs(fk.ok(pdf, content_type="application/pdf"), "https://a.example.org/x.pdf")
        self.assertEqual(fmt, "pdf")
        self.assertEqual([p["page"] for p in paragraphs], [1, 2, 3])
        self.assertIn("polishing", paragraphs[0]["text"])

    def test_broken_pdf_is_a_failure_without_content(self):
        with self.assertRaises(meb.FetchFailure) as caught:
            meb.extract_paragraphs(fk.ok(b"%PDF-1.4 broken " + fk.WORD.encode(), content_type="application/pdf"), "https://a.example.org/x.pdf")
        self.assertNotIn(fk.WORD, caught.exception.reason)

    def test_unsupported_content_type(self):
        with self.assertRaises(meb.FetchFailure):
            meb.extract_paragraphs(fk.ok(b"x", content_type="application/zip"), "https://a.example.org/x")

    def test_pdf_page_paragraphs_join_japanese_lines(self):
        text = "架空研磨は、表面を\n平らにする処理である。\n次の文は\n別の段落になる。"
        self.assertEqual([p["text"] for p in meb.pdf_page_paragraphs(text, 4)],
                         ["架空研磨は、表面を平らにする処理である。", "次の文は別の段落になる。"])
        self.assertEqual({p["page"] for p in meb.pdf_page_paragraphs(text, 4)}, {4})


class SelectTest(unittest.TestCase):
    def paragraphs(self, texts):
        return [{"text": t, "page": 1} for t in texts]

    def test_keeps_hits_and_one_neighbour_each_side(self):
        paras = self.paragraphs(["遠い前", "前の段落", f"{fk.TARGET}を含む段落", "後の段落", "遠い後"])
        kept, not_found = meb.select_paragraphs(paras, [fk.TARGET])
        self.assertFalse(not_found)
        self.assertEqual([p["text"] for p in kept], ["前の段落", f"{fk.TARGET}を含む段落", "後の段落"])

    def test_limit_is_6000_chars_and_hits_come_before_neighbours(self):
        long_hit = fk.TARGET + filler(3000)
        paras = self.paragraphs([filler(3000, 0x5000), long_hit, filler(3000, 0x6000), "間", fk.TARGET + "二つ目" + filler(2900), filler(3000, 0x7000)])
        kept, _ = meb.select_paragraphs(paras, [fk.TARGET])
        self.assertLessEqual(sum(len(p["text"]) for p in kept), meb.KEEP_CHARS)
        texts = [p["text"] for p in kept]
        self.assertIn(long_hit, texts)  # 語を含む段落が、隣より優先される
        self.assertTrue(any("二つ目" in t for t in texts))

    def test_a_single_huge_hit_is_truncated(self):
        kept, _ = meb.select_paragraphs(self.paragraphs([fk.TARGET + filler(20000)]), [fk.TARGET])
        self.assertEqual(sum(len(p["text"]) for p in kept), meb.KEEP_CHARS)

    def test_not_found_keeps_first_1500_chars(self):
        paras = self.paragraphs([filler(1000), filler(1000, 0x5000), filler(1000, 0x6000)])
        kept, not_found = meb.select_paragraphs(paras, [fk.TARGET])
        self.assertTrue(not_found)
        self.assertEqual(sum(len(p["text"]) for p in kept), meb.NOT_FOUND_CHARS)
        self.assertEqual(kept[0]["text"], paras[0]["text"])

    def test_ascii_word_matches_on_word_boundaries_only(self):
        paras = self.paragraphs(["mediaeda is not a hit", "the EDA tool is a hit", "ＥＤＡ（全角）も当たる"])
        kept, not_found = meb.select_paragraphs(paras, ["EDA"])
        self.assertFalse(not_found)
        self.assertEqual([p["text"] for p in kept], ["mediaeda is not a hit", "the EDA tool is a hit", "ＥＤＡ（全角）も当たる"])
        only, _ = meb.select_paragraphs(self.paragraphs(["遠い", "mediaeda is not a hit", "遠い2", "遠い3", "the EDA tool is a hit"]), ["EDA"])
        self.assertEqual([p["text"] for p in only], ["遠い3", "the EDA tool is a hit"])  # mediaeda は、当たらない（前後の段落でもない）

    def test_target_words(self):
        self.assertEqual(meb.target_words("term", {"term": "EDA(設計ツール)", "sources": []}), ["EDA(設計ツール)", "EDA"])
        words = meb.target_words("process", {"process": "シリコンウェーハの製造", "keywords": ["ウェーハ"], "aliases": ["Ｗafer"], "sources": []})
        self.assertEqual(words, ["シリコンウェーハの製造", "シリコンウェーハ", "Wafer", "ウェーハ"])


class Base(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.tmp = Path(directory.name)
        self.clock = fk.Clock()
        self.r2 = fk.FakeR2()

    def run_main(self, sources, responses, *, argv=("--kind", "term", "--slug", "test-term"), env=None, extra_config=None):
        config = fk.make_config(self.tmp / "config.yaml", sources, extra=extra_config)
        transport = fk.FakeTransport(responses, self.clock)
        self.transport = transport
        summary = self.tmp / "summary.md"
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = meb.main([*argv, "--summary", str(summary)], env=fk.ENV if env is None else env, transport=transport,
                            sleep=self.clock.sleep, monotonic=self.clock.monotonic, now=lambda: NOW,
                            r2_factory=lambda creds: self.r2, config_path=config)
        self.stdout, self.stderr = out.getvalue(), err.getvalue()
        self.summary = summary.read_text(encoding="utf-8") if summary.exists() else ""
        return code

    def saved(self):
        self.assertEqual(len(self.r2.puts), 1)
        bucket, key, body = self.r2.puts[0]
        return bucket, key, json.loads(body.decode("utf-8"))

    def all_text(self):
        return "\n".join([self.stdout, self.stderr, self.summary])


class FetchTest(Base):
    def test_fetches_only_approved_urls_and_saves_to_r2(self):
        sources = [fk.source(fk.APPROVED, title="一つ目"), fk.source(fk.CANDIDATE, status="candidate"),
                   fk.source(fk.REJECTED, status="rejected"), fk.source(fk.APPROVED2, role="supplementary", title="二つ目")]
        responses = {fk.APPROVED: fk.ok(fk.html_page(f"{fk.TARGET}は、{fk.WORD}を使う処理である。")),
                     fk.APPROVED2: fk.ok(fk.html_page("補助の段落である。"))}
        self.assertEqual(self.run_main(sources, responses), 0, self.stderr)
        fetched = [u for u in self.transport.urls() if not u.endswith("/robots.txt")]
        self.assertEqual(fetched, [fk.APPROVED, fk.APPROVED2])
        bucket, key, bundle = self.saved()
        self.assertEqual((bucket, key), ("semicompass-bundles", "bundles/explainer/term-test-term.json"))
        self.assertEqual((bundle["schema_version"], bundle["kind"], bundle["slug"], bundle["fetched_on"]),
                         (1, "term", "test-term", "2026-10-07"))
        self.assertEqual([(s["id"], s["role"], s["url"]) for s in bundle["sources"]],
                         [("S1", "primary", fk.APPROVED), ("S2", "supplementary", fk.APPROVED2)])
        first = bundle["sources"][0]
        self.assertEqual(set(first), {"id", "url", "publisher", "title", "role", "kind", "fetched_at", "content_sha256", "format",
                                      "paragraphs", "not_found", "failure"})
        self.assertEqual(first["content_sha256"], hashlib.sha256(fk.html_page(f"{fk.TARGET}は、{fk.WORD}を使う処理である。")).hexdigest())
        self.assertFalse(first["not_found"])
        self.assertTrue(bundle["sources"][1]["not_found"])  # 補助の資料には、語がない
        self.assertEqual(first["paragraphs"][0]["page"], 1)

    def test_user_agent_names_semicompass_with_contact(self):
        self.run_main([fk.source(fk.APPROVED)], {fk.APPROVED: fk.ok(fk.html_page(fk.TARGET + "の段落である。"))})
        for _, headers, _ in self.transport.calls:
            self.assertIn("SemiCompass", headers["User-Agent"])
            self.assertIn("https://semicompass.com/contact/", headers["User-Agent"])

    def test_no_text_in_stdout_summary_or_errors(self):
        responses = {fk.APPROVED: fk.ok(fk.html_page(f"{fk.TARGET}と{fk.WORD}の段落である。")), fk.APPROVED2: RuntimeError(fk.WORD)}
        code = self.run_main([fk.source(fk.APPROVED), fk.source(fk.APPROVED2)], responses)
        self.assertEqual(code, 4)
        self.assertNotIn(fk.WORD, self.all_text())
        self.assertNotIn(fk.TARGET + "と", self.all_text())

    def test_failure_does_not_stop_the_others_and_exit_is_4(self):
        responses = {fk.APPROVED: meb.HttpResponse(404, {}, b""), fk.APPROVED2: fk.ok(fk.html_page(fk.TARGET + "の段落である。"))}
        code = self.run_main([fk.source(fk.APPROVED), fk.source(fk.APPROVED2)], responses)
        self.assertEqual(code, 4)
        _, _, bundle = self.saved()
        self.assertEqual([s["failure"] for s in bundle["sources"]], ["HTTP 404", None])
        self.assertEqual(bundle["sources"][0]["paragraphs"], [])
        self.assertIn("S1（HTTP 404）", self.stderr)
        self.assertIn("| S1 | primary | — | 失敗 |", self.summary)

    def test_all_failed_saves_nothing_and_exits_1(self):
        code = self.run_main([fk.source(fk.APPROVED)], {fk.APPROVED: TimeoutError()})
        self.assertEqual(code, 1)
        self.assertEqual(self.r2.puts, [])
        self.assertIn("すべて失敗", self.stderr)

    def test_communication_errors_are_failures_with_the_error_type_only(self):
        import urllib.error
        responses = {fk.APPROVED: urllib.error.URLError(ConnectionResetError(fk.WORD)), fk.APPROVED2: TimeoutError()}
        code = self.run_main([fk.source(fk.APPROVED), fk.source(fk.APPROVED2)], responses)
        self.assertEqual(code, 1)
        self.assertNotIn(fk.WORD, self.all_text())
        self.assertIn("ConnectionResetError", self.stderr + self.summary)
        self.assertIn("タイムアウト", self.summary)

    def test_too_large_is_a_failure(self):
        responses = {fk.APPROVED: meb.HttpResponse(200, {"content-type": "text/html"}, b"x", too_large=True)}
        self.assertEqual(self.run_main([fk.source(fk.APPROVED)], responses), 1)
        self.assertIn("10MB", self.summary)

    def test_pdf_source_keeps_page_numbers_and_format(self):
        url = "https://a.example.org/book.pdf"
        pdf = fk.make_pdf(["Intro text", "The test-term is described here", "Closing text"])
        self.assertEqual(self.run_main([fk.source(url)], {url: fk.ok(pdf, content_type="application/pdf")}, extra_config={"keywords": ["test-term"]}), 0,
                         self.stderr)
        _, _, bundle = self.saved()
        source = bundle["sources"][0]
        self.assertEqual(source["format"], "pdf")
        self.assertEqual([p["page"] for p in source["paragraphs"]], [1, 2, 3])
        self.assertFalse(source["not_found"])

    def test_dry_run_fetches_but_does_not_write_and_needs_no_credentials(self):
        code = self.run_main([fk.source(fk.APPROVED)], {fk.APPROVED: fk.ok(fk.html_page(fk.TARGET + "の段落である。"))},
                             argv=("--kind", "term", "--slug", "test-term", "--dry-run"), env={})
        self.assertEqual(code, 0, self.stderr)
        self.assertEqual(self.r2.puts, [])
        self.assertIn("保存しない（dry-run）", self.summary)

    def test_missing_credentials_is_a_usage_error(self):
        code = self.run_main([fk.source(fk.APPROVED)], {}, env={})
        self.assertEqual(code, 2)
        self.assertEqual(self.transport.calls, [])

    def test_r2_error_does_not_leak_credentials(self):
        class Broken:
            def put_object(self, **kw):
                raise RuntimeError(" ".join(fk.SECRETS))
        self.r2 = Broken()
        code = self.run_main([fk.source(fk.APPROVED)], {fk.APPROVED: fk.ok(fk.html_page(fk.TARGET + "の段落である。"))})
        self.assertEqual(code, 1)
        for secret in fk.SECRETS[:3]:  # 3つの認証情報（バケット名は、保存先として出してよい）
            self.assertNotIn(secret, self.all_text())

    def test_unknown_slug_and_no_approved_sources_are_usage_errors(self):
        self.assertEqual(self.run_main([fk.source(fk.APPROVED)], {}, argv=("--kind", "term", "--slug", "no-such-term")), 2)
        self.assertEqual(self.run_main([fk.source(fk.CANDIDATE, status="candidate")], {}), 2)
        self.assertEqual(self.run_main([fk.source(fk.APPROVED)], {}, argv=("--kind", "term", "--slug", "Bad Slug")), 2)
        self.assertEqual(self.transport.calls, [])

    def test_kind_is_validated_by_argparse(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            meb.main(["--kind", "company", "--slug", "x"])
        self.assertEqual(caught.exception.code, 2)

    def test_the_real_config_is_valid(self):
        meb.load_config()  # 形の検査だけ。どの対象が reviewed かには頼らない

    def test_the_test_config_fetches_for_a_slug_with_sources(self):
        path = fk.write_config(self.tmp / "config.yaml", fk.base_config())
        config = meb.load_config(path)
        entry = meb.find_entry(config, "term", "eda")
        self.assertEqual(meb.target_words("term", entry)[:2], ["EDA(設計ツール)", "EDA"])
        transport = fk.FakeTransport({"https://t.example.org/eda.html":
                                      fk.ok(fk.html_page("EDAは、回路の設計を助けるツールである。"))}, self.clock)
        code = meb.main(["--kind", "term", "--slug", "eda", "--dry-run"], env={}, transport=transport, sleep=self.clock.sleep,
                        monotonic=self.clock.monotonic, now=lambda: NOW, config_path=path)
        self.assertEqual(code, 0)


class PoliteTest(Base):
    def test_robots_disallow_blocks_the_page_and_is_recorded(self):
        responses = {"https://a.example.org/robots.txt": meb.HttpResponse(200, {}, b"User-agent: *\nDisallow: /page1.html\n"),
                     fk.APPROVED: fk.ok(fk.html_page("取得してはいけない段落である。")), fk.APPROVED2: fk.ok(fk.html_page(fk.TARGET + "の段落である。"))}
        code = self.run_main([fk.source(fk.APPROVED), fk.source(fk.APPROVED2)], responses)
        self.assertEqual(code, 4)
        self.assertNotIn(fk.APPROVED, self.transport.urls())
        _, _, bundle = self.saved()
        self.assertEqual(bundle["sources"][0]["failure"], "robots.txt で許可されていない")

    def test_robots_for_our_user_agent_token(self):
        robots = b"User-agent: SemiCompass\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
        code = self.run_main([fk.source(fk.APPROVED)], {"https://a.example.org/robots.txt": meb.HttpResponse(200, {}, robots),
                                                       fk.APPROVED: fk.ok(fk.html_page("段落である。"))})
        self.assertEqual(code, 1)
        self.assertNotIn(fk.APPROVED, self.transport.urls())

    def test_robots_404_allows_and_5xx_blocks(self):
        page = {fk.APPROVED: fk.ok(fk.html_page(fk.TARGET + "の段落である。"))}
        self.assertEqual(self.run_main([fk.source(fk.APPROVED)], {"https://a.example.org/robots.txt": meb.HttpResponse(404, {}, b""), **page}), 0)
        self.r2 = fk.FakeR2()
        code = self.run_main([fk.source(fk.APPROVED)], {"https://a.example.org/robots.txt": meb.HttpResponse(503, {}, b""), **page})
        self.assertEqual(code, 1)
        self.assertNotIn(fk.APPROVED, self.transport.urls())
        self.assertIn("robots.txt を確かめられない", self.summary)

    def test_robots_is_fetched_once_per_origin(self):
        page = fk.ok(fk.html_page(fk.TARGET + "の段落である。"))
        self.run_main([fk.source(fk.APPROVED), fk.source(fk.APPROVED2)], {fk.APPROVED: page, fk.APPROVED2: page})
        self.assertEqual(self.transport.urls().count("https://a.example.org/robots.txt"), 1)

    def test_same_domain_requests_are_at_least_one_second_apart(self):
        page = fk.ok(fk.html_page(fk.TARGET + "の段落である。"))
        self.run_main([fk.source(fk.APPROVED), fk.source(fk.APPROVED2)], {fk.APPROVED: page, fk.APPROVED2: page})
        times = [t for url, _, t in self.transport.calls]
        self.assertEqual(len(times), 3)  # robots.txt と2ページ
        self.assertTrue(all(b - a >= 1.0 for a, b in zip(times, times[1:])), times)

    def test_different_domains_do_not_wait(self):
        page = fk.ok(fk.html_page(fk.TARGET + "の段落である。"))
        self.run_main([fk.source(fk.APPROVED), fk.source(fk.OTHER_HOST)], {fk.APPROVED: page, fk.OTHER_HOST: page})
        times = [(url, t) for url, _, t in self.transport.calls]
        self.assertEqual([u for u, _ in times], ["https://a.example.org/robots.txt", fk.APPROVED, "https://b.example.net/robots.txt", fk.OTHER_HOST])
        self.assertEqual(times[2][1], times[1][1])  # 別のドメインの最初のリクエストは、待たない
        self.assertEqual(len(self.clock.sleeps), 2)  # 待つのは、同じドメインの robots.txt とページの間だけ


class RedirectTest(Base):
    def test_redirect_to_another_domain_is_refused_without_requesting_it(self):
        responses = {fk.APPROVED: redirect(fk.OTHER_HOST), fk.OTHER_HOST: fk.ok(fk.html_page("別のドメインの段落である。"))}
        code = self.run_main([fk.source(fk.APPROVED)], responses)
        self.assertEqual(code, 1)
        self.assertNotIn(fk.OTHER_HOST, self.transport.urls())
        self.assertIn("リダイレクト先のドメインが", self.summary)

    def test_redirect_within_the_domain_is_followed_and_www_is_the_same_domain(self):
        responses = {fk.APPROVED: redirect("https://www.a.example.org/moved.html"),
                     "https://www.a.example.org/moved.html": fk.ok(fk.html_page(fk.TARGET + "の段落である。"))}
        self.assertEqual(self.run_main([fk.source(fk.APPROVED)], responses), 0, self.stderr)
        self.assertIn("https://www.a.example.org/moved.html", self.transport.urls())
        self.assertEqual(self.saved()[2]["sources"][0]["url"], fk.APPROVED)  # 保存するURLは、yaml のURLのまま

    def test_relative_redirect_is_resolved_on_the_same_host(self):
        responses = {fk.APPROVED: redirect("/other/page.html", 302), "https://a.example.org/other/page.html": fk.ok(fk.html_page(fk.TARGET + "の段落である。"))}
        self.assertEqual(self.run_main([fk.source(fk.APPROVED)], responses), 0)

    def test_downgrade_to_http_is_refused(self):
        responses = {fk.APPROVED: redirect("http://a.example.org/page1.html")}
        self.assertEqual(self.run_main([fk.source(fk.APPROVED)], responses), 1)
        self.assertIn("https でない", self.summary)
        self.assertNotIn("http://a.example.org/page1.html", self.transport.urls())

    def test_redirect_loop_stops(self):
        responses = {fk.APPROVED: redirect(fk.APPROVED)}
        self.assertEqual(self.run_main([fk.source(fk.APPROVED)], responses), 1)
        self.assertIn("リダイレクトが5回を超えた", self.summary)

    def test_redirect_target_is_checked_against_robots(self):
        responses = {"https://a.example.org/robots.txt": meb.HttpResponse(200, {}, b"User-agent: *\nDisallow: /private/\n"),
                     fk.APPROVED: redirect("/private/page.html")}
        self.assertEqual(self.run_main([fk.source(fk.APPROVED)], responses), 1)
        self.assertNotIn("https://a.example.org/private/page.html", self.transport.urls())


class UrllibTransportTest(unittest.TestCase):
    def test_default_transport_does_not_follow_redirects_and_limits_size(self):
        import http.server
        import threading

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path == "/moved":
                    self.send_response(302)
                    self.send_header("Location", "https://elsewhere.invalid/")
                    self.end_headers()
                elif self.path == "/big":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"x" * 5000)
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"
        import os
        from unittest import mock
        patch = mock.patch.dict(os.environ, {"NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"})
        patch.start()
        self.addCleanup(patch.stop)
        moved = meb.urllib_transport(base + "/moved", {"User-Agent": "t"}, 5, 1000)
        self.assertEqual((moved.status, moved.headers["location"]), (302, "https://elsewhere.invalid/"))
        big = meb.urllib_transport(base + "/big", {"User-Agent": "t"}, 5, 1000)
        self.assertTrue(big.too_large)
        self.assertEqual(len(big.body), 1000)
        self.assertEqual(meb.urllib_transport(base + "/none", {"User-Agent": "t"}, 5, 1000).status, 404)


if __name__ == "__main__":
    unittest.main()

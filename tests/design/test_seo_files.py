"""robots.txt と sitemap.xml の確認（本番は登録を許可してサイトマップを出す。プレビューは登録させない）。"""

import re
import shutil
import unittest

from test_pages import HAS_NODE, ROOT, build_site


@unittest.skipUnless(HAS_NODE, "node_modules がない")
class SeoFilesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dist = {}
        for env in ("production", "preview"):
            out, failure = build_site(env)
            cls.addClassCleanup(shutil.rmtree, out, True)
            if failure:
                raise AssertionError(failure)
            cls.dist[env] = out / "dist"

    def test_preview_is_closed_to_search(self):
        dist = self.dist["preview"]
        self.assertEqual((dist / "robots.txt").read_text(encoding="utf-8"), "User-agent: *\nDisallow: /\n")
        self.assertFalse((dist / "sitemap.xml").exists())

    def test_production_allows_search_and_points_to_the_sitemap(self):
        text = (self.dist["production"] / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("Allow: /", text)
        self.assertNotIn("Disallow: /\n", text)
        self.assertIn("Sitemap: https://semicompass.com/sitemap.xml", text)

    def test_sitemap_lists_only_indexable_pages(self):
        dist = self.dist["production"]
        xml = (dist / "sitemap.xml").read_text(encoding="utf-8")
        urls = re.findall(r"<loc>([^<]+)</loc>", xml)
        self.assertGreater(len(urls), 50)
        self.assertEqual(urls, sorted(set(urls)))
        self.assertIn("https://semicompass.com/", urls)
        self.assertIn("https://semicompass.com/companies/tokyo-electron/", urls)
        # 転送だけのページ、検索に登録させないページ（404、Coming Soon の企業）は載せない
        self.assertNotIn("https://semicompass.com/supply-chain/", urls)
        self.assertNotIn("https://semicompass.com/404/", urls)
        for url in urls:
            html = (dist / url.removeprefix("https://semicompass.com/").strip("/") / "index.html" if url != "https://semicompass.com/" else dist / "index.html").read_text(encoding="utf-8")
            self.assertNotIn('name="robots" content="noindex', html[:2000], url)
            self.assertNotIn('http-equiv="refresh"', html[:2000], url)
        # 出力した全ページのうち、載せていないものは、すべて noindex か転送のページ
        for path in dist.rglob("index.html"):
            head = path.read_text(encoding="utf-8")[:2000]
            rel = "/" + "/".join(path.relative_to(dist).parts[:-1])
            url = "https://semicompass.com" + (rel + "/" if rel != "/" else "/")
            if url not in urls:
                self.assertTrue('name="robots" content="noindex' in head or 'http-equiv="refresh"' in head, url)


if __name__ == "__main__":
    unittest.main()

"""広告の枠の確認（要件定義書 4.13 の「広告の表示の切り替え」、AD-301、AD-401、LG-02、RL-06。画面とデザインの仕様書 8.23、9.8）。

* 本番で enabled: false（いまの設定）のとき：出力のどのファイルにも、広告のタグがなく、HTMLに広告の枠がない（RL-06）
* プレビュー：見本の枠を出し、AdSenseのコードは出さない。枠には「広告」の表示がある。数は上限（運用ルール書 5.1）以下
* 本番で enabled: true（作業用のコピー）：広告ユニットと読み込みのスクリプトを出す。サイト運営者IDが空なら、ビルドを失敗させる
"""

import re
import unittest
from html.parser import HTMLParser
import yaml

from test_pages import HAS_NODE, ROOT, make_site, real_site, submit_build

ADS = yaml.safe_load((ROOT / "config" / "ads.yaml").read_text(encoding="utf-8"))
TAGS = ("adsbygoogle", "googlesyndication")
FRAME = re.compile(r'<aside class="ad[^"]*" aria-label="広告" data-ad-frame data-ad-page="(\w+)" data-ad-position="([\w-]+)"')


def live_config(client: str) -> str:
    data = yaml.safe_load((ROOT / "config" / "ads.yaml").read_text(encoding="utf-8"))
    data["enabled"] = True
    data["client"] = client
    for page in data["pages"].values():
        for i, spec in enumerate(page["positions"].values()):
            spec["slot"] = f"12345678{i:02d}"
    return yaml.safe_dump(data, allow_unicode=True)


_LIVE = {}


def live_future(key: str, client: str):
    if key not in _LIVE:
        _LIVE[key] = submit_build("production", lambda: make_site(extra_files={"config/ads.yaml": live_config(client)}))
    return _LIVE[key]


if HAS_NODE:  # 組み立てを先に始める（待たない）
    live_future("live", "ca-pub-1234567890123456")
    live_future("noclient", "")


class _Ancestors(HTMLParser):
    """広告の枠（data-ad-position が position のもの）の祖先の要素のうち、class が page__aside で始まるものを集める。"""

    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self, position: str):
        super().__init__()
        self.position, self.stack, self.found = position, [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("data-ad-position") == self.position and self.found is None:
            self.found = [c for c in self.stack if c.startswith("page__aside")]
        if tag not in self.VOID:
            self.stack.append((a.get("class") or "").split(" ")[0])

    def handle_endtag(self, tag):
        if tag not in self.VOID and self.stack:
            self.stack.pop()


def ancestors_of_frame(html: str, position: str) -> list[str]:
    parser = _Ancestors(position)
    parser.feed(html)
    return parser.found or []


def frames(html: str) -> list[tuple[str, str]]:
    return FRAME.findall(html)


@unittest.skipUnless(HAS_NODE, "node_modules がない")
class AdsTest(unittest.TestCase):
    def test_config_is_off_by_default(self):
        # 審査に通るまでは出さない（RL-06）。true にするのは、広告の表示を始める変更案だけ
        self.assertIs(ADS["enabled"], False)
        self.assertEqual(ADS["client"], "")

    def test_production_outputs_no_ad_tags_and_no_frames(self):
        # 本番のどのページのHTMLにも、広告のタグと枠がなく、ページが読み込むスクリプトとCSSにも、広告のタグがない（RL-06）。
        # （Astro は、使われない部品のスクリプトも _astro/ に書き出すが、どのページも読み込まないファイルは、出力の確認の対象にしない）
        dist = real_site("production")
        assets = set()
        for path in dist.rglob("*.html"):
            html = path.read_text(encoding="utf-8")
            for tag in TAGS:
                self.assertNotIn(tag, html, path)
            self.assertNotIn("data-ad-frame", html, path)
            self.assertNotIn("data-ad-client", html, path)
            assets.update(re.findall(r'(?:src|href)="(/_astro/[^"]+\.(?:js|css))"', html))
        self.assertGreater(len(assets), 0)
        seen = set()
        while assets:  # 読み込むスクリプトが、さらに読み込むもの（import）もたどる
            rel = assets.pop()
            if rel in seen:
                continue
            seen.add(rel)
            text = (dist / rel.lstrip("/")).read_text(encoding="utf-8")
            for tag in TAGS:
                self.assertNotIn(tag, text, rel)
            assets.update("/_astro/" + m for m in re.findall(r'["./]([\w.-]+\.js)["]', text) if (dist / "_astro" / m).exists())
        self.assertFalse((dist / "ads.txt").exists())  # ads.txt はサイト運営者IDを受け取ってから置く（AD-304）

    def test_preview_shows_sample_frames_within_limits(self):
        dist = real_site("preview")
        counted = 0
        for path in dist.rglob("index.html"):
            html = path.read_text(encoding="utf-8")
            for tag in TAGS:
                self.assertNotIn(tag, html, path)
            found = frames(html)
            if not found:
                continue
            counted += 1
            pages = {p for p, _ in found}
            self.assertEqual(len(pages), 1, path)
            page = pages.pop()
            self.assertLessEqual(len(found), ADS["pages"][page]["limit"], path)  # AD-401
            for _, position in found:
                self.assertIn(position, ADS["pages"][page]["positions"], path)
            # 「広告」の表示（LG-02）と見本の文字が、枠の数だけある
            self.assertEqual(html.count('<p class="ad__label"'), len(found), path)
            self.assertEqual(html.count("広告の枠の見本（プレビューだけに表示）"), len(found), path)
        self.assertGreater(counted, 50)

    def test_frames_are_placed_where_the_spec_says(self):
        dist = real_site("preview")
        company = (dist / "companies" / "tokyo-electron" / "index.html").read_text(encoding="utf-8")
        self.assertEqual([p for _, p in frames(company)], ["after-financials", "after-body", "aside"])
        # 業績の節の後、「同じ工程の企業と比べる」より前。本文の後の枠は、出典より前（仕様書 9.8）
        self.assertLess(company.index('id="performance"'), company.index('data-ad-position="after-financials"'))
        self.assertLess(company.index('data-ad-position="after-financials"'), company.index('id="peers"'))
        self.assertLess(company.index('id="documents"'), company.index('data-ad-position="after-body"'))
        self.assertLess(company.index('data-ad-position="after-body"'), company.index('id="sources-heading"'))
        # 右の列の枠は、張り付く上の部分の外（右の列の下端）に置く（仕様書 8.4、8.23）
        self.assertEqual(ancestors_of_frame(company, "aside"), ["page__aside"])
        # 広告を置かないページ（運用ルール書 5.1 の上限0。工程の一覧は仕様書 9.8 で0として扱う）
        for rel in ("index.html", "processes/index.html", "about/index.html", "privacy/index.html", "search/index.html", "corrections/index.html"):
            path = dist / rel
            if path.exists():
                self.assertEqual(frames(path.read_text(encoding="utf-8")), [], rel)
        # Coming Soon の企業ページには、広告の部品を出さない（FR-110）
        coming = [p for p in (dist / "companies").glob("*/index.html") if "このページは準備中です" in p.read_text(encoding="utf-8")]
        self.assertGreater(len(coming), 0)
        for path in coming:
            self.assertEqual(frames(path.read_text(encoding="utf-8")), [], path)

    def test_live_build_outputs_ad_units_and_loader(self):
        out, failure = live_future("live", "ca-pub-1234567890123456").result()
        self.assertIsNone(failure, failure)
        dist = out / "dist"
        html = (dist / "companies" / "tokyo-electron" / "index.html").read_text(encoding="utf-8")
        units = re.findall(r'<ins class="adsbygoogle ad__unit" data-ad-unit data-ad-client="ca-pub-1234567890123456" data-ad-slot="(\d+)"', html)
        self.assertEqual(len(units), 3)
        self.assertIn('data-ad-client="ca-pub-1234567890123456"', html[html.index("<body"):html.index("<body") + 300])
        # 読み込みのスクリプト（AdLoader → src/scripts/ads.ts）を、ページが読み込む
        loaders = [rel for rel in re.findall(r'src="(/_astro/[^"]+\.js)"', html) if "googlesyndication" in (dist / rel.lstrip("/")).read_text(encoding="utf-8")]
        self.assertEqual(len(loaders), 1)
        self.assertIn("requestNonPersonalizedAds", (dist / loaders[0].lstrip("/")).read_text(encoding="utf-8"))  # 同意しない閲覧者
        self.assertIn("data-consent", html)  # 同意の確認を出す（LG-03）
        self.assertNotIn("広告の枠の見本", html)
        # 広告を置かないページには、枠も広告ユニットもない
        self.assertNotIn("<ins", (dist / "index.html").read_text(encoding="utf-8"))

    def test_live_build_without_client_fails(self):
        out, failure = live_future("noclient", "").result()
        self.assertIsNotNone(failure)
        self.assertIn("client", failure)


if __name__ == "__main__":
    unittest.main()

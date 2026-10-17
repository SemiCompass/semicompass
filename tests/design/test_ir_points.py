"""企業ページのIR重要ポイント（FR-307）と「最新の決算は未反映」（CT-03、AT-11、AT-22）の表示のテスト。
作業用のコピーに、架空のIR重要ポイントと決算発表の行を置いて、ビルドの日（BUILD_DATE）を変えて組み立てる。"""
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_pages import HAS_NODE, make_site, submit_build  # noqa: E402

POINT = """---
company: advantest
fiscal_period_end: '2027-03'
quarter: 2
announced_on: '2026-10-28'
uses_quarterly_figures: false
published_at: '2026-10-29'
draft: false
ai_generated: true
sources:
- id: S1
  title: 2027年3月期第2四半期 決算短信
  publisher: アドバンテスト
  url: https://www.release.tdnet.info/inbs/test-a.pdf
  published_on: '2026-10-28'
  accessed_on: '2026-10-29'
---

## 業績の要点

テスト用の業績の文である。[S1]

## 今期見通し

テスト用の見通しの文である。[S1]

## 注目材料

テスト用の材料の文である。[S1]
"""


def announcement(url):
    return {"fiscal_period_end": "2027-03", "quarter": 2, "announced_on": "2026-10-28", "detected_at": "2026-10-29T09:00:00+09:00",
            "documents": [{"type": "tanshin", "title": "決算短信", "url": url, "published_at": "2026-10-28T00:00:00+09:00"}]}


def auto_with_announcement(slug, url):
    data = json.loads((ROOT / "data" / "auto" / f"{slug}.json").read_text(encoding="utf-8"))
    data["announcements"] = [announcement(url)]
    return json.dumps(data, ensure_ascii=False)


def auto_without_announcements(slug):
    data = json.loads((ROOT / "data" / "auto" / f"{slug}.json").read_text(encoding="utf-8"))
    data["announcements"] = []
    return json.dumps(data, ensure_ascii=False)


@unittest.skipUnless(HAS_NODE, "node_modules がない")
class IrPointsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        extra = {
            "content/ir-points/advantest/2027-03-q2.md": POINT,
            "data/auto/advantest.json": auto_with_announcement("advantest", "https://www.release.tdnet.info/inbs/test-a.pdf"),
            "data/auto/disco.json": auto_with_announcement("disco", "https://www.release.tdnet.info/inbs/test-d.pdf"),
            # 決算発表のない企業の見本。リポジトリの data/auto に決算発表が加わっても、このテストが変わらないように空にする
            "data/auto/tokyo-electron.json": auto_without_announcements("tokyo-electron"),
        }
        # ビルドの日を変えた2つの組み立てを、並べて動かす（tests/design の共通の仕組み）
        futures = {day: submit_build("production", lambda: make_site(extra_files=extra), {"BUILD_DATE": day})
                   for day in ("2026-11-04", "2026-11-05")}
        cls.sites = {}
        for day, future in futures.items():
            out, failure = future.result()
            if failure is not None:
                raise AssertionError(failure)
            cls.sites[day] = out / "dist"

    def page(self, day, slug):
        return (self.sites[day] / "companies" / slug / "index.html").read_text(encoding="utf-8")

    def test_point_is_shown_with_date_and_sources(self):
        html = self.page("2026-11-05", "advantest")
        section = html.split('id="ir-points"')[1].split('id="work"')[0]
        for heading in ("業績の要点", "今期見通し", "注目材料"):
            self.assertRegex(section, rf"<h3[^>]*>{heading}</h3>")
        self.assertIn("テスト用の見通しの文", section.replace("<wbr>", ""))
        self.assertIn("作成日：2026年10月29日", section)
        self.assertIn("2027年3月期第2四半期", section)
        self.assertIn("決算短信を見る", section)  # グラフはまだこの期を含まない（FR-307 の注記）
        self.assertNotIn("未反映", section)
        self.assertIn("test-a.pdf", html.split('id="sources-heading"')[1])  # 出典の一覧に加わる

    def test_unreflected_after_five_business_days(self):
        # 2026-10-28（水）から5営業日は 11-04（水）。11-04 までは出さず、11-05 から出す（AT-22）
        self.assertNotIn("最新の決算は未反映", self.page("2026-11-04", "disco"))
        html = self.page("2026-11-05", "disco")
        self.assertIn("最新の決算は未反映です（決算発表：2026年10月28日）", html)
        self.assertIn("test-d.pdf", html)

    def test_company_without_announcements_has_no_notice(self):
        self.assertNotIn("最新の決算は未反映", self.page("2026-11-05", "tokyo-electron"))


if __name__ == "__main__":
    unittest.main()

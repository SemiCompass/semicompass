"""企業の一覧表（企業一覧と、工程ページの「この工程の企業」）の、営業利益率と平均年間給与の列（FR-309）。"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from test_pages import real_site

ROOT = Path(__file__).resolve().parents[2]
HAS_NODE = shutil.which("npx") is not None and (ROOT / "node_modules" / "astro").is_dir()


def build(env: str) -> Path:
    return real_site(env)


def table_rows(html: str) -> list[dict]:
    """企業の表の行：{cells: [セルの文字列], attrs: {data-*}}。"""
    rows = []
    for attrs, inner in re.findall(r"<tr ([^>]*data-index[^>]*)>(.*?)</tr>", html, re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", inner, re.S)]
        rows.append({"cells": cells, "attrs": dict((k, v) for k, v in re.findall(r'(data-[\w-]+)(?:="([^"]*)")?', attrs)),
                     "href": (re.search(r'href="(/companies/[^"]+/)"', inner) or [None, None])[1]})
    return rows


def table_heads(html: str) -> list[str]:
    return re.findall(r'<span class="data-table__label"[^>]*>(.*?)</span>', html)


def real_metrics(slugs: list[str]) -> dict:
    """data/auto/{slug}.json から、src/lib/metrics.ts で、営業利益率と平均年間給与を計算する（ファイルの値が、表と合うかの確認用）。"""
    script = ("import { readFileSync } from 'node:fs'; import('./src/lib/metrics.ts').then((m) => { const out = {};"
              "for (const slug of JSON.parse(process.argv[1])) { const a = JSON.parse(readFileSync(`data/auto/${slug}.json`, 'utf-8'));"
              "out[slug] = { margin: m.operatingMargin(a.financials), salary: m.averageSalary(a.employees ?? []) }; } console.log(JSON.stringify(out)); })")
    done = subprocess.run(["node", "--input-type=module", "-e", script, json.dumps(slugs)], cwd=ROOT, text=True, capture_output=True)
    assert done.returncode == 0, done.stderr[-800:]
    return json.loads(done.stdout.strip().splitlines()[-1])


COLUMNS = ["企業名", "証券コード", "企業区分", "工程", "売上高（億円）", "半導体関連の比率（%）", "営業利益率（％）", "平均年間給与（万円）", "掲載の状態"]
COMPACT = ["企業名", "企業区分", "売上高（億円）", "半導体関連の比率（%）", "営業利益率（％）", "平均年間給与（万円）"]
NOTES = ["営業利益率は、全社の連結の数値です。半導体事業だけの数値ではありません。",
         "平均年間給与は、提出会社の従業員の数値です。持株会社では、事業会社の水準を表しません。",
         "会計基準の違いで、営業利益の定義が異なる場合があります。"]


@unittest.skipUnless(HAS_NODE, "node_modules がない")
class CompanyTableMetricsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.companies = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "data" / "companies").glob("*.yaml"))]

    def build(self, env: str) -> Path:
        return build(env)

    def read(self, dist: Path, path: str) -> str:
        return (dist / path).read_text(encoding="utf-8")

    def test_company_list_has_the_columns_in_order_and_the_note_below_the_table(self):
        html = self.read(self.build("preview"), "companies/index.html")
        self.assertEqual(table_heads(html), COLUMNS)
        for key in ("margin", "salary"):  # 見出しを押して並べ替えられる（売上高・比率と同じ仕組み）
            self.assertRegex(html, rf'<th scope="col"[^>]*aria-sort="none"[^>]*data-sort-key="{key}"')
        self.assertTrue(all("data-sort-margin" in r["attrs"] and "data-sort-salary" in r["attrs"] for r in table_rows(html)))
        flat = html.replace("<wbr>", "")
        self.assertEqual(flat.count("定義と範囲"), 1)
        table_end = flat.index("</table>")
        positions = [flat.index(text) for text in NOTES]
        self.assertTrue(all(p > table_end for p in positions), "注記は、表の下にある")
        self.assertEqual(positions, sorted(positions))

    def test_process_page_uses_the_compact_columns_and_the_same_note(self):
        dist = self.build("preview")
        html = self.read(dist, "processes/etching/index.html")
        self.assertEqual(table_heads(html), COMPACT)
        self.assertTrue(all(len(r["cells"]) == 6 for r in table_rows(html)))
        flat = html.replace("<wbr>", "")
        self.assertTrue(all(flat.index(text) > flat.index("</table>") for text in NOTES))
        for page in sorted((dist / "processes").glob("*/index.html")):  # 企業のある工程は、どの工程でも同じ列と注記
            text = page.read_text(encoding="utf-8")
            if "data-table--wide-first" in text:
                self.assertEqual(table_heads(text), COMPACT, page.parent.name)
                self.assertIn("定義と範囲", text, page.parent.name)

    def test_values_come_from_the_data_files(self):
        for env in ("preview", "production"):
            html = self.read(self.build(env), "companies/index.html")
            rows = table_rows(html)
            detailed = [r for r in rows if r["cells"][-1] == "詳細"]
            if env == "preview":
                self.assertTrue(detailed, env)  # 本番は、事業概要が下書きの間、詳細掲載がなくてもよい（すべて準備中）
            expected = real_metrics([r["href"].split("/")[2] for r in detailed]) if detailed else {}
            for r in detailed:
                slug = r["href"].split("/")[2]
                margin, salary = expected[slug]["margin"], expected[slug]["salary"]
                self.assertEqual(r["cells"][6], "—" if margin is None else f"{margin:,.1f}", f"{env} {slug} 営業利益率")
                self.assertEqual(r["cells"][7], "—" if salary is None else f"{salary:,}", f"{env} {slug} 平均年間給与")
                self.assertEqual(r["attrs"]["data-sort-margin"], "" if margin is None else str(margin).removesuffix(".0"), slug)
                self.assertEqual(r["attrs"]["data-sort-salary"], "" if salary is None else str(salary), slug)

    def test_coming_soon_companies_show_dashes_and_sort_last(self):
        for env in ("preview", "production"):
            rows = table_rows(self.read(self.build(env), "companies/index.html"))
            coming = [r for r in rows if r["cells"][-1] == "準備中"]
            self.assertTrue(coming, env)
            for r in coming:
                self.assertEqual((r["cells"][4], r["cells"][5], r["cells"][6], r["cells"][7]), ("—", "—", "—", "—"), env)
                self.assertEqual((r["attrs"]["data-sort-margin"], r["attrs"]["data-sort-salary"]), ("", ""), env)  # 並べ替えでは、末尾

    def test_company_page_work_note_uses_the_shared_component(self):
        """企業ページの「働く環境」の注記（FR-803）は、共通の部品（FigureNotes）から、これまでと同じ文言で出る。
        持株会社だけに出る（プレビューでは、事業概要が下書きの企業も、詳細掲載として出る）。"""
        note = "持株会社のため、提出会社単体の数値は、持株会社の社員だけです。"
        dist = self.build("preview")
        holding = sorted(c["slug"] for c in self.companies if c.get("is_holding_company"))
        self.assertTrue(holding)
        counts = {s: self.read(dist, f"companies/{s}/index.html").count(note) for s in holding if (dist / "companies" / s / "index.html").is_file()}
        self.assertTrue(counts)
        self.assertTrue(any(n == 1 for n in counts.values()), counts)  # 働く環境のデータがある持株会社には、注記が1つ出る
        self.assertTrue(all(n <= 1 for n in counts.values()), counts)
        others = [c["slug"] for c in self.companies if not c.get("is_holding_company") and (dist / "companies" / c["slug"] / "index.html").is_file()]
        for slug in others:
            self.assertNotIn(note, self.read(dist, f"companies/{slug}/index.html"), slug)
            self.assertNotIn("定義と範囲", self.read(dist, f"companies/{slug}/index.html"), slug)  # 表の注記は、企業ページには出ない

    def test_the_table_is_wrapped_in_a_scroll_frame_with_a_fixed_first_column(self):
        """8.7：幅が足りないときは、表を囲む枠の中だけで横にスクロールし、企業名の列を左に固定する（構造と CSS の確認）。"""
        dist = self.build("preview")
        css = "".join(p.read_text(encoding="utf-8") for p in (dist / "_astro").glob("*.css"))
        self.assertRegex(css, r"\.table-scroll\[?[^{]*\{[^}]*overflow-x:\s*auto")
        self.assertRegex(css, r"\.is-first[^{]*\{[^}]*position:\s*sticky[^}]*left:\s*0")
        for path in ("companies/index.html", "processes/etching/index.html"):
            html = self.read(dist, path)
            frame = re.search(r'<div class="table-scroll"[^>]*>(.*?)</div>', html, re.S)
            self.assertIsNotNone(frame, path)
            self.assertIn('role="region"', frame.group(0)[:300])
            self.assertIn('tabindex="0"', frame.group(0)[:300])
            self.assertIn("<table", frame.group(1))  # 表は、枠の中にある
            self.assertRegex(frame.group(0)[:300], r"aria-label=\"[^\"]*横にスクロールできます")
            self.assertEqual(len(re.findall(r'<th scope="row" class="is-first', html)), len(table_rows(html)))  # 企業名の列が、行の見出し（左に固定）

    def test_no_page_overflow_in_a_real_browser(self):
        """ページ全体が横にはみ出さないこと（幅 360、768、1280）。表は、枠の中だけでスクロールし、企業名の列が左に残る。
        Chromium と Playwright があるときだけ行う（なければ、飛ばす）。"""
        import glob
        import http.server
        import threading
        module = next((p for p in (os.environ.get("PLAYWRIGHT_MODULE", ""), "/opt/node-tools/node_modules/playwright/index.mjs",
                                   str(ROOT / "node_modules" / "playwright" / "index.mjs")) if p and Path(p).is_file()), None)
        browsers = glob.glob(os.path.join(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers"), "chromium-*", "chrome-linux", "chrome"))
        if module is None or not browsers:
            self.skipTest("Playwright と Chromium がない")
        dist = self.build("preview")

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(dist), **kwargs)

            def log_message(self, *args):
                pass
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        script = """
import { chromium } from process.argv[1];
""".replace("process.argv[1]", "'" + module + "'") + """
const [exe, base] = [process.argv[2], process.argv[3]];
const b = await chromium.launch({ executablePath: exe });
const out = [];
for (const path of ['/companies/', '/processes/etching/']) for (const w of [360, 768, 1280]) {
  const pg = await b.newPage({ viewport: { width: w, height: 800 } });
  await pg.goto(base + path);
  const r = await pg.evaluate(() => {
    const sc = document.querySelector('.table-scroll');
    sc.scrollLeft = 10000;
    const th = sc.querySelector('tbody th');
    return { doc: document.documentElement.scrollWidth, win: window.innerWidth, frame: sc.clientWidth, scrolls: sc.scrollWidth > sc.clientWidth,
      firstOffset: Math.round(th.getBoundingClientRect().left - sc.getBoundingClientRect().left) };
  });
  out.push({ path, w, ...r });
  await pg.close();
}
await b.close();
console.log(JSON.stringify(out));
"""
        done = subprocess.run(["node", "--input-type=module", "-e", script, "x", browsers[0], f"http://127.0.0.1:{server.server_port}"],
                              text=True, capture_output=True, cwd=ROOT, env={**os.environ, "NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"})
        self.assertEqual(done.returncode, 0, done.stderr[-800:])
        for r in json.loads(done.stdout.strip().splitlines()[-1]):
            self.assertLessEqual(r["doc"], r["win"], r)  # ページ全体が、横にはみ出さない
            if r["scrolls"]:
                self.assertEqual(r["firstOffset"], 0, r)  # 枠の中で、いちばん右までスクロールしても、企業名の列は、左に残る
        narrow = [r for r in json.loads(done.stdout.strip().splitlines()[-1]) if r["w"] == 360]
        self.assertTrue(all(r["scrolls"] for r in narrow))  # スマートフォンでは、枠の中で横にスクロールする


if __name__ == "__main__":
    unittest.main()

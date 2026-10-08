"""企業一覧、工程、用語、検索、トップの確認（画面とデザインの仕様書 13章の5）。"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
HAS_NODE = shutil.which("npx") is not None and (ROOT / "node_modules" / "astro").is_dir()


def node(code: str):
    script = "Promise.all([import('./src/lib/normalize.ts'), import('./src/lib/content.ts')]).then(([n, c]) => console.log(JSON.stringify((" + code + ")(n, c))))"
    done = subprocess.run(["node", "-e", script], cwd=ROOT, text=True, capture_output=True)
    assert done.returncode == 0, done.stderr[-800:]
    return json.loads(done.stdout.strip().splitlines()[-1])


@unittest.skipUnless(HAS_NODE, "node_modules がない")
class NormalizeTest(unittest.TestCase):
    def test_width_kana_and_case_are_unified(self):
        same = node("(n) => ['TOKYO', 'ｔｏｋｙｏ', 'Tokyo ', 'to kyo'].map(n.normalizeForSearch)")
        self.assertEqual(len(set(same)), 1)
        kana = node("(n) => ['とうきょう', 'トウキョウ', 'ﾄｳｷｮｳ'].map(n.normalizeForSearch)")
        self.assertEqual(len(set(kana)), 1)
        self.assertEqual(node("(n) => n.normalizeForSearch('８０３５')"), "8035")

    def test_search_ranks_exact_before_prefix_and_requires_every_token(self):
        result = node("""(n) => {
          const e = (name, keys) => ({ type: 'term', name, url: '/' + name, keys: keys.map(n.normalizeForSearch) });
          const entries = [e('b', ['エッチング装置']), e('a', ['エッチング']), e('c', ['洗浄'])];
          return [n.search(entries, 'えっちんぐ').map((x) => x.name), n.search(entries, 'えっちんぐ 洗浄').map((x) => x.name), n.search(entries, '').map((x) => x.name)];
        }""")
        self.assertEqual(result, [["a", "b"], [], []])

    def test_glossary_headings(self):
        heading = node("(n, c) => ['あんそく', 'かい', 'ちょ', 'Alpha', '1', 'ん'].map(c.glossaryHeading)")
        self.assertEqual(heading[0], "あ行")
        self.assertEqual(heading[1], "か行")
        self.assertEqual(heading[3], "A")
        self.assertEqual(heading[4], "その他")


@unittest.skipUnless(HAS_NODE, "node_modules がない")
class PagesBuildTest(unittest.TestCase):
    def build(self, env: str, cwd: Path = ROOT) -> Path:
        out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, out, True)
        done = subprocess.run(["npx", "astro", "build", "--outDir", str(out / "dist")], text=True, capture_output=True,
                              cwd=cwd, env={**os.environ, "BUILD_ENV": env})
        self.assertEqual(done.returncode, 0, done.stdout[-1500:] + done.stderr[-1500:])
        return out / "dist"

    def read(self, dist: Path, path: str) -> str:
        return (dist / path).read_text(encoding="utf-8")

    @classmethod
    def setUpClass(cls):
        cls.companies = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "data" / "companies").glob("*.yaml"))]
        cls.processes = yaml.safe_load((ROOT / "data" / "supply-chain.yaml").read_text(encoding="utf-8"))["processes"]

    def test_company_list(self):
        for env in ("preview", "production"):
            dist = self.build(env)
            html = self.read(dist, "companies/index.html")
            rows = re.findall(r"<tr[^>]*data-index", html)
            self.assertEqual(len(rows), len(self.companies), env)
            for label in ("企業名", "証券コード", "企業区分", "工程", "売上高（億円）", "半導体関連の比率", "掲載の状態"):
                self.assertIn(label, html)
            self.assertIn('aria-sort="none"', html)
            self.assertNotIn("card", html.lower().replace("discard", ""))
            self.assertIn('role="status"', html)
            self.assertEqual(html.count('href="/companies/process/'), 0 if env else 0)  # 工程ごとの長いリンクの並びは、置かない
            self.assertIn('href="/processes/"', html.split("<main")[1])
            # 工程ごとの一覧
            self.assertTrue(list((dist / "companies" / "process").glob("*/index.html")))

    def test_production_shows_draft_companies_as_coming_soon(self):
        preview = self.read(self.build("preview"), "companies/index.html")
        production = self.read(self.build("production"), "companies/index.html")
        self.assertGreater(preview.count(">詳細<"), production.count(">詳細<"))

    def test_process_pages_and_neighbours(self):
        dist = self.build("preview")
        index = self.read(dist, "processes/index.html")
        pages = sorted(p.parent.name for p in (dist / "processes").glob("*/index.html"))
        self.assertEqual(len(pages), len(self.processes))
        for slug in pages:
            self.assertIn(f'href="/processes/{slug}/"', index)
            html = self.read(dist, f"processes/{slug}/index.html")
            self.assertEqual(html.count("<h1"), 1, slug)
            self.assertIn("この工程の企業", html)
            self.assertIn("準備中", html)  # content/processes に本文がない間
            heads = re.findall(r'<span class="data-table__label"[^>]*>(.*?)</span>', html)
            if "data-table--wide-first" in html:  # 企業がない工程は、表でなく空の表示
                self.assertEqual(heads, ["企業名", "企業区分", "売上高（億円）", "半導体関連の比率（%）"], slug)  # 本文の列に収める
            self.assertIn(f'href="/companies/process/{slug}/"', html)

    def test_empty_glossary_and_search(self):
        dist = self.build("preview")
        html = self.read(dist, "glossary/index.html")
        self.assertIn("準備中", html)
        search = self.read(dist, "search/index.html")
        self.assertIn('name="robots" content="noindex, nofollow"', search)
        self.assertIn("data-search-results", search)
        index = json.loads(self.read(dist, "search-index.json"))
        types = {e["type"] for e in index}
        self.assertTrue({"company", "process"} <= types)
        tel = [e for e in index if e["type"] == "company" and e.get("code") == "8035"]
        self.assertEqual(len(tel), 1)
        self.assertEqual(tel[0]["url"], "/companies/tokyo-electron/")
        for key in ("とうきょうえれくとろん", "tokyoelectronlimited", "8035"):
            self.assertIn(key, tel[0]["keys"])

    def test_home_has_description_three_entries_and_news_empty_state(self):
        html = self.read(self.build("preview"), "index.html")
        self.assertEqual(html.count("<h1"), 1)
        entries = re.findall(r'<dl class="entries"[^>]*>(.*?)</dl>', html, re.S)[0]
        self.assertEqual(entries.count("<dt"), 3)
        self.assertIn("role=\"search\"", html)
        self.assertIn("新着のニュース解説", html)

    def test_fixture_with_glossary_and_process_content(self):
        work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, work, True)
        for name in ("src", "data", "config", "content", "public", "package.json", "astro.config.mjs", "tsconfig.json"):
            source = ROOT / name
            if source.is_dir():
                shutil.copytree(source, work / name)
            elif source.is_file():
                shutil.copy(source, work / name)
        for extra in ROOT.glob("*"):
            if extra.name.startswith("."):
                continue
            if extra.is_file() and not (work / extra.name).exists() and extra.suffix in (".mjs", ".json", ".ts"):
                shutil.copy(extra, work / extra.name)
        os.symlink(ROOT / "node_modules", work / "node_modules")
        slugs = [p["slug"] for p in yaml.safe_load((ROOT / "data" / "supply-chain.yaml").read_text(encoding="utf-8"))["processes"]]
        src = "sources:\n  - id: S1\n    title: 例の資料\n    publisher: 例の団体\n    url: https://example.com/a\n    accessed_on: '2026-01-01'\n"
        (work / "content" / "glossary").mkdir(exist_ok=True)
        (work / "content" / "processes").mkdir(exist_ok=True)
        (work / "content" / "glossary" / "cmp.md").write_text(
            f"---\nslug: cmp\nterm: CMP\nreading: しーえむぴー\nname_en: Chemical Mechanical Planarization\nshort_definition: ウエハーの表面を平らにする工程である。\n"
            f"published_at: '2026-01-01'\nai_generated: true\nprocesses: [{slugs[0]}]\n{src}---\n## 概要\n\n試験用の本文である[S1]。\n", encoding="utf-8")
        (work / "content" / "glossary" / "draft-term.md").write_text(
            f"---\nslug: draft-term\nterm: 下書きの語\nreading: したがきのご\nshort_definition: 下書きである。\ndraft: true\n"
            f"published_at: '2026-01-01'\nai_generated: true\nprocesses: [{slugs[0]}]\n{src}---\n## 概要\n\n試験用である。\n", encoding="utf-8")
        (work / "content" / "processes" / f"{slugs[0]}.md").write_text(
            f"---\ntitle: 試験用の工程\ndescription: 試験用の説明である。\nprocess: {slugs[0]}\npublished_at: '2026-01-01'\nai_generated: true\nterms: [cmp]\n{src}---\n## 解説\n\n試験用の解説である[S1]。\n", encoding="utf-8")
        preview = self.build("preview", work)
        self.assertIn("CMP", self.read(preview, "glossary/index.html"))
        self.assertTrue((preview / "glossary" / "cmp" / "index.html").is_file())
        self.assertTrue((preview / "glossary" / "draft-term" / "index.html").is_file())
        process = self.read(preview, f"processes/{slugs[0]}/index.html")
        self.assertIn("試験用の解説", process.replace("<wbr>", ""))
        self.assertIn("/glossary/cmp/", process)
        index = json.loads(self.read(preview, "search-index.json"))
        self.assertTrue(any(e["type"] == "term" and e["name"] == "CMP" for e in index))
        production = self.build("production", work)
        self.assertTrue((production / "glossary" / "cmp" / "index.html").is_file())
        self.assertFalse((production / "glossary" / "draft-term").exists())


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
class CompanyTableMetricsTest(PagesBuildTest):
    """企業の一覧表の、営業利益率と平均年間給与の列（FR-309）。"""

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
            self.assertTrue(detailed, env)
            expected = real_metrics([r["href"].split("/")[2] for r in detailed])
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
        holding = sorted(c["slug"] for c in self.companies if c.get("is_holding_company") and c.get("listing") == "detailed")
        if not holding:
            self.skipTest("詳細掲載の持株会社がない")
        dist = self.build("preview")
        shown = [s for s in holding if (dist / "companies" / s / "index.html").is_file()
                 and "働く環境" in self.read(dist, f"companies/{s}/index.html")]
        notes = [self.read(dist, f"companies/{s}/index.html").count("持株会社のため、提出会社単体の数値は、持株会社の社員だけです。") for s in shown]
        self.assertTrue(any(n == 1 for n in notes) or not shown, notes)  # 従来の注記（FR-803）が、そのまま出る
        other = [c["slug"] for c in self.companies if not c.get("is_holding_company") and (dist / "companies" / c["slug"] / "index.html").is_file()]
        for slug in other[:5]:
            self.assertNotIn("持株会社のため、提出会社単体の数値は", self.read(dist, f"companies/{slug}/index.html"))

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

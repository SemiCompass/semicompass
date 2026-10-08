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
                self.assertEqual(heads, ["企業名", "企業区分", "売上高（億円）", "半導体関連の比率（%）", "営業利益率（％）", "平均年間給与（万円）"], slug)  # 本文の列に収める（FR-309）
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


if __name__ == "__main__":
    unittest.main()

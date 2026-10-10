"""企業一覧、工程、用語、ニュース、検索、トップの確認（画面とデザインの仕様書 13章の5）。"""

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


def normalize_key(text: str) -> str:
    """検索の語の正規化（src/lib/normalize.ts の normalizeForSearch）を、node で呼ぶ。"""
    return node(f"(n) => n.normalizeForSearch({json.dumps(text, ensure_ascii=False)})")


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


def build_site(env: str, cwd: Path = ROOT) -> tuple[Path, str | None]:
    """astro build を動かし、(出力のディレクトリ、失敗したときの出力の末尾)を返す。出力の置き場は、呼び出し側が消す。"""
    out = Path(tempfile.mkdtemp())
    done = subprocess.run(["npx", "astro", "build", "--outDir", str(out / "dist")], text=True, capture_output=True,
                          cwd=cwd, env={**os.environ, "BUILD_ENV": env})
    return out, (None if done.returncode == 0 else done.stdout[-1500:] + done.stderr[-1500:])


def make_site(glossary: dict[str, str] | None = None, processes: dict[str, str] | None = None, news: dict[str, str] | None = None) -> Path:
    """サイトの作業用のコピーを作る。**content/glossary/、content/processes/、content/news/ は、リポジトリの中身を写さず、空にして、
    glossary、processes、news のファイル（名前 → 本文）だけを置く**。リポジトリの実際の content/ は、書き換えない。
    これで、用語・工程の件数が0件のときの表示を、リポジトリの中身（用語が増えても）に左右されずに確かめられる。"""
    work = Path(tempfile.mkdtemp())
    for name in ("src", "data", "config", "content", "public", "package.json", "astro.config.mjs", "tsconfig.json"):
        source = ROOT / name
        if name == "content":
            shutil.copytree(source, work / name, ignore=shutil.ignore_patterns("glossary", "processes", "news"))
        elif source.is_dir():
            shutil.copytree(source, work / name)
        elif source.is_file():
            shutil.copy(source, work / name)
    for extra in ROOT.glob("*"):
        if extra.name.startswith("."):
            continue
        if extra.is_file() and not (work / extra.name).exists() and extra.suffix in (".mjs", ".json", ".ts"):
            shutil.copy(extra, work / extra.name)
    os.symlink(ROOT / "node_modules", work / "node_modules")
    for directory, files in (("glossary", glossary or {}), ("processes", processes or {}), ("news", news or {})):
        (work / "content" / directory).mkdir(parents=True)
        for filename, text in files.items():
            (work / "content" / directory / filename).write_text(text, encoding="utf-8")
    return work


def make_draft_site(slugs: tuple[str, ...]) -> Path:
    """サイトの作業用のコピーを作り、指定した企業の事業概要（content/companies/{slug}.md）を draft: true にする。
    リポジトリの企業は公開済みのため、「下書きのときの表示」（プレビューでは詳細掲載、本番では Coming Soon）は、このコピーで確かめる。
    content/ は、用語・工程・ニュースも含めてそのまま写す。リポジトリの実際のファイルは、書き換えない。"""
    work = Path(tempfile.mkdtemp())
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
    for slug in slugs:
        path = work / "content" / "companies" / f"{slug}.md"
        text = path.read_text(encoding="utf-8")
        changed = re.sub(r"^draft: false$", "draft: true", text, count=1, flags=re.M)
        assert changed != text, f"{slug} は draft: false のはず"
        path.write_text(changed, encoding="utf-8")
    return work


@unittest.skipUnless(HAS_NODE, "node_modules がない")
class PagesBuildTest(unittest.TestCase):
    _cache: dict[str, Path] = {}  # 同じ条件のビルドを、クラスの中で1回だけ行う（キーは "real-preview" など）

    @classmethod
    def _built(cls, key: str, env: str, work: Path | None = None) -> Path:
        if key not in cls._cache:
            out, failure = build_site(env, work or ROOT)
            cls.addClassCleanup(shutil.rmtree, out, True)
            if work is not None:
                cls.addClassCleanup(shutil.rmtree, work, True)
            if failure is not None:
                raise AssertionError(failure)
            cls._cache[key] = out / "dist"
        return cls._cache[key]

    def build(self, env: str) -> Path:
        """リポジトリそのままの content/ で、サイトを組み立てる（用語・工程の件数は、問わない）。"""
        return self._built(f"real-{env}", env)

    def build_empty(self, env: str = "preview") -> Path:
        """content/glossary/ と content/processes/ を空にした、作業用のコピーで、サイトを組み立てる。"""
        return self._built(f"empty-{env}", env, make_site())

    def build_with(self, key: str, env: str, glossary: dict[str, str] | None = None, processes: dict[str, str] | None = None,
                   news: dict[str, str] | None = None) -> Path:
        return self._built(f"{key}-{env}", env, make_site(glossary, processes, news))

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
        # 企業はすべて公開済み。下書き（draft: true）の企業を2社置いたコピーで、本番にだけ出ない（Coming Soon になる）ことを確かめる
        drafts = ("tokyo-electron", "sony")
        preview = self.read(self._built("drafts-preview", "preview", make_draft_site(drafts)), "companies/index.html")
        production = self.read(self._built("drafts-production", "production", make_draft_site(drafts)), "companies/index.html")
        self.assertEqual(preview.count(">詳細<") - production.count(">詳細<"), len(drafts))

    def test_process_pages_and_neighbours(self):
        dist = self.build_empty()  # 「解説は準備中」は、content/processes/ に本文がない（空の）ときの表示
        index = self.read(dist, "processes/index.html")
        pages = sorted(p.parent.name for p in (dist / "processes").glob("*/index.html"))
        self.assertEqual(len(pages), len(self.processes))
        for slug in pages:
            self.assertIn(f'href="/processes/{slug}/"', index)
            html = self.read(dist, f"processes/{slug}/index.html")
            self.assertEqual(html.count("<h1"), 1, slug)
            self.assertIn("この工程の企業", html)
            self.assertIn("この工程の解説は、準備中です", html.replace("<wbr>", ""))  # 本文がない工程の、解説の欄
            heads = re.findall(r'<span class="data-table__label"[^>]*>(.*?)</span>', html)
            if "data-table--wide-first" in html:  # 企業がない工程は、表でなく空の表示
                self.assertEqual(heads, ["企業名", "企業区分", "売上高（億円）", "半導体関連の比率（%）", "営業利益率（％）", "平均年間給与（万円）"], slug)  # 本文の列に収める（FR-309）
            self.assertIn(f'href="/companies/process/{slug}/"', html)

    def test_empty_glossary_and_search(self):
        dist = self.build_empty()  # content/glossary/ が空の、作業用のコピー（リポジトリの用語の数に左右されない）
        html = self.read(dist, "glossary/index.html")
        self.assertIn("用語集は、準備中です", html)
        self.assertEqual([p.name for p in (dist / "glossary").iterdir()], ["index.html"])  # 用語のページは、1つもない
        search = self.read(dist, "search/index.html")
        self.assertIn('name="robots" content="noindex, nofollow"', search)
        self.assertIn("data-search-results", search)
        index = json.loads(self.read(dist, "search-index.json"))
        types = {e["type"] for e in index}
        self.assertTrue({"company", "process"} <= types)
        self.assertNotIn("term", types)  # 用語が0件のとき、検索の候補にも、用語はない
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

    def fixture_site(self, env: str) -> Path:
        """試験用の用語2件（公開1件、下書き1件）と、工程の解説1件を置いた、作業用のコピーで組み立てる。"""
        slug = self.processes[0]["slug"]
        src = "sources:\n  - id: S1\n    title: 例の資料\n    publisher: 例の団体\n    url: https://example.com/a\n    accessed_on: '2026-01-01'\n"
        glossary = {
            "cmp.md": f"---\nslug: cmp\nterm: CMP\nreading: しーえむぴー\nname_en: Chemical Mechanical Planarization\n"
                      f"short_definition: ウエハーの表面を平らにする工程である。\npublished_at: '2026-01-01'\nai_generated: true\n"
                      f"processes: [{slug}]\n{src}---\n## 概要\n\n試験用の本文である[S1]。\n",
            "draft-term.md": f"---\nslug: draft-term\nterm: 下書きの語\nreading: したがきのご\nshort_definition: 下書きである。\ndraft: true\n"
                             f"published_at: '2026-01-01'\nai_generated: true\nprocesses: [{slug}]\n{src}---\n## 概要\n\n試験用である。\n"}
        processes = {f"{slug}.md": f"---\ntitle: 試験用の工程\ndescription: 試験用の説明である。\nprocess: {slug}\npublished_at: '2026-01-01'\n"
                                   f"ai_generated: true\nterms: [cmp]\n{src}---\n## 解説\n\n試験用の解説である[S1]。\n"}
        return self.build_with("fixture", env, glossary, processes)

    def test_glossary_with_terms_lists_them_and_has_no_coming_soon(self):
        """用語が1件以上あるときの表示（試験用の用語を、作業用のコピーに置く。リポジトリの content/ は使わない）。"""
        preview = self.read(self.fixture_site("preview"), "glossary/index.html")
        self.assertIn("CMP", preview)
        self.assertIn("下書きの語", preview)  # 下書きの用語は、プレビューにだけ出る
        self.assertNotIn("用語集は、準備中です", preview)
        production = self.read(self.fixture_site("production"), "glossary/index.html")
        self.assertIn("CMP", production)
        self.assertNotIn("下書きの語", production)
        self.assertNotIn("用語集は、準備中です", production)
        term = self.read(self.fixture_site("preview"), "glossary/cmp/index.html")
        self.assertIn("ウエハーの表面を平らにする工程である", term)

    def test_fixture_with_glossary_and_process_content(self):
        slug = self.processes[0]["slug"]
        preview = self.fixture_site("preview")
        self.assertTrue((preview / "glossary" / "cmp" / "index.html").is_file())
        self.assertTrue((preview / "glossary" / "draft-term" / "index.html").is_file())
        process = self.read(preview, f"processes/{slug}/index.html")
        self.assertIn("試験用の解説", process.replace("<wbr>", ""))
        self.assertNotIn("この工程の解説は、準備中です", process.replace("<wbr>", ""))  # 本文がある工程は、準備中にならない
        self.assertIn("/glossary/cmp/", process)
        index = json.loads(self.read(preview, "search-index.json"))
        self.assertTrue(any(e["type"] == "term" and e["name"] == "CMP" for e in index))
        production = self.fixture_site("production")
        self.assertTrue((production / "glossary" / "cmp" / "index.html").is_file())
        self.assertFalse((production / "glossary" / "draft-term").exists())

    # ---- ニュース（仕様書 9.6）。試験用の記事は、ここだけに置く（content/news/ には置かない） ----
    def news_files(self) -> dict[str, str]:
        company, process = self.companies[0]["slug"], self.processes[0]["slug"]

        def article(title: str, published: str, category: str, overseas: str, extra: str = "") -> str:
            return (
                f"---\ntitle: {title}\ndescription: 試験用の要約である。\npublished_at: '{published}'\nai_generated: true\ncategory: {category}\n"
                f"source_article:\n  title: 試験用の元記事の見出し\n  publisher: 試験用の発信元\n  url: https://example.com/original\n"
                f"  published_on: '{published}'\n  reporting: primary\n"
                f"score: {{impact: 2, supply_chain: 1, novelty: 3, reliability: 3}}\noverseas: {overseas}\n"
                f"tags: {{companies: [{company}], processes: [{process}], themes: []}}\n{extra}---\n"
                "## 何が起きたか\n\n試験用の事実である[S1]。\n\n## なぜ重要か\n\n試験用の説明である。\n\n"
                "## 関係する企業・工程とサプライチェーン上の位置\n\n試験用の位置づけである。\n"
            )

        return {
            "2026-10-older-sample.md": article("古い試験用のニュース", "2026-10-08", "technology", "false"),
            "2026-10-newer-sample.md": article("新しい試験用のニュース", "2026-10-09", "investment", "true"),
            "2026-10-draft-sample.md": article("下書きの試験用のニュース", "2026-10-07", "policy", "false", "draft: true\n"),
        }

    def news_site(self, env: str) -> Path:
        return self.build_with("news", env, news=self.news_files())

    def test_empty_news_list_and_search(self):
        dist = self.build_empty()  # content/news/ が空の、作業用のコピー
        html = self.read(dist, "news/index.html")
        self.assertIn("ニュース解説は、まだありません", html)
        self.assertEqual(html.count("<h1"), 1)
        self.assertEqual([p.name for p in (dist / "news").iterdir()], ["index.html"])  # 個別のページは、1つもない
        self.assertNotIn("news", {e["type"] for e in json.loads(self.read(dist, "search-index.json"))})

    def test_news_list_is_newest_first_with_date_category_and_company_tag(self):
        company = self.companies[0]
        html = self.read(self.news_site("production"), "news/index.html").replace("<wbr>", "")
        self.assertEqual(html.count("<h1"), 1)
        self.assertLess(html.index("新しい試験用のニュース"), html.index("古い試験用のニュース"))
        self.assertIn("2026年10月9日", html)
        self.assertIn("分類：投資", html)
        self.assertIn("分類：技術", html)
        self.assertIn(f'href="/companies/{company["slug"]}/"', html.split("<main")[1])
        self.assertIn('href="/news/2026/10/newer-sample/"', html)
        self.assertNotIn("card", html.lower().replace("discard", ""))

    def test_news_draft_only_in_preview(self):
        preview, production = self.news_site("preview"), self.news_site("production")
        self.assertIn("下書きの試験用のニュース", self.read(preview, "news/index.html").replace("<wbr>", ""))
        self.assertTrue((preview / "news" / "2026" / "10" / "draft-sample" / "index.html").is_file())
        self.assertNotIn("下書きの試験用のニュース", self.read(production, "news/index.html").replace("<wbr>", ""))
        self.assertFalse((production / "news" / "2026" / "10" / "draft-sample").exists())
        self.assertFalse(any("下書きの試験用" in e["name"] for e in json.loads(self.read(production, "search-index.json"))))
        draft = self.read(preview, "news/2026/10/draft-sample/index.html")
        self.assertIn('name="robots" content="noindex', draft)

    def test_news_page_shows_source_article_three_headings_and_tags(self):
        dist = self.news_site("production")
        html = self.read(dist, "news/2026/10/newer-sample/index.html")
        text = html.replace("<wbr>", "")
        self.assertEqual(html.count("<h1"), 1)
        self.assertIn("分類：投資", text)
        self.assertIn("公開日：", text)
        self.assertIn("試験用の元記事の見出し", text)  # 元記事（見出し、発信元、リンク、公表日）
        self.assertIn("試験用の発信元", text)
        self.assertIn('href="https://example.com/original"', html)
        self.assertIn("公表日：", text)
        self.assertIn("（外部サイト）", text)
        headings = re.findall(r"<h2[^>]*>(.*?)</h2>", text.split("<main")[1].split("</main>")[0])
        self.assertEqual(headings[:3], ["何が起きたか", "なぜ重要か", "関係する企業・工程とサプライチェーン上の位置"])
        self.assertEqual(headings[3:], ["関係する企業・工程", "出典"])
        self.assertIn('href="#source-1"', html)  # 本文の [S1] は、出典の1番へのリンク
        self.assertIn('id="source-1"', html)
        self.assertIn(f'href="/companies/{self.companies[0]["slug"]}/"', html)
        self.assertIn(f'href="/processes/{self.processes[0]["slug"]}/"', html)
        self.assertIn('href="/news/"', html)  # パンくず
        # 点と海外の印は、画面に出さない（仕様書に表示の指定がない）
        for hidden in ("overseas", "impact", "reliability", "重要度"):
            self.assertNotIn(hidden, html)
        self.assertIn("AIが下書きし、運営者が確認しました", html)

    def test_news_in_search_index(self):
        index = json.loads(self.read(self.news_site("production"), "search-index.json"))
        news = [e for e in index if e["type"] == "news"]
        self.assertEqual(sorted(e["url"] for e in news), ["/news/2026/10/newer-sample/", "/news/2026/10/older-sample/"])
        newer = next(e for e in news if e["name"] == "新しい試験用のニュース")
        self.assertEqual(newer["detail"], "2026年10月9日")
        self.assertIn(normalize_key("新しい試験用のニュース"), newer["keys"])

    def test_news_search_script_has_news_group(self):
        script = (ROOT / "src" / "scripts" / "search.ts").read_text(encoding="utf-8")
        self.assertIn("news: 'ニュース'", script)
        self.assertNotIn("まだ検索の対象にありません", script)

    def test_repository_content_renders_whatever_its_size(self):
        """リポジトリの content/glossary/ と content/processes/ が、何件でも（0件でも）、サイトが組み立てられ、表示が合う。
        件数は、決め打ちしない（ファイルを数えて、期待を決める）。"""
        terms = sorted(p.stem for p in (ROOT / "content" / "glossary").glob("*.md"))
        process_files = {p.stem for p in (ROOT / "content" / "processes").glob("*.md")}
        preview, production = self.build("preview"), self.build("production")
        for dist in (preview, production):
            html = self.read(dist, "glossary/index.html")
            published = [t for t in terms if "draft: true" not in (ROOT / "content" / "glossary" / f"{t}.md").read_text(encoding="utf-8")]
            expected = published if dist == production else terms
            self.assertEqual("用語集は、準備中です" in html, not expected)  # 用語が0件のときだけ、準備中
            for term in expected:
                self.assertTrue((dist / "glossary" / term / "index.html").is_file(), term)
        for process in self.processes:
            html = self.read(preview, f"processes/{process['slug']}/index.html").replace("<wbr>", "")
            if process["slug"] not in process_files:
                self.assertIn("この工程の解説は、準備中です", html, process["slug"])  # 本文がない工程だけ、準備中


if __name__ == "__main__":
    unittest.main()

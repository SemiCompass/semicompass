"""企業一覧、工程、用語、ニュース、検索、トップの確認（画面とデザインの仕様書 13章の5）。"""

import atexit
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
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


def build_site(env: str, cwd: Path = ROOT, extra_env: dict[str, str] | None = None) -> tuple[Path, str | None]:
    """astro build を動かし、(出力のディレクトリ、失敗したときの出力の末尾)を返す。出力の置き場は、呼び出し側が消す。"""
    out = Path(tempfile.mkdtemp())
    command = ["npx", "astro", "build", "--outDir", str(out / "dist")]
    if Path(cwd).resolve() != ROOT:
        # 作業用のコピーは node_modules をリポジトリと共有するため、Astro と Vite の作業用の場所（cacheDir）を、
        # コピーの中に分ける（並べて組み立てたときに、互いの作業用のファイルを壊さないように）
        (Path(cwd) / "astro.test.config.mjs").write_text(
            "import base from './astro.config.mjs';\n"
            "export default { ...base, cacheDir: './.astro-test-cache', vite: { ...(base.vite ?? {}), cacheDir: './.vite-test-cache' } };\n",
            encoding="utf-8")
        command += ["--config", "astro.test.config.mjs"]
    done = subprocess.run(command, text=True, capture_output=True,
                          cwd=cwd, env={**os.environ, "BUILD_ENV": env, **(extra_env or {})})
    return out, (None if done.returncode == 0 else done.stdout[-1500:] + done.stderr[-1500:])


# 組み立て（astro build）は、design のテストの時間のほとんどを占める。組み立ては1つずつは1コアしか使わないため、
# 同時に DESIGN_BUILD_JOBS 個（既定はコアの数、最低2）まで並べて動かす。必要な組み立ては、読み込みの時点で先に始める（_prefetch）
BUILD_JOBS = int(os.environ.get("DESIGN_BUILD_JOBS") or max(2, os.cpu_count() or 2))
_POOL = ThreadPoolExecutor(max_workers=BUILD_JOBS)


def _build_job(env: str, work_factory=None, extra_env: dict[str, str] | None = None) -> tuple[Path, str | None]:
    """作業用のコピー（work_factory があれば作る）を組み立てる。出力とコピーは、プロセスの終わりに消す。"""
    work = work_factory() if work_factory is not None else None
    out, failure = build_site(env, work or ROOT, extra_env)
    atexit.register(shutil.rmtree, out, True)
    if work is not None:
        atexit.register(shutil.rmtree, work, True)
    return out, failure


_REAL_FUTURES: dict = {}
_REAL_SITES: dict[str, Path] = {}


def _real_future(env: str):
    if env not in _REAL_FUTURES:
        # リポジトリそのものではなく、そのままの写しで組み立てる（ほかの組み立てと並べても、作業用の場所がぶつからない）
        _REAL_FUTURES[env] = _POOL.submit(_build_job, env, lambda: make_draft_site(()))
    return _REAL_FUTURES[env]


def submit_build(env: str, work_factory=None, extra_env: dict[str, str] | None = None):
    """組み立てを、並べて動かす列に入れる。返り値の .result() は (出力のディレクトリ, 失敗の出力の末尾)。"""
    return _POOL.submit(_build_job, env, work_factory, extra_env)


_DRAFT_FUTURES: dict = {}


def _draft_future(env: str, slugs: tuple[str, ...]):
    key = (env, tuple(slugs))
    if key not in _DRAFT_FUTURES:
        _DRAFT_FUTURES[key] = submit_build(env, lambda: make_draft_site(tuple(slugs)))
    return _DRAFT_FUTURES[key]


def draft_site(env: str, slugs: tuple[str, ...]) -> Path:
    """指定した企業を draft: true にした作業用のコピーで組み立てる（同じ条件は1回だけ）。"""
    out, failure = _draft_future(env, slugs).result()
    if failure is not None:
        raise AssertionError(failure)
    return out / "dist"


def real_site(env: str) -> Path:
    """リポジトリそのままのサイトを、環境ごとに、プロセスの中で1回だけ組み立てる（design の全テストで使い回す）。
    **使う側は、出力を書き換えない・消さない**。"""
    if env not in _REAL_SITES:
        out, failure = _real_future(env).result()
        if failure is not None:
            raise AssertionError(failure)
        _REAL_SITES[env] = out / "dist"
    return _REAL_SITES[env]


# テーマの試験用のファイル（データ定義書 6.7）。tests/validate/test_themes.py と同じ形。
# tests/validate を読み込まない（sys.path に足すと、同じ名前のテスト（test_ir_points）が入れ替わるため）
_FILL = "生成AIの計算に使う半導体の需要が増え、後工程の装置と材料の出荷が伸びている。[S1]"
THEME_BODY = ("## 要旨\n\n- 要点の一つ目である。[S1]\n- 要点の二つ目である。\n- 要点の三つ目である。\n\n"
              "## 市場の動き\n\n" + _FILL * 15 + "\n\n## バリューチェーン\n\n" + _FILL * 15 + "\n\n"
              "## 日本企業の位置\n\n" + _FILL * 10 + "\n\n"
              "## 論点と今後の注目点\n\n### 発表元の見方\n\n" + _FILL * 5 + "\n\n### 本サイトの見方\n\n" + _FILL * 5 + "\n")


def theme_front(**extra):
    front = {
        "theme": "generative-ai", "title": "生成AIと半導体",
        "description": "生成AIの計算に使う半導体を作るのに、どの工程と企業が関わっているかをまとめる。",
        "published_at": "2026-10-22", "ai_generated": True, "draft": True,
        "criteria": "AI向けの半導体の製造・検査に使う装置・材料・部品を、公開資料で確かめられる企業。",
        "groups": [{"label": "HBMの積層と検査", "process": "advanced-packaging",
                    "companies": [{"company": "advantest", "role": "メモリの検査に使う試験装置を作る。", "basis": ["S2"]}],
                    "others": [{"name": "SKハイニックス", "region": "韓国", "role": "HBMを製造する。", "basis": ["S3"]}]}],
        "sources": [{"id": f"S{n}", "title": f"資料{n}", "publisher": "発行元", "url": f"https://example.org/{n}", "accessed_on": "2026-10-22"}
                    for n in (1, 2, 3)],
    }
    front.update(extra)
    return front


def make_site(glossary: dict[str, str] | None = None, processes: dict[str, str] | None = None, news: dict[str, str] | None = None,
              extra_files: dict[str, str] | None = None) -> Path:
    """サイトの作業用のコピーを作る。**content/glossary/、content/processes/、content/news/、content/themes/ は、リポジトリの中身を写さず、空にして、
    glossary、processes、news のファイル（名前 → 本文）だけを置く**。リポジトリの実際の content/ は、書き換えない。
    これで、用語・工程の件数が0件のときの表示を、リポジトリの中身（用語が増えても）に左右されずに確かめられる。"""
    work = Path(tempfile.mkdtemp())
    for name in ("src", "data", "config", "content", "public", "package.json", "astro.config.mjs", "tsconfig.json"):
        source = ROOT / name
        if name == "content":
            shutil.copytree(source, work / name, ignore=shutil.ignore_patterns("glossary", "processes", "news", "themes"))
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
    (work / "content" / "themes").mkdir(parents=True, exist_ok=True)  # テーマも、リポジトリの中身を写さない（extra_files で置く）
        for filename, text in files.items():
            (work / "content" / directory / filename).write_text(text, encoding="utf-8")
    for relpath, text in (extra_files or {}).items():  # そのほかのファイル（学習のページ、図など。作業用のコピーからの相対の位置）
        (work / relpath).parent.mkdir(parents=True, exist_ok=True)
        (work / relpath).write_text(text, encoding="utf-8")
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
    _cache: dict[str, Path] = {}  # 同じ条件のビルドを、1回だけ行う（キーは "fixture-preview" など）
    _futures: dict = {}
    _prefetch = False  # true の間は、組み立てを始めるだけで待たない（_prefetch から使う）

    @classmethod
    def _built(cls, key: str, env: str, work=None) -> Path:
        """work は、作業用のコピーを作る関数（またはコピーそのもの）。None はリポジトリそのまま。"""
        if key not in cls._futures:
            factory = work if callable(work) else ((lambda: make_draft_site(())) if work is None else (lambda w=work: w))
            cls._futures[key] = _POOL.submit(_build_job, env, factory)
        if cls._prefetch:
            return ROOT
        if key not in cls._cache:
            out, failure = cls._futures[key].result()
            if failure is not None:
                raise AssertionError(failure)
            cls._cache[key] = out / "dist"
        return cls._cache[key]

    @classmethod
    def prefetch(cls) -> None:
        """このクラスが使う作業用のコピーの組み立てを、先に始める（待たない）。"""
        cls.setUpClass()
        probe = cls("test_company_list")
        cls._prefetch = True
        try:
            probe.build_empty()
            for env in ("preview", "production"):
                probe.fixture_site(env)
                probe.news_site(env)
                probe.drafts_site(env)
            probe.learn_site()
            probe.learn_site(physics=True)
            probe.learnpath_site()
            probe.events_site()
            probe.nolearn_site()
            probe.theme_site("preview")
            probe.theme_site("production")
        finally:
            cls._prefetch = False

    def build(self, env: str) -> Path:
        """リポジトリそのままの content/ で、サイトを組み立てる（用語・工程の件数は、問わない）。"""
        return real_site(env)

    def build_empty(self, env: str = "preview") -> Path:
        """content/glossary/ と content/processes/ を空にした、作業用のコピーで、サイトを組み立てる。"""
        return self._built(f"empty-{env}", env, make_site)

    def build_with(self, key: str, env: str, glossary: dict[str, str] | None = None, processes: dict[str, str] | None = None,
                   news: dict[str, str] | None = None, extra: dict[str, str] | None = None) -> Path:
        return self._built(f"{key}-{env}", env, lambda: make_site(glossary, processes, news, extra))

    def read(self, dist: Path, path: str) -> str:
        return (dist / path).read_text(encoding="utf-8")

    @classmethod
    def setUpClass(cls):
        cls.companies = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "data" / "companies").glob("*.yaml"))]
        cls.processes = yaml.safe_load((ROOT / "data" / "supply-chain.yaml").read_text(encoding="utf-8"))["processes"]

    def test_employee_chart_states_its_scope(self):
        # FR-803、AT-05：従業員数のグラフは、連結か提出会社単体かを見出しに書く（単体の表は「提出会社単体」と書く）
        html = self.read(self.build("production"), "companies/disco/index.html")
        work = html.split('id="work"')[1].split('id="news"')[0]
        self.assertRegex(work, r"従業員数の推移（(連結|提出会社単体|連結。連結の数値がない期は提出会社単体)）")
        self.assertIn("提出会社単体", work[work.index("従業員数の推移"):])

    def test_company_list(self):
        for env in ("preview", "production"):
            dist = self.build(env)
            html = self.read(dist, "companies/index.html")
            rows = re.findall(r"<tr[^>]*data-index", html)
            self.assertEqual(len(rows), len(self.companies), env)
            for label in ("企業名", "工程", "売上高（億円）", "半導体関連の比率", "営業利益率", "平均年間給与", "詳しいページのある企業だけ"):
                self.assertIn(label, html)
            self.assertIn('aria-sort="none"', html)
            self.assertNotIn("card", html.split("<main")[1].lower().replace("discard", ""))  # 一覧はカードの格子にしない（head の twitter:card は対象外）
            self.assertIn('role="status"', html)
            self.assertEqual(html.count('href="/companies/process/'), 0 if env else 0)  # 工程ごとの長いリンクの並びは、置かない
            self.assertIn('href="/processes/"', html.split("<main")[1])
            # 工程ごとの一覧
            self.assertTrue(list((dist / "companies" / "process").glob("*/index.html")))

    def test_internal_links_point_to_existing_pages(self):
        # 出力したすべてのページの、サイトの中へのリンク（href="/..."）が、出力したページか転送を指す。
        # 企業を詳細掲載に切り替えたときに、分類のタグが存在しないページを指していた不具合（本番で29か所）を防ぐ
        for env in ("preview", "production"):
            dist = self.build(env)
            pages = set()
            for f in dist.rglob("*.html"):
                rel = f.relative_to(dist).as_posix()
                pages.add("/" + (rel[: -len("index.html")] if rel.endswith("index.html") else rel))
            broken: dict[str, set[str]] = {}
            for f in dist.rglob("*.html"):
                if f.relative_to(dist).parts[0] == "dev":
                    continue  # 部品の一覧（プレビューだけ）は、見本のリンク（/companies/sample/ など）を並べる
                for href in re.findall(r'href="(/[^"#?]*)', f.read_text(encoding="utf-8")):
                    last = href.rstrip("/").rsplit("/", 1)[-1]
                    if href.startswith("/_astro/") or "." in last:
                        continue  # CSS・スクリプト・画像・robots.txt などのファイル
                    if href not in pages:
                        broken.setdefault(href, set()).add(f.relative_to(dist).as_posix())
            self.assertEqual({k: sorted(v)[:3] for k, v in broken.items()}, {}, f"{env}: リンク先のページがない")

    def test_category_pages_list_companies_of_the_category(self):
        dist = self.build("production")
        supply = yaml.safe_load((ROOT / "data" / "supply-chain.yaml").read_text(encoding="utf-8"))
        for category in supply["categories"]:
            html = self.read(dist, f"companies/process/{category['slug']}/index.html")
            self.assertIn(f"{category['name']}の企業", html)
            expected = sum(1 for c in self.companies if category["slug"] in (c.get("categories") or []))
            self.assertEqual(len(re.findall(r"<tr[^>]*data-index", html)), expected, category["slug"])

    def test_production_shows_draft_companies_as_coming_soon(self):
        # 企業はすべて公開済み。下書き（draft: true）の企業を2社置いたコピーで、本番にだけ出ない（Coming Soon になる）ことを確かめる
        preview = self.read(self.drafts_site("preview"), "companies/index.html")
        production = self.read(self.drafts_site("production"), "companies/index.html")
        self.assertEqual(preview.count('data-detailed="true"') - production.count('data-detailed="true"'), len(self.DRAFTS))

    DRAFTS = ("tokyo-electron", "sony")

    def drafts_site(self, env: str) -> Path:
        return self._built(f"drafts-{env}", env, lambda: make_draft_site(self.DRAFTS))

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

    def test_home_has_description_four_entries_and_news_empty_state(self):
        # 4つの入口（要件定義書 3.3 の3）：記号・見出し・一文の説明を組にしたリンク
        html = self.read(self.build("preview"), "index.html")
        self.assertEqual(html.count("<h1"), 1)
        entries = re.findall(r'<nav class="[^"]*\bentries\b[^"]*"[^>]*>(.*?)</nav>', html, re.S)[0]
        links = re.findall(r'<a class="entry"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', entries, re.S)
        # 「半導体を学ぶ」は、学習のページがあれば /learn/、なければ用語集（プレビューでは下書きのページも数える）
        self.assertIn(links[0][0], ("/learn/", "/glossary/"))
        self.assertEqual([h for h, _ in links[1:]], ["/processes/", "/news/", "/companies/"])
        for title, (_, body) in zip(["半導体を学ぶ", "工程を学ぶ", "ニュースを読む", "企業を比べる"], links):
            self.assertIn(title, body)
            self.assertIn('aria-hidden="true"', body)  # 絵は見出しと組にし、読み上げない
        self.assertIn("role=\"search\"", html)  # 企業名・証券コードの検索は、帯の中の大きな検索欄
        self.assertIn("新着のニュース解説", html)

    def test_home_has_process_flow_but_no_sales_chart(self):
        # トップの「半導体ができるまで」（仕様書 9.1 の3・4、2026年10月17日の作り直し）：工程の流れの図。各工程は工程ページへ。
        # 下に工場設備の帯（分類の企業の一覧へ）と、できあがる半導体の帯。売上高の上位10社は置かない
        html = self.read(self.build("production"), "index.html")
        main = html.split("<main")[1]
        self.assertIn("半導体ができるまで", main)
        for p in self.processes:
            self.assertIn(f'href="/processes/{p["slug"]}/"', main, p["slug"])
        for category in ("facilities", "devices"):
            self.assertIn(f'href="/companies/process/{category}/"', main)
        self.assertNotIn("上位10社", main)
        self.assertIn("ニュースを読む", main)
        self.assertNotIn("ニュース・テーマを読む", main)
        # 帯の中の大きな検索欄があるため、トップではヘッダーの検索欄を出さない（8.1）
        self.assertIn("site-header--home", html)
        self.assertIn('id="home-search"', main)

    def test_facilities_band_on_processes(self):
        # 工場設備（分類 facilities）：特定の工程ではなく工場全体を支える会社。工程の一覧の全体図の下の帯から、分類の企業の一覧へ
        dist = self.build("production")
        n = sum(1 for c in self.companies if "facilities" in (c.get("categories") or []))
        self.assertGreater(n, 0)
        for page in ("processes/index.html",):
            main = self.read(dist, page).split("<main")[1]
            self.assertRegex(main, r'class="pflow__band[^"]*"[^>]*href="/companies/process/facilities/"', page)
            self.assertIn(f"{n}社", main, page)
        self.assertTrue((dist / "companies" / "process" / "facilities" / "index.html").exists())

    def test_analytics_only_in_production_with_consent_and_feedback_on_content_pages(self):
        # GA4（要件定義書 LG-03）：本番のビルドだけ、測定IDとCookieの利用の確認を出す。計測のプログラムは、同意の後に読み込む（ページに直接書かない）
        prod, prev = self.build("production"), self.build("preview")
        home = self.read(prod, "index.html")
        self.assertRegex(home, r'data-ga-id="G-[A-Z0-9]+"')
        self.assertIn("data-consent ", home)
        self.assertIn("data-consent-open", home)
        self.assertNotIn("googletagmanager.com/gtag/js", home)  # 同意の前は読み込まない
        self.assertNotIn("data-ga-id", self.read(prev, "index.html"))
        self.assertNotIn("data-consent ", self.read(prev, "index.html"))
        # 疑問の解決ボタン（FR-709）：企業（詳細掲載）・工程・用語・ニュースのページの末尾
        pages = [p for p in (prod / "companies").glob("*/index.html") if "data-feedback-wrap" in p.read_text(encoding="utf-8")]
        self.assertGreater(len(pages), 0)
        for pattern in ("processes/*/index.html", "glossary/*/index.html", "news/*/*/*/index.html"):
            found = list(prod.glob(pattern))
            if found:
                self.assertIn("知りたいことは分かりましたか？", found[0].read_text(encoding="utf-8"), pattern)
        self.assertNotIn("data-feedback", home)
        # CSP：Google Analytics 4 だけを許す
        headers = (ROOT / "public" / "_headers").read_text(encoding="utf-8")
        self.assertIn("script-src 'self' https://www.googletagmanager.com", headers)
        self.assertNotIn("unsafe-inline", headers)

    def test_structured_data_author_ogp_and_sitemap_lastmod(self):
        # 要件定義書 SE-03、SE-07、NF-07：構造化データ（トップに Organization と WebSite、ページにパンくずリスト、ニュースに NewsArticle、
        # 用語に DefinedTerm）、作成者（/about/ へのリンク）、OGP、サイトマップの lastmod
        import json
        dist = self.build("production")
        def ld(html):
            return [json.loads(x) for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]
        home = self.read(dist, "index.html")
        self.assertEqual({d["@type"] for d in ld(home)}, {"Organization", "WebSite"})
        self.assertIn('property="og:image"', home)
        self.assertIn('name="twitter:card"', home)
        news = sorted((dist / "news").glob("*/*/*/index.html"))
        self.assertTrue(news)
        html = news[0].read_text(encoding="utf-8")
        types = {d["@type"]: d for d in ld(html)}
        self.assertIn("BreadcrumbList", types)
        article = types["NewsArticle"]
        self.assertTrue(article["datePublished"])
        self.assertTrue(article["author"]["url"].endswith("/about/"))
        self.assertIn('作成者：<a href="/about/"', html)
        self.assertIn('property="og:type" content="article"', html)
        term = sorted((dist / "glossary").glob("*/index.html"))[0].read_text(encoding="utf-8")
        self.assertIn("DefinedTerm", {d["@type"] for d in ld(term)})
        sitemap = self.read(dist, "sitemap.xml")
        self.assertRegex(sitemap, r"/news/[^<]+</loc><lastmod>\d{4}-\d{2}-\d{2}</lastmod>")
        self.assertTrue((dist / "og-default.png").is_file())

    def test_home_lists_latest_news_up_to_five(self):
        # 公開しているニュース解説を、トップに新しい順で最大5件出す（仕様書 9.1 の4）。0件のときだけ「まだありません」
        for env in ("preview", "production"):
            html = self.read(self.build(env), "index.html")
            news_dir = ROOT / "content" / "news"
            published = [p for p in news_dir.glob("*.md") if env == "preview" or not re.search(r"^draft: true$", p.read_text(encoding="utf-8"), re.M)]
            items = re.findall(r'<li class="home-news__item"', html)
            self.assertEqual(len(items), min(5, len(published)), env)
            if published:
                self.assertNotIn("ニュース解説は、まだありません。", html)
                self.assertIn('href="/news/"', html.split("<main")[1])
        self.assertNotIn("広告主", self.read(self.build("production"), "index.html").split("<main")[1])

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

    def learn_site(self, env: str = "preview", physics: bool = False) -> Path:
        """学習のページ1件（図と理解度チェック付き）と、理解度チェック付きの用語1件を置いた、作業用のコピーで組み立てる。
        physics が true のときは、深掘り編「半導体の物理」のカードAに、式を含むページ1件（基礎編の学習のページと工程に効く）も置く。"""
        src = "sources:\n  - id: S1\n    title: 例の資料\n    publisher: 例の団体\n    url: https://example.com/a\n    accessed_on: '2026-01-01'\n"
        quiz = ("## 理解度チェック\n\n### 問1\n試験の問いである。\n\n1. 一つ目\n2. 二つ目\n3. 三つ目\n4. 四つ目\n\n"
                "答え：3\n解説：試験の解説である。\n")
        slug = self.processes[0]["slug"]
        glossary = {"cmp.md": f"---\nslug: cmp\nterm: CMP\nreading: しーえむぴー\nshort_definition: ウエハーの表面を平らにする工程である。\n"
                              f"published_at: '2026-01-01'\nai_generated: true\nprocesses: [{slug}]\n{src}---\n## 概要\n\n試験用の本文である[S1]。\n\n{quiz}"}
        tree = yaml.safe_load((ROOT / "content" / "learn" / "path.yaml").read_text(encoding="utf-8"))
        for field in tree["fields"]:
            if field["slug"] == "basics":
                field["units"] = [{"type": "learn", "ref": "test-page"}]  # リポジトリの学習のページは写さない（下の content/learn/basics/ を置き換える）
                field.pop("sections", None)
            elif field["slug"] == "industry":
                field["units"] = []  # 単元のない分野の表示（準備中）を確かめるため、空にする
                field.pop("sections", None)
        for card in tree.get("physics", {}).get("cards", []):
            card["units"] = [{"type": "learn", "ref": "test-deep"}] if physics and card["label"] == "A" else []
            card.pop("sections", None)
        path = yaml.safe_dump(tree, allow_unicode=True, sort_keys=False)
        extra = {
            "content/learn/path.yaml": path,
            "content/learn/basics/test-page.md": f"---\ntitle: 試験の学習ページ\nfield: basics\ndescription: 試験用の説明である。\n"
                                                 f"published_at: '2026-01-01'\nai_generated: true\nrelated_terms: [cmp]\n{src}---\n"
                                                 f"## 一つ目の節\n\n試験用の本文である[S1]。\n\n{quiz}",
            "src/figures/learn/basics/test-page.astro": '<figure class="learn-figure-test"><svg role="img" aria-label="試験の図" viewBox="0 0 10 10"></svg><figcaption>図：試験の図。模式図、本サイトで作成</figcaption></figure>\n',
        }
        if physics:
            extra.update({
                "content/learn/solid-state/test-deep.md": f"---\ntitle: 試験の深掘りページ\nfield: solid-state\ndescription: 試験用の深掘りの説明である。\n"
                                                          f"published_at: '2026-01-01'\nai_generated: true\napplies_to:\n"
                                                          f"  - {{ type: learn, ref: test-page, folder: basics, note: 試験の現れ方である。 }}\n"
                                                          f"  - {{ type: process, ref: {slug}, note: 工程での現れ方である。 }}\n{src}---\n"
                                                          f"## 式\n\n$$n_i \\propto \\exp\\left(-\\frac{{E_g}}{{2kT}}\\right)$$\n\n"
                                                          f"$E_g$ はバンドギャップである[S1]。\n\n## 式のどこを見るか\n\n指数の中を見る。\n\n"
                                                          f"## 数値例\n\n試験の数値例である。\n\n{quiz}",
                "src/figures/learn/solid-state/test-deep.astro": '<figure><svg role="img" aria-label="試験の図" viewBox="0 0 10 10"></svg><figcaption>図。模式図、本サイトで作成</figcaption></figure>\n',
            })
        return self.build_with("learn-physics" if physics else "learn", env, glossary=glossary, extra=extra)

    def test_learn_index_page_and_quiz(self):
        # 半導体を学ぶ（FR-901、FR-904）：一覧に分野と単元、学習のページに図・本文・理解度チェック、トップの入口は /learn/ へ
        dist = self.learn_site()
        index = self.read(dist, "learn/index.html")
        self.assertIn("1. 半導体の基礎", index)
        self.assertIn('href="/learn/basics/"', index)  # 一覧には基礎編の9分野の入口を並べ、分野のページへ進む（仕様書 8.18）
        basic = index.split('id="tier-basic"')[1].split('id="tier-physics"')[0]
        self.assertEqual(len(re.findall(r'class="learn-field-entry[ "]', basic)), 9)
        self.assertIn("前提知識", basic)  # 段ごとに、対象・前提知識・読む順を示す
        self.assertIn("1から順に読むのがおすすめ", basic)
        physics = index.split('id="tier-physics"')[1].split("</main>")[0]  # 基礎編の下に、深掘り編「半導体の物理」のカード
        self.assertIn("半導体の物理", physics)
        self.assertIn("A. 固体物理学", physics)
        # 単元のない分野・カードは、リンクにせず、名前の横に「準備中」と示す（押す前に分かるように）
        self.assertNotIn('href="/learn/solid-state/"', physics)
        self.assertNotIn('href="/learn/industry/"', index.split("<main")[1])
        self.assertIn("（準備中）", basic.split("9. 工場と業界")[1].split("</div>")[0])
        start = index.split('class="learn-start"')[1].split("</div>")[0]  # 初めての人の始め方：基礎編の最初のページへ
        self.assertIn('href="/learn/basics/test-page/"', start)
        self.assertIn("初めての方は", start)
        field = self.read(dist, "learn/basics/index.html")
        self.assertIn('href="/learn/basics/test-page/"', field)
        self.assertIn("次の分野：", field)
        self.assertIn("この分野のページは、準備中です。", self.read(dist, "learn/industry/index.html"))
        page = self.read(dist, "learn/basics/test-page/index.html")
        self.assertIn("learn-figure-test", page)
        self.assertIn('href="/learn/basics/"', page)  # パンくずリストの分野は、分野のページへ
        self.assertNotIn("さらに深く", page)  # 深掘り編のページがないときは、枠を出さない（準備中とも書かない）
        quiz = re.findall(r'<section class="quiz"[^>]*data-quiz[^>]*>(.*?)</section>', page, re.S)[0]
        self.assertEqual(quiz.count('data-choice='), 4)
        self.assertIn('data-answer="3"', page)
        self.assertIn("答えと解説を見る", quiz)  # JavaScriptがなくても読める
        self.assertNotIn("答え：3", page.split('<section class="quiz"')[0])  # 理解度チェックの行は、本文の節に出さない
        home = self.read(dist, "index.html")
        self.assertIn('href="/learn/"', home.split("<main")[1])
        term = self.read(dist, "glossary/cmp/index.html")
        self.assertIn('data-quiz data-page-type="term"', term)

    def test_learn_physics_tier(self):
        # 深掘り編「半導体の物理」（運用ルール書 4.2、仕様書 8.18）：式は MathML、本文の後に「基礎編のどこに効くか」、
        # 効く先の基礎編のページと工程ページに「さらに深く」。学習の順は基礎編と別（基礎編から深掘り編へは進まない）
        slug = self.processes[0]["slug"]
        dist = self.learn_site(physics=True)
        deep = self.read(dist, "learn/solid-state/test-deep/index.html")
        self.assertIn('class="math-display"', deep)
        self.assertNotIn("$$", deep)
        self.assertGreaterEqual(deep.count("<math"), 2)  # 行の式と、文の中の式
        self.assertNotIn('display="block"', deep)  # 行の式も中央揃えにしない
        applies = deep.split('id="applies"')[1].split("</section>")[0]
        self.assertIn('href="/learn/basics/test-page/"', applies)
        self.assertIn("試験の現れ方である。", applies)
        self.assertIn(f'href="/processes/{slug}/"', applies)
        self.assertIn("半導体の物理", deep.split('aria-label="パンくずリスト"')[1].split("</nav>")[0])
        self.assertNotIn('href="/companies/"', deep.split('id="next-read"')[1].split("</nav>")[0] if 'id="next-read"' in deep else "")
        base = self.read(dist, "learn/basics/test-page/index.html")
        deeper = base.split('id="deeper"')[1].split("</aside>")[0]
        self.assertIn('href="/learn/solid-state/test-deep/"', deeper)
        self.assertIn("A. 固体物理学", deeper)
        self.assertNotIn("/learn/solid-state/", base.split('id="next-read"')[1].split("</nav>")[0])  # 基礎編の順は、深掘り編へ進まない
        self.assertNotIn("<math", base)  # 基礎編のページの本文は、式にしない
        self.assertIn('href="/learn/solid-state/test-deep/"', self.read(dist, f"processes/{slug}/index.html").split('id="deeper"')[1])
        card = self.read(dist, "learn/solid-state/index.html")
        self.assertIn("A. 固体物理学", card)
        self.assertIn("次の分野：", card)  # カードの前後は、同じ段（深掘り編）の中だけ
        self.assertIn('href="/learn/device-physics/"', card.split('class="learn-field-nav"')[1])
        self.assertNotIn('href="/learn/industry/"', card.split('class="learn-field-nav"')[1])

    def learnpath_site(self) -> Path:
        slug = self.processes[0]["slug"]
        tree = yaml.safe_load((ROOT / "content" / "learn" / "path.yaml").read_text(encoding="utf-8"))
        for field in tree["fields"]:
            # 分野2には、別のフォルダ（devices）のページを folder で並べる。分野4は、小分け（sections）の中に工程を並べる
            field.pop("sections", None)
            field["units"] = {"basics": [{"type": "learn", "ref": "path-a"}],
                              "materials": [{"type": "learn", "ref": "path-b", "folder": "devices"}]}.get(field["slug"], [])
            if field["slug"] == "process":
                field["sections"] = [{"slug": "front-end", "title": "試験の小分け", "units": [{"type": "process", "ref": slug}]}]
        def page(field: str, name: str) -> str:
            return (f"---\ntitle: {name}\nfield: {field}\ndescription: 試験用の説明である。\npublished_at: '2026-01-01'\nai_generated: true\n"
                    f"sources:\n  - id: S1\n    title: 例\n    publisher: 例\n    url: https://example.com/a\n    accessed_on: '2026-01-01'\n"
                    f"---\n## 節\n\n試験用の本文である[S1]。\n")
        figure = '<figure><svg role="img" aria-label="図" viewBox="0 0 10 10"></svg><figcaption>図。模式図、本サイトで作成</figcaption></figure>\n'
        extra = {"content/learn/path.yaml": yaml.safe_dump(tree, allow_unicode=True, sort_keys=False)}
        for name in [p.relative_to(ROOT).as_posix() for p in (ROOT / "content" / "learn").glob("*/*.md")]:
            extra[name] = "---\ntitle: 下書き\nfield: x\ndescription: 下書き\ndraft: true\npublished_at: '2026-01-01'\nai_generated: true\n---\n## 節\n\n下書き。\n"
        extra.update({"content/learn/basics/path-a.md": page("basics", "試験の一つ目"), "content/learn/devices/path-b.md": page("devices", "試験の二つ目"),
                      "src/figures/learn/basics/path-a.astro": figure, "src/figures/learn/devices/path-b.astro": figure})
        return self.build_with("learnpath", "production", extra=extra)

    def test_learn_path_can_be_followed_to_the_end(self):
        # 要件定義書 AT-09：最初のページから、次の案内だけで最後までたどれ、最後に業績とニュース解説の入口に着く。
        # 分野の境目では次の分野の最初のページへ、学習の順に入った工程ページにも学習の前後を出す
        slug = self.processes[0]["slug"]
        dist = self.learnpath_site()
        first = self.read(dist, "learn/basics/path-a/index.html")
        self.assertIn("次の分野（2. 半導体材料とウェーハ）の最初のページ：", first)
        self.assertIn('href="/learn/devices/path-b/"', first)
        second = self.read(dist, "learn/devices/path-b/index.html")
        self.assertIn("前の分野（1. 半導体の基礎）の最後のページ：", second)
        self.assertIn("半導体材料とウェーハ", second.split('aria-label="パンくずリスト"')[1].split("</nav>")[0])  # パンくずは並べた分野（フォルダの devices ではない）
        index = self.read(dist, "learn/process/index.html")
        self.assertIn("試験の小分け", index)
        self.assertIn(f'href="/processes/{slug}/"', index.split('id="section-front-end"')[1])
        self.assertIn(f'href="/processes/{slug}/"', second.split('id="next-read"')[1])
        last = self.read(dist, f"processes/{slug}/index.html")
        nav = last.split('id="learn-order"')[1].split("</nav>")[0]
        self.assertIn("半導体を学ぶの順で読む", last)
        self.assertIn('href="/learn/devices/path-b/"', nav)
        self.assertIn('href="/companies/"', nav)
        self.assertIn('href="/news/"', nav)
        other = next(p["slug"] for p in self.processes[1:])
        self.assertNotIn('id="learn-order"', self.read(dist, f"processes/{other}/index.html"))  # 学習の順にない工程には出さない

    def events_site(self) -> Path:
        events = [{"id": f"e{i}", "name": f"試験の展示会{i}", "kind": "exhibition", "start_date": f"2099-0{i}-10", "end_date": f"2099-0{i}-12",
                   "venue": "試験の会場", "city": "東京都", "organizer": "試験の主催者", "url": f"https://example.org/{i}", "source": "S1",
                   "checked_on": "2098-12-01"} for i in range(1, 8)]
        events.append({**events[0], "id": "past", "name": "終わった展示会", "start_date": "2000-01-01", "end_date": "2000-01-02"})
        data = {"schema_version": 1, "sources": [{"id": "S1", "title": "公式", "publisher": "主催者", "url": "https://example.org/",
                                                   "accessed_on": "2098-12-01"}], "events": events}
        return self.build_with("events", "production", extra={"data/events.yaml": yaml.safe_dump(data, allow_unicode=True, sort_keys=False)})

    def test_home_lists_upcoming_events_only(self):
        # 近く開かれる技術系のイベント（要件定義書 3.3 の5）：終わったものは出さず、開催日の近い順に最大5件
        dist = self.events_site()
        main = self.read(dist, "index.html").split("<main")[1]
        self.assertIn("近く開かれるイベント", main)
        self.assertEqual(main.count('class="home-events__item"'), 5)
        self.assertNotIn("終わった展示会", main)
        self.assertLess(main.index("試験の展示会1"), main.index("試験の展示会2"))
        self.assertIn("2099年1月10日〜12日", main)
        self.assertIn("出典：各主催者の公式ページ", main)

    def test_process_pages_have_figures(self):
        # 工程の図（仕様書 7章）：src/figures/process/{slug}.astro がある工程は、その図を解説の最初に出す。図の説明（figcaption）を必ず付ける
        dist = self.build("production")
        for slug in ("etching", "deposition", "cmp", "dicing", "wafer", "cleaning", "circuit-design", "packaging", "final-test"):
            html = self.read(dist, f"processes/{slug}/index.html")
            figure = re.findall(r'<figure class="fig"[^>]*>(.*?)</figure>', html, re.S)
            self.assertTrue(figure, slug)
            self.assertIn('role="img"', figure[0], slug)
            self.assertIn("模式図、本サイトで作成", figure[0], slug)

    def test_term_pages_have_figures(self):
        # 用語の図（仕様書 7章、9.5）：src/figures/term/{slug}.astro がある用語は、短い定義の後、解説の前に図を出す
        dist = self.build("production")
        for slug in ("euv", "chiplet", "wire-bonding"):
            html = self.read(dist, f"glossary/{slug}/index.html")
            figure = re.findall(r'<figure class="fig"[^>]*>(.*?)</figure>', html, re.S)
            self.assertTrue(figure, slug)
            self.assertIn("模式図、本サイトで作成", figure[0], slug)
            self.assertLess(html.index('<figure class="fig"'), html.index('id="related"'), slug)

    def nolearn_site(self) -> Path:
        def work():
            site = make_site()
            for page in (site / "content" / "learn").glob("*/*.md"):
                page.unlink()
            return site
        return self._built("nolearn-production", "production", work)

    def theme_site(self, env: str) -> Path:
        """テーマ2件（公開1件、下書き1件）と、公開したテーマのタグを付けたニュース1件を置いた、作業用のコピーで組み立てる（仕様書 9.9）。"""
        front = theme_front(draft=False, learn=[{"folder": "power", "ref": "diode"}], processes=["advanced-packaging"])
        front["groups"][0]["companies"] += [{"company": "adeka", "role": "封止に使う材料を作る。", "basis": ["S2"]},
                                            {"company": "disco", "role": "ウェーハを薄く削る装置を作る。", "basis": ["S2"]}]
        draft = theme_front(theme="data-center", title="データセンターと半導体（下書き）", draft=True)
        dump = lambda f, body=THEME_BODY: "---\n" + yaml.safe_dump(f, allow_unicode=True, sort_keys=False) + "---\n" + body
        real = sorted((ROOT / "content" / "news").glob("*.md"))[0]
        news = {real.name: real.read_text(encoding="utf-8").replace("  themes: []", "  themes:\n  - generative-ai")}
        return self.build_with("themes", env, news=news,
                               extra={"content/themes/generative-ai.md": dump(front), "content/themes/data-center.md": dump(draft),
                                      "src/figures/theme/generative-ai-market.astro": '<figure id="fig-theme-market"></figure>\n',
                                      "src/figures/theme/generative-ai-value-chain.astro": '<figure id="fig-theme-chain"></figure>\n'})

    def test_theme_pages(self):
        # テーマの一覧とテーマのページ（仕様書 9.9、FR-602）：掲載企業は証券コードの順、外の企業は後ろで名前と国・地域だけ（リンクなし）
        dist = self.theme_site("production")
        listing = self.read(dist, "themes/index.html").split("<main")[1]
        self.assertIn('href="/themes/generative-ai/"', listing)
        self.assertIn("関連する企業 4社", listing)
        self.assertNotIn("data-center", listing)  # 下書きは本番に出さない
        self.assertFalse((dist / "themes" / "data-center" / "index.html").exists())
        page = self.read(dist, "themes/generative-ai/index.html").split("<main")[1]
        # レポートの並び（仕様書 9.9）：要旨 → 市場の動き（グラフ）→ バリューチェーン（図）→ 日本企業の位置（基準と企業）→ 論点
        marks = ['class="summary"', 'id="s1"', 'id="fig-theme-market"', 'id="s2"', 'id="fig-theme-chain"', 'id="s3"',
                 "このページに載せる企業", 'href="/companies/adeka/"', "発表元の見方", "本サイトの見方", "投資の判断の材料ではありません"]
        at = [page.index(m) for m in marks]
        self.assertEqual(at, sorted(at), "レポートの並びが仕様書 9.9 と違う")
        self.assertIn("このページに載せる企業", page)
        self.assertIn("HBMの積層と検査", page)
        order = [page.index(f'href="/companies/{slug}/"') for slug in ("adeka", "disco", "advantest")]
        self.assertEqual(order, sorted(order), "掲載企業が証券コードの順でない")
        self.assertLess(order[-1], page.index("SKハイニックス"))
        self.assertIn("韓国", page)
        self.assertIn("準備中", page)  # Coming Soon の企業（adeka）
        self.assertIn('href="/processes/advanced-packaging/"', page)
        self.assertIn('href="/learn/power/diode/"', page)
        self.assertIn("このテーマのニュース", page)
        self.assertIn('href="/disclaimer/"', page)
        self.assertNotIn("注目銘柄", page)
        news = sorted((dist / "news").glob("*/*/*/index.html"))
        self.assertTrue(any('href="/themes/generative-ai/"' in n.read_text(encoding="utf-8") for n in news), "ニュースにテーマのタグがない")
        index = json.loads(self.read(dist, "search-index.json"))
        self.assertTrue(any(e["type"] == "theme" and e["url"] == "/themes/generative-ai/" for e in index))

    def test_theme_draft_is_built_in_preview(self):
        dist = self.theme_site("preview")
        self.assertTrue((dist / "themes" / "data-center" / "index.html").exists())

    def test_empty_theme_list(self):
        html = self.read(self.build_empty("preview"), "themes/index.html").split("<main")[1]
        self.assertIn("テーマのページは、まだありません", html)

    def test_learn_index_without_pages_keeps_glossary_entry(self):
        # 学習のページが1つもない間は、トップの入口を用語集へ（要件定義書 3.3）。リポジトリの学習のページは公開済みのため、
        # 作業用のコピーから content/learn/{分野}/*.md を除いて確かめる
        html = self.read(self.nolearn_site(), "index.html").split("<main")[1]
        self.assertIn('href="/glossary/"', html)
        self.assertNotIn('href="/learn/"', html)

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
        self.assertNotIn("card", html.split("<main")[1].lower().replace("discard", ""))  # 一覧はカードの格子にしない（head の twitter:card は対象外）

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
        self.assertEqual(headings[3:], ["関係する企業・工程", "出典", "知りたいことは分かりましたか？"])  # 末尾に疑問の解決ボタン（FR-709）
        self.assertIn('href="#source-1"', html)  # 本文の [S1] は、出典の1番へのリンク
        self.assertIn('id="source-1"', html)
        self.assertIn(f'href="/companies/{self.companies[0]["slug"]}/"', html)
        self.assertIn(f'href="/processes/{self.processes[0]["slug"]}/"', html)
        self.assertIn('href="/news/"', html)  # パンくず
        # 点と海外の印は、画面に出さない（仕様書に表示の指定がない）
        for hidden in ("overseas", "impact", "reliability", "重要度"):
            self.assertNotIn(hidden, html)
        self.assertNotIn("AIが下書き", html)  # AI作成の表示は、どのページにも出さない（運営者の判断）

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


def _prefetch() -> None:
    """読み込みの時点で、必要な組み立てを先に始める（DESIGN_PREFETCH=0 で止める）。"""
    if HAS_NODE and os.environ.get("DESIGN_PREFETCH") != "0":
        for env in ("preview", "production"):
            _real_future(env)
        PagesBuildTest.prefetch()
        # test_design.py の下書きのコピー（企業の組み合わせは、そのテストと同じにする）
        for env, slugs in (("preview", ("tokyo-electron", "jasm")), ("production", ("tokyo-electron", "jasm")),
                           ("preview", ("tokyo-electron", "sony", "screen"))):
            _draft_future(env, slugs)


_prefetch()


if __name__ == "__main__":
    unittest.main()

"""デザインの基盤の確認（画面とデザインの仕様書 13章の1〜3）：値、stylelintの禁止、メニューの設定、プレビュー専用のページ。"""

import colorsys
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TOKENS = (ROOT / "src" / "styles" / "tokens.css").read_text(encoding="utf-8")
HAS_NODE = shutil.which("npx") is not None and (ROOT / "node_modules" / "stylelint").is_dir()


def variables(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for m in re.finditer(r"^\s*(--[a-z0-9-]+):\s*([^;]+);", text, re.M):
        found.setdefault(m.group(1), m.group(2).strip())  # 最初の値（画面の幅で上書きする値は含めない）
    return found


V = variables(TOKENS)

# 仕様書 4章の値
SPEC_COLORS = {
    "--color-bg": "#fbfaf6", "--color-surface": "#ffffff", "--color-surface-sunken": "#f2f4f2", "--color-text": "#1b2a2c",
    "--color-text-muted": "#4a5b5e", "--color-primary": "#0b4f54", "--color-primary-hover": "#083b3f",
    "--color-primary-tint": "#e8f1f0", "--color-visited": "#3d5f61", "--color-accent": "#b7791f",
    "--color-accent-text": "#8a5a12", "--color-border": "#c9d3d3", "--color-border-strong": "#6b7c7e",
    "--color-focus": "#0b4f54", "--color-warning-bg": "#fff4e0", "--color-error": "#b42318",
    "--color-error-bg": "#fdecea", "--color-success": "#1e6b3a", "--chart-single": "#0b4f54",
    "--chart-highlight": "#0b4f54", "--chart-other": "#9aa7a8", "--chart-cat-1": "#008c7a", "--chart-cat-2": "#c2550a",
    "--chart-cat-3": "#4a7bd0", "--chart-cat-4": "#c2a000", "--chart-grid": "#e3e8e8", "--chart-axis": "#6b7c7e",
}


def stylelint(css: str, filename: str = "src/components/x.css") -> subprocess.CompletedProcess:
    return subprocess.run(["npx", "stylelint", "--stdin-filename", filename], input=css, text=True,
                          capture_output=True, cwd=ROOT)


class TokensTest(unittest.TestCase):
    def test_colors_match_the_specification(self):
        for name, value in SPEC_COLORS.items():
            with self.subTest(name):
                self.assertEqual(V.get(name), value)

    def test_no_purple_or_violet_colors(self):
        for name, value in V.items():
            if re.fullmatch(r"#[0-9a-f]{6}", value):
                r, g, b = (int(value[i:i + 2], 16) / 255 for i in (1, 3, 5))
                hue, _, saturation = colorsys.rgb_to_hls(r, g, b)
                if saturation > 0.15:
                    self.assertFalse(255 <= hue * 360 <= 330, f"{name} {value} は紫・青紫の色相")

    def test_text_scale_has_seven_steps_and_two_weights(self):
        steps = sorted(m.group(1) for k in V for m in [re.fullmatch(r"--text-(h1|h2|h3|lead|body|dense|small)", k)] if m)
        self.assertEqual(steps, sorted(["h1", "h2", "h3", "lead", "body", "dense", "small"]))
        self.assertEqual((V["--font-weight-normal"], V["--font-weight-bold"]), ("400", "700"))
        self.assertEqual((V["--text-body"], V["--text-body-leading"], V["--text-small"], V["--text-dense"]),
                         ("1.0625rem", "1.85", "0.875rem", "0.9375rem"))

    def test_h1_is_smaller_on_smartphones_only(self):
        self.assertEqual(V["--text-h1"], "1.75rem")
        self.assertRegex(TOKENS, r"@media \(--tablet\) \{\s*:root \{\s*--text-h1: 2rem;")

    def test_eight_spaces(self):
        self.assertEqual([V[f"--space-{i}"] for i in range(1, 9)],
                         ["0.25rem", "0.5rem", "0.75rem", "1rem", "1.5rem", "2rem", "3rem", "4rem"])
        self.assertNotIn("--space-9", V)

    def test_layout_borders_and_radius(self):
        expected = {"--layout-max-width": "68rem", "--content-max-width": "40rem", "--aside-width": "16rem",
                    "--border-width": "1px", "--border-width-accent": "4px", "--border-width-focus": "3px",
                    "--focus-offset": "2px", "--radius-control": "2px", "--radius-none": "0", "--target-min": "2.75rem",
                    "--bp-tablet": "768px", "--bp-pc": "1024px"}
        for name, value in expected.items():
            self.assertEqual(V.get(name), value, name)

    def test_breakpoints_css_matches_the_variables(self):
        text = (ROOT / "src" / "styles" / "breakpoints.css").read_text(encoding="utf-8")
        self.assertIn(f"@custom-media --tablet (min-width: {V['--bp-tablet']});", text)
        self.assertIn(f"@custom-media --pc (min-width: {V['--bp-pc']});", text)


class SourceRulesTest(unittest.TestCase):
    def astro_files(self):
        return list((ROOT / "src").rglob("*.astro"))

    def test_no_inline_style_attributes_or_inline_scripts(self):
        for path in self.astro_files():
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"<[^<>]*\sstyle=", f"{path.name} に style 属性がある")
            for body in re.findall(r"<script[^>]*>(.*?)</script>", text, re.S):
                self.assertTrue(body.strip().startswith("import "), f"{path.name} に、ページに埋め込むスクリプトがある")

    def test_no_direct_colors_in_components(self):
        for path in self.astro_files():
            self.assertNotRegex(path.read_text(encoding="utf-8"), r"(?<![&\w#])#[0-9a-fA-F]{6}\b", path.name)


@unittest.skipUnless(HAS_NODE, "node_modules（stylelint）がない")
class StylelintTest(unittest.TestCase):
    def rejected(self, css):
        return stylelint(css).returncode != 0

    def test_valid_css_passes(self):
        css = ('.a {\n  padding: var(--space-3) var(--space-5);\n  color: var(--color-text);\n'
               '  border: var(--border-width) solid var(--color-border);\n  font-size: var(--text-dense);\n  width: 100%;\n'
               '  margin: 0;\n  background: transparent;\n  transition: transform var(--motion-duration);\n}\n'
               '@media (--pc) {\n  .a {\n    display: none;\n  }\n}\n')
        done = stylelint(css)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_direct_colors_are_rejected(self):
        for value in ("#0b4f54", "#fff", "rgb(0 0 0)", "rgba(0, 0, 0, .5)", "hsl(180 50% 30%)", "oklch(50% 0.1 200)",
                      "red", "purple", "rebeccapurple", "indigo"):
            with self.subTest(value):
                self.assertTrue(self.rejected(f".a {{ color: {value}; }}\n"))
        self.assertTrue(self.rejected(".a { border: var(--border-width) solid #000; }\n"))

    def test_direct_sizes_spaces_and_times_are_rejected(self):
        for decl in ("padding: 8px", "margin: 1rem 0", "margin-top: -0.5rem", "width: 20em", "gap: 12px", "font-size: 14px",
                     "font-size: 1rem", "font-weight: 700", "line-height: 1.5", "letter-spacing: 0.02em",
                     "height: 100vh", "border-width: 2px", "border-radius: 4px", "transition: color 0.2s",
                     "outline-offset: 2px"):
            with self.subTest(decl):
                self.assertTrue(self.rejected(f".a {{ {decl}; }}\n"))

    def test_gradients_shadows_blur_italic_center_and_purple_are_rejected(self):
        for decl in ("background: linear-gradient(var(--color-bg), var(--color-surface))",
                     "background-image: radial-gradient(circle, var(--color-bg), var(--color-surface))",
                     "box-shadow: var(--border-width) var(--border-width) var(--color-border)", "text-shadow: none",
                     "backdrop-filter: blur(var(--space-2))", "-webkit-backdrop-filter: blur(var(--space-2))",
                     "filter: blur(var(--space-2))", "filter: drop-shadow(var(--space-1) var(--space-1) var(--color-border))",
                     "font-style: italic", "text-align: center", "color: violet"):
            with self.subTest(decl):
                self.assertTrue(self.rejected(f".a {{ {decl}; }}\n"))

    def test_media_queries_must_use_the_named_breakpoints(self):
        self.assertTrue(self.rejected("@media (min-width: 768px) { .a { display: none; } }\n"))
        self.assertTrue(self.rejected("@media (max-width: 40rem) { .a { display: none; } }\n"))

    def test_astro_style_blocks_are_checked(self):
        astro = '---\n---\n<p class="a">x</p>\n<style>\n  .a { color: #123456; padding: 8px; }\n</style>\n'
        self.assertNotEqual(stylelint(astro, "src/components/X.astro").returncode, 0)

    def test_tokens_css_is_exempt(self):
        done = stylelint(":root { --a: #123456; --b: 8px; }\n", "src/styles/tokens.css")
        self.assertEqual(done.returncode, 0, done.stdout)

    def test_the_repository_css_passes(self):
        done = subprocess.run(["npm", "run", "lint:css"], text=True, capture_output=True, cwd=ROOT)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


class PreviewFixesTest(unittest.TestCase):
    """プレビューの確認で見つかった点の直し（変更案 #112 の追加のコミット）。見た目そのものは、ブラウザで確かめる。"""

    def read(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_lead_text_uses_the_heading_wrapping_rule(self):
        css = self.read("src/styles/global.css")
        block = re.search(r"\.lead \{(.*?)\}", css, re.S).group(1)
        self.assertIn("word-break: auto-phrase", block)
        self.assertIn("text-wrap: balance", block)
        self.assertIn("lead", self.read("src/pages/index.astro"))
        self.assertIn("lead", self.read("src/components/KeyPoints.astro"))

    def test_table_first_column_has_a_width_range_and_wraps(self):
        self.assertIn("--table-first-column-min", V)
        self.assertIn("--table-first-column-max", V)
        css = self.read("src/components/DataTable.astro")
        first = re.search(r"\.data-table \.is-first \{(.*?)\}", css, re.S).group(1)
        for needle in ("min-width: var(--table-first-column-min)", "max-width: var(--table-first-column-max)", "white-space: normal"):
            self.assertIn(needle, first)

    def test_menu_button_is_an_opening_mark_with_aria_expanded(self):
        header = self.read("src/components/Header.astro")
        self.assertIn('aria-expanded="false"', header)
        self.assertIn('name="chevron-down"', header)
        self.assertNotIn('name="chevron" ', header)
        self.assertIn("scripts/menu", header)
        self.assertIn("aria-expanded", self.read("src/scripts/menu.ts"))

    def test_header_height_and_logo_sizes_are_tokens(self):
        for name in ("--header-height-sp", "--logo-size", "--logo-size-sp"):
            self.assertIn(name, V)

    def test_aside_has_one_sticky_group_and_no_sticky_toc(self):
        page = self.read("src/layouts/Page.astro")
        self.assertIn("page__aside-sticky", page)
        self.assertEqual(page.count("position: sticky"), 1)
        toc = re.sub(r"/\*.*?\*/|//[^\n]*|<!--.*?-->", "", self.read("src/components/Toc.astro"), flags=re.S)
        self.assertNotIn("sticky", toc)

    def test_hit_areas_are_taken_by_a_transparent_after_not_by_row_spacing(self):
        for rel in ("src/components/Footer.astro", "src/components/Toc.astro"):
            css = self.read(rel)
            self.assertRegex(css, r"a::after \{[^}]*height: var\(--target-min\)")
            self.assertNotRegex(css, r"a \{[^}]*min-height: var\(--target-min\)")

    def test_screen_guidance_is_in_polite_form(self):
        for rel in ("src/pages/404.astro", "src/pages/index.astro", "src/components/StateMessage.astro",
                    "src/components/PendingNotice.astro", "src/components/Button.astro", "src/components/Notice.astro"):
            text = re.sub(r"<!--.*?-->|/\*.*?\*/|^\s*//.*$", "", self.read(rel), flags=re.S | re.M)
            self.assertNotRegex(text, r"(ある|いる|ない|する|した|できる|れる)。<", rel)


class CompanyPageSourceTest(unittest.TestCase):
    def read(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_no_literal_amounts_in_the_page_and_chart_code(self):
        for rel in ("src/pages/companies/[slug].astro", "src/lib/companies.ts", "src/lib/chart.ts", "src/components/Chart.astro",
                    "src/components/ChartSvg.astro"):
            self.assertNotRegex(self.read(rel), r"\d{1,3}(,\d{3})+", f"{rel} に、数値が直接書かれている")

    def test_chart_colors_yaml_uses_existing_variables_only(self):
        data = yaml.safe_load(self.read("config/chart-colors.yaml"))
        names = [v["color"] for v in [*data["segment_classification"].values(), *data["metrics"].values()]]
        for name in names:
            self.assertIn(name, V)
        self.assertEqual(set(data["segment_classification"]), {"semiconductor", "partial", "excluded"})
        self.assertEqual(data["segment_classification"]["semiconductor"]["color"], "--chart-highlight")
        self.assertEqual(data["segment_classification"]["excluded"]["color"], "--chart-other")
        self.assertTrue(data["segment_classification"]["excluded"]["pattern"])

    def test_charts_get_title_unit_period_and_source(self):
        chart = self.read("src/components/Chart.astro")
        for needle in ("title: string", "unit: string", "period: string", "source:", "表で見る", "SourceLine"):
            self.assertIn(needle, chart)

    def test_numbers_with_units_do_not_wrap_and_budoux_is_used(self):
        self.assertRegex(self.read("src/lib/phrase.ts"), r"億円\|百万円")
        self.assertIn("budoux", self.read("src/lib/phrase.ts"))
        self.assertIn("nowrap", self.read("src/components/RichText.astro"))
        self.assertIn("white-space: nowrap", self.read("src/components/KeyPoints.astro"))
        self.assertIn("auto-phrase", self.read("src/styles/global.css"))  # auto-phrase は残す


class MenuTest(unittest.TestCase):
    def test_menu_yaml(self):
        data = yaml.safe_load((ROOT / "config" / "menu.yaml").read_text(encoding="utf-8"))
        self.assertEqual([(i["label"], i["path"]) for i in data["main"]],
                         [("企業", "/companies/"), ("工程", "/processes/"), ("ニュース", "/news/")])
        for item in [*data["main"], *(link for g in data["footer"] for link in g["links"])]:
            self.assertRegex(item["path"], r"^/[a-z0-9/-]*/$")
        paths = {link["path"] for g in data["footer"] for link in g["links"]}
        for required in ("/faq/", "/corrections/", "/about/roadmap/", "/policy/", "/privacy/", "/disclaimer/",
                         "/external-transmission/", "/editorial-policy/", "/contact/", "/about/"):
            self.assertIn(required, paths)  # 要件定義書 3.1、3.2 のフッターのリンク


@unittest.skipUnless(HAS_NODE, "node_modules がない")
class BuildTest(unittest.TestCase):
    def build(self, env: str) -> Path:
        out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, out, True)
        done = subprocess.run(["npx", "astro", "build", "--outDir", str(out / "dist")], text=True, capture_output=True,
                              cwd=ROOT, env={**os.environ, "BUILD_ENV": env})
        self.assertEqual(done.returncode, 0, done.stdout[-1500:] + done.stderr[-1500:])
        return out / "dist"

    def test_component_page_only_in_preview(self):
        preview = self.build("preview")
        page = preview / "dev" / "components" / "index.html"
        self.assertTrue(page.is_file())
        html = page.read_text(encoding="utf-8")
        self.assertIn('name="robots" content="noindex, nofollow"', html)
        self.assertRegex(html, r'<header class="[^"]*site-header')
        self.assertRegex(html, r'<footer class="[^"]*site-footer')
        self.assertNotRegex(html, r"<script>[^<]")  # スクリプトは、ファイルとして出力する（CSP）
        self.assertNotRegex(html, r"<style")  # CSSも、ファイルとして出力する
        production = self.build("production")
        self.assertFalse((production / "dev").exists())
        self.assertTrue((production / "index.html").is_file())

    def test_pages_have_the_frame_and_menu_in_config_order(self):
        dist = self.build("preview")
        for path in dist.rglob("*.html"):
            html = path.read_text(encoding="utf-8")
            self.assertIn('class="skip-link"', html, path.name)
            self.assertIn("site-footer", html, path.name)
        html = (dist / "index.html").read_text(encoding="utf-8")
        self.assertEqual(html.count("<h1"), 1)
        self.assertRegex(html, r"企業</a>.*工程</a>.*ニュース</a>")


@unittest.skipUnless(HAS_NODE, "node_modules がない")
class CompanyPageBuildTest(BuildTest):
    def page(self, dist, slug):
        return (dist / "companies" / slug / "index.html").read_text(encoding="utf-8")

    def test_detailed_in_preview_and_coming_soon_in_production(self):
        preview = self.build("preview")
        html = self.page(preview, "tokyo-electron")
        self.assertIn('class="chart-svg', html)
        self.assertIn("表で見る", html)
        self.assertIn('aria-pressed="false"', html)
        self.assertIn("<wbr>", html)  # 文節の切れ目（BudouX）
        self.assertIn("class=\"nowrap\"", html)
        self.assertIn("下書きです", html)
        self.assertIn('name="robots" content="noindex, nofollow"', html)  # draft: true は、検索に登録させない
        for needle in ("事業概要", "工程上の位置づけ", "業績", "IR重要ポイント", "働く環境", "ニュース", "資料", "出典"):
            self.assertIn(needle, html)
        # 数値は data/auto から（百万円 → 億円、小数第1位に四捨五入）
        import json
        from decimal import ROUND_HALF_UP, Decimal
        auto = json.loads((ROOT / "data" / "auto" / "tokyo-electron.json").read_text(encoding="utf-8"))
        latest = [r for r in auto["financials"] if r["period_type"] == "annual"][-1]
        expected = Decimal(latest["net_sales"]["value"]) / 100
        text = f"{expected.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP):,}億円"
        self.assertIn(text, html)
        self.assertRegex(html, r">0</text>")  # 金額の縦軸は0から
        # セグメントの対応表がない企業は、状態の表示
        self.assertIn("セグメント別の売上のグラフは、まだありません", html)
        # 外資系日本法人（事業概要も業績もない）は、プレビューでも Coming Soon
        jasm = self.page(preview, "jasm")
        self.assertIn("Coming Soon", jasm)
        self.assertNotIn('class="chart-svg', jasm)
        self.assertIn('name="robots" content="noindex, nofollow"', jasm)
        production = self.build("production")
        html = self.page(production, "tokyo-electron")
        self.assertIn("Coming Soon", html)
        self.assertNotIn('class="chart-svg', html)
        self.assertNotIn("下書きです", html)
        self.assertIn('name="robots" content="noindex, nofollow"', html)
        self.assertIn('href="/about/roadmap/"', html)
        self.assertNotIn("売上高", html.split("<main")[1])  # 業績を出さない
        self.assertEqual(len(list((production / "companies").glob("*/index.html"))), len(list((ROOT / "data" / "companies").glob("*.yaml"))))

    def test_component_page_has_every_chart_kind(self):
        html = (self.build("preview") / "dev" / "components" / "index.html").read_text(encoding="utf-8")
        self.assertGreaterEqual(html.count('class="chart-svg chart-svg--wide'), 5)
        for needle in ("縦の棒", "積み上げの縦の棒", "横の棒", "折れ線", "url(#hatch-", "半導体関連以外"):
            self.assertIn(needle, html)


if __name__ == "__main__":
    unittest.main()

"""工程の解説図（仕様書 8.15）の確認。"""

import re
import shutil
import unittest

from test_pages import HAS_NODE, ROOT, build_site

SOURCE = (ROOT / "src" / "lib" / "processFigures.ts").read_text(encoding="utf-8")
COMPONENT = (ROOT / "src" / "components" / "ProcessFigure.astro").read_text(encoding="utf-8")


class FigureSourceTest(unittest.TestCase):
    def test_figure_text_has_no_numbers_or_company_names(self):
        texts = re.findall(r"(?:label|text|summary|title): '([^']*)'", SOURCE)
        self.assertTrue(texts)
        for text in texts:
            self.assertIsNone(re.search(r"[0-9０-９]", text), text)  # 数値、年は入れない（8.15）

    def test_component_uses_only_css_variables_and_no_text_in_svg(self):
        style = COMPONENT.split("<style>")[1]
        self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,8}\b", style))
        self.assertNotIn("gradient", COMPONENT.lower())
        self.assertNotIn("filter", COMPONENT.lower())
        self.assertNotIn("<text", COMPONENT)  # 文字はHTMLで書く（大きさをCSSの変数で決める）
        self.assertNotIn("animation", COMPONENT)
        self.assertNotIn("<image", COMPONENT)  # 画像ファイルや外部の画像は使わない


@unittest.skipUnless(HAS_NODE, "node_modules がない")
class FigurePageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out, failure = build_site("preview", ROOT)
        cls.addClassCleanup(shutil.rmtree, out, True)
        if failure is not None:
            raise AssertionError(failure)
        cls.dist = out / "dist"

    def test_lithography_has_the_figure_with_caption_and_four_steps(self):
        html = (self.dist / "processes" / "lithography" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r'<li class="pfigure__step', html)), 4)
        svgs = re.findall(r'<svg class="pfigure__svg[^>]*>', html)
        self.assertEqual(len(svgs), 4)
        self.assertTrue(all('aria-hidden="true"' in s for s in svgs))
        self.assertIn("<figcaption", html)
        self.assertIn("実際の寸法や形ではありません", html)
        self.assertIn("塗布", html.split("pfigure__steps")[1])

    def test_other_processes_have_no_figure(self):
        html = (self.dist / "processes" / "cleaning" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("pfigure", html)


if __name__ == "__main__":
    unittest.main()

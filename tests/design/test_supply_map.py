"""サプライチェーンマップ（FR-102）の確認：図の形の計算と、出力したページ。"""

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

import yaml

from test_pages import HAS_NODE, ROOT, build_site


def node(expr: str):
    script = "import('./src/lib/supplyMap.ts').then((m) => console.log(JSON.stringify((" + expr + ")(m))))"
    done = subprocess.run(["node", "-e", script], cwd=ROOT, text=True, capture_output=True)
    assert done.returncode == 0, done.stderr[-800:]
    return json.loads(done.stdout.strip().splitlines()[-1])


SUPPLY = yaml.safe_load((ROOT / "data" / "supply-chain.yaml").read_text(encoding="utf-8"))


@unittest.skipUnless(HAS_NODE, "node_modules がない")
class SupplyMapModelTest(unittest.TestCase):
    def model(self, layout: str, counts: dict | None = None):
        data = json.dumps(SUPPLY, ensure_ascii=False)
        c = json.dumps(counts or {})
        return node(f"(m) => {{ const s = {data}; return m.buildSupplyMap(s.categories, s.processes, {c}, '{layout}'); }}")

    def test_wrap_name_keeps_every_character_and_short_names(self):
        names = ["洗浄", "ボンディング（ダイボンド、ワイヤボンド）", "リソグラフィ（塗布・露光・現像）", "成膜（CVD、PVD、ALD）"]
        lines = node(f"(m) => {json.dumps(names, ensure_ascii=False)}.map((n) => m.wrapName(n, 10))")
        self.assertEqual(lines[0], ["洗浄"])
        for name, entry in zip(names, lines):
            self.assertEqual("".join(entry), name)  # 文字を省かない
            for line in entry:
                self.assertLessEqual(sum(0.5 if ord(c) < 256 else 1 for c in line), 10)  # 半角は0.5字

    def test_every_process_appears_once_in_both_layouts(self):
        slugs = sorted(p["slug"] for p in SUPPLY["processes"])
        for layout in ("compact", "wide"):
            model = self.model(layout)
            found = sorted(b["slug"] for c in model["columns"] for b in c["boxes"])
            self.assertEqual(found, slugs, layout)

    def test_stage_order_follows_the_flow_and_skips_empty_stages(self):
        model = self.model("wide")
        names = [c["slug"] for c in model["columns"]]
        self.assertEqual(names, ["design", "materials", "front-end", "back-end"])  # 工程のない段階（装置など）は出さない

    def test_boxes_fit_inside_the_figure_and_do_not_overlap(self):
        for layout in ("compact", "wide"):
            model = self.model(layout)
            boxes = [b for c in model["columns"] for b in c["boxes"]]
            for b in boxes:
                self.assertGreaterEqual(b["x"], 0)
                self.assertLessEqual(b["x"] + b["w"], model["width"])
                self.assertLessEqual(b["y"] + b["h"], model["height"])
                self.assertGreaterEqual(b["h"], 44)  # 押せる範囲（DS-07）
            for i, a in enumerate(boxes):
                for b in boxes[i + 1:]:
                    apart = a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"] or a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"]
                    self.assertTrue(apart, (layout, a["slug"], b["slug"]))

    def test_wide_figure_fits_the_pc_content_width(self):
        self.assertLessEqual(self.model("wide")["width"], 1024 - 2 * 32)  # 縮めて文字が小さくならない

    def test_compact_figure_fits_a_320px_screen(self):
        self.assertLessEqual(self.model("compact")["width"], 320 - 2 * 16)

    def test_counts_are_passed_to_boxes(self):
        model = self.model("wide", {"cleaning": 3})
        box = next(b for c in model["columns"] for b in c["boxes"] if b["slug"] == "cleaning")
        self.assertEqual(box["count"], 3)
        self.assertIn("3社", box["aria"])


@unittest.skipUnless(HAS_NODE, "node_modules がない")
class SupplyMapPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out, failure = build_site("preview", ROOT)
        cls.addClassCleanup(shutil.rmtree, out, True)
        if failure is not None:
            raise AssertionError(failure)
        cls.html = (out / "dist" / "supply-chain" / "index.html").read_text(encoding="utf-8")

    def test_every_link_in_the_figure_has_a_matching_heading(self):
        ids = set(re.findall(r'<h4 id="(p-[a-z-]+)"', self.html))
        links = set(re.findall(r'<a class="[^"]*map-box[^"]*" href="#(p-[a-z-]+)"', self.html))
        self.assertEqual(links, {f"p-{p['slug']}" for p in SUPPLY["processes"]})
        self.assertLessEqual(links, ids)

    def test_has_source_line_and_two_figures_and_no_noindex_problem(self):
        self.assertIn("出典：", self.html)
        self.assertEqual(len(re.findall(r'<svg class="[^"]*map-svg ', self.html)), 2)
        self.assertNotIn("<script src=\"http", self.html)

    def test_company_tables_list_companies_and_empty_processes_say_so(self):
        companies = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in (ROOT / "data" / "companies").glob("*.yaml")]
        used = {p for c in companies for p in (c.get("processes") or [])}
        empty = [p for p in SUPPLY["processes"] if p["slug"] not in used]
        self.assertEqual(self.html.count("まだ掲載していません"), len(empty))
        self.assertEqual(self.html.count('<table class="data-table'), len(SUPPLY["processes"]) - len(empty))


if __name__ == "__main__":
    unittest.main()

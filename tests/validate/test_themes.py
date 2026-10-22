"""テーマ（データ定義書 6.7、運用ルール書 4.6）の検査のテスト：V-02、V-04、V-07、V-08、V-10、V-12、V-25 と、
ニュースの tags.themes の参照（V-04）。"""
import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_validate_data import Base  # noqa: E402

BODY = "## 何が起きているか\n\n" + "生成AIの計算に使う半導体の需要が増えている。[S1]" * 12 + \
       "\n\n## 半導体のどこに関わるか\n\n" + "高帯域のメモリを積み重ねる工程と、その検査に装置が使われる。" * 12 + "\n"


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


class ThemeTest(Base):
    def write_theme(self, name="generative-ai", body=BODY, **extra):
        folder = self.root / "content" / "themes"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{name}.md").write_text("---\n" + yaml.safe_dump(theme_front(**extra), allow_unicode=True, sort_keys=False) + "---\n" + body,
                                           encoding="utf-8")
        return f"content/themes/{name}.md"

    def errors(self, rel):
        return [p for p in self.check() if p.file == rel and p.severity == "error"]

    def test_valid_theme_passes(self):
        rel = self.write_theme()
        self.assertEqual(self.errors(rel), [])

    def test_file_name_and_references(self):
        rel = self.write_theme(name="data-center", processes=["no-such-process"], terms=["no-such-term"],
                               learn=[{"folder": "power", "ref": "no-such-page"}])
        problems = self.check()
        self.has(problems, "V-02", "ファイル名", file=rel)
        self.has(problems, "V-04", "no-such-process", file=rel)
        self.has(problems, "V-04", "no-such-term", file=rel)
        self.has(problems, "V-04", "no-such-page", file=rel)

    def test_unknown_company_duplicate_and_missing_basis(self):
        groups = theme_front()["groups"] + [{"label": "試験", "companies": [
            {"company": "advantest", "role": "重複して載せる。", "basis": ["S9"]},
            {"company": "no-such-company", "role": "マスタにない。", "basis": ["S1"]}]}]
        rel = self.write_theme(groups=groups)
        problems = self.check()
        self.has(problems, "V-25", "2回以上", file=rel)
        self.has(problems, "V-25", "S9", file=rel)
        self.has(problems, "V-04", "no-such-company", file=rel)

    def test_too_many_others_is_a_warning(self):
        others = [{"name": f"企業{n}", "region": "米国", "role": "役割。", "basis": ["S3"]} for n in range(11)]
        rel = self.write_theme(groups=[{"label": "海外", "others": others}])
        problems = self.check()
        self.has(problems, "V-25", "11社", file=rel)
        self.assertFalse([p for p in problems if p.file == rel and p.rule == "V-25" and p.severity == "error"])

    def test_headings_length_and_citations(self):
        rel = self.write_theme(body="## 何が起きたか\n\n短い。[S7]\n")
        problems = self.check()
        self.has(problems, "V-10", "何が起きているか", file=rel)
        self.has(problems, "V-12", "本文", file=rel)
        self.has(problems, "V-07", "S7", file=rel)
        self.has(problems, "V-08", "S1", file=rel)  # S1 は本文でも根拠でも使われていない

    def test_schema_requires_companies_or_others(self):
        rel = self.write_theme(groups=[{"label": "空のまとまり"}])
        self.has(self.check(), "V-01", file=rel)

    def test_news_theme_tag_must_exist(self):
        self.write_theme()
        news_dir = self.root / "content" / "news"
        news_dir.mkdir(parents=True)
        real = sorted((Path(__file__).resolve().parents[2] / "content" / "news").glob("*.md"))[0]
        text = real.read_text(encoding="utf-8").replace("  themes: []", "  themes:\n  - generative-ai\n  - no-such-theme")
        (news_dir / real.name).write_text(text, encoding="utf-8")
        problems = [p for p in self.check() if p.file == f"content/news/{real.name}" and p.rule == "V-04"]
        self.assertTrue(any("no-such-theme" in p.message for p in problems), problems)
        self.assertFalse(any("generative-ai" in p.message for p in problems), problems)


if __name__ == "__main__":
    unittest.main()

"""理解度チェック（データ定義書 6.11、V-24）と、半導体を学ぶ（データ定義書 6.8）の検査のテスト。"""
import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_validate_data import Base, vd  # noqa: E402

QUIZ = """## 理解度チェック

### 問1
エッチングで行うことは、どれか。

1. 表面を平らに削る
2. 不要な膜を取り除く
3. 膜を積む
4. 形を光で写す

答え：2
解説：エッチングは、覆われていない部分の膜を取り除く工程である。
"""


def path_yaml(units=None):
    return {"schema_version": 1, "fields": [
        {"no": 1, "slug": "basics", "title": "半導体の基礎", "summary": "基礎を学ぶ。", "units": units or []}]}


class QuizFormTest(unittest.TestCase):
    def rules(self, body):
        return [p.message for p in vd.check_quiz("x.md", body)]

    def test_valid_quiz_has_no_problem(self):
        self.assertEqual(self.rules("## 解説\n\n本文。\n\n" + QUIZ), [])

    def test_no_quiz_is_fine(self):
        self.assertEqual(self.rules("## 解説\n\n本文。\n"), [])

    def test_three_choices_answer_missing_and_heading_after(self):
        bad = QUIZ.replace("4. 形を光で写す\n", "").replace("答え：2\n", "")
        messages = self.rules(bad)
        self.assertTrue(any("1〜4の4つ" in m for m in messages))
        self.assertTrue(any("答え" in m for m in messages))
        self.assertTrue(any("見出し" in m for m in self.rules(QUIZ + "\n## 出典\n")))

    def test_more_than_three_questions(self):
        many = QUIZ + "".join(QUIZ.split("\n", 2)[2].replace("問1", f"問{n}") for n in (2, 3, 4))
        self.assertTrue(any("4問" in m for m in self.rules(many)))


class LearnPageTest(Base):
    def write_learn(self, slug="what-is-semiconductor", field="basics", body=None, front=None, figure=True, unit=True):
        front = {"title": "半導体とは何か", "field": field, "description": "導体と絶縁体の間の性質を持つ物質としての半導体を、身近な例から説明する。",
                 "published_at": "2026-10-12", "ai_generated": True, "draft": True,
                 "sources": [{"id": "S1", "title": "資料", "publisher": "発行元", "url": "https://example.org/a", "accessed_on": "2026-10-12"}],
                 **(front or {})}
        text = body if body is not None else "## 半導体とは\n\n説明の文。[S1]\n\n" + QUIZ
        folder = self.root / "content" / "learn" / field
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{slug}.md").write_text("---\n" + yaml.safe_dump(front, allow_unicode=True, sort_keys=False) + "---\n" + text,
                                           encoding="utf-8")
        units = [{"type": "learn", "ref": slug}] if unit else []
        (self.root / "content" / "learn" / "path.yaml").write_text(yaml.safe_dump(path_yaml(units), allow_unicode=True), encoding="utf-8")
        if figure:
            fig = self.root / "src" / "figures" / "learn" / field
            fig.mkdir(parents=True, exist_ok=True)
            (fig / f"{slug}.astro").write_text("<figure></figure>\n", encoding="utf-8")
        return f"content/learn/{field}/{slug}.md"

    def errors(self, rel):
        return [p for p in self.check() if p.file in (rel, "content/learn/path.yaml") and p.severity == "error"]

    def test_valid_page(self):
        rel = self.write_learn()
        self.assertEqual(self.errors(rel), [])

    def test_missing_figure_and_quiz(self):
        rel = self.write_learn(figure=False, body="## 半導体とは\n\n説明の文。[S1]\n")
        problems = self.check()
        self.has(problems, "V-24", "図", file=rel)
        self.has(problems, "V-24", "理解度チェック", file=rel)

    def test_field_must_match_folder(self):
        rel = self.write_learn(front={"field": "devices"})
        self.has(self.check(), "V-02", "フォルダ", file=rel)

    def test_unit_reference_must_exist(self):
        self.write_learn()
        (self.root / "content" / "learn" / "path.yaml").write_text(
            yaml.safe_dump(path_yaml([{"type": "learn", "ref": "missing"}]), allow_unicode=True), encoding="utf-8")
        self.has(self.check(), "V-04", "missing", file="content/learn/path.yaml")


if __name__ == "__main__":
    unittest.main()

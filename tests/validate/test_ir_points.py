"""IR重要ポイント（データ定義書 6.3、要求定義書 FR-307、LG-06）の検査のテスト。見本は作業用のコピーにだけ置く（content/ には置かない）。"""
import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_validate_data import Base  # noqa: E402

SOURCES_YAML = {"schema_version": 1, "ir": [{"domain": "www.release.tdnet.info", "kind": "exchange"}], "news": [], "blocked": []}
BODY = """## 業績の要点

売上高と営業利益は、前年の同じ期より増えた。[S1]

## 今期見通し

会社は、通期の見通しを据え置いた。[S1]

## 注目材料

会社は、新しい試験装置の出荷を始めたと示した。[S1]
"""


class IrPointTest(Base):
    def write_point(self, name="2026-03-q2", front=None, body=BODY, folder="advantest", sources_yaml=SOURCES_YAML):
        if sources_yaml is not None:
            (self.root / "config" / "sources.yaml").write_text(yaml.safe_dump(sources_yaml, allow_unicode=True), encoding="utf-8")
        front = {"company": "advantest", "fiscal_period_end": "2026-03", "quarter": 2, "announced_on": "2025-10-29",
                 "uses_quarterly_figures": False, "published_at": "2025-10-30", "ai_generated": True, "draft": True,
                 "sources": [{"id": "S1", "title": "決算短信", "publisher": "取引所", "url": "https://www.release.tdnet.info/a.pdf",
                              "accessed_on": "2025-10-30"}], **(front or {})}
        d = self.root / "content" / "ir-points" / folder
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.md").write_text("---\n" + yaml.safe_dump(front, allow_unicode=True, sort_keys=False) + "---\n" + body, encoding="utf-8")
        return f"content/ir-points/{folder}/{name}.md"

    def errors(self, rel):
        return [str(p) for p in self.check() if p.file == rel and p.severity == "error"]

    def test_valid_point(self):
        rel = self.write_point()
        self.assertEqual(self.errors(rel), [])

    def test_headings_and_length(self):
        long = "あ" * 101
        rel = self.write_point(body=f"## 業績の要点\n\n{long}\n\n## 注目材料\n\n材料。\n")
        problems = self.check()
        self.has(problems, "V-10", "3つだけ", file=rel)
        self.has(problems, "V-12", "上限（100字）", file=rel)

    def test_file_name_and_fields_must_match(self):
        rel = self.write_point(name="2026-03-q3")
        self.has(self.check(), "V-02", "四半期", file=rel)

    def test_source_domain_must_be_allowed(self):
        rel = self.write_point(front={"sources": [{"id": "S1", "title": "記事", "publisher": "他社", "url": "https://example.com/a",
                                                   "accessed_on": "2025-10-30"}]})
        self.has(self.check(), "V-04", "example.com", file=rel)

    def test_company_domain_is_allowed(self):
        url = self.company["ir_url"]
        rel = self.write_point(front={"sources": [{"id": "S1", "title": "決算説明資料", "publisher": "会社", "url": url,
                                                   "accessed_on": "2025-10-30"}]})
        self.assertEqual(self.errors(rel), [])

    def test_missing_sources_config(self):
        self.write_point(sources_yaml=None)
        self.has(self.check(), "V-04", "config/sources.yaml", file="config/sources.yaml")

    def test_schema_requires_fields(self):
        rel = self.write_point(front={"quarter": 5})
        self.has(self.check(), "V-01", "", file=rel)


if __name__ == "__main__":
    unittest.main()

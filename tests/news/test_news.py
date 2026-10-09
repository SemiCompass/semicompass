"""ニュース（content/news）と config/news.yaml の検査（validate_data.py）の単体テスト。

サンプルの記事は、このファイルの中で作り、一時のフォルダに書く（content/news/ には置かない。本番に出るため）。
"""

import copy
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "validate"))
sys.path.insert(0, str(ROOT / "scripts" / "edinet"))

import validate_data as vd  # noqa: E402

H1, H2, H3 = "何が起きたか", "なぜ重要か", "関係する企業・工程とサプライチェーン上の位置"


def article(**kw):
    data = {"title": "架空の設備投資の発表", "description": "架空のニュースの説明である。", "published_at": "2026-10-07",
            "ai_generated": True, "draft": True, "category": "investment",
            "source_article": {"title": "架空の見出し", "publisher": "架空協会", "url": "https://example.org/a.html",
                               "published_on": "2026-10-06", "reporting": "primary"},
            "score": {"impact": 2, "supply_chain": 2, "novelty": 2, "reliability": 3},
            "overseas": False, "tags": {"companies": ["advantest"], "processes": ["cmp"], "themes": []}}
    data.update(kw)
    return data


def body(n1=150, n2=150, n3=150, third_extra="", sep="\n\n"):
    return (f"## {H1}{sep}" + "あ" * n1 + f"。{sep}## {H2}{sep}" + "い" * n2 + f"。{sep}## {H3}{sep}" + "う" * n3 + f"。{third_extra}\n")


def news_config(**kw):
    config = {"schema_version": 1, "daily_limit": 2, "busy_period_daily_limit": 2, "candidate_limit": 30,
              "weekly_max_per_category": 4, "tag_index_threshold": 5,
              "weekly_targets": {c: {"min": 0, "max": 2} for c in ("investment", "policy", "m_and_a", "earnings", "technology", "supply_demand")},
              "priority_rules": {c: "試験用の基準" for c in ("investment", "policy", "m_and_a", "earnings", "technology", "supply_demand")},
              "sources": [{"id": "test-source", "name": "試験用の情報源", "kind": "government", "reliability": "high",
                           "page_url": "https://example.org/news/"}]}
    config.update(kw)
    return config


class Base(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "data" / "companies").mkdir(parents=True)
        (self.root / "content" / "news").mkdir(parents=True)
        (self.root / "config").mkdir()
        shutil.copy(ROOT / "data" / "supply-chain.yaml", self.root / "data" / "supply-chain.yaml")
        for slug in ("advantest", "tokyo-electron"):
            shutil.copy(ROOT / "data" / "companies" / f"{slug}.yaml", self.root / "data" / "companies" / f"{slug}.yaml")

    def write(self, name, data, text):
        (self.root / "content" / "news" / f"{name}.md").write_text(
            "---\n" + yaml.safe_dump(data, allow_unicode=True, sort_keys=False) + "---\n\n" + text, encoding="utf-8")

    def write_config(self, config):
        (self.root / "config" / "news.yaml").write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def problems(self, name="2026-10-test", data=None, text=None, severity=None):
        self.write(name, article() if data is None else data, body() if text is None else text)
        found = [p for p in vd.validate(self.root, ROOT) if p.file == f"content/news/{name}.md"]
        return [p for p in found if severity is None or p.severity == severity]

    def rules(self, *args, severity="error", **kw):
        return sorted({p.rule for p in self.problems(*args, severity=severity, **kw)})


class FileAndFrontMatterTest(Base):
    def test_a_clean_draft_has_no_problems(self):
        self.assertEqual([str(p) for p in self.problems()], [])

    def test_kinds_are_registered_and_collected(self):
        self.write("2026-10-test", article(), body())
        self.write_config(news_config())
        kinds = {k for k, _ in vd.collect_files(self.root)}
        self.assertTrue({"news", "news-config"} <= kinds)
        self.assertEqual(vd.kind_of(self.root / "content" / "news" / "2026-10-test.md", self.root), "news")
        self.assertEqual(vd.kind_of(self.root / "config" / "news.yaml", self.root), "news-config")

    def test_front_matter_is_checked_by_the_schema(self):
        problems = self.problems(data=article(extra_field=1, category="gossip"))
        self.assertEqual({p.rule for p in problems}, {"V-01"})
        self.assertTrue({"/category", ""} <= {p.path for p in problems})
        self.assertIn("V-01", self.rules(data={k: v for k, v in article().items() if k != "score"}))

    def test_speculative_reliability_is_limited_by_the_schema(self):
        source = {**article()["source_article"], "reporting": "speculative"}
        self.assertEqual(self.rules(data=article(source_article=source)), ["V-01"])
        self.assertEqual(self.rules(data=article(source_article=source, score={"impact": 2, "supply_chain": 2, "novelty": 2, "reliability": 1})), [])

    def test_file_name_shape_and_month(self):
        self.assertEqual(self.rules("2026-10", ), ["V-02"])
        self.assertEqual(self.rules("2026-1-test"), ["V-02"])
        self.assertEqual(self.rules("2026-10-Test"), ["V-02"])
        problems = self.problems("2026-09-test")
        self.assertEqual([(p.rule, p.path) for p in problems], [("V-09", "/published_at")])
        self.assertEqual(self.rules("2025-10-test"), ["V-09"])  # 年が違う
        self.assertEqual(self.rules("2026-10-test-two"), [])

    def test_draft_true_and_draft_absent_are_both_checked(self):
        self.assertEqual(self.rules(data=article(draft=True), text="## 見出し\n本文\n"), ["V-10"])
        data = article()
        del data["draft"]
        self.assertEqual(self.rules(data=data, text="## 見出し\n本文\n"), ["V-10"])


class BodyTest(Base):
    def test_headings_must_be_the_three_in_order(self):
        for text in (body().replace(f"## {H2}", f"## {H2}と理由"),
                     body() + "## おまけ\nあ\n",
                     f"## {H2}\n" + "あ" * 300 + f"\n## {H1}\n" + "い" * 100 + f"\n## {H3}\n" + "う" * 100 + "\n",
                     f"## {H1}\n" + "あ" * 300 + f"\n## {H2}\n" + "い" * 300 + "\n",
                     "あ" * 500 + "\n"):
            self.assertEqual(self.rules(text=text), ["V-10"], text[:30])

    def test_level_1_heading_and_wrong_level_and_text_before_the_first_heading(self):
        self.assertEqual(self.rules(text="# 題\n" + body()), ["V-10"])
        self.assertEqual(self.rules(text=body().replace(f"## {H2}", f"### {H2}")), ["V-10"])
        self.assertEqual(self.rules(text="前置きの文である。\n\n" + body()), ["V-10"])

    def test_headings_in_code_blocks_are_ignored(self):
        text = body() + "```\n## 例\n```\n"
        self.assertEqual(self.rules(text=text), [])

    def test_length_is_a_warning_outside_400_to_700(self):
        # 本文は見出しを除いて数える。1つの区分の「。」を含めて、合計を変える
        self.assertEqual(self.rules(text=body(100, 100, 100), severity="warning"), ["V-12"])
        self.assertEqual(self.rules(text=body(250, 250, 250), severity="warning"), ["V-12"])
        self.assertEqual(self.rules(text=body(150, 150, 150), severity="warning"), [])
        self.assertEqual(self.rules(text=body(100, 150, 150), severity="warning"), [])  # 3つの合計で数える
        self.assertEqual(self.rules(text=body(100, 100, 100)), [])  # エラーにはならない
        problems = self.problems(text=body(50, 50, 50), severity="warning")
        self.assertIn("目安", problems[0].message)

    def test_length_boundaries(self):
        # 各区分の末尾の「。」を含めて数える。合計がちょうど 400 と 700 の場合は警告にならない
        self.assertEqual(self.rules(text=body(132, 132, 132), severity="warning"), ["V-12"])  # (132+1)*3 = 399
        self.assertEqual(self.rules(text=body(133, 132, 132), severity="warning"), [])  # 400
        self.assertEqual(self.rules(text=body(231, 233, 233), severity="warning"), [])  # 700
        self.assertEqual(self.rules(text=body(233, 233, 233), severity="warning"), ["V-12"])  # 702


class TagsAndOverseasTest(Base):
    def test_tag_references_must_exist(self):
        tags = {"companies": ["advantest", "no-such-company"], "processes": ["cmp", "no-such-process"], "themes": []}
        problems = self.problems(data=article(tags=tags))
        self.assertEqual(sorted((p.rule, p.path) for p in problems),
                         [("V-04", "/tags/companies/1"), ("V-04", "/tags/processes/1")])

    def test_unlisted_companies_are_not_references(self):
        tags = {"companies": [], "unlisted_companies": [{"name": "架空商事"}], "processes": [], "themes": []}
        self.assertEqual(self.rules(data=article(tags=tags)), [])

    def test_overseas_needs_a_company_tag(self):
        tags = {"companies": [], "processes": [], "themes": []}
        problems = self.problems(data=article(overseas=True, tags=tags))
        self.assertEqual([(p.rule, p.path) for p in problems], [("V-13", "/tags/companies")])
        self.assertEqual(self.rules(data=article(overseas=False, tags=tags)), [])

    def test_overseas_needs_the_company_name_under_the_third_heading(self):
        data = article(overseas=True)
        self.assertEqual(self.rules(data=data), ["V-13"])  # 名前がない
        self.assertEqual(self.rules(data=data, text=body(third_extra="アドバンテストの測定装置に関わる。")), [])  # 略称
        self.assertEqual(self.rules(data=data, text=body(third_extra="ADVANTEST CORPORATIONの装置である。")), ["V-13"])  # 英語表記は、対象にしない
        # 名前が、3つ目より前の見出しの下にあるだけでは足りない
        text = body().replace("あ" * 150, "アドバンテストの話である。" + "あ" * 130, 1)
        self.assertEqual(self.rules(data=data, text=text), ["V-13"])

    def test_overseas_accepts_the_formal_name_of_any_tagged_company(self):
        tokyo = yaml.safe_load((ROOT / "data" / "companies" / "tokyo-electron.yaml").read_text(encoding="utf-8"))
        data = article(overseas=True, tags={"companies": ["advantest", "tokyo-electron"], "processes": [], "themes": []})
        text = body(third_extra=f"{tokyo['name']}の装置に関わる。")
        self.assertEqual(self.rules(data=data, text=text), [])

    def test_overseas_company_name_of_an_untagged_company_does_not_count(self):
        data = article(overseas=True)  # タグは advantest だけ
        self.assertEqual(self.rules(data=data, text=body(third_extra="東京エレクトロンの装置に関わる。")), ["V-13"])


class XPostTest(Base):
    def test_length_counts_urls_as_23(self):
        url = "https://example.org/news/2026/10/a-very-long-path-that-is-much-longer-than-twenty-three-characters/"
        self.assertEqual(vd.x_post_length("あ" * 10 + url), 33)
        self.assertEqual(self.rules(data=article(x_post="あ" * 117 + url)), [])  # 117 + 23 = 140
        self.assertEqual(self.rules(data=article(x_post="あ" * 118 + url)), ["V-11"])  # 141
        self.assertEqual(self.rules(data=article(x_post="あ" * 140)), [])
        self.assertEqual(self.rules(data=article(x_post="あ" * 141)), ["V-11"])

    def test_hashtags_up_to_two(self):
        self.assertEqual(self.rules(data=article(x_post="説明である。 #半導体 #投資")), [])
        self.assertEqual(self.rules(data=article(x_post="説明である。 #半導体 #投資 #政策")), ["V-11"])
        self.assertEqual(self.rules(data=article(x_post="説明である。＃半導体 ＃投資 ＃政策")), ["V-11"])  # 全角の＃も数える
        self.assertEqual(vd.x_post_hashtags("見出し #A#B"), 2)
        self.assertEqual(vd.x_post_hashtags("# は記号 #"), 0)

    def test_hash_inside_a_url_is_not_a_hashtag(self):
        self.assertEqual(vd.x_post_hashtags("詳しくは https://example.org/a#one #半導体 #投資"), 2)
        self.assertEqual(self.rules(data=article(x_post="https://example.org/a#one #半導体 #投資")), [])

    def test_x_post_is_optional(self):
        self.assertNotIn("x_post", article())
        self.assertEqual(self.rules(), [])


class ConfigTest(Base):
    def config_problems(self, config):
        self.write_config(config)
        return [p for p in vd.validate(self.root, ROOT) if p.file == "config/news.yaml"]

    def test_a_valid_config_has_no_problems(self):
        self.assertEqual(self.config_problems(news_config()), [])

    def test_schema_is_applied(self):
        config = news_config()
        del config["daily_limit"]
        config["extra"] = 1
        problems = self.config_problems(config)
        self.assertEqual({p.rule for p in problems}, {"V-01"})
        self.assertEqual(self.config_problems(news_config(sources=[])), self.config_problems(news_config(sources=[])))
        self.assertEqual({p.rule for p in self.config_problems(news_config(sources=[]))}, {"V-01"})  # minItems: 1

    def test_min_must_not_exceed_max(self):
        config = news_config()
        config["weekly_targets"]["policy"] = {"min": 3, "max": 1}
        self.assertEqual([(p.rule, p.path) for p in self.config_problems(config)], [("V-01", "/weekly_targets/policy")])

    def test_source_ids_are_unique_and_company_must_exist(self):
        row = news_config()["sources"][0]
        problems = self.config_problems(news_config(sources=[row, copy.deepcopy(row)]))
        self.assertEqual([(p.rule, p.path) for p in problems], [("V-03", "/sources/1/id")])
        company = {**row, "id": "advantest-news", "kind": "company", "company": "advantest"}
        self.assertEqual(self.config_problems(news_config(sources=[row, company])), [])
        company["company"] = "no-such-company"
        self.assertEqual([(p.rule, p.path) for p in self.config_problems(news_config(sources=[row, company]))],
                         [("V-04", "/sources/1/company")])

    def test_a_source_needs_a_feed_or_a_page_url(self):
        row = news_config()["sources"][0]
        del row["page_url"]
        self.assertEqual({p.rule for p in self.config_problems(news_config(sources=[row]))}, {"V-01"})
        self.assertEqual(self.config_problems(news_config(sources=[{**row, "feed_url": "https://example.org/rss.xml"}])), [])

    def test_the_real_config_and_news_have_no_errors(self):
        self.assertEqual([str(p) for p in vd.validate(ROOT, ROOT) if p.severity == "error"
                          and (p.file == "config/news.yaml" or p.file.startswith("content/news/"))], [])

    def test_cli_path_option_accepts_the_new_kinds(self):
        import contextlib
        import io
        self.write("2026-10-test", article(), body())
        self.write_config(news_config())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(vd.main(["--path", str(self.root / "content" / "news" / "2026-10-test.md")], root=self.root, schema_root=ROOT), 0)
            self.assertEqual(vd.main(["--path", str(self.root / "config" / "news.yaml")], root=self.root, schema_root=ROOT), 0)


if __name__ == "__main__":
    unittest.main()

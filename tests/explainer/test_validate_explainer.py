import copy
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

import explainer_fakes as fk
import validate_data as vd

ROOT = fk.ROOT
CONFIG = yaml.safe_load((ROOT / "config" / "explainer-sources.yaml").read_text(encoding="utf-8"))
SUPPLY = yaml.safe_load((ROOT / "data" / "supply-chain.yaml").read_text(encoding="utf-8"))


def messages(problems, severity=None):
    return [(p.rule, p.path, p.message) for p in problems if severity is None or p.severity == severity]


def rules(problems, severity="error"):
    return sorted({p.rule for p in problems if p.severity == severity})


class ConfigTest(unittest.TestCase):
    def check(self, mutate):
        config = copy.deepcopy(CONFIG)
        mutate(config)
        return vd.check_explainer_sources(config, SUPPLY)

    def test_the_repository_config_has_no_errors(self):
        self.assertEqual(messages(vd.check_explainer_sources(CONFIG, SUPPLY), "error"), [])

    def test_bad_enum_values_are_errors(self):
        for key, value in (("status", "maybe"), ("role", "main"), ("kind", "blog")):
            problems = self.check(lambda c: c["terms"]["eda"]["sources"][0].__setitem__(key, value))
            self.assertIn(f"/terms/eda/sources/0/{key}", [p.path for p in problems if p.severity == "error"], key)

    def test_url_must_be_https(self):
        problems = self.check(lambda c: c["terms"]["eda"]["sources"][0].__setitem__("url", "ftp://x.example/a"))
        self.assertEqual(rules(problems), ["V-01"])
        problems = self.check(lambda c: c["terms"]["eda"]["sources"][0].__setitem__("url", "not a url"))
        self.assertEqual(rules(problems), ["V-01"])
        problems = self.check(lambda c: c["terms"]["eda"]["sources"][0].__setitem__("url", "http://x.example/a"))
        self.assertEqual(rules(problems), [])  # http は、取得できない旨の警告（運営者が https に直すまで）
        self.assertTrue(any("http://" in p.message and p.severity == "warning" for p in problems))

    def test_empty_sources_is_a_warning_not_an_error(self):
        problems = self.check(lambda c: c["terms"]["eda"].__setitem__("sources", []))
        self.assertEqual(rules(problems), [])
        self.assertIn("/terms/eda/sources", [p.path for p in problems if p.severity == "warning"])
        problems = self.check(lambda c: c["terms"]["eda"].__setitem__("sources", "x"))
        self.assertEqual(rules(problems), ["V-01"])

    def test_process_slug_must_be_in_supply_chain_and_mvp_processes_must_be_defined(self):
        def rename(c):
            c["processes"]["not-a-process"] = c["processes"].pop("cmp")
        problems = self.check(rename)
        self.assertEqual(sorted({(p.rule, p.path) for p in problems if p.severity == "error"}),
                         [("V-04", "/processes"), ("V-04", "/processes/not-a-process")])
        self.assertTrue(any("cmp" in p.message and "定義" in p.message for p in problems))

    def test_duplicate_approved_url_in_one_target_is_an_error_but_not_across_targets(self):
        def dup(c):
            c["terms"]["eda"]["sources"].append(copy.deepcopy(c["terms"]["eda"]["sources"][0]))
        self.assertEqual(rules(self.check(dup)), ["V-03"])
        urls = [s["url"] for t in CONFIG["terms"].values() for s in t["sources"] if s["status"] == "approved"]
        self.assertGreater(len(urls) - len(set(urls)), 0)  # 実際の設定でも、別の対象で同じURLを使っている
        self.assertEqual(messages(vd.check_explainer_sources(CONFIG, SUPPLY), "error"), [])

    def test_candidate_urls_may_repeat(self):
        def dup(c):
            row = copy.deepcopy(c["terms"]["eda"]["sources"][0])
            row["status"] = "candidate"
            c["terms"]["eda"]["sources"] += [row, copy.deepcopy(row)]
        self.assertEqual(rules(self.check(dup)), [])

    def test_missing_required_fields_and_bad_slug(self):
        def broken(c):
            del c["terms"]["eda"]["term"]
            c["terms"]["Bad Slug"] = {"term": "x", "sources": [fk.source("https://x.example/a")]}
            del c["terms"]["plasma"]["sources"][0]["publisher"]
        problems = self.check(broken)
        self.assertEqual({p.path for p in problems if p.severity == "error"},
                         {"/terms/eda/term", "/terms/Bad Slug", "/terms/plasma/sources/0/publisher"})
        self.assertEqual(vd.check_explainer_sources([], SUPPLY)[0].rule, "V-01")
        self.assertTrue(vd.check_explainer_sources({"schema_version": 2, "terms": {}, "processes": {}}, SUPPLY))


def fm(**kw):
    data = {"term": "架空研磨", "reading": "カソウケンマ", "short_definition": "短い説明である。", "processes": ["cmp"],
            "description": "あ" * 60, "published_at": "2026-10-07", "draft": True, "ai_generated": True,
            "sources": [{"id": "S1", "title": "t", "publisher": "p", "url": "https://a.example.org/1", "accessed_on": "2026-10-07"}]}
    data.update(kw)
    return data


def body(n=300, cite="[S1]", extra=""):
    return "あ" * n + f"。{cite}\n{extra}"


class TermCheckTest(unittest.TestCase):
    CFG = copy.deepcopy(CONFIG)

    def run_check(self, files, config=None):
        return vd.check_terms({f"content/glossary/{k}.md": v for k, v in files.items()}, SUPPLY, config or self.CFG)

    def test_clean_file_has_no_problems(self):
        self.assertEqual(self.run_check({"eda": (fm(term="EDA(設計ツール)"), body())}), [])

    def test_file_name_must_be_a_term_slug_in_the_config(self):
        problems = self.run_check({"no-such-term": (fm(), body())})
        self.assertEqual([(p.rule, p.severity) for p in problems], [("V-02", "error")])

    def test_name_differs_from_config_is_a_warning(self):
        problems = self.run_check({"eda": (fm(term="別の名前"), body())})
        self.assertEqual([(p.rule, p.severity) for p in problems], [("V-02", "warning")])

    def test_references(self):
        problems = self.run_check({"eda": (fm(term="EDA(設計ツール)", processes=["no-such"], related_terms=["no-such-term", "eda", "plasma"]), body())})
        by_path = {p.path: (p.rule, p.severity) for p in problems}
        self.assertEqual(by_path["/processes/0"], ("V-04", "error"))
        self.assertEqual(by_path["/related_terms/0"], ("V-04", "error"))  # どこにもない
        self.assertEqual(by_path["/related_terms/1"], ("V-04", "error"))  # 自分自身
        self.assertEqual(by_path["/related_terms/2"], ("V-04", "warning"))  # 設定にあるが、まだ原稿がない

    def test_related_term_with_a_file_is_fine(self):
        files = {"eda": (fm(term="EDA(設計ツール)", related_terms=["plasma"]), body()), "plasma": (fm(term="プラズマ"), body())}
        self.assertEqual(self.run_check(files), [])

    def test_v16_term_and_aliases_must_not_repeat_across_the_glossary(self):
        files = {"eda": (fm(term="EDA(設計ツール)", aliases=["ＥＤＡ"]), body()), "plasma": (fm(term="プラズマ", aliases=["eda(設計ツール)"]), body())}
        problems = self.run_check(files)
        self.assertEqual([(p.rule, p.severity, p.file) for p in problems if p.rule == "V-16"], [("V-16", "error", "content/glossary/plasma.md")])
        files = {"eda": (fm(term="EDA(設計ツール)"), body()), "plasma": (fm(term="プラズマ", aliases=["EDA(設計ツール)"]), body())}
        self.assertEqual(rules(self.run_check(files)), ["V-16"])

    def test_term_equal_to_its_own_alias_is_v16(self):
        problems = self.run_check({"eda": (fm(term="EDA(設計ツール)", aliases=["EDA(設計ツール)"]), body())})
        self.assertEqual(rules(problems), ["V-16"])

    def test_citations_v07_v08(self):
        problems = self.run_check({"eda": (fm(term="EDA(設計ツール)"), body(cite="[S1][S2]"))})
        self.assertEqual([(p.rule, p.severity) for p in problems], [("V-07", "error")])
        problems = self.run_check({"eda": (fm(term="EDA(設計ツール)"), body(cite=""))})
        self.assertEqual([(p.rule, p.severity) for p in problems], [("V-08", "warning")])

    def test_supplementary_only_citation_is_a_warning(self):
        config = copy.deepcopy(CONFIG)
        url = config["terms"]["coater-developer"]["sources"][0]["url"]  # この用語の出典は、補助だけ
        data = fm(term="コータ・デベロッパ", sources=[{"id": "S1", "title": "t", "publisher": "p", "url": url, "accessed_on": "2026-10-07"}])
        problems = [p for p in self.run_check({"coater-developer": (data, body())}, config) if p.rule == "V-08"]
        self.assertEqual([(p.rule, p.severity) for p in problems], [("V-08", "warning")])
        self.assertIn("補助", problems[0].message)
        primary = fm(term="EDA(設計ツール)", sources=[{"id": "S1", "title": "t", "publisher": "p",
                                                      "url": config["terms"]["eda"]["sources"][0]["url"], "accessed_on": "2026-10-07"}])
        self.assertEqual(self.run_check({"eda": (primary, body())}, config), [])

    def test_headings_v10(self):
        problems = self.run_check({"eda": (fm(term="EDA(設計ツール)"), "# 大見出し\n" + body())})
        self.assertEqual(rules(problems), ["V-10"])
        problems = self.run_check({"eda": (fm(term="EDA(設計ツール)"), "## 見出し\n" + body() + "#### 飛ぶ\n")})
        self.assertEqual(rules(problems), ["V-10"])

    def test_length_warnings_v12(self):
        for n, ok in ((100, False), (300, True), (500, False)):
            problems = self.run_check({"eda": (fm(term="EDA(設計ツール)"), body(n))})
            self.assertEqual(any(p.rule == "V-12" for p in problems), not ok, n)
            self.assertEqual(rules(problems), [])
        problems = self.run_check({"eda": (fm(term="EDA(設計ツール)", description="短い"), body())})
        self.assertEqual([(p.rule, p.path) for p in problems], [("V-12", "/description")])

    def test_without_config_the_name_checks_are_skipped(self):
        self.assertEqual(vd.check_terms({"content/glossary/x.md": (fm(), body())}, SUPPLY, None), [])


class ProcessCheckTest(unittest.TestCase):
    def run_check(self, slug, data, text, terms=None, config=CONFIG):
        return vd.check_process_pages({f"content/processes/{slug}.md": (data, text)}, SUPPLY, config, terms or {})

    def pf(self, **kw):
        data = {"process": "cmp", "title": "CMPの解説", "description": "あ" * 60, "published_at": "2026-10-07", "ai_generated": True,
                "sources": [{"id": "S1", "title": "t", "publisher": "p", "url": "https://a.example.org/1", "accessed_on": "2026-10-07"}]}
        data.update(kw)
        return data

    def test_clean(self):
        self.assertEqual(self.run_check("cmp", self.pf(), "## 見出し\n" + body()), [])

    def test_process_must_match_file_name_and_supply_chain(self):
        problems = self.run_check("cmp", self.pf(process="etching"), body())
        self.assertEqual([(p.rule, p.severity) for p in problems], [("V-02", "error")])
        problems = self.run_check("no-such-process", self.pf(process="no-such-process"), body())
        self.assertEqual([(p.rule, p.severity) for p in problems], [("V-04", "error")])

    def test_terms_exist(self):
        problems = self.run_check("cmp", self.pf(terms=["plasma", "no-such"]), body())
        self.assertEqual([(p.rule, p.severity, p.path) for p in problems], [("V-04", "warning", "/terms/0"), ("V-04", "error", "/terms/1")])
        terms = {"content/glossary/plasma.md": (fm(), body())}
        self.assertEqual([p.path for p in self.run_check("cmp", self.pf(terms=["plasma"]), body(), terms)], [])

    def test_citations_headings_and_title(self):
        problems = self.run_check("cmp", self.pf(title="あ" * 61), "## 見出し\n" + body(cite="[S2]"))
        self.assertEqual(sorted((p.rule, p.severity) for p in problems), [("V-07", "error"), ("V-08", "warning"), ("V-12", "warning")])
        self.assertEqual(rules(self.run_check("cmp", self.pf(), "# 大見出し\n" + body())), ["V-10"])


class WholeRepositoryTest(unittest.TestCase):
    def make_repo(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        repo = Path(directory.name)
        shutil.copytree(ROOT / "data", repo / "data")
        shutil.copytree(ROOT / "config", repo / "config")
        (repo / "content" / "glossary").mkdir(parents=True)
        (repo / "content" / "processes").mkdir(parents=True)
        return repo

    def write(self, repo, rel, data, text):
        (repo / rel).write_text("---\n" + yaml.safe_dump(data, allow_unicode=True, sort_keys=False) + "---\n\n" + text, encoding="utf-8")

    def test_kinds_and_files_are_collected_and_checked(self):
        repo = self.make_repo()
        url = CONFIG["terms"]["eda"]["sources"][0]["url"]
        data = fm(term="EDA(設計ツール)", sources=[{"id": "S1", "title": "t", "publisher": "p", "url": url, "accessed_on": "2026-10-07"}])
        self.write(repo, "content/glossary/eda.md", data, body())
        self.write(repo, "content/processes/cmp.md", TermCheckTest().__class__ and ProcessCheckTest().pf(
            sources=data["sources"]), "## 見出し\n" + body())
        kinds = sorted({k for k, _ in vd.collect_files(repo)})
        self.assertIn("term", kinds)
        self.assertIn("process", kinds)
        self.assertIn("explainer-sources", kinds)
        self.assertEqual([str(p) for p in vd.validate(repo, ROOT) if p.severity == "error"], [])
        self.assertEqual(vd.kind_of(repo / "content" / "glossary" / "eda.md", repo), "term")
        self.assertEqual(vd.kind_of(repo / "content" / "processes" / "cmp.md", repo), "process")
        self.assertEqual(vd.kind_of(repo / "config" / "explainer-sources.yaml", repo), "explainer-sources")

    def test_schema_violations_and_extra_fields_are_errors(self):
        repo = self.make_repo()
        data = fm(term="EDA(設計ツール)", reading="eda", extra_field=1)
        self.write(repo, "content/glossary/eda.md", data, body())
        problems = [p for p in vd.validate(repo, ROOT) if p.file == "content/glossary/eda.md" and p.severity == "error"]
        self.assertEqual({p.rule for p in problems}, {"V-01"})
        self.assertTrue(any(p.path == "/reading" for p in problems))

    def test_cli_path_option_accepts_the_new_kinds(self):
        repo = self.make_repo()
        url = CONFIG["terms"]["eda"]["sources"][0]["url"]
        self.write(repo, "content/glossary/eda.md", fm(term="EDA(設計ツール)", sources=[{"id": "S1", "title": "t", "publisher": "p", "url": url, "accessed_on": "2026-10-07"}]), body())
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(vd.main(["--path", str(repo / "content" / "glossary" / "eda.md")], root=repo, schema_root=ROOT), 0)
            self.assertEqual(vd.main(["--path", str(repo / "config" / "explainer-sources.yaml")], root=repo, schema_root=ROOT), 0)

    def test_the_real_repository_has_no_errors(self):
        self.assertEqual([str(p) for p in vd.validate(ROOT, ROOT) if p.severity == "error"], [])


if __name__ == "__main__":
    unittest.main()


class ReviewedConfigTest(unittest.TestCase):
    def check(self, mutate):
        config = copy.deepcopy(CONFIG)
        mutate(config)
        return vd.check_explainer_sources(config, SUPPLY)

    def test_the_designated_targets_have_basis_reviewed(self):
        terms = sorted(k for k, v in CONFIG["terms"].items() if v.get("basis") == "reviewed")
        self.assertEqual(terms, sorted(["ald", "coater-developer", "hbm", "osat", "mold-compound", "power-semiconductor", "process-node"]))
        self.assertEqual([k for k, v in CONFIG["processes"].items() if v.get("basis") == "reviewed"], ["etching"])

    def test_reviewed_with_empty_or_missing_sources_is_not_a_warning(self):
        problems = self.check(lambda c: c["terms"]["ald"].__setitem__("sources", []))
        self.assertEqual([p for p in problems if p.path.startswith("/terms/ald")], [])
        problems = self.check(lambda c: c["terms"]["ald"].pop("sources", None))
        self.assertEqual([p for p in problems if p.path.startswith("/terms/ald")], [])
        problems = self.check(lambda c: c["processes"]["etching"].__setitem__("sources", []))
        self.assertEqual([p for p in problems if p.path.startswith("/processes/etching")], [])

    def test_reviewed_may_keep_sources_and_they_are_still_checked(self):
        def add(c):
            c["terms"]["ald"]["sources"] = [fk.source("https://a.example.org/x"), {**fk.source("ftp://bad"), "status": "weird"}]
        problems = self.check(add)
        self.assertEqual({p.path for p in problems if p.severity == "error" and p.path.startswith("/terms/ald")},
                         {"/terms/ald/sources/1/status", "/terms/ald/sources/1/url"})

    def test_basis_value_must_be_reviewed(self):
        for value in ("sources", "other", True):
            problems = self.check(lambda c: c["terms"]["ald"].__setitem__("basis", value))
            self.assertIn("/terms/ald/basis", [p.path for p in problems if p.severity == "error"], value)

    def test_without_basis_an_empty_sources_is_still_a_warning(self):
        def drop(c):
            del c["terms"]["ald"]["basis"]
        problems = self.check(drop)
        self.assertEqual([(p.path, p.severity) for p in problems if p.path.startswith("/terms/ald")], [("/terms/ald/sources", "warning")])

    def test_the_repository_config_has_only_the_http_warning_left(self):
        warnings = [(p.path, p.severity) for p in vd.check_explainer_sources(CONFIG, SUPPLY) if p.severity == "warning"]
        self.assertEqual([w for w in warnings if "sources" in w[0] and w[0].endswith("/sources")], [])


class ReviewedFileTest(unittest.TestCase):
    NAMES = {"東京エレクトロン", "SUMCO"}
    REVIEWED_CFG = copy.deepcopy(CONFIG)

    def term(self, **kw):
        data = fm(term="ALD", basis="reviewed", sources=[], **kw)
        return data

    def run_check(self, data, text, config=None, slug="ald", names=None):
        return vd.check_terms({f"content/glossary/{slug}.md": (data, text)}, SUPPLY, config or self.REVIEWED_CFG,
                              self.NAMES if names is None else names)

    def test_a_clean_draft_has_no_problems(self):
        self.assertEqual(self.run_check(self.term(), "あ" * 300 + "。\n"), [])

    def test_unpublished_needs_no_review_fields_but_published_does(self):
        self.assertEqual(self.run_check(self.term(draft=True), body(300, cite="")), [])
        data = self.term()
        data["draft"] = False
        problems = [p for p in self.run_check(data, body(300, cite="")) if p.severity == "error"]
        self.assertEqual(sorted(p.path for p in problems), ["/review_methods", "/reviewed_on"])
        data.pop("draft")  # draft の省略も、公開として扱う
        self.assertEqual(sorted(p.path for p in self.run_check(data, body(300, cite="")) if p.severity == "error"), ["/review_methods", "/reviewed_on"])
        data.update({"draft": False, "reviewed_on": "2026-10-07", "review_methods": ["operator_knowledge"]})
        self.assertEqual(self.run_check(data, body(300, cite="")), [])

    def test_empty_review_methods_is_an_error_when_published(self):
        data = self.term(draft=False, reviewed_on="2026-10-07", review_methods=[])
        self.assertEqual([p.path for p in self.run_check(data, body(300, cite="")) if p.severity == "error"], ["/review_methods"])

    def test_citation_digits_and_company_names_are_warnings(self):
        problems = self.run_check(self.term(draft=True), "あ" * 300 + "。[S1]\n")
        self.assertEqual([(p.rule, p.severity) for p in problems], [("V-07", "warning"), ("V-07", "error")])  # sources が空なので、[S1] は V-07 のエラーでもある
        problems = self.run_check(self.term(draft=True), "あ" * 300 + "。2020年である。\n")
        self.assertEqual([(p.rule, p.severity, "数字" in p.message) for p in problems], [("V-12", "warning", True)])
        problems = self.run_check(self.term(draft=True), "あ" * 300 + "。東京エレクトロンの装置である。\n")
        self.assertEqual([(p.rule, p.severity) for p in problems], [("V-12", "warning")])
        self.assertIn("東京エレクトロン", problems[0].message)
        problems = self.run_check(self.term(draft=True), "あ" * 300 + "。２０２０年である。\n")  # 全角の数字も
        self.assertEqual([p.rule for p in problems], ["V-12"])

    def test_company_names_come_from_the_master(self):
        companies = {"a.yaml": {"name": "架空エレクトロニクス", "short_names": ["架空電子", "Ｋ"], "name_en": "Fictional Electronics Co."},
                     "b.yaml": "not a dict"}
        names = vd.company_names(companies)
        self.assertEqual(names, {"架空エレクトロニクス", "架空電子", "Fictional Electronics Co."})  # 1字は除く
        problems = self.run_check(self.term(draft=True), "あ" * 300 + "。fictional electronics co.の装置である。\n", names=names)
        self.assertEqual([p.rule for p in problems], ["V-12"])

    def test_sources_may_be_empty_and_unused_sources_are_not_warned(self):
        source = {"id": "S1", "kind": "book", "title": "入門書", "publisher": "出版社", "author": "著者", "pages": "10"}
        self.assertEqual(self.run_check(self.term(draft=True, sources=[source]) if False else {**self.term(draft=True), "sources": [source]},
                                        "あ" * 300 + "。\n"), [])

    def test_basis_reviewed_must_be_designated_in_the_config(self):
        problems = self.run_check(self.term(draft=True), "あ" * 300 + "。\n", slug="eda")
        self.assertIn(("V-04", "error", "/basis"), [(p.rule, p.severity, p.path) for p in problems])
        config = copy.deepcopy(CONFIG)
        del config["terms"]["ald"]["basis"]
        problems = self.run_check(self.term(draft=True), "あ" * 300 + "。\n", config=config)
        self.assertIn(("V-04", "error", "/basis"), [(p.rule, p.severity, p.path) for p in problems])

    def test_a_sources_file_for_a_reviewed_target_is_a_warning(self):
        data = fm(term="ALD")
        problems = self.run_check(data, body(300, cite="[S1]"))
        self.assertIn(("V-04", "warning", "/basis"), [(p.rule, p.severity, p.path) for p in problems])

    def test_process_pages(self):
        data = {"process": "etching", "title": "エッチング", "description": "あ" * 60, "basis": "reviewed", "published_at": "2026-10-07",
                "draft": True, "ai_generated": True, "sources": []}
        run = lambda d, t, **kw: vd.check_process_pages({"content/processes/etching.md": (d, t)}, SUPPLY, kw.get("config", CONFIG), {}, self.NAMES)
        self.assertEqual(run(data, "あ" * 400 + "。\n"), [])
        self.assertEqual([p.severity for p in run(data, "あ" * 400 + "。3回行う\n")], ["warning"])
        published = {**data, "draft": False}
        self.assertEqual(sorted(p.path for p in run(published, "あ" * 400 + "。\n") if p.severity == "error"), ["/review_methods", "/reviewed_on"])
        config = copy.deepcopy(CONFIG)
        del config["processes"]["etching"]["basis"]
        self.assertIn("/basis", [p.path for p in run(data, "あ" * 400 + "。\n", config=config) if p.severity == "error"])


class ReviewedRepositoryTest(unittest.TestCase):
    def test_a_reviewed_file_goes_through_the_whole_validation(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        repo = Path(directory.name)
        shutil.copytree(ROOT / "data", repo / "data")
        shutil.copytree(ROOT / "config", repo / "config")
        (repo / "content" / "glossary").mkdir(parents=True)
        (repo / "content" / "processes").mkdir(parents=True)

        def write(rel, data, text):
            (repo / rel).write_text("---\n" + yaml.safe_dump(data, allow_unicode=True, sort_keys=False) + "---\n\n" + text, encoding="utf-8")
        term = {"term": "ALD", "reading": "エーエルディー", "short_definition": "短い説明である。", "processes": ["deposition"],
                "description": "あ" * 60, "basis": "reviewed", "published_at": "2026-10-07", "draft": True, "ai_generated": True, "sources": []}
        write("content/glossary/ald.md", term, "あ" * 300 + "。\n")
        errors = lambda: [str(p) for p in vd.validate(repo, ROOT) if p.severity == "error"]
        self.assertEqual(errors(), [])
        term["draft"] = False  # reviewed_on と review_methods がなく、スキーマにも、検査にも、引っかかる
        write("content/glossary/ald.md", term, "あ" * 300 + "。\n")
        found = errors()
        self.assertTrue(any("/reviewed_on" in e for e in found), found)
        self.assertTrue(any("/review_methods" in e for e in found), found)
        term.update({"reviewed_on": "2026-10-07", "review_methods": ["operator_knowledge"]})
        write("content/glossary/ald.md", term, "あ" * 300 + "。\n")
        self.assertEqual(errors(), [])
        term["review_methods"] = ["book"]  # 書籍で確かめたのに、sources がない
        write("content/glossary/ald.md", term, "あ" * 300 + "。\n")
        self.assertTrue(errors())
        term["sources"] = [{"id": "S1", "kind": "book", "title": "入門書", "publisher": "出版社", "author": "著者", "pages": "10-12"}]
        write("content/glossary/ald.md", term, "あ" * 300 + "。\n")
        self.assertEqual(errors(), [])

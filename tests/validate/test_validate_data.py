import contextlib
import copy
import io
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "validate"))
sys.path.insert(0, str(ROOT / "scripts" / "edinet"))
sys.path.insert(0, str(ROOT / "tests" / "edinet"))

import validate_data as vd  # noqa: E402

import ingest_company  # noqa: E402
from test_comparative import fy2025, fy2026, prior_fin, seg_rows  # noqa: E402

build_auto = __import__("build_auto")
JST = ZoneInfo("Asia/Tokyo")


def auto_data():
    """合成のCSVから、build_auto で、正しい data/auto の内容を作る（2期、前期の列による置き換えを含む）。"""
    import test_comparative as tc
    first, _ = build_auto.build("advantest", "E01950", None, [fy2025()], datetime(2026, 10, 4, 10, 0, tzinfo=JST), tc.DOC_TYPES)
    data, _ = build_auto.build("advantest", "E01950", first, [fy2026(prior=prior_fin(oi=400_000_000))],
                               datetime(2026, 10, 5, 10, 0, tzinfo=JST), tc.DOC_TYPES)
    assert data["revisions"], "合成データに revisions がない"
    return data


class Base(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "data" / "companies").mkdir(parents=True)
        (self.root / "data" / "auto").mkdir()
        (self.root / "config").mkdir()
        shutil.copy(ROOT / "data" / "supply-chain.yaml", self.root / "data" / "supply-chain.yaml")
        shutil.copy(ROOT / "config" / "xbrl-map.yaml", self.root / "config" / "xbrl-map.yaml")
        shutil.copy(ROOT / "data" / "companies" / "advantest.yaml", self.root / "data" / "companies" / "advantest.yaml")
        self.company = yaml.safe_load((ROOT / "data" / "companies" / "advantest.yaml").read_text(encoding="utf-8"))
        self.write_auto(auto_data())

    def write_company(self, data, name=None):
        name = name or data["slug"]
        (self.root / "data" / "companies" / f"{name}.yaml").write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def write_auto(self, data, name="advantest"):
        (self.root / "data" / "auto" / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                                                                  encoding="utf-8")

    def check(self, **kw):
        return vd.validate(self.root, **kw)

    def has(self, problems, rule, text="", file=None, path=None):
        found = [p for p in problems if p.rule == rule and text in p.message and (file is None or p.file == file)
                 and (path is None or p.path == path)]
        self.assertTrue(found, msg=f"{rule} {text} {file} {path} が出ない。実際: {[str(p) for p in problems]}")


class RealDataTest(unittest.TestCase):
    def test_repository_data_passes(self):
        """リポジトリのデータに、エラー（severity が error）が0件であること。

        警告（severity が warning。V-12 の文字数の目安など）は、データ定義書 13章で「変更案に表示するだけ」と定めており、
        不合格にしない。そのため、警告があっても、このテストは失敗しない。警告は、テストの出力に一覧として出す。
        validate_data.py の終了コード（警告だけなら0、--strict で警告もエラー）は、ここでは確かめない（test_cli_on_whole_repository と、警告の終了コードのテストで確かめる）。
        """
        problems = vd.validate()
        warnings = [p for p in problems if p.severity == "warning"]
        errors = [p for p in problems if p.severity == "error"]
        if warnings:
            print(f"\n警告 {len(warnings)}件（失敗にしない）：", file=sys.stderr)
            for warning in warnings:
                print(f"  {warning}", file=sys.stderr)
        self.assertEqual([str(p) for p in errors], [])

    def test_repository_has_the_expected_files(self):
        files = vd.collect_files(ROOT)
        kinds = [k for k, _ in files]
        self.assertEqual(kinds.count("company"), 88)
        self.assertEqual((kinds.count("supply-chain"), kinds.count("xbrl-map")), (1, 1))
        self.assertEqual(kinds.count("auto"), len(list((ROOT / "data" / "auto").glob("*.json"))))

    def test_cli_on_whole_repository(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = vd.main([])
        self.assertEqual(code, 0)
        self.assertIn("エラー 0件", out.getvalue())

    def test_date_time_check_is_the_same_as_ingestion(self):
        self.assertIs(vd.format_checker, ingest_company.format_checker)
        self.assertFalse(vd.format_checker().conforms("2026-13-45T10:00:00+09:00", "date-time"))


class ValidSyntheticTest(Base):
    def test_valid_data_passes(self):
        self.assertEqual([str(p) for p in self.check()], [])

    def test_valid_auto_has_revisions_and_validates_against_schema(self):
        self.assertEqual(ingest_company.validate(auto_data()), [])


class SchemaRuleTest(Base):  # V-01
    def test_extra_key_and_bad_date(self):
        bad = copy.deepcopy(self.company)
        bad["unknown_key"] = 1
        bad["selection"]["decided_on"] = "2026-13-45"
        self.write_company(bad)
        problems = self.check()
        self.has(problems, "V-01", file="data/companies/advantest.yaml")
        self.assertTrue(any("2026-13-45" in p.message or "format" in p.message or "date" in p.message
                            for p in problems if p.path == "/selection/decided_on"))

    def test_auto_bad_date_time_is_caught_by_format_check(self):
        data = auto_data()
        data["updated_at"] = "2026-13-45T10:00:00+09:00"
        self.write_auto(data)
        self.has(self.check(), "V-01", file="data/auto/advantest.json", path="/updated_at")

    def test_auto_missing_required_and_extra(self):
        data = auto_data()
        del data["revisions"]
        data["x"] = 1
        self.write_auto(data)
        self.has(self.check(), "V-01", file="data/auto/advantest.json")

    def test_supply_chain_and_xbrl_map_are_checked(self):
        supply = yaml.safe_load((self.root / "data" / "supply-chain.yaml").read_text(encoding="utf-8"))
        supply["flow"] = []
        (self.root / "data" / "supply-chain.yaml").write_text(yaml.safe_dump(supply, allow_unicode=True), encoding="utf-8")
        xmap = yaml.safe_load((self.root / "config" / "xbrl-map.yaml").read_text(encoding="utf-8"))
        del xmap["employees"]
        (self.root / "config" / "xbrl-map.yaml").write_text(yaml.safe_dump(xmap, allow_unicode=True), encoding="utf-8")
        problems = self.check()
        self.has(problems, "V-01", file="data/supply-chain.yaml")
        self.has(problems, "V-01", file="config/xbrl-map.yaml")

    def test_unreadable_files(self):
        (self.root / "data" / "companies" / "broken.yaml").write_text("a: [unclosed", encoding="utf-8")
        (self.root / "data" / "auto" / "broken.json").write_text("{ nope", encoding="utf-8")
        problems = self.check()
        self.has(problems, "V-01", "読めない", file="data/companies/broken.yaml")
        self.has(problems, "V-01", "読めない", file="data/auto/broken.json")


class FileNameRuleTest(Base):  # V-02
    def test_company_file_name_and_slug(self):
        self.write_company(self.company, name="other-name")
        self.has(self.check(), "V-02", "other-name", file="data/companies/other-name.yaml", path="/slug")

    def test_auto_file_name_and_company(self):
        (self.root / "data" / "auto" / "advantest.json").rename(self.root / "data" / "auto" / "disco.json")
        self.has(self.check(), "V-02", "disco", file="data/auto/disco.json", path="/company")


class DuplicateRuleTest(Base):  # V-03
    def other_company(self, **changes):
        data = copy.deepcopy(self.company)
        data["slug"] = "another-co"
        data["edinet_code"] = "E99999"
        data["securities_code"] = "9999"
        data.update(changes)
        self.write_company(data, name="another-co")

    def test_duplicate_edinet_code_and_securities_code(self):
        self.other_company(edinet_code=self.company["edinet_code"], securities_code=self.company["securities_code"])
        problems = self.check()
        self.has(problems, "V-03", "edinet_code", file="data/companies/another-co.yaml", path="/edinet_code")
        self.has(problems, "V-03", "securities_code", file="data/companies/another-co.yaml")

    def test_duplicate_slug(self):
        self.other_company(slug=self.company["slug"])
        problems = self.check()
        self.has(problems, "V-03", "slug", file="data/companies/another-co.yaml", path="/slug")

    def test_duplicate_source_id(self):
        data = copy.deepcopy(self.company)
        source = {"id": "S1", "title": "t", "publisher": "p", "url": "https://example.com/a", "accessed_on": "2026-10-04"}
        data["sources"] = [source, copy.deepcopy(source)]
        self.write_company(data)
        self.has(self.check(), "V-03", "S1", path="/sources/1/id")

    def test_duplicate_doc_id_and_periods(self):
        data = auto_data()
        data["filings"].append(copy.deepcopy(data["filings"][0]))
        data["financials"].append(copy.deepcopy(data["financials"][0]))
        data["employees"].append(copy.deepcopy(data["employees"][0]))
        self.write_auto(data)
        problems = self.check()
        self.has(problems, "V-03", "doc_id", path=f"/filings/{len(data['filings']) - 1}/doc_id")
        self.has(problems, "V-03", "期間", path=f"/financials/{len(data['financials']) - 1}")
        self.has(problems, "V-03", "期間", path=f"/employees/{len(data['employees']) - 1}")

    def test_same_fiscal_period_end_with_different_period_type_is_not_a_duplicate(self):
        data = auto_data()
        half = copy.deepcopy(data["financials"][0])
        half["period_type"] = "half"
        half["period_end"] = "2024-09-30"
        data["financials"].insert(0, half)
        self.write_auto(data)
        self.assertEqual([p for p in self.check() if "期間" in p.message and "重複" in p.message], [])

    def test_order(self):
        data = auto_data()
        data["financials"].reverse()
        data["employees"].reverse()
        self.write_auto(data)
        problems = self.check()
        self.has(problems, "V-03", "古い順", path="/financials")
        self.has(problems, "V-03", "古い順", path="/employees")

    def test_duplicate_supply_chain_slug(self):
        supply = yaml.safe_load((self.root / "data" / "supply-chain.yaml").read_text(encoding="utf-8"))
        supply["processes"].append(copy.deepcopy(supply["processes"][0]))
        (self.root / "data" / "supply-chain.yaml").write_text(yaml.safe_dump(supply, allow_unicode=True), encoding="utf-8")
        self.has(self.check(), "V-03", "重複", file="data/supply-chain.yaml")


class ReferenceRuleTest(Base):  # V-04
    def test_auto_company_must_exist_and_edinet_code_must_match(self):
        data = auto_data()
        data["edinet_code"] = "E00001"
        self.write_auto(data)
        self.has(self.check(), "V-04", "一致しない", file="data/auto/advantest.json", path="/edinet_code")
        data = auto_data()
        data["company"] = "ghost-co"
        (self.root / "data" / "auto" / "advantest.json").unlink()
        self.write_auto(data, "ghost-co")
        self.has(self.check(), "V-04", "ghost-co", file="data/auto/ghost-co.json", path="/company")

    def test_source_references(self):
        data = copy.deepcopy(self.company)
        data["sources"] = [{"id": "S1", "title": "t", "publisher": "p", "url": "https://example.com/a",
                            "accessed_on": "2026-10-04"}]
        data["selection"]["source"] = "S1"
        data["parent"] = {"name": "親", "name_en": "Parent", "country": "US", "source": "S1"}
        data["history"] = [{"date": "2020-01-01", "type": "other", "description": "d", "source": "S1"}]
        self.write_company({k: v for k, v in data.items() if k != "parent"})
        self.assertEqual([p for p in self.check() if p.rule == "V-04"], [])
        data["selection"]["source"] = "S9"
        data["parent"]["source"] = "S8"
        data["history"][0]["source"] = "S7"
        (self.root / "data" / "companies" / "advantest.yaml").write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        problems = self.check()
        self.has(problems, "V-04", "S9", path="/selection/source")
        self.has(problems, "V-04", "S8", path="/parent/source")
        self.has(problems, "V-04", "S7", path="/history/0/source")

    def test_categories_and_processes_must_exist_in_supply_chain(self):
        supply = yaml.safe_load((self.root / "data" / "supply-chain.yaml").read_text(encoding="utf-8"))
        supply["categories"] = [c for c in supply["categories"] if c["slug"] != self.company["categories"][0]]
        supply["processes"] = [p for p in supply["processes"] if p["slug"] != "cmp"]
        (self.root / "data" / "supply-chain.yaml").write_text(yaml.safe_dump(supply, allow_unicode=True), encoding="utf-8")
        data = copy.deepcopy(self.company)
        data["processes"] = ["cmp"]
        self.write_company(data)
        problems = self.check()
        self.has(problems, "V-04", "categories", file="data/companies/advantest.yaml")
        self.has(problems, "V-04", "cmp", file="data/companies/advantest.yaml", path="/processes/0")

    def test_schema_enum_and_supply_chain_must_agree(self):
        schemas = vd.SchemaSet(ROOT)
        supply = yaml.safe_load((ROOT / "data" / "supply-chain.yaml").read_text(encoding="utf-8"))
        schemas.documents["company"]["properties"]["processes"]["items"]["enum"] = ["wafer"]
        problems = vd.check_supply_chain({}, supply, schemas)
        self.has(problems, "V-04", "一致しない", file="data/supply-chain.yaml", path="/processes")

    def test_revision_path_must_point_to_an_existing_value(self):
        data = auto_data()
        data["revisions"][0]["path"] = "/financials/9/net_sales/value"
        data["revisions"].append({**data["revisions"][0], "path": "/financials/0/no_such_item/value"})
        self.write_auto(data)
        problems = self.check()
        self.has(problems, "V-04", "実在", path="/revisions/0/path")
        self.has(problems, "V-04", "実在", path=f"/revisions/{len(data['revisions']) - 1}/path")

    def test_removed_items_with_null_new_are_allowed_only_for_removed_item_paths(self):
        data = auto_data()
        base = data["revisions"][0]
        data["revisions"] += [{**base, "path": "/financials/0/ordinary_income/value", "old": 1, "new": None},
                              {**base, "path": "/financials/0/segment_adjustment/value", "old": 1, "new": None}]
        del data["financials"][0]["ordinary_income"]
        self.write_auto(data)
        self.assertEqual([p for p in self.check() if p.rule == "V-04"], [])
        # new が null でなければ、不合格。行が実在しなければ、不合格。ほかの項目の path も、不合格
        data["revisions"][-2]["new"] = 5
        data["revisions"].append({**base, "path": "/financials/9/ordinary_income/value", "old": 1, "new": None})
        data["revisions"].append({**base, "path": "/financials/0/net_sales_missing/value", "old": 1, "new": None})
        self.write_auto(data)
        paths = sorted(p.path for p in self.check() if p.rule == "V-04" and "実在" in p.message)
        n = len(data["revisions"])
        self.assertEqual(paths, sorted([f"/revisions/{n - 4}/path", f"/revisions/{n - 2}/path", f"/revisions/{n - 1}/path"]))

    def test_revision_path_that_exists_passes(self):
        data = auto_data()
        self.assertTrue(data["revisions"][0]["path"].startswith("/financials/0/"))
        self.assertEqual([p for p in self.check() if "実在" in p.message], [])

    def test_revision_supersedes_and_doc_id_must_be_in_filings(self):
        data = auto_data()
        data["revisions"][0]["supersedes"] = "S100ZZZ9"
        data["revisions"][0]["doc_id"] = "S100ZZZ8"
        self.write_auto(data)
        problems = self.check()
        self.has(problems, "V-04", "S100ZZZ9", path="/revisions/0/supersedes")
        self.has(problems, "V-04", "S100ZZZ8", path="/revisions/0/doc_id")

    def test_row_doc_id_must_be_in_filings(self):
        data = auto_data()
        data["financials"][0]["doc_id"] = "S100ZZZ7"
        self.write_auto(data)
        self.has(self.check(), "V-04", "S100ZZZ7", path="/financials/0/doc_id")


class YamlPitfallTest(Base):
    def test_unquoted_date(self):
        data = (ROOT / "data" / "companies" / "advantest.yaml").read_text(encoding="utf-8")
        import re
        text = re.sub(r'decided_on: "(\d{4}-\d{2}-\d{2})"', r"decided_on: \1", data)
        self.assertNotEqual(text, data)
        (self.root / "data" / "companies" / "advantest.yaml").write_text(text, encoding="utf-8")
        problems = self.check()
        self.has(problems, "YAML", "引用符なしの日付", path="/selection/decided_on")
        self.assertTrue(any("行目" in p.message for p in problems if p.rule == "YAML"))
        self.has(problems, "V-01", path="/selection/decided_on")

    def test_unquoted_no_yes_on_off(self):
        data = (ROOT / "data" / "companies" / "advantest.yaml").read_text(encoding="utf-8")
        for word in ("no", "yes", "on", "off", "No", "YES"):
            (self.root / "data" / "companies" / "advantest.yaml").write_text(data + f"\nname_en_note: {word}\n", encoding="utf-8")
            self.has(self.check(), "YAML", word, path="/name_en_note")

    def test_no_in_a_string_field_is_also_a_schema_error(self):
        data = (ROOT / "data" / "companies" / "advantest.yaml").read_text(encoding="utf-8")
        import re
        text = re.sub(r"^name_en: .*$", "name_en: no", data, count=1, flags=re.M)
        (self.root / "data" / "companies" / "advantest.yaml").write_text(text, encoding="utf-8")
        problems = self.check()
        self.has(problems, "YAML", path="/name_en")
        self.has(problems, "V-01", path="/name_en")

    def test_quoted_values_and_real_booleans_pass(self):
        data = (ROOT / "data" / "companies" / "advantest.yaml").read_text(encoding="utf-8")
        text = data + '\nis_holding_company: false\n'
        (self.root / "data" / "companies" / "advantest.yaml").write_text(text, encoding="utf-8")
        self.assertEqual([p for p in self.check() if p.rule == "YAML"], [])
        (self.root / "data" / "companies" / "advantest.yaml").write_text(data + '\nname_en_note: "no"\n', encoding="utf-8")
        self.assertEqual([p for p in self.check() if p.rule == "YAML"], [])

    def test_supply_chain_and_xbrl_map_pitfalls(self):
        path = self.root / "data" / "supply-chain.yaml"
        path.write_text(path.read_text(encoding="utf-8") + "\nnote: 2026-10-04\n", encoding="utf-8")
        path = self.root / "config" / "xbrl-map.yaml"
        path.write_text(path.read_text(encoding="utf-8") + "\nflag: off\n", encoding="utf-8")
        problems = self.check()
        self.has(problems, "YAML", file="data/supply-chain.yaml", path="/note")
        self.has(problems, "YAML", file="config/xbrl-map.yaml", path="/flag")


class CliTest(Base):
    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = vd.main(argv, root=self.root)
        return code, out.getvalue(), err.getvalue()

    def test_valid_exit_0_and_error_exit_1_with_listing(self):
        code, out, _ = self.run_main([])
        self.assertEqual(code, 0)
        self.assertIn("エラー 0件", out)
        data = auto_data()
        data["revisions"][0]["path"] = "/financials/9/x/value"
        self.write_auto(data)
        code, out, _ = self.run_main([])
        self.assertEqual(code, 1)
        self.assertIn("data/auto/advantest.json: /revisions/0/path: [V-04]", out)

    def test_warning_mechanism_and_strict_still_work(self):
        # 今は、警告になる検査はない。警告の仕組みと --strict は、今後のために残してあるので、模擬の警告で確かめる
        from unittest import mock
        warning = vd.Problem("data/auto/advantest.json", "/x", "V-04", "模擬の警告", severity="warning")
        with mock.patch.object(vd, "check_auto", return_value=[warning]):
            code, out, _ = self.run_main([])
            self.assertEqual(code, 0)
            self.assertIn("警告 data/auto/advantest.json: /x: [V-04] 模擬の警告", out)
            self.assertIn("エラー 0件 / 警告 1件", out)
            self.assertEqual(self.run_main(["--strict"])[0], 1)

    def test_broken_chain_is_an_error(self):
        data = auto_data()
        data["filings"][0]["status"] = "superseded"  # どの書類の supersedes からも指されていない
        self.write_auto(data)
        problems = self.check()
        chain = [p for p in problems if "supersedes からも指されていない" in p.message]
        self.assertEqual([(p.severity, p.rule, p.path) for p in chain], [("error", "V-04", "/filings/0/status")])
        self.assertEqual(self.run_main([])[0], 1)

    def test_path_checks_one_file_only(self):
        data = auto_data()
        data["revisions"][0]["path"] = "/financials/9/x/value"
        self.write_auto(data)
        bad_company = copy.deepcopy(self.company)
        bad_company["unknown_key"] = 1
        self.write_company(bad_company)
        code, out, _ = self.run_main(["--path", str(self.root / "data" / "auto" / "advantest.json")])
        self.assertEqual(code, 1)
        self.assertIn("data/auto/advantest.json", out)
        self.assertNotIn("data/companies/advantest.yaml", out)
        self.assertIn("検査したファイル 1件", out)
        code, out, _ = self.run_main(["--path", str(self.root / "data" / "supply-chain.yaml")])
        self.assertEqual(code, 0)

    def test_path_still_uses_other_files_for_references(self):
        (self.root / "data" / "companies" / "advantest.yaml").unlink()
        code, out, _ = self.run_main(["--path", str(self.root / "data" / "auto" / "advantest.json")])
        self.assertEqual(code, 1)
        self.assertIn("data/companies にない", out)

    def test_path_outside_targets_or_missing_is_usage_error(self):
        (self.root / "README.md").write_text("x", encoding="utf-8")
        for target in (self.root / "README.md", self.root / "data" / "companies" / "nope.yaml"):
            code, _, err = self.run_main(["--path", str(target)])
            self.assertEqual(code, 2)
            self.assertIn("対象のファイルではない", err)

    def test_relative_path_from_repository_root(self):
        import os
        previous = os.getcwd()
        os.chdir(ROOT)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(vd.main(["--path", "data/supply-chain.yaml"]), 0)
                self.assertEqual(vd.main(["--path", "data/companies/advantest.yaml"]), 0)
        finally:
            os.chdir(previous)


MEMBER_A, MEMBER_B = "TestAlphaReportableSegmentsMember", "TestBetaReportableSegmentsMember"


def segment_row(member, doc_id="S100AAA1"):
    """data/auto の financials のセグメントの行（合成）。形は auto-company.schema.json に合わせる。"""
    def value(element, number):
        return {"value": number, "unit": "million_yen", "original_unit": "yen", "element": element,
                "context": f"CurrentYearDuration_jpcrp030000-asr_E01950-000{member}", "doc_id": doc_id,
                "ingested_at": "2026-10-04T22:42:50+09:00"}
    return {"name": member, "member": member,
            "net_sales_external": value("jpcrp_cor:RevenuesFromExternalCustomers", 100),
            "net_sales_total": value("jppfs_cor:NetSales", 110),
            "profit": value("jppfs_cor:OperatingIncome", 10)}


def overview_body(length=350, extra="", cites="[S1]"):
    """合成の本文。「事業概要」は、全角の文字を length 字にする（出典の番号は数えない）。"""
    text = "あ" * (length - 1) + "。"
    return f"## 事業概要\n\n{text}{cites}\n\n## 工程上の位置づけ\n\n工程の説明（合成）。[S2]\n{extra}"


SOURCES = [{"id": f"S{n}", "title": f"資料{n}", "publisher": "発行元", "url": f"https://example.com/{n}",
            "accessed_on": "2026-10-06"} for n in (1, 2)]


class SegmentsOverviewBase(Base):
    def setUp(self):
        super().setUp()
        auto = auto_data()
        for row, member in zip(auto["financials"][-2:], (MEMBER_A, MEMBER_B)):
            row["segments"] = [segment_row(member, row["doc_id"])]
        self.write_auto(auto)
        self.doc_id = auto["filings"][0]["doc_id"]
        self.segment_map = {
            "schema_version": 1, "company": "advantest", "reviewed_on": "2026-10-06", "based_on": self.doc_id,
            "segments": [
                {"name": "セグメントA（合成）", "xbrl_members": [MEMBER_A], "classification": "semiconductor",
                 "rationale": {"source": "S1", "pages": "10"}},
                {"name": "セグメントB（合成）", "xbrl_members": [MEMBER_B], "classification": "excluded",
                 "rationale": {"source": "S1", "pages": "11"}},
            ],
            "reference_values": [{"fiscal_period_end": "2026-03", "period_type": "annual", "value_mjpy": 100,
                                  "label": "合成の売上", "source": "S2"}],
            "sources": copy.deepcopy(SOURCES),
        }
        self.front = {"company": "advantest", "published_at": "2026-10-06", "ai_generated": True,
                      "sources": copy.deepcopy(SOURCES)}

    def write_segments(self, data=None, name="advantest"):
        directory = self.root / "data" / "segments"
        directory.mkdir(exist_ok=True)
        (directory / f"{name}.yaml").write_text(
            yaml.safe_dump(self.segment_map if data is None else data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def write_overview(self, body=None, front=None, name="advantest", raw=None):
        directory = self.root / "content" / "companies"
        directory.mkdir(parents=True, exist_ok=True)
        text = raw if raw is not None else (
            "---\n" + yaml.safe_dump(self.front if front is None else front, allow_unicode=True, sort_keys=False)
            + "---\n\n" + (overview_body() if body is None else body))
        (directory / f"{name}.md").write_text(text, encoding="utf-8")


class NoFilesTest(Base):
    def test_no_segments_or_overviews_passes(self):
        self.assertFalse((self.root / "data" / "segments").exists())
        self.assertEqual([str(p) for p in self.check()], [])
        kinds = [k for k, _ in vd.collect_files(self.root)]
        self.assertNotIn("segment-map", kinds)
        self.assertNotIn("overview", kinds)

    def test_empty_directories_pass(self):
        (self.root / "data" / "segments").mkdir()
        (self.root / "content" / "companies").mkdir(parents=True)
        self.assertEqual([str(p) for p in self.check()], [])


class SegmentMapTest(SegmentsOverviewBase):
    FILE = "data/segments/advantest.yaml"

    def test_valid_passes(self):
        self.write_segments()
        self.assertEqual([str(p) for p in self.check()], [])

    def test_schema_violation(self):
        bad = copy.deepcopy(self.segment_map)
        bad["segments"][0]["classification"] = "unknown"
        bad["unknown_key"] = 1
        self.write_segments(bad)
        self.has(self.check(), "V-01", file=self.FILE)

    def test_file_name_and_company_must_match(self):
        self.write_segments(name="other")
        self.has(self.check(), "V-02", "一致しない", file="data/segments/other.yaml")

    def test_company_must_exist_in_master(self):
        bad = copy.deepcopy(self.segment_map)
        bad["company"] = "nosuchco"
        self.write_segments(bad, name="nosuchco")
        problems = self.check()
        self.has(problems, "V-04", "data/companies にない", file="data/segments/nosuchco.yaml")
        self.has(problems, "V-04", "data/auto/nosuchco.json がない", file="data/segments/nosuchco.yaml")

    def test_based_on_must_be_in_filings(self):
        bad = copy.deepcopy(self.segment_map)
        bad["based_on"] = "S100ZZZZ"
        self.write_segments(bad)
        self.has(self.check(), "V-04", "S100ZZZZ", file=self.FILE, path="/based_on")

    def test_xbrl_member_must_exist_in_auto_segments(self):
        bad = copy.deepcopy(self.segment_map)
        bad["segments"][1]["xbrl_members"] = [MEMBER_B, "NoSuchMember"]
        self.write_segments(bad)
        problems = self.check()
        self.has(problems, "V-04", "NoSuchMember", file=self.FILE, path="/segments/1/xbrl_members/1")
        self.assertEqual(len([p for p in problems if "xbrl_members" in p.path]), 1)

    def test_members_from_any_period_are_accepted(self):
        # MEMBER_A は前の期、MEMBER_B は後の期の financials にだけある
        self.write_segments()
        auto = json.loads((self.root / "data" / "auto" / "advantest.json").read_text(encoding="utf-8"))
        self.assertNotEqual(auto["financials"][-2]["segments"], auto["financials"][-1]["segments"])
        self.assertEqual([str(p) for p in self.check()], [])

    def test_segments_without_xbrl_members_are_allowed(self):
        data = copy.deepcopy(self.segment_map)
        del data["segments"][0]["xbrl_members"]
        self.write_segments(data)
        self.assertEqual([str(p) for p in self.check()], [])

    def test_rationale_source_must_be_in_sources(self):
        bad = copy.deepcopy(self.segment_map)
        bad["segments"][0]["rationale"]["source"] = "S9"
        self.write_segments(bad)
        self.has(self.check(), "V-04", "S9", file=self.FILE, path="/segments/0/rationale/source")

    def test_reference_value_source_must_be_in_sources(self):
        bad = copy.deepcopy(self.segment_map)
        bad["reference_values"][0]["source"] = "S9"
        self.write_segments(bad)
        self.has(self.check(), "V-04", "S9", file=self.FILE, path="/reference_values/0/source")

    def test_duplicate_source_ids(self):
        bad = copy.deepcopy(self.segment_map)
        bad["sources"].append(copy.deepcopy(bad["sources"][0]))
        self.write_segments(bad)
        self.has(self.check(), "V-03", "S1", file=self.FILE)

    def test_missing_auto_file_is_an_error(self):
        self.write_segments()
        (self.root / "data" / "auto" / "advantest.json").unlink()
        self.has(self.check(), "V-04", "data/auto/advantest.json がない", file=self.FILE)

    def test_path_option_checks_one_segment_file(self):
        self.write_segments()
        bad = copy.deepcopy(self.segment_map)
        bad["company"] = "nosuchco"
        self.write_segments(bad, name="nosuchco")
        self.assertEqual(vd.kind_of(self.root / "data" / "segments" / "advantest.yaml", self.root), "segment-map")
        problems = self.check(only=self.root / "data" / "segments" / "advantest.yaml")
        self.assertEqual(problems, [])


class OverviewTest(SegmentsOverviewBase):
    FILE = "content/companies/advantest.md"

    def only(self, problems, rule):
        return [p for p in problems if p.rule == rule]

    def test_valid_passes_without_warnings(self):
        self.write_overview()
        self.assertEqual([str(p) for p in self.check()], [])

    def test_front_matter_schema_violation(self):
        bad = dict(self.front, unknown_key=1)
        del bad["ai_generated"]
        self.write_overview(front=bad)
        self.has(self.check(), "V-01", file=self.FILE)

    def test_missing_or_unclosed_front_matter(self):
        self.write_overview(raw="## 事業概要\n本文\n")
        self.has(self.check(), "V-01", "front matter", file=self.FILE)
        self.write_overview(raw="---\ncompany: advantest\n本文\n")
        self.has(self.check(), "V-01", "閉じる", file=self.FILE)

    def test_unquoted_date_in_front_matter_is_caught(self):
        text = ("---\ncompany: advantest\npublished_at: 2026-10-06\nai_generated: true\nsources:\n"
                "  - {id: S1, title: t, publisher: p, url: 'https://example.com/1', accessed_on: '2026-10-06'}\n"
                "  - {id: S2, title: t, publisher: p, url: 'https://example.com/2', accessed_on: '2026-10-06'}\n---\n"
                + overview_body())
        self.write_overview(raw=text)
        problems = self.check()
        self.has(problems, "YAML", "引用符なしの日付", file=self.FILE)
        self.assertIn("3行目", [p for p in problems if p.rule == "YAML"][0].message)  # ファイルの行と合う

    def test_file_name_and_company_must_match(self):
        self.write_overview(name="other")
        self.has(self.check(), "V-02", "一致しない", file="content/companies/other.md")

    def test_company_must_exist_in_master(self):
        self.write_overview(front=dict(self.front, company="nosuchco"), name="nosuchco")
        self.has(self.check(), "V-04", "data/companies にない", file="content/companies/nosuchco.md")

    def test_h1_is_an_error(self):
        self.write_overview(body="# 大見出し\n\n" + overview_body())
        self.has(self.check(), "V-10", "`#`", file=self.FILE)

    def test_wrong_headings(self):
        cases = {
            "only one": "## 事業概要\n\n" + "あ" * 350 + "[S1][S2]\n",
            "reversed": "## 工程上の位置づけ\n\n説明[S2]\n\n## 事業概要\n\n" + "あ" * 350 + "[S1]\n",
            "extra": overview_body(extra="\n## 追加の見出し\n\n本文\n"),
            "level jump": overview_body(extra="\n#### 段の飛び\n\n本文\n"),
            "renamed": overview_body().replace("## 工程上の位置づけ", "## 工程"),
            "level 3": overview_body().replace("## 工程上の位置づけ", "### 工程上の位置づけ"),
            "no headings": "本文だけ[S1][S2]\n",
        }
        for name, body in cases.items():
            with self.subTest(name):
                self.write_overview(body=body)
                self.has(self.check(), "V-10", "2つだけ", file=self.FILE)

    def test_headings_inside_code_fences_are_ignored(self):
        self.write_overview(body=overview_body(extra="\n```\n# 例\n## 例2\n```\n"))
        self.assertEqual([str(p) for p in self.check()], [])

    def test_unknown_citation_is_an_error(self):
        self.write_overview(body=overview_body(cites="[S1][S3]"))
        problems = self.check()
        self.has(problems, "V-07", "[S3]", file=self.FILE)
        self.assertEqual(len(self.only(problems, "V-07")), 1)

    def test_unused_source_is_a_warning(self):
        sources = self.front["sources"] + [dict(SOURCES[0], id="S3")]
        self.write_overview(front=dict(self.front, sources=sources))
        problems = self.check()
        self.has(problems, "V-08", "S3", file=self.FILE)
        self.assertEqual([p.severity for p in self.only(problems, "V-08")], ["warning"])
        self.assertEqual([p for p in problems if p.severity == "error"], [])

    def test_duplicate_source_ids(self):
        self.write_overview(front=dict(self.front, sources=self.front["sources"] + [SOURCES[0]]))
        self.has(self.check(), "V-03", "S1", file=self.FILE)

    def test_length_boundaries(self):
        for length, expected in ((299, 1), (300, 0), (500, 0), (501, 1)):
            with self.subTest(length=length):
                self.write_overview(body=overview_body(length))
                found = self.only(self.check(), "V-12")
                self.assertEqual(len(found), expected)
                for p in found:
                    self.assertEqual(p.severity, "warning")
                    self.assertIn(f"{length}字", p.message)

    def test_length_warning_does_not_fail_but_strict_does(self):
        self.write_overview(body=overview_body(100))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(vd.main([], root=self.root), 0)
            self.assertEqual(vd.main(["--strict"], root=self.root), 1)
        self.assertIn("警告 1件", out.getvalue())

    def test_character_count_follows_data_definition_2_6(self):
        # 出典の番号、改行、行頭と行末の空白、Markdownの記法は数えない。NFKCの後の文字を1字と数える
        lines = ["  **あいう**[S1]  ", "- え[S2]お", "[リンク](https://example.com/x)", "ＡＢＣ１２３", "", "> 引用"]
        self.assertEqual(vd.count_characters(lines), 3 + 2 + 3 + 6 + 2)
        self.assertEqual(vd.count_characters(["`コード`と_強調_と snake_case"]), 3 + 1 + 2 + 1 + 1 + 10)

    def test_count_uses_only_the_overview_section(self):
        self.write_overview(body=overview_body(350, extra="あ" * 1000 + "\n"))  # 工程の節が長くても、事業概要は350字
        self.assertEqual(self.only(self.check(), "V-12"), [])

    def test_messages_do_not_contain_body_text(self):
        self.write_overview(body="# 見出し\n\n合成の本文の語イプシロン[S9]\n")
        text = "\n".join(str(p) for p in self.check())
        self.assertNotIn("イプシロン", text)

    def test_path_option_and_cli_output(self):
        self.write_overview(body=overview_body(100))
        self.assertEqual(vd.kind_of(self.root / "content" / "companies" / "advantest.md", self.root), "overview")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = vd.main(["--path", str(self.root / "content" / "companies" / "advantest.md")], root=self.root)
        self.assertEqual(code, 0)
        self.assertIn("V-12", out.getvalue())


if __name__ == "__main__":
    unittest.main()

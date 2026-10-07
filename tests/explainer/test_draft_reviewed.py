import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

import explainer_fakes as fk
import llm_fakes as lf
import agent_call
import draft_explainer as de
import make_explainer_bundle as meb
import validate_data as vd

ROOT = fk.ROOT
OUTPUT_WORD = lf.OUTPUT_WORD
POINTS = [{"claim": "基本の説明その一", "risk": "low"}, {"claim": "誤りやすい点その一", "risk": "high"},
          {"claim": "基本の説明その二", "risk": "low"}, {"claim": "言い方が分かれる点その二", "risk": "high"}]


def term_output(**kw):
    out = {"reading": "エーエルディー", "short_definition": lf.cjk(30, 0x4E00) + "。", "description": lf.cjk(70, 0x5000) + "。",
           "body": lf.cjk(150, 0x5400) + "。\n\n" + lf.cjk(100, 0x5800) + f"。{OUTPUT_WORD}", "processes": ["deposition"],
           "related_terms": [], "check_points": POINTS}
    out.update(kw)
    return out


def process_output(**kw):
    out = {"title": "エッチングの解説", "description": lf.cjk(70, 0x5000) + "。",
           "body": lf.cjk(250, 0x5400) + "。\n\n" + lf.cjk(150, 0x5800) + f"。{OUTPUT_WORD}", "terms": [], "check_points": POINTS}
    out.update(kw)
    return out


class Base(unittest.TestCase):
    kind, slug = "term", "ald"

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.tmp = Path(directory.name)
        self.root = self.tmp / "repo"
        self.out, self.ledger = self.tmp / "out", self.tmp / "ledger"
        self.ledger.mkdir()
        (self.root / "content" / "glossary").mkdir(parents=True)
        (self.root / "content" / "processes").mkdir(parents=True)
        shutil.copytree(ROOT / "data" / "companies", self.root / "data" / "companies")  # 本文に企業名がないかの検査に使う
        self.operations = self.tmp / "operations.yaml"
        self.operations.write_text("status: active\n", encoding="utf-8")
        self.r2 = fk.FakeR2(error=RuntimeError("R2 を読んではいけない"))

    def output(self, **kw):
        return term_output(**kw) if self.kind == "term" else process_output(**kw)

    def client(self, output=None):
        return lf.FakeClient(lf.reply(output or self.output()))

    def run_draft(self, client, *, env=None, extra=(), operations=None, config=None):
        summary = self.tmp / "summary.md"
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = de.main(["--kind", self.kind, "--slug", self.slug, "--out-dir", str(self.out), "--ledger-dir", str(self.ledger),
                            "--run-id", "run42", "--summary", str(summary), *extra],
                           env={} if env is None else env, now=lambda: lf.NOW, r2_factory=lambda creds: self.r2,
                           client_factory=lambda: client, sleep=lambda s: None, root=self.root,
                           budgets_path=ROOT / "config" / "budgets.yaml", operations_path=operations or self.operations,
                           config_path=config or ROOT / "config" / "explainer-sources.yaml")
        self.stdout, self.stderr = out.getvalue(), err.getvalue()
        self.summary = summary.read_text(encoding="utf-8") if summary.exists() else ""
        return code

    def written(self):
        return sorted(p.relative_to(self.out).as_posix() for p in self.out.rglob("*") if p.is_file()) if self.out.exists() else []

    def pr_body(self):
        return (self.out / "pr-body.md").read_text(encoding="utf-8")

    def front_and_body(self, rel):
        _, front, body = (self.out / rel).read_text(encoding="utf-8").split("---\n", 2)
        return yaml.safe_load(front), body.strip()


class TermReviewedTest(Base):
    def test_writes_the_file_without_touching_r2_or_needing_credentials(self):
        client = self.client()
        self.assertEqual(self.run_draft(client), 0, self.stderr)
        self.assertEqual(self.written(), ["content/glossary/ald.md", "ledger/2026-10.jsonl", "pr-body.md"])
        self.assertEqual(self.r2.gets, [])

    def test_front_matter(self):
        self.run_draft(self.client())
        front, body = self.front_and_body("content/glossary/ald.md")
        self.assertEqual(list(front), ["term", "reading", "short_definition", "processes", "description", "basis", "published_at",
                                       "draft", "ai_generated", "sources"])
        self.assertEqual((front["term"], front["basis"], front["draft"], front["ai_generated"], front["sources"], front["published_at"]),
                         ("ALD", "reviewed", True, True, [], "2026-10-06"))
        self.assertNotIn("reviewed_on", front)
        self.assertNotIn("review_methods", front)
        self.assertNotIn("check_points", front)
        self.assertEqual(body, term_output()["body"].strip())

    def test_agent_is_called_with_the_reviewed_variant_and_no_materials_block(self):
        client = self.client()
        self.run_draft(client)
        call = client.calls[0]
        self.assertIn("運営者が確かめる方式", call["system"])
        self.assertIn("用語の下書き", call["system"])
        blocks = call["messages"][0]["content"]
        self.assertEqual(len(blocks), 1)  # 資料の区画がない
        task = json.loads(blocks[0]["text"].split("\n", 1)[1])
        self.assertEqual((task["kind"], task["name"], task["basis"]), ("term", "ALD", "reviewed"))
        self.assertNotIn("ald", [t["slug"] for t in task["selectable_terms"]])
        self.assertIn("deposition", [p["slug"] for p in task["selectable_processes"]])
        self.assertNotIn("sources", task)
        self.assertNotIn("<資料>", json.dumps(call["messages"], ensure_ascii=False))

    def test_the_output_schema_is_the_reviewed_one(self):
        _, schema = agent_call.load_agent("AG-14", variant="term-reviewed")
        self.assertIn("check_points", schema["required"])
        _, plain = agent_call.load_agent("AG-14", variant="term")
        self.assertNotIn("check_points", plain["properties"])

    def test_pr_body_has_check_points_high_first_and_the_steps(self):
        self.assertEqual(self.run_draft(self.client()), 0, self.stderr)
        pr = self.pr_body()
        rows = [l for l in pr.splitlines() if l.startswith("| ") and l.split("|")[1].strip().isdigit()]
        self.assertEqual([(r.split("|")[2].strip(), r.split("|")[3].strip()) for r in rows],
                         [("**high**", "誤りやすい点その一"), ("**high**", "言い方が分かれる点その二"), ("low", "基本の説明その一"), ("low", "基本の説明その二")])
        for needle in ("確かめに使った資料を `sources` に書く", "`review_methods`", "`reviewed_on`", "`draft: true` を外す", "basis: reviewed",
                       "原資料束は使っていない", "使わない（運営者が確かめる方式）", "転載の検査：しない", "AIは、出典を作らない" if False else "AI は、出典を作らない"):
            self.assertIn(needle, pr)
        self.assertNotIn("check_points", (self.out / "content" / "glossary" / "ald.md").read_text(encoding="utf-8"))

    def test_output_passes_schema_and_validate_data_without_errors(self):
        self.assertEqual(self.run_draft(self.client()), 0, self.stderr)
        repo = self.tmp / "repo2"
        shutil.copytree(ROOT / "data", repo / "data")
        shutil.copytree(ROOT / "config", repo / "config")
        shutil.copytree(self.out / "content", repo / "content")
        self.assertEqual([str(p) for p in vd.validate(repo, ROOT) if p.file.startswith("content/")], [])

    def test_no_reprint_check_and_summary_says_so(self):
        self.assertEqual(self.run_draft(self.client()), 0)
        self.assertIn("転載の検査: しない", self.summary)

    def test_citation_marker_fails_and_writes_no_file(self):
        for field, value in (("body", lf.cjk(150, 0x5400) + "。[S1]"), ("description", lf.cjk(70, 0x5000) + "。[S1]")):
            self.assertEqual(self.run_draft(self.client(term_output(**{field: value}))), 1)
            self.assertFalse((self.out / "content").exists())
            self.assertIn("出典の番号", self.summary)

    def test_lists_must_come_from_the_input(self):
        for kw in ({"processes": ["no-such-process"]}, {"related_terms": ["no-such-term"]}, {"related_terms": ["ald"]}):
            self.assertEqual(self.run_draft(self.client(term_output(**kw))), 1, kw)
        self.assertFalse((self.out / "content").exists())
        self.assertEqual(self.run_draft(self.client(term_output(related_terms=["hbm"], processes=["deposition"]))), 0, self.stderr)

    def test_missing_check_points_is_an_invalid_output(self):
        out = term_output()
        del out["check_points"]
        self.assertEqual(self.run_draft(self.client(out)), 1)
        self.assertFalse((self.out / "content").exists())

    def test_digits_company_names_and_length_are_warnings_not_failures(self):
        text = lf.cjk(120, 0x5400) + "。2020年に、東京エレクトロンが発表した。"
        self.assertEqual(self.run_draft(self.client(term_output(body=text))), 0, self.stderr)
        pr = self.pr_body()
        self.assertIn("半角の数字", pr)
        self.assertIn("企業名", pr)
        self.assertIn("V-12", pr)

    def test_note_goes_to_the_pr_body_only(self):
        self.assertEqual(self.run_draft(self.client(term_output(note="定義が分かれるため、一部を省いた"))), 0, self.stderr)
        self.assertNotIn("定義が分かれる", (self.out / "content" / "glossary" / "ald.md").read_text(encoding="utf-8"))
        self.assertIn("定義が分かれるため、一部を省いた", self.pr_body())

    def test_ledger_row_and_budget_are_ag14(self):
        self.run_draft(self.client())
        rows = [json.loads(l) for l in (self.out / "ledger" / "2026-10.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(r["agent"], r["subject"], r["status"]) for r in rows], [("AG-14", "term-ald", "ok")])

    def test_dry_run_does_nothing(self):
        client = self.client()
        self.assertEqual(self.run_draft(client, extra=("--dry-run",)), 0, self.stderr)
        self.assertEqual((client.calls, self.written(), self.r2.gets), ([], [], []))
        self.assertIn("basis: reviewed", self.stdout)

    def test_paused_returns_3_and_existing_file_stops(self):
        paused = self.tmp / "paused.yaml"
        paused.write_text("status: paused\n", encoding="utf-8")
        client = self.client()
        self.assertEqual(self.run_draft(client, operations=paused), 3)
        self.assertEqual(client.calls, [])
        (self.root / "content" / "glossary" / "ald.md").write_text("x", encoding="utf-8")
        self.assertEqual(self.run_draft(client), 1)

    def test_a_target_without_basis_still_reads_the_bundle(self):
        self.slug = "eda"
        self.r2 = fk.FakeR2({})
        self.assertEqual(self.run_draft(self.client(), env=fk.ENV), 1)
        self.assertEqual(len(self.r2.gets), 1)  # 設定に basis がない用語は、これまでどおり原資料束を読む

    def test_reviewed_is_decided_by_the_config_only(self):
        config = yaml.safe_load((ROOT / "config" / "explainer-sources.yaml").read_text(encoding="utf-8"))
        del config["terms"]["ald"]["basis"]
        path = self.tmp / "config.yaml"
        path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
        client = self.client()
        self.assertEqual(self.run_draft(client, config=path), 2)  # basis がなければ、公開資料の方式（sources が空で止まる）
        self.assertEqual(client.calls, [])


class ProcessReviewedTest(Base):
    kind, slug = "process", "etching"

    def test_writes_the_process_file(self):
        client = self.client()
        self.assertEqual(self.run_draft(client), 0, self.stderr)
        self.assertEqual(self.written(), ["content/processes/etching.md", "ledger/2026-10.jsonl", "pr-body.md"])
        front, body = self.front_and_body("content/processes/etching.md")
        self.assertEqual(list(front), ["process", "title", "description", "basis", "published_at", "draft", "ai_generated", "sources"])
        self.assertEqual((front["process"], front["basis"], front["draft"], front["ai_generated"], front["sources"]),
                         ("etching", "reviewed", True, True, []))
        self.assertEqual(body, process_output()["body"].strip())
        self.assertIn("工程の解説の下書き", client.calls[0]["system"])
        self.assertIn("運営者が確かめる方式", client.calls[0]["system"])
        task = json.loads(client.calls[0]["messages"][0]["content"][0]["text"].split("\n", 1)[1])
        self.assertEqual((task["kind"], task["basis"], len(task["selectable_terms"])), ("process", "reviewed", 30))
        self.assertEqual(len(client.calls[0]["messages"][0]["content"]), 1)
        self.assertEqual(self.r2.gets, [])

    def test_terms_must_come_from_the_list_and_warn_when_the_page_is_missing(self):
        self.assertEqual(self.run_draft(self.client(process_output(terms=["no-such-term"]))), 1)
        self.assertEqual(self.run_draft(self.client(process_output(terms=["plasma"]))), 0, self.stderr)
        self.assertIn("まだ原稿", self.pr_body())

    def test_pr_body_table_and_validation(self):
        self.run_draft(self.client())
        self.assertIn("**high**", self.pr_body())
        repo = self.tmp / "repo2"
        shutil.copytree(ROOT / "data", repo / "data")
        shutil.copytree(ROOT / "config", repo / "config")
        shutil.copytree(self.out / "content", repo / "content")
        self.assertEqual([str(p) for p in vd.validate(repo, ROOT) if p.file.startswith("content/")], [])


class BundleAndAgentTest(unittest.TestCase):
    def test_bundle_command_refuses_a_reviewed_target_without_network(self):
        transport = fk.FakeTransport({})
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = meb.main(["--kind", "term", "--slug", "ald", "--dry-run"], env={}, transport=transport)
        self.assertEqual(code, 2)
        self.assertEqual(transport.calls, [])
        self.assertIn("basis: reviewed", err.getvalue())

    def test_agent_call_without_materials_sends_only_the_task_block(self):
        client = lf.FakeClient(lf.reply(term_output()))
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        ops = Path(tmp) / "ops.yaml"
        ops.write_text("status: active\n", encoding="utf-8")
        result = agent_call.call_agent("AG-14", "## 入力\n{}", "", run_id="r", ledger_dir=Path(tmp), now=lambda: lf.NOW, sleep=lambda s: None,
                                       client_factory=lambda: client, operations_path=ops, variant="term-reviewed")
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(client.calls[0]["messages"][0]["content"]), 1)
        # 資料があるときは、これまでどおり、資料の区画が付く
        client2 = lf.FakeClient(lf.reply(term_output()))
        agent_call.call_agent("AG-14", "## 入力\n{}", "資料の文章", run_id="r", ledger_dir=Path(tmp), now=lambda: lf.NOW, sleep=lambda s: None,
                              client_factory=lambda: client2, operations_path=ops, variant="term-reviewed")
        self.assertEqual(len(client2.calls[0]["messages"][0]["content"]), 2)

    def test_prompts_contain_the_reviewed_rules(self):
        for variant in ("term", "process"):
            text = (ROOT / "agents" / "AG-14" / f"prompt.{variant}-reviewed.md").read_text(encoding="utf-8")
            for needle in ("資料の区画はない", "原資料束は使わない", "定義", "どこで何をするか", "数値、年、企業名、シェア、順位", "最上級",
                           "迷う内容は、書かない", "note", "出典の番号（`[S1]` など）を、本文にも、ほかの項目にも付けない", "check_points",
                           "risk", "high", "先に並べる", "である調", "CMP（化学機械研磨）"):
                self.assertIn(needle, text, f"{variant}: {needle}")
            self.assertNotIn("入力で渡した資料の段落に書かれていることだけ", text)  # 資料がある方式の指示とは違う
        for name in ("term-reviewed-01-basic.json", "process-reviewed-01-basic.json"):
            self.assertIn("expect", json.loads((ROOT / "agents" / "AG-14" / "examples" / name).read_text(encoding="utf-8")))
        for variant in ("term", "process"):
            schema = json.loads((ROOT / "agents" / "AG-14" / f"output.{variant}-reviewed.schema.json").read_text(encoding="utf-8"))
            self.assertEqual(schema["$ref"], f"../../schemas/agents/AG-14.{variant}-reviewed.output.schema.json")


if __name__ == "__main__":
    unittest.main()

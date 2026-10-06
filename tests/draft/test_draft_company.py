import contextlib
import copy
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "llm"))
sys.path.insert(0, str(ROOT / "tests" / "validate"))
sys.path.insert(0, str(ROOT / "tests" / "edinet"))

import llm_fakes as fk  # noqa: E402
import draft_company as dc  # noqa: E402
import validate_data as vd  # noqa: E402
import test_validate_data as tv  # noqa: E402

SLUG = "advantest"
MEMBER = "AlphaReportableSegmentsMember"
ENV = {"R2_ACCOUNT_ID": "0123456789abcdef0123456789abcdef", "R2_ACCESS_KEY_ID": "AKIAFAKEACCESSKEY0001",
       "R2_SECRET_ACCESS_KEY": "FAKE+secret/key=0000zzzz", "R2_BUCKET": "semicompass-bundles"}
SECRETS = tuple(ENV.values())


def kana(n):
    return "".join(chr(0x3041 + i % 80) for i in range(n))


def section(key, element, text):
    return {"key": key, "element_id": element, "label": "合成", "context_id": "FilingDateInstant", "file": "x.csv",
            "chars": len(text), "text": text}


def bundle_json(doc_id):
    return {"schema_version": 2, "bundle_id": f"{SLUG}-{doc_id}", "company": SLUG, "sections": [
        section("business_description", "test_cor:BusinessTextBlock", f"{fk.SOURCE_WORD}。" + kana(900)),
        section("affiliated_entities", "test_cor:AffiliatedTextBlock", kana(300)),
        section("segment_information", "test_cor:SegmentTextBlock", kana(600)),
        section("research_and_development", "test_cor:RdTextBlock", kana(400)),
    ]}


class FakeR2:
    def __init__(self, bundle=None, error=None):
        self.bundle, self.error, self.gets = bundle, error, []

    def get_object(self, Bucket, Key):  # noqa: N803
        self.gets.append((Bucket, Key))
        if self.error:
            raise self.error
        return {"Body": io.BytesIO(json.dumps(self.bundle, ensure_ascii=False).encode("utf-8"))}


class NoSuchKey(Exception):
    response = {"Error": {"Code": "NoSuchKey", "Message": fk.SOURCE_WORD}}


class Base(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.tmp = Path(directory.name)
        self.root = self.tmp / "repo"
        self.out = self.tmp / "out"
        self.ledger = self.tmp / "ledger"
        self.ledger.mkdir()
        (self.root / "data" / "companies").mkdir(parents=True)
        (self.root / "data" / "auto").mkdir()
        (self.root / "config").mkdir()
        for rel in ("data/supply-chain.yaml", "config/xbrl-map.yaml", f"data/companies/{SLUG}.yaml"):
            shutil.copy(ROOT / rel, self.root / rel)
        auto = tv.auto_data()
        for row in auto["financials"][-2:]:
            row["segments"] = [tv.segment_row(MEMBER, row["doc_id"])]
        (self.root / "data" / "auto" / f"{SLUG}.json").write_text(json.dumps(auto, ensure_ascii=False), encoding="utf-8")
        self.auto = auto
        self.doc_id = auto["filings"][-1]["doc_id"]
        self.operations = self.tmp / "operations.yaml"
        self.operations.write_text("status: active\n", encoding="utf-8")
        self.budgets = ROOT / "config" / "budgets.yaml"
        self.r2 = FakeR2(bundle_json(self.doc_id))

    def run_draft(self, client, *, r2=None, env=None, extra=(), slug=SLUG):
        summary = self.tmp / "summary.md"
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = dc.main(["--company", slug, "--out-dir", str(self.out), "--ledger-dir", str(self.ledger),
                            "--run-id", "run42", "--summary", str(summary), *extra],
                           env=ENV if env is None else env, now=lambda: fk.NOW, r2_factory=lambda creds: r2 or self.r2,
                           client_factory=lambda: client, sleep=lambda s: None, root=self.root,
                           budgets_path=self.budgets, operations_path=self.operations)
        self.stdout, self.stderr = out.getvalue(), err.getvalue()
        self.summary = summary.read_text(encoding="utf-8") if summary.exists() else ""
        return code

    def written(self):
        return sorted(p.relative_to(self.out).as_posix() for p in self.out.rglob("*") if p.is_file()) if self.out.exists() else []

    def all_text(self):
        parts = [self.stdout, self.stderr, self.summary]
        parts += [p.read_text(encoding="utf-8") for p in self.out.glob("pr-body.md")] if self.out.exists() else []
        return "\n".join(parts)

    def client(self, output=None, **kw):
        return fk.FakeClient(fk.reply(output or fk.valid_output(members=[MEMBER]), **kw))


class SuccessTest(Base):
    def test_writes_exactly_the_four_files(self):
        client = self.client()
        self.assertEqual(self.run_draft(client), 0, self.stderr)
        self.assertEqual(self.written(), ["content/companies/advantest.md", "data/segments/advantest.yaml",
                                          "ledger/2026-10.jsonl", "pr-body.md"])
        self.assertEqual(self.r2.gets, [("semicompass-bundles", f"bundles/{SLUG}-{self.doc_id}.json")])

    def test_output_files_match_schemas_and_validate_data(self):
        self.assertEqual(self.run_draft(self.client()), 0, self.stderr)
        repo2 = self.tmp / "repo2"
        shutil.copytree(self.root, repo2)
        shutil.copytree(self.out / "content", repo2 / "content")
        shutil.copytree(self.out / "data" / "segments", repo2 / "data" / "segments")
        problems = vd.validate(repo2)
        self.assertEqual([str(p) for p in problems], [])
        kinds = [k for k, _ in vd.collect_files(repo2)]
        self.assertIn("overview", kinds)
        self.assertIn("segment-map", kinds)

    def test_markdown_and_yaml_content(self):
        self.run_draft(self.client())
        text = (self.out / "content" / "companies" / f"{SLUG}.md").read_text(encoding="utf-8")
        front = yaml.safe_load(text.split("---\n")[1])
        self.assertEqual(list(front), ["company", "reviewed_filing", "published_at", "draft", "ai_generated", "sources"])
        self.assertEqual((front["company"], front["reviewed_filing"], front["published_at"], front["draft"],
                          front["ai_generated"]), (SLUG, self.doc_id, "2026-10-06", True, True))
        self.assertEqual(front["sources"][0]["id"], "S1")
        self.assertEqual(front["sources"][0]["doc_id"], self.doc_id)
        self.assertEqual(front["sources"][0]["accessed_on"], "2026-10-06")
        self.assertIn("\n## 事業概要\n", text)
        self.assertLess(text.index("## 事業概要"), text.index("## 工程上の位置づけ"))
        seg = yaml.safe_load((self.out / "data" / "segments" / f"{SLUG}.yaml").read_text(encoding="utf-8"))
        self.assertEqual((seg["schema_version"], seg["company"], seg["reviewed_on"], seg["based_on"]),
                         (1, SLUG, "2026-10-06", self.doc_id))
        self.assertEqual(seg["segments"][0]["rationale"], {"source": "S1", "pages": "セグメント情報"})
        self.assertEqual(seg["segments"][0]["xbrl_members"], [MEMBER])

    def test_s1_comes_from_master_sources_when_doc_id_matches(self):
        path = self.root / "data" / "companies" / f"{SLUG}.yaml"
        master = yaml.safe_load(path.read_text(encoding="utf-8"))
        master["sources"] = [{"id": "S1", "title": "マスタの題名", "publisher": "マスタの発行元",
                              "url": "https://example.com/master", "published_on": "2026-06-22",
                              "accessed_on": "2026-01-01", "doc_id": self.doc_id}]
        path.write_text(yaml.safe_dump(master, allow_unicode=True, sort_keys=False), encoding="utf-8")
        self.run_draft(self.client())
        front = yaml.safe_load((self.out / "content" / "companies" / f"{SLUG}.md").read_text(encoding="utf-8").split("---\n")[1])
        source = front["sources"][0]
        self.assertEqual((source["title"], source["publisher"], source["url"], source["published_on"], source["accessed_on"]),
                         ("マスタの題名", "マスタの発行元", "https://example.com/master", "2026-06-22", "2026-10-06"))

    def test_s1_from_filings_when_master_has_no_match(self):
        self.run_draft(self.client())
        front = yaml.safe_load((self.out / "content" / "companies" / f"{SLUG}.md").read_text(encoding="utf-8").split("---\n")[1])
        filing = next(f for f in self.auto["filings"] if f["doc_id"] == self.doc_id)
        self.assertEqual(front["sources"][0]["url"], filing["url"])
        self.assertEqual(front["sources"][0]["published_on"], filing["submitted_at"][:10])

    def test_ledger_row_is_written(self):
        self.run_draft(self.client(i=10_000, o=2_000))
        rows = [json.loads(l) for l in (self.out / "ledger" / "2026-10.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["agent"], rows[0]["run_id"], rows[0]["subject"], rows[0]["status"]), ("AG-14", "run42", SLUG, "ok"))
        self.assertAlmostEqual(rows[0]["cost_jpy"], (10_000 * 2.0 + 2_000 * 10.0) / 1e6 * 150, places=3)

    def test_input_sent_to_the_agent(self):
        client = self.client()
        self.run_draft(client)
        blocks = client.calls[0]["messages"][0]["content"]
        task = json.loads(blocks[0]["text"].split("\n", 1)[1])
        self.assertEqual(task["xbrl_members"], [MEMBER])
        self.assertEqual([s["key"] for s in task["sections"]],
                         ["business_description", "segment_information", "affiliated_entities", "research_and_development"])
        self.assertEqual(task["fiscal_period"], dc.fiscal_period_label(next(f for f in self.auto["filings"] if f["doc_id"] == self.doc_id)))
        self.assertRegex(task["fiscal_period"], r"^\d{4}年\d{1,2}月期$")
        self.assertIn("test_cor:RdTextBlock", blocks[1]["text"])
        self.assertTrue(all("name" in p for p in task["processes"]))  # 工程の名前が付く
        self.assertIn(fk.SOURCE_WORD, blocks[1]["text"])
        self.assertNotIn(fk.SOURCE_WORD, blocks[0]["text"])  # 資料は、指示の区画に入れない

    def test_summary_and_pr_body_have_no_body_text(self):
        self.assertEqual(self.run_draft(self.client()), 0)
        text = self.all_text()
        for forbidden in (fk.SOURCE_WORD, fk.OUTPUT_WORD, fk.cjk(40), kana(30), *SECRETS):
            self.assertNotIn(forbidden, text)
        pr = (self.out / "pr-body.md").read_text(encoding="utf-8")
        for expected in (self.doc_id, "test_cor:SegmentTextBlock", "business_description", "最長の一致", "利用額",
                         "有価証券報告書と見比べ", "rationale.pages", "draft: true"):
            self.assertIn(expected, pr)
        for expected in ("business_description", "下書き", self.doc_id, "転載の検査"):
            self.assertIn(expected, self.summary)

    def test_overview_length_outside_range_is_a_warning_only(self):
        self.assertEqual(self.run_draft(self.client(fk.valid_output(members=[MEMBER], overview_len=250))), 0)
        self.assertIn("V-12", (self.out / "pr-body.md").read_text(encoding="utf-8"))


def copied_output(copied, members=(MEMBER,), start=20, length=40):
    """overview に、資料と同じ箇所（length 字）を入れた出力。"""
    output = fk.valid_output(members=list(members))
    output["overview"] = fk.cjk(200) + copied[start:start + length] + fk.cjk(100, 0x5200) + "[S1]"
    return output


class RewriteTest(Base):
    def setUp(self):
        super().setUp()
        self.copied = bundle_json(self.doc_id)["sections"][0]["text"]
        self.same = self.copied[20:60]  # 資料と同じになる箇所（ひらがな）

    def ledger_rows(self):
        return [json.loads(l) for l in (self.out / "ledger" / "2026-10.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_rewrite_passes_and_reports_both_lengths(self):
        client = fk.FakeClient(fk.reply(copied_output(self.copied)), fk.reply(fk.valid_output(members=[MEMBER])))
        self.assertEqual(self.run_draft(client), 0, self.stderr)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(self.written(), ["content/companies/advantest.md", "data/segments/advantest.yaml",
                                          "ledger/2026-10.jsonl", "pr-body.md"])
        pr = (self.out / "pr-body.md").read_text(encoding="utf-8")
        self.assertRegex(pr, r"1回目 40字 → 書き直し後 \d+字")
        self.assertRegex(self.summary, r"1回目 40字 → 書き直し後 \d+字")
        self.assertIn("overview", self.summary)

    def test_rewrite_request_carries_the_matched_text_only_to_the_ai(self):
        client = fk.FakeClient(fk.reply(copied_output(self.copied)), fk.reply(fk.valid_output(members=[MEMBER])))
        self.run_draft(client)
        followup = client.calls[1]["messages"][0]["content"][2]["text"]
        self.assertIn(self.same, followup)  # AIへの入力には入る
        self.assertIn("overview", followup)
        self.assertIn("事実は変えずに、自分の言葉で言い換える", followup)
        self.assertIn("固有名詞（製品名、社名）はそのままでよい", followup)
        self.assertIn("前回の出力", followup)
        self.assertNotIn(self.same, client.calls[0]["messages"][0]["content"][0]["text"])
        for piece in (self.same, self.same[:25], self.same[-25:]):  # ログ、要約、変更案の説明、ledger、画面に出ない
            self.assertNotIn(piece, self.all_text())
            self.assertNotIn(piece, "\n".join(p.read_text(encoding="utf-8") for p in self.out.rglob("*") if p.is_file()))

    def test_ledger_has_two_rows(self):
        client = \
            fk.FakeClient(fk.reply(copied_output(self.copied), i=1000, o=100), fk.reply(fk.valid_output(members=[MEMBER]), i=2000, o=200))
        self.run_draft(client)
        rows = self.ledger_rows()
        self.assertEqual([r["status"] for r in rows], ["ok", "ok"])
        self.assertEqual([r["input_tokens"] for r in rows], [1000, 2000])
        self.assertIn("利用額", self.stdout)
        self.assertAlmostEqual(float(self.stdout.split("利用額 ")[1].split("円")[0]), sum(r["cost_jpy"] for r in rows), places=2)

    def test_still_failing_after_rewrite_stops_without_files(self):
        client = fk.FakeClient(fk.reply(copied_output(self.copied)), fk.reply(copied_output(self.copied, start=100)))
        self.assertEqual(self.run_draft(client), 1)
        self.assertEqual(len(client.calls), 2)  # 書き直しは1回だけ
        self.assertEqual(self.written(), ["ledger/2026-10.jsonl"])
        self.assertEqual(len(self.ledger_rows()), 2)
        self.assertIn("1回目 40字 → 書き直し後 40字", self.summary)
        self.assertIn("転載の検査に不合格", self.stderr)
        for piece in (self.same, self.copied[100:130]):
            self.assertNotIn(piece, self.all_text())

    def test_citation_failure_is_not_rewritten(self):
        output = fk.valid_output(members=[MEMBER])
        output["overview"] = output["overview"][:-4] + "[S2]"
        client = fk.FakeClient(fk.reply(output), fk.reply(fk.valid_output(members=[MEMBER])))
        self.assertEqual(self.run_draft(client), 1)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(len(self.ledger_rows()), 1)

    def test_member_failure_is_not_rewritten(self):
        client = fk.FakeClient(fk.reply(fk.valid_output(members=["NotGivenMember"])), fk.reply(fk.valid_output(members=[MEMBER])))
        self.assertEqual(self.run_draft(client), 1)
        self.assertEqual(len(client.calls), 1)

    def test_reprint_together_with_another_failure_is_not_rewritten(self):
        output = copied_output(self.copied, members=("NotGivenMember",))
        client = fk.FakeClient(fk.reply(output), fk.reply(fk.valid_output(members=[MEMBER])))
        self.assertEqual(self.run_draft(client), 1)
        self.assertEqual(len(client.calls), 1)

    def test_no_rewrite_when_the_first_output_passes_and_the_summary_keeps_the_old_form(self):
        client = self.client()
        self.assertEqual(self.run_draft(client), 0)
        self.assertEqual(len(client.calls), 1)
        self.assertNotIn("書き直し後", self.summary)
        self.assertNotIn("書き直し後", (self.out / "pr-body.md").read_text(encoding="utf-8"))
        self.assertIn("最長の一致", self.summary)

    def test_rewrite_skipped_for_budget_exits_3_and_keeps_both_ledger_rows(self):
        budgets = yaml.safe_load((ROOT / "config" / "budgets.yaml").read_text(encoding="utf-8"))
        budgets["agents"]["AG-14"]["cap_jpy"] = 12
        self.budgets = self.tmp / "budgets.yaml"
        self.budgets.write_text(yaml.safe_dump(budgets), encoding="utf-8")
        client = fk.FakeClient(fk.reply(copied_output(self.copied), i=1_000_000, o=100_000))  # 1回目で、上限を超える利用額
        self.assertEqual(self.run_draft(client), 3)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual([r["status"] for r in self.ledger_rows()], ["ok", "skipped_budget"])
        self.assertEqual(self.written(), ["ledger/2026-10.jsonl"])

    def test_first_call_and_rewrite_share_one_client(self):
        made = []
        client = fk.FakeClient(fk.reply(copied_output(self.copied)), fk.reply(fk.valid_output(members=[MEMBER])))

        def factory():
            made.append(1)
            return client
        self.assertEqual(self.run_with_factory(factory), 0)
        self.assertEqual(len(client.calls), 2)  # 最初と書き直し
        self.assertEqual(len(made), 1)  # クライアントは、1回しか作らない

    def test_client_is_created_lazily_and_not_at_all_when_paused(self):
        self.operations.write_text("status: paused\n", encoding="utf-8")
        made = []
        self.assertEqual(self.run_with_factory(lambda: made.append(1)), 3)
        self.assertEqual(made, [])

    def test_failed_creation_is_not_cached(self):
        calls = []

        def factory():
            calls.append(1)
            if len(calls) == 1:
                raise fk.agent_call.anthropic.WorkloadIdentityError("x")
            return fk.FakeClient(fk.reply(fk.valid_output(members=[MEMBER])))
        factory_get = dc.shared_client_factory(factory)
        with self.assertRaises(fk.agent_call.anthropic.WorkloadIdentityError):
            factory_get()
        self.assertIsNotNone(factory_get())
        self.assertIs(factory_get(), factory_get())
        self.assertEqual(len(calls), 2)

    def run_with_factory(self, factory):
        summary = self.tmp / "summary.md"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return dc.main(["--company", SLUG, "--out-dir", str(self.out), "--ledger-dir", str(self.ledger),
                            "--run-id", "run42", "--summary", str(summary)],
                           env=ENV, now=lambda: fk.NOW, r2_factory=lambda creds: self.r2, client_factory=factory,
                           sleep=lambda s: None, root=self.root, budgets_path=self.budgets, operations_path=self.operations)

    def test_rewrite_returning_invalid_output_exits_1(self):
        client = fk.FakeClient(fk.reply(copied_output(self.copied)), fk.reply("JSONではない"))
        self.assertEqual(self.run_draft(client), 1)
        self.assertEqual(self.written(), ["ledger/2026-10.jsonl"])
        self.assertEqual([r["status"] for r in self.ledger_rows()], ["ok", "invalid_output", "invalid_output"])

    def test_rewritten_files_pass_validate_data(self):
        client = fk.FakeClient(fk.reply(copied_output(self.copied)), fk.reply(fk.valid_output(members=[MEMBER])))
        self.assertEqual(self.run_draft(client), 0)
        repo2 = self.tmp / "repo2"
        shutil.copytree(self.root, repo2)
        shutil.copytree(self.out / "content", repo2 / "content")
        shutil.copytree(self.out / "data" / "segments", repo2 / "data" / "segments")
        self.assertEqual([str(p) for p in vd.validate(repo2)], [])


class SkipTest(Base):
    def test_paused_exits_3_and_writes_only_the_ledger(self):
        self.operations.write_text("status: paused\n", encoding="utf-8")
        client = self.client()
        self.assertEqual(self.run_draft(client), 3)
        self.assertEqual(client.calls, [])
        self.assertEqual(self.written(), ["ledger/2026-10.jsonl"])
        self.assertIn("skipped_paused", (self.out / "ledger" / "2026-10.jsonl").read_text(encoding="utf-8"))
        self.assertIn("paused", self.summary)

    def test_agent_budget_exits_3(self):
        (self.ledger / "2026-10.jsonl").write_text(json.dumps({"agent": "AG-14", "cost_jpy": 1499.99}) + "\n", encoding="utf-8")
        client = self.client()
        self.assertEqual(self.run_draft(client), 3)
        self.assertEqual(client.calls, [])
        self.assertIn("skipped_budget", (self.out / "ledger" / "2026-10.jsonl").read_text(encoding="utf-8"))

    def test_monthly_budget_exits_3(self):
        (self.ledger / "2026-10.jsonl").write_text(json.dumps({"agent": "AG-10", "cost_jpy": 9999.99}) + "\n", encoding="utf-8")
        self.assertEqual(self.run_draft(self.client()), 3)


class FailureTest(Base):
    def assert_no_content_files(self):
        self.assertNotIn("content/companies/advantest.md", self.written())
        self.assertNotIn("data/segments/advantest.yaml", self.written())
        self.assertNotIn("pr-body.md", self.written())

    def test_invalid_output_after_retry_exits_1_but_keeps_ledger(self):
        client = fk.FakeClient(fk.reply("JSONではない"))
        self.assertEqual(self.run_draft(client), 1)
        self.assert_no_content_files()
        rows = (self.out / "ledger" / "2026-10.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(r)["status"] for r in rows], ["invalid_output", "invalid_output"])

    def test_reprint_failure_writes_no_content(self):
        output = fk.valid_output(members=[MEMBER])
        copied = bundle_json(self.doc_id)["sections"][0]["text"]
        output["overview"] = fk.cjk(200) + copied[20:60] + fk.cjk(100, 0x5200) + "[S1]"  # 資料と40字、同じ
        self.assertEqual(self.run_draft(self.client(output)), 1)
        self.assert_no_content_files()
        self.assertIn("転載", self.stderr)
        self.assertIn("overview", self.stderr)
        self.assertIn("ledger/2026-10.jsonl", self.written())
        self.assertNotIn(copied[20:30], self.all_text())

    def test_citation_other_than_s1_fails(self):
        output = fk.valid_output(members=[MEMBER])
        output["overview"] = output["overview"][:-4] + "[S2]"
        self.assertEqual(self.run_draft(self.client(output)), 1)
        self.assert_no_content_files()
        self.assertIn("[S1] 以外", self.stderr)

    def test_xbrl_member_outside_the_given_list_fails(self):
        self.assertEqual(self.run_draft(self.client(fk.valid_output(members=["NotGivenMember"]))), 1)
        self.assert_no_content_files()
        self.assertIn("渡した一覧にない", self.stderr)

    def test_markdown_heading_in_output_fails_validation_without_echoing_it(self):
        output = fk.valid_output(members=[MEMBER])
        output["overview"] = "# " + fk.OUTPUT_WORD + "\n\n" + output["overview"]
        self.assertEqual(self.run_draft(self.client(output)), 1)
        self.assert_no_content_files()
        self.assertIn("V-10", self.stderr)
        self.assertNotIn(fk.OUTPUT_WORD, self.all_text())

    def test_existing_files_stop_before_any_call_or_read(self):
        for rel in ("content/companies", "data/segments"):
            (self.root / rel).mkdir(parents=True, exist_ok=True)
            (self.root / rel / (SLUG + (".md" if rel.startswith("content") else ".yaml"))).write_text("x", encoding="utf-8")
            client = self.client()
            self.assertEqual(self.run_draft(client), 1)
            self.assertEqual(client.calls, [])
            self.assertEqual(self.r2.gets, [])
            self.assertEqual(self.written(), [])
            self.assertIn("もうある", self.stderr)
            shutil.rmtree(self.root / rel)

    def test_missing_bundle_says_to_run_edinet_bundle(self):
        client = self.client()
        self.assertEqual(self.run_draft(client, r2=FakeR2(error=NoSuchKey())), 1)
        self.assertIn("edinet-bundle", self.stderr)
        self.assertEqual(client.calls, [])
        self.assertEqual(self.written(), [])

    def test_bundle_missing_a_section_stops(self):
        bundle = bundle_json(self.doc_id)
        bundle["sections"] = [s for s in bundle["sections"] if s["key"] != "affiliated_entities"]
        self.assertEqual(self.run_draft(self.client(), r2=FakeR2(bundle)), 1)
        self.assertIn("affiliated_entities", self.stderr)

    def test_bundle_without_research_and_development_stops_with_a_hint(self):
        bundle = bundle_json(self.doc_id)
        bundle["sections"] = [s for s in bundle["sections"] if s["key"] != "research_and_development"]
        client = self.client()
        self.assertEqual(self.run_draft(client, r2=FakeR2(bundle)), 1)
        self.assertIn("research_and_development", self.stderr)
        self.assertIn("edinet-bundle を動かし直す", self.stderr)
        self.assertEqual(client.calls, [])
        self.assertEqual(self.written(), [])

    def test_identity_failure_exits_1_and_keeps_a_ledger_row_without_the_message(self):
        error = fk.agent_call.anthropic.WorkloadIdentityError(f"exchange failed {fk.SOURCE_WORD} " + " ".join(SECRETS))
        self.assertEqual(self.run_draft(fk.FakeClient(error)), 1)
        self.assertIn("ID連携の認証に失敗した", self.stderr)
        self.assertNotIn("想定外", self.stderr)
        self.assertEqual(self.written(), ["ledger/2026-10.jsonl"])
        row = json.loads((self.out / "ledger" / "2026-10.jsonl").read_text(encoding="utf-8"))
        self.assertEqual((row["status"], row["agent"], row["cost_jpy"]), ("failed", "AG-14", 0))
        for forbidden in (fk.SOURCE_WORD, *SECRETS):
            self.assertNotIn(forbidden, self.all_text())

    def test_old_bundle_schema_version_stops(self):
        bundle = bundle_json(self.doc_id)
        bundle["schema_version"] = 1
        self.assertEqual(self.run_draft(self.client(), r2=FakeR2(bundle)), 1)

    def test_r2_error_hides_credentials(self):
        error = RuntimeError(" ".join(SECRETS) + fk.SOURCE_WORD)
        self.assertEqual(self.run_draft(self.client(), r2=FakeR2(error=error)), 1)
        for forbidden in (*SECRETS, fk.SOURCE_WORD):
            self.assertNotIn(forbidden, self.all_text())
        self.assertIn("RuntimeError", self.stderr)

    def test_unexpected_error_prints_only_the_type(self):
        from unittest import mock
        with mock.patch.object(dc.agent_call, "call_agent", side_effect=KeyError(fk.SOURCE_WORD)):
            self.assertEqual(self.run_draft(self.client()), 1)
        self.assertIn("KeyError", self.stderr)
        self.assertNotIn(fk.SOURCE_WORD, self.all_text())

    def test_usage_errors_exit_2(self):
        self.assertEqual(self.run_draft(self.client(), slug="Bad_Slug"), 2)
        self.assertEqual(self.run_draft(self.client(), env={"R2_ACCOUNT_ID": ENV["R2_ACCOUNT_ID"]}), 2)
        self.assertEqual(self.written(), [])

    def test_no_annual_report_in_auto_stops(self):
        path = self.root / "data" / "auto" / f"{SLUG}.json"
        auto = json.loads(path.read_text(encoding="utf-8"))
        for f in auto["filings"]:
            f["status"] = "failed"
        path.write_text(json.dumps(auto), encoding="utf-8")
        self.assertEqual(self.run_draft(self.client()), 1)


class SelectionTest(unittest.TestCase):
    def test_uses_the_same_selection_as_make_bundle(self):
        self.assertIs(dc.make_bundle.latest_annual_report, __import__("make_bundle").latest_annual_report)


if __name__ == "__main__":
    unittest.main()

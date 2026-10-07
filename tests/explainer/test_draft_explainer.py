import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

import explainer_fakes as fk
import llm_fakes as lf
import draft_explainer as de
import validate_data as vd

ROOT = fk.ROOT
SLUG = "test-term"
ENV = fk.ENV
OUTPUT_WORD = lf.OUTPUT_WORD
SOURCE_WORD = lf.SOURCE_WORD


def kana(n, start=0x3041):
    return "".join(chr(start + i % 80) for i in range(n))


def paragraphs(*texts, page=1):
    return [{"text": t, "page": page} for t in texts]


def source_row(sid, role="primary", texts=None, failure=None, fmt="html", pages=None, url=None):
    texts = texts if texts is not None else [f"{SOURCE_WORD}。" + kana(300)]
    rows = [] if failure else [{"text": t, "page": (pages[i] if pages else 1)} for i, t in enumerate(texts)]
    return {"id": sid, "url": url or f"https://a.example.org/{sid}.html", "publisher": f"発行元{sid}", "title": f"資料{sid}",
            "role": role, "kind": "web", "fetched_at": "2026-10-07T09:00:00+09:00", "content_sha256": None if failure else "ab" * 32,
            "format": None if failure else fmt, "paragraphs": rows, "not_found": False, "failure": failure}


def bundle_json(kind="term", slug=SLUG, name="架空研磨", sources=None):
    return {"schema_version": 1, "kind": kind, "slug": slug, "name": name, "target_words": [name], "fetched_on": "2026-10-07",
            "sources": sources if sources is not None else [source_row("S1"), source_row("S2", "supplementary")]}


def term_output(**kw):
    out = {"reading": "カソウケンマ", "short_definition": lf.cjk(30, 0x4E00) + "。", "description": lf.cjk(70, 0x5000) + "。",
           "body": lf.cjk(150, 0x5400) + "。[S1]\n\n" + lf.cjk(100, 0x5800) + f"。{OUTPUT_WORD}[S2]",
           "processes": ["cmp"], "related_terms": []}
    out.update(kw)
    return out


def process_output(**kw):
    out = {"title": "架空工程の解説", "description": lf.cjk(70, 0x5000) + "。",
           "body": "## この工程とは\n\n" + lf.cjk(200, 0x5400) + "。[S1]\n\n## 仕組み\n\n" + lf.cjk(150, 0x5800) + f"。{OUTPUT_WORD}[S2]",
           "terms": []}
    out.update(kw)
    return out


class Base(unittest.TestCase):
    kind = "term"
    slug = SLUG

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.tmp = Path(directory.name)
        self.root = self.tmp / "repo"
        self.out = self.tmp / "out"
        self.ledger = self.tmp / "ledger"
        self.ledger.mkdir()
        (self.root / "content" / "glossary").mkdir(parents=True)
        (self.root / "content" / "processes").mkdir(parents=True)
        self.config = fk.make_config(self.tmp / "config.yaml", [fk.source("https://a.example.org/S1.html"),
                                                                fk.source("https://a.example.org/S2.html", role="supplementary")])
        self.operations = self.tmp / "operations.yaml"
        self.operations.write_text("status: active\n", encoding="utf-8")
        self.r2 = fk.FakeR2({f"bundles/explainer/{self.kind}-{self.slug}.json": self.encode(bundle_json(self.kind, self.slug))})

    @staticmethod
    def encode(bundle):
        return json.dumps(bundle, ensure_ascii=False).encode("utf-8")

    def set_bundle(self, bundle):
        self.r2.objects[f"bundles/explainer/{self.kind}-{self.slug}.json"] = self.encode(bundle)

    def run_draft(self, client, *, env=None, extra=(), r2=None, operations=None):
        summary = self.tmp / "summary.md"
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = de.main(["--kind", self.kind, "--slug", self.slug, "--out-dir", str(self.out), "--ledger-dir", str(self.ledger),
                            "--run-id", "run42", "--summary", str(summary), *extra],
                           env=ENV if env is None else env, now=lambda: lf.NOW, r2_factory=lambda creds: r2 or self.r2,
                           client_factory=lambda: client, sleep=lambda s: None, root=self.root,
                           budgets_path=ROOT / "config" / "budgets.yaml", operations_path=operations or self.operations,
                           config_path=self.config)
        self.stdout, self.stderr = out.getvalue(), err.getvalue()
        self.summary = summary.read_text(encoding="utf-8") if summary.exists() else ""
        return code

    def client(self, output=None):
        return lf.FakeClient(lf.reply(output or (term_output() if self.kind == "term" else process_output())))

    def written(self):
        return sorted(p.relative_to(self.out).as_posix() for p in self.out.rglob("*") if p.is_file()) if self.out.exists() else []

    def all_text(self):
        pr = self.out / "pr-body.md"
        return "\n".join([self.stdout, self.stderr, self.summary, pr.read_text(encoding="utf-8") if pr.exists() else ""])

    def front_and_body(self, rel):
        text = (self.out / rel).read_text(encoding="utf-8")
        _, front, body = text.split("---\n", 2)
        return yaml.safe_load(front), body.strip()


class TermTest(Base):
    def test_writes_exactly_the_file_ledger_and_pr_body(self):
        client = self.client()
        self.assertEqual(self.run_draft(client), 0, self.stderr)
        self.assertEqual(self.written(), ["content/glossary/test-term.md", "ledger/2026-10.jsonl", "pr-body.md"])
        self.assertEqual(self.r2.gets, [("semicompass-bundles", "bundles/explainer/term-test-term.json")])

    def test_front_matter_and_body(self):
        self.run_draft(self.client())
        front, body = self.front_and_body("content/glossary/test-term.md")
        self.assertEqual(list(front), ["term", "reading", "short_definition", "processes", "description", "published_at", "draft",
                                       "ai_generated", "sources"])
        self.assertEqual((front["term"], front["reading"], front["published_at"], front["draft"], front["ai_generated"]),
                         ("架空研磨", "カソウケンマ", "2026-10-06", True, True))
        self.assertEqual([s["id"] for s in front["sources"]], ["S1", "S2"])
        self.assertEqual(front["sources"][0], {"id": "S1", "title": "資料S1", "publisher": "発行元S1", "url": "https://a.example.org/S1.html",
                                               "accessed_on": "2026-10-07"})
        self.assertEqual(body, term_output()["body"].strip())

    def test_output_passes_schema_and_validate_data(self):
        self.assertEqual(self.run_draft(self.client()), 0, self.stderr)
        repo = self.tmp / "repo2"
        shutil.copytree(ROOT / "data", repo / "data")
        shutil.copytree(ROOT / "config", repo / "config")
        shutil.copy(self.config, repo / "config" / "explainer-sources.yaml")
        shutil.copytree(self.out / "content", repo / "content")
        problems = vd.validate(repo)
        self.assertEqual([str(p) for p in problems if p.file.startswith("content/")], [])
        self.assertIn("term", [k for k, _ in vd.collect_files(repo)])

    def test_only_cited_sources_are_in_the_file(self):
        self.run_draft(self.client(term_output(body=lf.cjk(150, 0x5400) + "。[S1]")))
        front, _ = self.front_and_body("content/glossary/test-term.md")
        self.assertEqual([s["id"] for s in front["sources"]], ["S1"])
        pr = (self.out / "pr-body.md").read_text(encoding="utf-8")
        self.assertIn("| S2 | supplementary |", pr)
        self.assertIn("引用なし", pr)

    def test_pdf_source_gets_pages_and_failed_source_keeps_its_number(self):
        sources = [source_row("S1", "primary", fmt="pdf", texts=["a" + kana(50), "b" + kana(50), "c" + kana(50), "d" + kana(50)],
                              pages=[3, 4, 5, 9], url="https://a.example.org/doc.pdf"),
                   source_row("S2", "primary", failure="HTTP 404"), source_row("S3", "supplementary")]
        self.set_bundle(bundle_json(sources=sources))
        client = self.client(term_output(body=lf.cjk(150, 0x5400) + "。[S1]\n\n" + lf.cjk(100, 0x5800) + "。[S3]"))
        self.assertEqual(self.run_draft(client), 0, self.stderr)
        front, _ = self.front_and_body("content/glossary/test-term.md")
        self.assertEqual([(s["id"], s.get("pages")) for s in front["sources"]], [("S1", "3-5, 9"), ("S3", None)])
        blocks = client.calls[0]["messages"][0]["content"]
        task = json.loads(blocks[0]["text"].split("\n", 1)[1])
        self.assertEqual([s["id"] for s in task["sources"]], ["S1", "S3"])  # 失敗した資料は、AIに渡さない
        self.assertIn('page="4"', blocks[1]["text"])
        self.assertNotIn('role="primary" page', blocks[1]["text"].split("S3")[0].split("S1")[0])

    def test_citing_a_failed_source_fails_and_writes_no_file(self):
        self.set_bundle(bundle_json(sources=[source_row("S1"), source_row("S2", failure="HTTP 404")]))
        self.assertEqual(self.run_draft(self.client()), 1)
        self.assertEqual(self.written(), ["ledger/2026-10.jsonl"])
        self.assertIn("渡していない出典の番号", self.summary)

    def test_input_sent_to_the_agent(self):
        client = self.client()
        self.run_draft(client)
        call = client.calls[0]
        self.assertIn("用語の下書き", call["system"])  # 用語向けの指示文
        self.assertIn("schema", json.dumps(call["output_config"]) if "output_config" in call else "schema")
        blocks = call["messages"][0]["content"]
        task = json.loads(blocks[0]["text"].split("\n", 1)[1])
        self.assertEqual((task["kind"], task["name"], task["fetched_on"]), ("term", "架空研磨", "2026-10-07"))
        self.assertEqual([(s["id"], s["role"]) for s in task["sources"]], [("S1", "primary"), ("S2", "supplementary")])
        self.assertEqual([p["slug"] for p in task["selectable_processes"]][:3], ["circuit-design", "wafer", "cleaning"])
        self.assertIn({"slug": "cmp", "name": "CMP（平坦化）"}, task["selectable_processes"])  # mvp: true の工程
        self.assertNotIn(SLUG, [t["slug"] for t in task["selectable_terms"]])  # 自分自身は選べない
        self.assertIn("silicon-wafer", [t["slug"] for t in task["selectable_terms"]])
        self.assertIn(SOURCE_WORD, blocks[1]["text"])
        self.assertNotIn(SOURCE_WORD, blocks[0]["text"])

    def test_processes_and_related_terms_must_come_from_the_lists(self):
        self.assertEqual(self.run_draft(self.client(term_output(processes=["no-such-process"]))), 1)
        self.assertEqual(self.run_draft(self.client(term_output(related_terms=["no-such-term"]))), 1)
        self.assertEqual(self.run_draft(self.client(term_output(related_terms=[SLUG]))), 1)
        self.assertFalse((self.out / "content").exists())
        self.assertEqual(self.run_draft(self.client(term_output(related_terms=["silicon-wafer"], processes=["wafer"]))), 0, self.stderr)
        front, _ = self.front_and_body("content/glossary/test-term.md")
        self.assertEqual((front["related_terms"], front["processes"]), (["silicon-wafer"], ["wafer"]))

    def test_unknown_citation_and_no_citation_fail(self):
        for body in (lf.cjk(150, 0x5400) + "。[S9]", lf.cjk(150, 0x5400) + "。"):
            self.assertEqual(self.run_draft(self.client(term_output(body=body))), 1)
            self.assertFalse((self.out / "content").exists())

    def test_citation_in_description_fails(self):
        self.assertEqual(self.run_draft(self.client(term_output(description=lf.cjk(70, 0x5000) + "。[S1]"))), 1)

    def test_duplicate_alias_in_existing_glossary_is_v16(self):
        other = {"term": "別の用語", "reading": "ベツ", "aliases": ["架空研磨"], "short_definition": "短い。", "processes": [],
                 "description": "説明", "published_at": "2026-01-01", "ai_generated": True,
                 "sources": [{"id": "S1", "title": "t", "publisher": "p", "url": "https://x.example/", "accessed_on": "2026-01-01"}]}
        (self.root / "content" / "glossary" / "other.md").write_text("---\n" + yaml.safe_dump(other, allow_unicode=True) + "---\n\n本文[S1]\n", encoding="utf-8")
        self.assertEqual(self.run_draft(self.client()), 1)
        self.assertIn("V-16", self.summary)

    def test_warnings_for_length_are_not_failures(self):
        short = term_output(body=lf.cjk(110, 0x5400) + "。[S1]")
        self.assertEqual(self.run_draft(self.client(short)), 0, self.stderr)
        self.assertIn("V-12", (self.out / "pr-body.md").read_text(encoding="utf-8"))

    def test_supplementary_only_citation_warns(self):
        self.assertEqual(self.run_draft(self.client(term_output(body=lf.cjk(250, 0x5400) + "。[S2]"))), 0, self.stderr)
        self.assertIn("補助（supplementary）の出典だけ", (self.out / "pr-body.md").read_text(encoding="utf-8"))

    def test_note_goes_to_the_pr_body_only(self):
        self.assertEqual(self.run_draft(self.client(term_output(note="出典が1件だけである"))), 0, self.stderr)
        self.assertNotIn("出典が1件だけ", (self.out / "content" / "glossary" / "test-term.md").read_text(encoding="utf-8"))
        self.assertIn("出典が1件だけである", (self.out / "pr-body.md").read_text(encoding="utf-8"))

    def test_note_is_checked_for_reprint(self):
        run = "ひらがなだけの長い文章がここにあるのです。" * 3
        self.set_bundle(bundle_json(sources=[source_row("S1", texts=[run]), source_row("S2", "supplementary")]))
        client = lf.FakeClient(lf.reply(term_output(note=run[:40])), lf.reply(term_output(note="資料は1件")))
        self.assertEqual(self.run_draft(client), 0, self.stderr)
        self.assertEqual(len(client.calls), 2)

    def test_summary_pr_body_and_logs_have_no_source_or_credentials(self):
        self.assertEqual(self.run_draft(self.client()), 0)
        text = self.all_text()
        for forbidden in (SOURCE_WORD, OUTPUT_WORD, lf.cjk(40, 0x5400), kana(30), *fk.SECRETS[:3]):
            self.assertNotIn(forbidden, text)
        pr = (self.out / "pr-body.md").read_text(encoding="utf-8")
        for expected in ("bundles/explainer/term-test-term.json", "2026-10-07", "https://a.example.org/S1.html", "最長の一致", "利用額",
                         "draft: true", "本文での引用"):
            self.assertIn(expected, pr)

    def test_ledger_row(self):
        self.run_draft(self.client())
        rows = [json.loads(l) for l in (self.out / "ledger" / "2026-10.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual((len(rows), rows[0]["agent"], rows[0]["subject"], rows[0]["status"], rows[0]["run_id"]),
                         (1, "AG-14", "term-test-term", "ok", "run42"))


class RewriteTest(Base):
    def reprinting(self):
        run = "ひらがなだけの長い文章がここにあるのです。" * 3
        self.set_bundle(bundle_json(sources=[source_row("S1", texts=[run]), source_row("S2", "supplementary")]))
        return run

    def test_rewrites_once_and_passes(self):
        run = self.reprinting()
        bad = term_output(body=lf.cjk(100, 0x5400) + run + "[S1]")
        client = lf.FakeClient(lf.reply(bad), lf.reply(term_output()))
        self.assertEqual(self.run_draft(client), 0, self.stderr)
        self.assertEqual(len(client.calls), 2)
        followup = client.calls[1]["messages"][0]["content"][-1]["text"]
        self.assertIn("書き直しの依頼", followup)
        self.assertIn("[S1], [S2]", followup)
        rows = [json.loads(l) for l in (self.out / "ledger" / "2026-10.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertIn("書き直し後", (self.out / "pr-body.md").read_text(encoding="utf-8"))
        self.assertNotIn(run[:20], self.all_text())  # 資料の文章は、変更案にも要約にも出ない

    def test_second_failure_writes_nothing(self):
        run = self.reprinting()
        bad = term_output(body=lf.cjk(100, 0x5400) + run + "[S1]")
        client = lf.FakeClient(lf.reply(bad))
        self.assertEqual(self.run_draft(client), 1)
        self.assertEqual(len(client.calls), 2)  # 書き直しは、1回だけ
        self.assertEqual(self.written(), ["ledger/2026-10.jsonl"])
        self.assertNotIn(run[:20], self.all_text())


class ProcessTest(Base):
    kind = "process"
    slug = "cmp"

    def test_writes_the_process_file(self):
        self.config = ROOT / "config" / "explainer-sources.yaml"
        client = self.client()
        self.assertEqual(self.run_draft(client), 0, self.stderr)
        self.assertEqual(self.written(), ["content/processes/cmp.md", "ledger/2026-10.jsonl", "pr-body.md"])
        front, body = self.front_and_body("content/processes/cmp.md")
        self.assertEqual(list(front), ["process", "title", "description", "published_at", "draft", "ai_generated", "sources"])
        self.assertEqual((front["process"], front["title"], front["draft"], front["ai_generated"]), ("cmp", "架空工程の解説", True, True))
        self.assertTrue(body.startswith("## この工程とは"))
        self.assertIn("工程の解説の下書き", client.calls[0]["system"])
        task = json.loads(client.calls[0]["messages"][0]["content"][0]["text"].split("\n", 1)[1])
        self.assertEqual(task["kind"], "process")
        self.assertNotIn("selectable_processes", task)
        self.assertEqual(len(task["selectable_terms"]), 30)

    def test_terms_and_validation(self):
        self.config = ROOT / "config" / "explainer-sources.yaml"
        self.assertEqual(self.run_draft(self.client(process_output(terms=["no-such-term"]))), 1)
        self.assertEqual(self.run_draft(self.client(process_output(terms=["plasma"]))), 0, self.stderr)
        front, _ = self.front_and_body("content/processes/cmp.md")
        self.assertEqual(front["terms"], ["plasma"])
        self.assertIn("まだ原稿", (self.out / "pr-body.md").read_text(encoding="utf-8"))  # 用語の原稿がまだない（警告）

    def test_heading_level_skip_fails(self):
        self.config = ROOT / "config" / "explainer-sources.yaml"
        bad = process_output(body="## 見出し\n\n" + lf.cjk(150, 0x5400) + "。[S1]\n\n#### 飛んだ見出し\n\n" + lf.cjk(200, 0x5800) + "。[S1]")
        self.assertEqual(self.run_draft(self.client(bad)), 1)
        self.assertIn("V-10", self.summary)


class FailureTest(Base):
    def test_missing_bundle_tells_which_command_to_run(self):
        self.r2 = fk.FakeR2({})
        self.assertEqual(self.run_draft(self.client()), 1)
        self.assertIn("make_explainer_bundle.py", self.stderr)
        self.assertEqual(self.written(), [])

    def test_no_usable_primary_source(self):
        self.set_bundle(bundle_json(sources=[source_row("S1", failure="HTTP 404"), source_row("S2", "supplementary")]))
        client = self.client()
        self.assertEqual(self.run_draft(client), 1)
        self.assertEqual(client.calls, [])
        self.assertIn("primary", self.stderr)

    def test_existing_file_is_not_overwritten(self):
        (self.root / "content" / "glossary" / "test-term.md").write_text("x", encoding="utf-8")
        client = self.client()
        self.assertEqual(self.run_draft(client), 1)
        self.assertEqual(client.calls, [])

    def test_malformed_bundle(self):
        self.set_bundle({"schema_version": 2, "kind": "term", "slug": SLUG, "sources": []})
        self.assertEqual(self.run_draft(self.client()), 1)
        self.set_bundle(bundle_json(slug="other-slug"))
        self.assertEqual(self.run_draft(self.client()), 1)

    def test_usage_errors(self):
        self.assertEqual(self.run_draft(self.client(), env={}), 2)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            de.main(["--kind", "company", "--slug", "x", "--out-dir", "o", "--ledger-dir", "l", "--run-id", "r"])

    def test_dry_run_calls_nothing_and_writes_nothing(self):
        client = self.client()
        self.assertEqual(self.run_draft(client, extra=("--dry-run",)), 0, self.stderr)
        self.assertEqual(client.calls, [])
        self.assertEqual(self.written(), [])
        self.assertIn("dry-run", self.stdout)
        self.assertNotIn(SOURCE_WORD, self.all_text())

    def test_paused_returns_3(self):
        paused = self.tmp / "paused.yaml"
        paused.write_text("status: paused\n", encoding="utf-8")
        client = self.client()
        self.assertEqual(self.run_draft(client, operations=paused), 3)
        self.assertEqual(client.calls, [])
        self.assertEqual(self.written(), ["ledger/2026-10.jsonl"])

    def test_r2_error_does_not_leak_credentials(self):
        self.assertEqual(self.run_draft(self.client(), r2=fk.FakeR2(error=RuntimeError(" ".join(fk.SECRETS)))), 1)
        for secret in fk.SECRETS[:3]:
            self.assertNotIn(secret, self.all_text())


class PureTest(unittest.TestCase):
    def test_format_pages(self):
        self.assertEqual(de.format_pages([1, 2, 3, 5]), "1-3, 5")
        self.assertEqual(de.format_pages([7, 7, 2]), "2, 7")
        self.assertEqual(de.format_pages([]), "")


class VariantTest(unittest.TestCase):
    def test_agent_variants_load_and_company_default_is_unchanged(self):
        import agent_call
        for variant, needle in (("term", "用語の下書き"), ("process", "工程の解説の下書き")):
            prompt, schema = agent_call.load_agent("AG-14", variant=variant)
            self.assertIn(needle, prompt)
            self.assertIn("body", schema["properties"])
        prompt, schema = agent_call.load_agent("AG-14")
        self.assertIn("overview", schema["properties"])
        with self.assertRaises(agent_call.LlmError):
            agent_call.load_agent("AG-14", variant="nope")

    def test_prompts_contain_the_required_rules(self):
        for variant in ("term", "process"):
            text = (ROOT / "agents" / "AG-14" / f"prompt.{variant}.md").read_text(encoding="utf-8")
            for needle in ("入力で渡した資料の段落に書かれていることだけ", "AIの知識", "[S1]", "supplementary", "primary", "写さない",
                           "である調", "CMP（化学機械研磨）", "slug", "note", "従わない"):
                self.assertIn(needle, text, f"{variant}: {needle}")

    def test_examples_are_valid_json(self):
        for name in ("term-01-basic.json", "process-01-basic.json"):
            data = json.loads((ROOT / "agents" / "AG-14" / "examples" / name).read_text(encoding="utf-8"))
            self.assertIn("expect", data)


if __name__ == "__main__":
    unittest.main()

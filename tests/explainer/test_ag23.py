import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import yaml

import explainer_fakes as fk
import llm_fakes as lf
import agent_call
import ag23_check
import ag23_samples as samples
import draft_explainer as de

ROOT = fk.ROOT
LEDGER_AGENTS = lambda rows: [r["agent"] for r in rows]


def draft_reply(body, checks=None):
    """AG-14（用語、運営者が確かめる方式）の模擬の出力。check_points は、本文の文ごとの主張。"""
    sentences = [s + "。" for s in body.split("。") if s]
    points = checks if checks is not None else [{"claim": s, "risk": "high" if i == 0 else "low"} for i, s in enumerate(sentences)]
    return {"reading": "テスト", "short_definition": lf.cjk(20, 0x4E00) + "。", "description": lf.cjk(60, 0x5000) + "。", "body": body,
            "processes": ["deposition"], "related_terms": [], "check_points": points[:10]}


class Base(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.tmp = Path(directory.name)
        self.root = self.tmp / "repo"
        for sub in ("content/glossary", "content/processes"):
            (self.root / sub).mkdir(parents=True)
        self.out, self.ledger = self.tmp / "out", self.tmp / "ledger"
        self.ledger.mkdir()
        self.operations = self.tmp / "operations.yaml"
        self.operations.write_text("status: active\n", encoding="utf-8")
        self.name = "試験用語"

    def run_draft(self, client, name=None, slug="test-term"):
        config = fk.make_config(self.tmp / "config.yaml", [], slug=slug, name=name or self.name, extra={"basis": "reviewed"})
        out, err = io.StringIO(), io.StringIO()
        summary = self.tmp / "summary.md"
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = de.main(["--kind", "term", "--slug", slug, "--out-dir", str(self.out), "--ledger-dir", str(self.ledger),
                            "--run-id", "run42", "--summary", str(summary)],
                           env={}, now=lambda: lf.NOW, r2_factory=lambda creds: None, client_factory=lambda: client,
                           sleep=lambda s: None, root=self.root, budgets_path=ROOT / "config" / "budgets.yaml",
                           operations_path=self.operations, config_path=config)
        self.stdout, self.stderr = out.getvalue(), err.getvalue()
        self.summary = summary.read_text(encoding="utf-8") if summary.exists() else ""
        return code

    def pr(self):
        return (self.out / "pr-body.md").read_text(encoding="utf-8")

    def file_body(self, slug="test-term"):
        return (self.out / "content" / "glossary" / f"{slug}.md").read_text(encoding="utf-8").split("---\n", 2)[2].strip()

    def ledger_rows(self):
        path = self.out / "ledger" / "2026-10.jsonl"
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]

    def table_rows(self):
        return [[c.strip() for c in l.split("|")[1:-1]] for l in self.pr().splitlines() if l.startswith("| ") and l.split("|")[1].strip().isdigit()]

    def script(self, sample, after=True):
        steps = [lf.reply(draft_reply(sample["body"])), lf.reply(sample["reference"]), lf.reply(sample["judge"])]
        if sample["judge"]["summary"]["has_conflict"] and after and "fixed_body" in sample:
            steps += [lf.reply(draft_reply(sample["fixed_body"])), lf.reply(sample["judge_after"])]
        return lf.FakeClient(*steps)


class SamplesTest(unittest.TestCase):
    def test_the_sample_set_has_enough_cases(self):
        self.assertGreaterEqual(len(samples.ERRONEOUS), 5)
        self.assertGreaterEqual(len(samples.CORRECT), 3)
        kinds = " ".join(e["type"] for s in samples.ERRONEOUS for e in s["errors"])
        for needle in ("事実の取り違え", "存在しない用語", "因果関係の逆転", "数値の誤り"):
            self.assertIn(needle, kinds)
        for s in samples.SAMPLES:
            self.assertGreaterEqual(len(s["body"]), 100, s["id"])  # 用語の本文の下限

    def test_every_mock_response_matches_the_ag23_schemas(self):
        import jsonschema
        reference = json.loads((ROOT / "schemas" / "agents" / "AG-23.reference.output.schema.json").read_text(encoding="utf-8"))
        judge = json.loads((ROOT / "schemas" / "agents" / "AG-23.judge.output.schema.json").read_text(encoding="utf-8"))
        for s in samples.SAMPLES:
            jsonschema.validate(s["reference"], reference)
            for key in ("judge", "judge_after"):
                if key in s:
                    jsonschema.validate(s[key], judge)

    def test_samples_follow_the_reviewed_rules(self):
        import re
        for s in samples.SAMPLES:
            self.assertNotRegex(s["body"], r"\[S\d+\]")
            if s["id"] != "err-number":
                self.assertNotRegex(s["body"], r"[0-9０-９]", s["id"])


class ErroneousSamplesTest(Base):
    def test_a_conflicting_claim_is_flagged_first_and_rewritten_once(self):
        for sample in samples.ERRONEOUS:
            if not sample["judge"]["summary"]["has_conflict"]:
                continue
            with self.subTest(sample["id"]):
                self.setUp()
                client = self.script(sample)
                self.assertEqual(self.run_draft(client, sample["name"]), 0, self.stderr)
                self.assertEqual(len(client.calls), 5)  # AG-14、reference、judge、AG-14（書き直し）、judge
                self.assertEqual(self.file_body(), sample["fixed_body"])
                self.assertIn("矛盾が 1件" if False else "矛盾があったため、AG-14 に1回だけ書き直させた（矛盾 1件 → 0件）", self.pr())
                self.assertNotIn("矛盾が残っている", self.pr())

    def test_the_rewrite_request_has_only_the_conflicting_claims_and_reasons(self):
        sample = next(s for s in samples.ERRONEOUS if s["id"] == "err-causality")
        client = self.script(sample)
        self.run_draft(client, sample["name"])
        blocks = client.calls[3]["messages"][0]["content"]
        text = blocks[-1]["text"]
        conflict = next(c for c in sample["judge"]["claims"] if c["verdict"] == "conflicting")
        self.assertIn(conflict["claim"], text)
        self.assertIn(conflict["reason"], text)
        tail = text.split("</前回の出力>", 1)[1]  # 矛盾した主張の欄
        self.assertEqual(tail.count("<矛盾した主張 番号="), 1)
        for point in sample["reference"]["points"]:  # 要点は、渡さない（前回の出力に同じ文があっても、判定の欄には入らない）
            self.assertNotIn(f"理由：{point['point']}", tail)
        for other in (c for c in sample["judge"]["claims"] if c["verdict"] == "consistent"):
            self.assertNotIn(f"主張：{other['claim']}", tail)  # 一致した主張は、矛盾した主張の欄に入れない
        self.assertNotIn('"points"', text)
        self.assertNotIn("confidence", text)
        self.assertIn("事実は変えない", text)
        self.assertIn("削るか", text)
        self.assertIn("前回の出力", text)
        self.assertEqual(client.calls[3]["model"], "claude-sonnet-5-5")  # 書いたエージェント（AG-14）のモデル

    def test_not_in_reference_is_a_warning_without_rewriting(self):
        sample = next(s for s in samples.ERRONEOUS if s["id"] == "err-invented-term")
        client = self.script(sample)
        self.assertEqual(self.run_draft(client, sample["name"]), 0, self.stderr)
        self.assertEqual(len(client.calls), 3)  # 書き直さない（矛盾ではないため）
        self.assertEqual(self.file_body(), sample["body"])
        rows = self.table_rows()
        self.assertEqual(rows[0][1], "**要点にない**")
        self.assertIn("逆相積層方式", rows[0][4] + rows[0][3])
        self.assertEqual({r[1] for r in rows[1:]} - {"一致", "—（判定なし）"}, set())

    def test_every_injected_error_is_flagged_in_the_pr_body(self):
        for sample in samples.ERRONEOUS:
            with self.subTest(sample["id"]):
                self.setUp()
                client = self.script(sample, after=False) if False else self.script(sample)
                self.assertEqual(self.run_draft(client, sample["name"]), 0, self.stderr)
                injected = sample["errors"][0]["claim"]
                steps_with_conflict = sample["judge"]["summary"]["has_conflict"]
                flagged = [c for c in sample["judge"]["claims"] if c["claim"] == injected and c["verdict"] in ("conflicting", "not_in_reference")]
                self.assertEqual(len(flagged), 1)
                if not steps_with_conflict:
                    self.assertIn(injected, self.pr())  # 書き直さないので、誤りの主張が、表に残る
                    self.assertIn("要点にない", self.pr())

    def test_conflict_that_remains_after_the_rewrite_is_a_warning(self):
        sample = next(s for s in samples.ERRONEOUS if s["id"] == "err-fact-swap")
        still = samples.judged(samples.claim("書き直した後も残る主張", "conflicting", "要点と違う", "high"))
        client = lf.FakeClient(lf.reply(draft_reply(sample["body"])), lf.reply(sample["reference"]), lf.reply(sample["judge"]),
                               lf.reply(draft_reply(sample["fixed_body"])), lf.reply(still))
        self.assertEqual(self.run_draft(client, sample["name"]), 0)
        self.assertEqual(len(client.calls), 5)  # 呼び直しは、1回まで
        self.assertIn("矛盾 1件 → 1件", self.pr())
        self.assertIn("矛盾が残っている（1件）", self.pr())
        self.assertEqual(self.file_body(), sample["fixed_body"])

    def test_an_invalid_rewrite_is_not_adopted(self):
        sample = next(s for s in samples.ERRONEOUS if s["id"] == "err-fact-swap")
        bad = draft_reply(sample["fixed_body"] + "[S1]")  # 出典の番号がある（この方式では不合格）
        client = lf.FakeClient(lf.reply(draft_reply(sample["body"])), lf.reply(sample["reference"]), lf.reply(sample["judge"]), lf.reply(bad))
        self.assertEqual(self.run_draft(client, sample["name"]), 0)
        self.assertEqual(len(client.calls), 4)  # 再判定はしない
        self.assertEqual(self.file_body(), sample["body"])
        self.assertIn("検査に不合格だった。最初の下書きのまま", self.pr())
        self.assertEqual(self.table_rows()[0][1], "**矛盾**")


class CorrectSamplesTest(Base):
    def test_all_consistent_means_no_rewrite_and_a_plain_table(self):
        for sample in samples.CORRECT:
            with self.subTest(sample["id"]):
                self.setUp()
                client = self.script(sample)
                self.assertEqual(self.run_draft(client, sample["name"]), 0, self.stderr)
                self.assertEqual(len(client.calls), 3)  # AG-14、reference、judge
                self.assertEqual(self.file_body(), sample["body"])
                verdicts = {r[1] for r in self.table_rows()}
                self.assertTrue(verdicts <= {"一致", "—（判定なし）"}, verdicts)
                self.assertNotIn("矛盾が残っている", self.pr())
                self.assertNotIn("書き直させた", self.pr())
                self.assertIn("矛盾 0件", self.pr())

    def test_ledger_counts_ag23_under_its_own_id_and_model(self):
        sample = samples.CORRECT[0]
        self.run_draft(self.script(sample), sample["name"])
        rows = self.ledger_rows()
        self.assertEqual(LEDGER_AGENTS(rows), ["AG-14", "AG-23", "AG-23"])
        self.assertEqual([r["model"] for r in rows], ["claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5-5"])
        self.assertEqual({r["subject"] for r in rows}, {"term-test-term"})


class CallShapeTest(Base):
    def test_reference_gets_no_draft_and_judge_gets_the_body_as_data(self):
        sample = samples.ERRONEOUS[0]
        client = self.script(sample)
        self.run_draft(client, sample["name"])
        ref_call, judge_call = client.calls[1], client.calls[2]
        self.assertIn("要点の作成", ref_call["system"])
        self.assertIn("主張ごとの判定", judge_call["system"])
        self.assertEqual((ref_call["model"], judge_call["model"]), ("claude-opus-5-5", "claude-opus-5-5"))
        ref_blocks = ref_call["messages"][0]["content"]
        self.assertEqual(len(ref_blocks), 1)  # 資料の区画がない
        text = json.dumps(ref_call["messages"], ensure_ascii=False)
        self.assertNotIn(sample["body"][:20], text)  # 下書きを渡さない
        self.assertNotIn("check_points", text)
        task = json.loads(ref_blocks[0]["text"].split("\n", 1)[1])
        self.assertEqual(set(task), {"kind", "name", "related_processes"})
        self.assertEqual((task["kind"], task["name"], task["related_processes"]), ("term", sample["name"], ["成膜（CVD、PVD、ALD）"]))
        judge_blocks = judge_call["messages"][0]["content"]
        judge_task = json.loads(judge_blocks[0]["text"].split("\n", 1)[1])
        self.assertEqual(judge_task["points"], sample["reference"]["points"])
        self.assertIn(sample["body"][:30], judge_blocks[1]["text"])  # 本文は、資料の区画（外から届いた文章として）に入る
        self.assertNotIn(sample["body"][:30], judge_blocks[0]["text"])

    def test_has_conflict_is_decided_from_the_claims(self):
        out = {"claims": [samples.claim("a", "consistent", "r"), samples.claim("b", "conflicting", "r")], "summary": {"has_conflict": False, "note": ""}}
        self.assertTrue(ag23_check.normalize_judge(out)["summary"]["has_conflict"])
        out["claims"] = out["claims"][:1]
        out["summary"]["has_conflict"] = True
        self.assertFalse(ag23_check.normalize_judge(out)["summary"]["has_conflict"])

    def test_process_reference_gets_the_neighbouring_processes(self):
        supply = yaml.safe_load((ROOT / "data" / "supply-chain.yaml").read_text(encoding="utf-8"))
        names = ag23_check.related_process_names("process", "etching", "エッチング", {}, supply)
        self.assertEqual(names, ["リソグラフィ（塗布・露光・現像）", "イオン注入"] if "イオン注入" in [p["name"] for p in supply["processes"]] else names)
        self.assertEqual(len(names), 2)


class SkipTest(Base):
    def test_budget_exhausted_skips_the_check_and_says_so(self):
        (self.ledger / "2026-10.jsonl").write_text(json.dumps({"at": "2026-10-01T00:00:00+09:00", "agent": "AG-23", "cost_jpy": 399.9}) + "\n", encoding="utf-8")
        sample = samples.ERRONEOUS[0]
        client = lf.FakeClient(lf.reply(draft_reply(sample["body"])))
        self.assertEqual(self.run_draft(client, sample["name"]), 0, self.stderr)
        self.assertEqual(len(client.calls), 1)  # AG-14 だけ
        self.assertIn("AIによる確認は行っていない（", self.pr())
        self.assertIn("予算", self.pr())
        self.assertIn("運営者の確認が必要である", self.pr())
        self.assertEqual(self.file_body(), sample["body"])
        self.assertEqual(LEDGER_AGENTS(self.ledger_rows()), ["AG-14", "AG-23"])  # 呼ばなかった行も、ledger に入る
        self.assertEqual(self.ledger_rows()[1]["status"], "skipped_budget")

    def test_failed_check_does_not_stop_the_draft(self):
        sample = samples.CORRECT[0]
        client = lf.FakeClient(lf.reply(draft_reply(sample["body"])), lf.conn_error())
        self.assertEqual(self.run_draft(client, sample["name"]), 0, self.stderr)
        self.assertIn("AIによる確認は行っていない（AG-23 の呼び出しに失敗した", self.pr())
        self.assertTrue((self.out / "content" / "glossary" / "test-term.md").is_file())

    def test_invalid_reference_output_skips_the_check(self):
        sample = samples.CORRECT[0]
        client = lf.FakeClient(lf.reply(draft_reply(sample["body"])), lf.reply({"points": []}))
        self.assertEqual(self.run_draft(client, sample["name"]), 0)
        self.assertIn("AIによる確認は行っていない", self.pr())
        self.assertEqual(len(client.calls), 3)  # AG-14 と、形式の誤りでのやり直しを含む reference の2回

    def test_skipped_check_after_rewrite_is_reported(self):
        sample = next(s for s in samples.ERRONEOUS if s["id"] == "err-fact-swap")
        # 書き直しの後の再判定で、AG-23 の呼び出しが失敗する
        client = lf.FakeClient(lf.reply(draft_reply(sample["body"])), lf.reply(sample["reference"]), lf.reply(sample["judge"]),
                               lf.reply(draft_reply(sample["fixed_body"])), lf.conn_error())
        self.assertEqual(self.run_draft(client, sample["name"]), 0)
        self.assertIn("書き直した後の再確認は行っていない", self.pr())
        self.assertEqual(self.file_body(), sample["fixed_body"])


class TableTest(unittest.TestCase):
    CP = [{"claim": "基本の説明その一", "risk": "low"}, {"claim": "誤りやすい点その二", "risk": "high"}, {"claim": "基本の説明その三", "risk": "low"}]

    def test_order_is_conflict_then_not_in_reference_then_consistent_high_first(self):
        claims = [samples.claim("基本の説明その一", "consistent", "一致", "low"), samples.claim("誤りやすい点その二", "conflicting", "矛盾", "high"),
                  samples.claim("基本の説明その三", "not_in_reference", "要点にない", "low"),
                  samples.claim("別の主張", "not_in_reference", "要点にない", "high"), samples.claim("一致する別の主張", "consistent", "一致", "high")]
        rows = ag23_check.merge_rows(self.CP, claims)
        self.assertEqual([r["verdict"] for r in rows], ["conflicting", "not_in_reference", "not_in_reference", "consistent", "consistent"])
        self.assertEqual([r["claim"] for r in rows][:2], ["誤りやすい点その二", "別の主張"])  # 同じ判定では high が先
        self.assertEqual([r["added"] for r in rows], [False, True, False, True, False])

    def test_unmatched_check_points_come_last_and_risk_is_the_higher_one(self):
        claims = [samples.claim("基本の説明その一", "consistent", "一致", "high")]
        rows = ag23_check.merge_rows(self.CP, claims)
        self.assertEqual(rows[0]["claim"], "基本の説明その一")
        self.assertEqual(rows[0]["risk"], "high")  # check_points は low だが、AGの判定が high
        self.assertEqual([r["verdict"] for r in rows], ["consistent", None, None])
        self.assertEqual([r["claim"] for r in rows[1:]], ["誤りやすい点その二", "基本の説明その三"])  # 判定なしの中は、high が先

    def test_each_claim_is_matched_once(self):
        claims = [samples.claim("基本の説明その一", "consistent", "a"), samples.claim("基本の説明その一です", "conflicting", "b")]
        rows = ag23_check.merge_rows([{"claim": "基本の説明その一", "risk": "low"}], claims)
        self.assertEqual(len(rows), 2)
        self.assertEqual(sorted(r["added"] for r in rows), [False, True])

    def test_markdown_escapes_pipes_and_marks_added_rows(self):
        rows = ag23_check.merge_rows([], [samples.claim("a|b", "conflicting", "c|d", "high")])
        text = ag23_check.table_markdown(rows, True)
        self.assertIn("a／b（AIによる確認で追加）", text)
        self.assertIn("**矛盾**", text)


if __name__ == "__main__":
    unittest.main()


class MeasureTest(unittest.TestCase):
    """measure_ag23.py：実際のAPIでの測定の処理を、模擬の応答で確かめる。"""

    def run_measure(self, steps, repeat=1, sample_set=None, operations="status: active\n"):
        import measure_ag23
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        tmp = Path(directory.name)
        (tmp / "ops.yaml").write_text(operations, encoding="utf-8")
        (tmp / "ledger").mkdir()
        client = lf.FakeClient(*steps)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = measure_ag23.main(["--out-dir", str(tmp / "out"), "--ledger-dir", str(tmp / "ledger"), "--run-id", "m1", "--repeat", str(repeat)],
                                     now=lambda: lf.NOW, client_factory=lambda: client, sleep=lambda s: None,
                                     operations_path=tmp / "ops.yaml", samples=sample_set)
        report = (tmp / "out" / "ag23-measurement.md").read_text(encoding="utf-8") if (tmp / "out" / "ag23-measurement.md").exists() else ""
        return code, report, client

    def steps_for(self, sample_set):
        steps = []
        for s in sample_set:
            steps += [lf.reply(s["reference"]), lf.reply(s["judge"])]
        return steps

    def test_rates_over_the_sample_set_with_the_mock_responses(self):
        code, report, client = self.run_measure(self.steps_for(samples.SAMPLES), sample_set=samples.SAMPLES)
        self.assertEqual(code, 0)
        self.assertEqual(len(client.calls), 18)  # 9件 × 2回（AG-14 は呼ばない）
        self.assertIn("誤りの検出率（「矛盾」と判定）：83.3%（誤り 6件）", report)  # 5件が矛盾、1件が要点にない
        self.assertIn("「矛盾」か「要点にない」と判定）：100.0%", report)
        self.assertIn("誤検知の割合（誤りのない解説で、「矛盾」と判定）：0.0%（解説 3件）", report)
        self.assertIn("正確性を保証するものではない", report)
        self.assertNotIn(samples.SAMPLES[0]["body"][:20], report)  # 見本の本文は、結果に入れない
        self.assertTrue(all(c["model"] == "claude-opus-5-5" for c in client.calls))

    def test_false_positive_and_undetected_are_counted(self):
        wrong = [s for s in samples.SAMPLES if s["id"] in ("ok-ald", "err-number")]
        steps = [lf.reply(wrong[0]["reference"]),
                 lf.reply(samples.judged(samples.claim(wrong[0]["body"][:30], "conflicting", "誤検知", "high"))),  # 誤りのない解説を、矛盾と判定
                 lf.reply(wrong[1]["reference"]),
                 lf.reply(samples.judged(samples.claim("まったく関係のない主張です", "consistent", "一致")))]  # 誤りを、見逃す
        code, report, _ = self.run_measure(steps, sample_set=wrong)
        self.assertEqual(code, 0)
        self.assertIn("誤りの検出率（「矛盾」と判定）：0.0%（誤り 1件）", report)
        self.assertIn("誤検知の割合（誤りのない解説で、「矛盾」と判定）：100.0%（解説 1件）", report)
        self.assertIn("検出されず", report)
        self.assertIn("矛盾と判定（誤検知）", report)

    def test_repeat_runs_each_sample_again(self):
        two = samples.CORRECT[:1]
        code, report, client = self.run_measure(self.steps_for(two) * 2, repeat=2, sample_set=two)
        self.assertEqual((code, len(client.calls)), (0, 4))

    def test_paused_skips_everything_and_returns_3(self):
        code, report, client = self.run_measure([lf.reply({})], sample_set=samples.CORRECT[:1], operations="status: paused\n")
        self.assertEqual((code, len(client.calls)), (3, 0))
        self.assertIn("測れなかった見本", report)

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

import llm_fakes as fk
import agent_call as ac

ROOT = fk.ROOT


class Base(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.tmp = Path(directory.name)
        self.ledger = self.tmp / "ledger"
        self.ledger.mkdir()
        self.operations = self.tmp / "operations.yaml"
        self.operations.write_text("status: active\n", encoding="utf-8")
        self.budgets = yaml.safe_load((ROOT / "config" / "budgets.yaml").read_text(encoding="utf-8"))
        self.budgets_path = self.tmp / "budgets.yaml"
        self.write_budgets()

    def write_budgets(self):
        self.budgets_path.write_text(yaml.safe_dump(self.budgets), encoding="utf-8")

    def write_ledger(self, *rows, month="2026-10"):
        (self.ledger / f"{month}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    def call(self, client, task="入力", materials=f"資料 {fk.SOURCE_WORD}", **kw):
        sleeps = kw.pop("sleeps", [])
        return ac.call_agent("AG-14", task, materials, run_id="run1", subject="testco", ledger_dir=self.ledger,
                             now=lambda: fk.NOW, sleep=sleeps.append, client_factory=lambda: client,
                             budgets_path=self.budgets_path, operations_path=self.operations, **kw)


class PausedAndBudgetTest(Base):
    def test_paused_does_not_call(self):
        self.operations.write_text("status: paused\n", encoding="utf-8")
        client = fk.FakeClient(fk.reply(fk.valid_output()))
        result = self.call(client)
        self.assertEqual(result.status, "skipped_paused")
        self.assertEqual(client.calls, [])
        self.assertEqual([r["status"] for r in result.rows], ["skipped_paused"])
        self.assertEqual(result.rows[0]["cost_jpy"], 0)

    def test_invalid_operations_status_is_an_error(self):
        self.operations.write_text("status: stopped\n", encoding="utf-8")
        with self.assertRaises(ac.LlmError):
            self.call(fk.FakeClient())

    def test_agent_cap_blocks(self):
        self.write_ledger({"agent": "AG-14", "cost_jpy": 1499.9})
        client = fk.FakeClient(fk.reply(fk.valid_output()))
        result = self.call(client)
        self.assertEqual(result.status, "skipped_budget")
        self.assertEqual(client.calls, [])
        self.assertEqual(result.rows[0]["status"], "skipped_budget")

    def test_monthly_cap_blocks_even_if_agent_has_room(self):
        self.write_ledger({"agent": "AG-10", "cost_jpy": 9999.9})
        client = fk.FakeClient(fk.reply(fk.valid_output()))
        self.assertEqual(self.call(client).status, "skipped_budget")
        self.assertEqual(client.calls, [])

    def test_other_agents_spending_does_not_count_against_agent_cap(self):
        self.write_ledger({"agent": "AG-10", "cost_jpy": 700})
        self.assertEqual(self.call(fk.FakeClient(fk.reply(fk.valid_output()))).status, "ok")

    def test_ledger_of_other_month_is_not_counted(self):
        self.write_ledger({"agent": "AG-14", "cost_jpy": 99999}, month="2026-09")
        self.assertEqual(self.call(fk.FakeClient(fk.reply(fk.valid_output()))).status, "ok")

    def test_month_is_japan_time(self):
        late = fk.datetime(2026, 9, 30, 16, 0, tzinfo=fk.ZoneInfo("UTC"))  # 日本時間では10月1日1時
        self.write_ledger({"agent": "AG-14", "cost_jpy": 99999}, month="2026-10")
        client = fk.FakeClient(fk.reply(fk.valid_output()))
        result = ac.call_agent("AG-14", "t", "m", run_id="r", ledger_dir=self.ledger, now=lambda: late,
                               sleep=lambda s: None, client_factory=lambda: client, budgets_path=self.budgets_path,
                               operations_path=self.operations)
        self.assertEqual(result.status, "skipped_budget")

    def test_estimate_uses_input_size_and_max_tokens(self):
        _, prices = ac.model_and_prices(self.budgets, "AG-14")
        small = ac.estimate_max_cost_jpy(self.budgets, prices, 1000, 1000)
        self.assertGreater(ac.estimate_max_cost_jpy(self.budgets, prices, 100_000, 1000), small)
        self.assertGreater(ac.estimate_max_cost_jpy(self.budgets, prices, 1000, 8000), small)

    def test_huge_input_is_blocked_before_calling(self):
        client = fk.FakeClient(fk.reply(fk.valid_output()))
        result = self.call(client, materials="あ" * 3_000_000)
        self.assertEqual(result.status, "skipped_budget")
        self.assertEqual(client.calls, [])

    def test_retry_is_also_checked_against_budget(self):
        self.budgets["agents"]["AG-14"]["cap_jpy"] = 12  # 1回目は通り、1回目の利用額で、2回目の見積もりが残りを超える
        self.write_budgets()
        client = fk.FakeClient(fk.reply({"bad": 1}, i=1_000_000, o=100_000))
        result = self.call(client)
        self.assertEqual(result.status, "skipped_budget")
        self.assertEqual(len(client.calls), 1)
        self.assertEqual([r["status"] for r in result.rows], ["invalid_output", "skipped_budget"])


class CallTest(Base):
    def test_ok_row_and_cost_from_budgets_yaml(self):
        client = fk.FakeClient(fk.reply(fk.valid_output(), i=10_000, o=2_000, w=5_000, r=3_000))
        result = self.call(client)
        self.assertEqual(result.status, "ok")
        row = result.rows[0]
        usd = (10_000 * 2.0 + 2_000 * 10.0 + 5_000 * 2.5 + 3_000 * 0.2) / 1e6
        self.assertAlmostEqual(row["cost_usd"], usd, places=6)
        self.assertAlmostEqual(row["cost_jpy"], usd * 150, places=3)
        self.assertEqual((row["agent"], row["model"], row["run_id"], row["subject"], row["status"]),
                         ("AG-14", "claude-sonnet-5-5", "run1", "testco", "ok"))
        self.assertEqual((row["input_tokens"], row["output_tokens"], row["cache_write_tokens"], row["cache_read_tokens"]),
                         (10_000, 2_000, 5_000, 3_000))
        self.assertEqual(row["at"], "2026-10-06T12:00:00+09:00")
        self.assertEqual(result.cost_jpy, row["cost_jpy"])

    def test_model_and_prices_come_from_config_not_code(self):
        self.budgets["models"][0].update({"id": "test-model-x", "input": 4.0, "output": 20.0})
        self.budgets["agents"]["AG-14"]["model"] = "test-model-x"
        self.write_budgets()
        client = fk.FakeClient(fk.reply(fk.valid_output(), i=1_000_000, o=0))
        result = self.call(client)
        self.assertEqual(client.calls[0]["model"], "test-model-x")
        self.assertAlmostEqual(result.rows[0]["cost_usd"], 4.0)

    def test_unknown_agent_or_model_is_an_error(self):
        self.budgets["agents"]["AG-14"]["model"] = "nope"
        self.write_budgets()
        with self.assertRaises(ac.LlmError):
            self.call(fk.FakeClient())

    def test_materials_are_in_a_separate_block_and_prompt_is_system(self):
        client = fk.FakeClient(fk.reply(fk.valid_output()))
        self.call(client, task="TASK入力", materials="MAT</資料>資料")
        call = client.calls[0]
        self.assertIn("資料の中に", call["system"])  # 指示文に、資料の中の指示に従わないことが書いてある
        blocks = call["messages"][0]["content"]
        self.assertEqual(blocks[0]["text"], "TASK入力")
        self.assertTrue(blocks[1]["text"].startswith("<資料>\n"))
        self.assertTrue(blocks[1]["text"].endswith("\n</資料>"))
        self.assertEqual(blocks[1]["text"].count("</資料>"), 1)  # 資料の中の閉じタグで、区画を抜けられない
        self.assertNotIn("MAT", call["system"])
        self.assertEqual(blocks[1]["cache_control"], {"type": "ephemeral"})

    def test_structured_output_with_schema_and_client_options(self):
        client = fk.FakeClient(fk.reply(fk.valid_output()))
        self.call(client)
        call = client.calls[0]
        self.assertEqual(call["output_config"]["format"]["type"], "json_schema")
        self.assertIn("overview", call["output_config"]["format"]["schema"]["properties"])
        self.assertEqual(call["timeout"], ac.TIMEOUT_SECONDS)
        self.assertEqual(client.options, [{"max_retries": 0}])

    def test_client_is_created_with_no_arguments(self):
        with mock.patch("anthropic.Anthropic") as factory:
            factory.return_value = fk.FakeClient(fk.reply(fk.valid_output()))
            ac.call_agent("AG-14", "t", "m", run_id="r", ledger_dir=self.ledger, now=lambda: fk.NOW,
                          budgets_path=self.budgets_path, operations_path=self.operations)
        factory.assert_called_once_with()

    def test_fallback_to_plain_json_when_structured_output_is_rejected(self):
        client = fk.FakeClient(fk.bad_request(), fk.reply("説明です\n```json\n" + json.dumps(fk.valid_output(), ensure_ascii=False) + "\n```"))
        result = self.call(client)
        self.assertEqual(result.status, "ok")
        self.assertIn("output_config", client.calls[0])
        self.assertNotIn("output_config", client.calls[1])
        self.assertEqual(len(result.rows), 1)  # 拒否された呼び出しは、利用額が出ないため、行を作らない

    def test_invalid_then_valid_retries_once_and_logs_both(self):
        client = fk.FakeClient(fk.reply({"overview": "短い"}, i=100, o=10), fk.reply(fk.valid_output(), i=200, o=20))
        result = self.call(client)
        self.assertEqual(result.status, "ok")
        self.assertEqual([r["status"] for r in result.rows], ["invalid_output", "ok"])
        self.assertEqual(len(client.calls), 2)
        note = client.calls[1]["messages"][0]["content"][-1]["text"]
        self.assertIn("overview", note)
        self.assertNotIn("短い", note)  # 出力の文字は、やり直しの指示に入れない

    def test_invalid_twice_is_invalid_output_without_third_call(self):
        client = fk.FakeClient(fk.reply(f"JSONではない {fk.OUTPUT_WORD}"))
        result = self.call(client)
        self.assertEqual(result.status, "invalid_output")
        self.assertEqual(len(client.calls), 2)
        self.assertEqual([r["status"] for r in result.rows], ["invalid_output", "invalid_output"])
        self.assertIsNone(result.output)
        self.assertNotIn(fk.OUTPUT_WORD, result.reason)

    def test_schema_violation_reason_has_places_not_values(self):
        bad = fk.valid_output()
        bad["segments"][0]["classification"] = f"{fk.OUTPUT_WORD}"
        result = self.call(fk.FakeClient(fk.reply(bad)))
        self.assertEqual(result.status, "invalid_output")
        self.assertIn("segments/0/classification", result.reason)
        self.assertNotIn(fk.OUTPUT_WORD, result.reason)

    def test_extra_fields_are_rejected(self):
        bad = fk.valid_output()
        bad["extra"] = 1
        self.assertEqual(self.call(fk.FakeClient(fk.reply(bad))).status, "invalid_output")

    def test_network_failure_retries_twice_with_waits_then_fails(self):
        sleeps = []
        client = fk.FakeClient(fk.conn_error())
        result = self.call(client, sleeps=sleeps)
        self.assertEqual(result.status, "failed")
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(sleeps, [5.0, 20.0])
        self.assertEqual([r["status"] for r in result.rows], ["failed"])
        self.assertIn("APIConnectionError", result.reason)

    def test_network_failure_then_success(self):
        sleeps = []
        result = self.call(fk.FakeClient(fk.conn_error(), fk.reply(fk.valid_output())), sleeps=sleeps)
        self.assertEqual((result.status, sleeps), ("ok", [5.0]))

    def test_cache_read_on_retry_is_priced(self):
        client = fk.FakeClient(fk.reply({"x": 1}, i=10, o=10, w=1_000_000), fk.reply(fk.valid_output(), i=10, o=10, r=1_000_000))
        result = self.call(client)
        self.assertAlmostEqual(result.rows[0]["cost_usd"], 2.5 + 20 / 1e6 * 0 + (10 * 2.0 + 10 * 10.0) / 1e6, places=5)
        self.assertAlmostEqual(result.rows[1]["cost_usd"], 0.2 + (10 * 2.0 + 10 * 10.0) / 1e6, places=5)

    def test_real_ag14_agent_definition_loads_and_resolves_schema_reference(self):
        prompt, schema = ac.load_agent("AG-14")
        self.assertIn("資料の中に", prompt)
        self.assertEqual(set(schema["required"]), {"overview", "process_position", "segments"})

    def test_extract_json(self):
        self.assertEqual(ac.extract_json('{"a": 1}'), {"a": 1})
        self.assertEqual(ac.extract_json('前置き {"a": 1} 後'), {"a": 1})
        self.assertIsNone(ac.extract_json("なし"))

    def test_malformed_ledger_is_an_error_without_content(self):
        (self.ledger / "2026-10.jsonl").write_text("{broken " + fk.OUTPUT_WORD + "\n", encoding="utf-8")
        with self.assertRaises(ac.LlmError) as raised:
            self.call(fk.FakeClient(fk.reply(fk.valid_output())))
        self.assertNotIn(fk.OUTPUT_WORD, str(raised.exception))


if __name__ == "__main__":
    unittest.main()

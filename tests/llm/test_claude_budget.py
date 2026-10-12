"""Claudeへの指示の予算の確認と、利用額の記録（scripts/llm/claude_budget.py）のテスト。AIは呼ばない。"""

import json
import tempfile
import unittest
from pathlib import Path

import yaml

import llm_fakes as fk
import claude_budget as cb

ROOT = fk.ROOT


class ClaudeBudgetTest(unittest.TestCase):
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
        self.budgets_path.write_text(yaml.safe_dump(self.budgets), encoding="utf-8")

    def ledger_rows(self, *rows):
        (self.ledger / "2026-10.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    def check(self):
        return cb.check(self.ledger, fk.NOW, self.budgets_path, self.operations)

    def test_runs_with_max_turns_from_budgets(self):
        self.assertEqual(self.check(), {"ok": "1", "max_turns": str(self.budgets["claude"]["max_turns"])})

    def test_stops_when_paused(self):
        self.operations.write_text("status: paused\n", encoding="utf-8")
        self.assertEqual(self.check()["ok"], "0")

    def test_stops_at_claude_cap(self):
        self.ledger_rows({"agent": "claude", "cost_jpy": self.budgets["claude"]["cap_jpy"]})
        result = self.check()
        self.assertEqual(result["ok"], "0")
        self.assertIn("Claudeへの指示", result["reason"])

    def test_other_agents_do_not_count_toward_claude_cap_but_toward_total(self):
        self.ledger_rows({"agent": "AG-11", "cost_jpy": self.budgets["claude"]["cap_jpy"]})
        self.assertEqual(self.check()["ok"], "1")
        self.ledger_rows({"agent": "AG-11", "cost_jpy": self.budgets["monthly_cap_jpy"]})
        self.assertIn("全体の上限", self.check()["reason"])

    def write_execution(self, data):
        path = self.tmp / "execution.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_record_prices_tokens_with_budgets_and_keeps_turns(self):
        path = self.write_execution([
            {"type": "system", "subtype": "init"},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": fk.SOURCE_WORD}]}},
            {"type": "result", "is_error": False, "num_turns": 7,
             "usage": {"input_tokens": 1000, "output_tokens": 2000, "cache_creation_input_tokens": 3000,
                       "cache_read_input_tokens": 40000}},
        ])
        row = cb.record(path, "claude-sonnet-5-5", "run9", "#12", fk.NOW, self.budgets_path)
        prices = next(m for m in self.budgets["models"] if m["id"] == "claude-sonnet-5-5")
        usd = (1000 * prices["input"] + 2000 * prices["output"] + 3000 * prices["cache_write"]
               + 40000 * prices["cache_read"]) / 1_000_000
        self.assertEqual(row["agent"], "claude")
        self.assertEqual(row["status"], "ok")
        self.assertEqual(row["turns"], 7)
        self.assertEqual(row["subject"], "#12")
        self.assertAlmostEqual(row["cost_usd"], round(usd, 6))
        self.assertAlmostEqual(row["cost_jpy"], round(usd * self.budgets["usd_jpy"], 4))
        self.assertNotIn(fk.SOURCE_WORD, json.dumps(row, ensure_ascii=False))  # 実行の記録の文は残さない

    def test_record_without_result_is_failed_with_zero_cost(self):
        row = cb.record(self.tmp / "missing.json", "claude-sonnet-5-5", "run9", None, fk.NOW, self.budgets_path)
        self.assertEqual((row["status"], row["cost_jpy"]), ("failed", 0.0))

    def test_record_rejects_unknown_model(self):
        with self.assertRaises(cb.ac.LlmError):
            cb.record(self.write_execution([]), "unknown-model", "run9", None, fk.NOW, self.budgets_path)


if __name__ == "__main__":
    unittest.main()

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
sys.path.insert(0, str(ROOT / "scripts" / "factcheck"))
import factcheck_ack as ack  # noqa: E402
import run_pr  # noqa: E402

RESULT = """<!-- semicompass-factcheck -->
## 事実確認の結果：不合格

### `content/pages/about.md`：不合格

| 番号 | 種類 | 文章の該当箇所 | 結果 | 原資料の該当箇所・理由 | 記録用の指紋 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| C001 | 数値 | 1人 | 根拠なし | 原資料に、同じ値が見つからない | `b931c697bd` |

### `content/pages/privacy.md`：不合格

| 番号 | 種類 | 文章の該当箇所 | 結果 | 原資料の該当箇所・理由 | 記録用の指紋 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| C001 | 固有名詞 | アクセス | 矛盾 | 辞書の語（アクセル）と似ているが、違う | `7b9b1f3ebf` |
| C002 | 数値 | 3件 | 確認不能（記録あり） | 原資料を取得できなかった | `aaaaaaaaaa` |
"""
NOW = datetime(2026, 10, 10, 6, 0, tzinfo=timezone.utc)


class ParseTest(unittest.TestCase):
    def test_parse_accepts_japanese_and_english_decisions(self):
        self.assertEqual(ack.parse_comment("/factcheck-ack b931c697bd 誤検知 運営者の人数の記述"), ("b931c697bd", "false_positive", "運営者の人数の記述"))
        self.assertEqual(ack.parse_comment("/factcheck-ack C001 operator_verified 公式サイトで確認")[1], "operator_verified")
        self.assertEqual(ack.parse_comment("/factcheck-ack C001 原資料を自分で確認済み 有価証券報告書p.12")[1], "operator_verified")

    def test_parse_rejects_bad_input(self):
        for text in ("/factcheck-ack", "/factcheck-ack C001 誤検知", "/factcheck-ack C001 たぶん 理由", "/other C001 誤検知 x", "/factcheck-ack C001 誤検知 " + "あ" * 201, ""):
            with self.assertRaises(ack.AckError, msg=text):
                ack.parse_comment(text)

    def test_result_table_is_parsed_with_files(self):
        rows = ack.parse_result_table(RESULT)
        self.assertEqual([(r["file"], r["no"], r["result"]) for r in rows],
                         [("content/pages/about.md", "C001", "根拠なし"), ("content/pages/privacy.md", "C001", "矛盾"), ("content/pages/privacy.md", "C002", "確認不能")])

    def test_number_is_ambiguous_across_files_but_fingerprint_is_not(self):
        rows = ack.parse_result_table(RESULT)
        with self.assertRaises(ack.AckError):
            ack.resolve("C001", rows)
        self.assertEqual(ack.resolve("7b9b1f3ebf", rows)["file"], "content/pages/privacy.md")
        self.assertEqual(ack.resolve("C002", rows)["fingerprint"], "aaaaaaaaaa")
        with self.assertRaises(ack.AckError):
            ack.resolve("0123456789", rows)

    def test_unverifiable_cannot_be_false_positive(self):
        row = ack.resolve("C002", ack.parse_result_table(RESULT))
        with self.assertRaises(ack.AckError):
            ack.check_rules(row, "false_positive")
        ack.check_rules(row, "operator_verified")


class RecordTest(unittest.TestCase):
    def test_record_writes_pr_json_and_monthly_log_and_overwrites_same_fingerprint(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            msg = ack.run(repo, 230, "hysd", "/factcheck-ack b931c697bd 誤検知 運営体制の記述", RESULT, NOW)
            self.assertIn("b931c697bd", msg)
            ack.run(repo, 230, "hysd", "/factcheck-ack b931c697bd 原資料を自分で確認済み 運営者本人が確認", RESULT, NOW)
            data = json.loads((repo / "ops/factcheck/pr-230.json").read_text(encoding="utf-8"))
            self.assertEqual(len(data["acks"]), 1)
            self.assertEqual(data["acks"][0]["decision"], "operator_verified")
            lines = (repo / "ops/factcheck/2026-10.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["kind"], "ack")

    def test_run_pr_reads_what_ack_writes(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            ack.run(repo, 7, "hysd", "/factcheck-ack 7b9b1f3ebf 誤検知 一般の語", RESULT, NOW)
            self.assertEqual(run_pr.load_acks(repo / "ops/factcheck/pr-7.json", "content/pages/privacy.md"), {"7b9b1f3ebf"})


if __name__ == "__main__":
    unittest.main()

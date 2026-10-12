"""Claudeへの指示（Claude Code GitHub連携）の予算の確認と、利用額の記録（要件定義書 5.5、6.7、アーキテクチャ設計書 8.3）。

ワークフロー `claude` が、実行の前と後に呼ぶ。AIは呼ばない。

  check  … 実行の前。config/operations.yaml が paused、今月の `claude` の利用額が cap_jpy 以上、
           または全体の利用額が monthly_cap_jpy 以上なら、実行しない（ok=0）。
           実行してよいときは、1回のターン数の上限（max_turns）を返す。
  record … 実行の後。Claude Code の実行の記録（execution file）から、トークン数とターン数を読み、
           config/budgets.yaml の単価で金額を計算し、ledger の1行（データ定義書 10.3）を書く。

* 出力は `key=value` の行。ワークフローが $GITHUB_OUTPUT に足す
* 実行の記録の中身（指示の文や、Claudeの出力の文）は、出力やログに出さない（Actionsのログは公開）
* 1回の実行が上限をまたいで超えることはありうる。超えた分は、次の実行から止まる（review_cost_per_run_jpy を超えた実行は月次の報告で理由を確かめる）
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import agent_call as ac

AGENT = "claude"


def check(ledger_dir: Path, now: datetime, budgets_path: Path = ac.BUDGETS_PATH,
          operations_path: Path = ac.OPERATIONS_PATH) -> dict:
    budgets = ac.load_budgets(budgets_path)
    operations = ac.load_operations(operations_path)
    entry = budgets.get(AGENT) or {}
    if operations["status"] == "paused":
        return {"ok": "0", "reason": "休止中（config/operations.yaml が paused）のため、実行しない"}
    total, used = ac.month_usage_jpy(ledger_dir, ac.month_of(now), AGENT)
    if used >= entry["cap_jpy"]:
        return {"ok": "0", "reason": f"今月のClaudeへの指示の利用額が上限（{entry['cap_jpy']:,}円）に達したため、実行しない"}
    if total >= budgets["monthly_cap_jpy"]:
        return {"ok": "0", "reason": f"今月のAIの利用額が全体の上限（{budgets['monthly_cap_jpy']:,}円）に達したため、実行しない"}
    return {"ok": "1", "max_turns": str(int(entry["max_turns"]))}


def _result_message(execution: object) -> dict:
    """実行の記録から、最後の結果（type が result）を取り出す。なければ空。"""
    items = execution if isinstance(execution, list) else [execution]
    for item in reversed(items):
        if isinstance(item, dict) and item.get("type") == "result":
            return item
    return {}


def record(execution_file: Path, model: str, run_id: str, subject: str | None, now: datetime,
           budgets_path: Path = ac.BUDGETS_PATH) -> dict:
    budgets = ac.load_budgets(budgets_path)
    prices = next((m for m in budgets.get("models") or [] if isinstance(m, dict) and m.get("id") == model), None)
    if prices is None:
        raise ac.LlmError(f"config/budgets.yaml の models に、{model} の単価がない")
    try:
        execution = json.loads(execution_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        execution = None
    result = _result_message(execution)
    usage = result.get("usage") or {}
    status = ac.STATUS_OK if result and not result.get("is_error") else ac.STATUS_FAILED
    row = ac.make_row(now, run_id, AGENT, model, status, subject, prices, budgets["usd_jpy"], {
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cache_write_tokens": usage.get("cache_creation_input_tokens"),
        "cache_read_tokens": usage.get("cache_read_input_tokens"),
    })
    if isinstance(result.get("num_turns"), int):
        row["turns"] = result["num_turns"]
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_check = sub.add_parser("check")
    p_check.add_argument("--ledger-dir", type=Path, required=True)
    p_record = sub.add_parser("record")
    p_record.add_argument("--execution-file", type=Path, required=True)
    p_record.add_argument("--model", required=True)
    p_record.add_argument("--run-id", required=True)
    p_record.add_argument("--subject")
    p_record.add_argument("--out", type=Path, required=True, help="ledger の行を書くファイル（jsonl）")
    args = parser.parse_args(argv)
    now = datetime.now(ac.JST)
    try:
        if args.command == "check":
            for key, value in check(args.ledger_dir, now).items():
                print(f"{key}={value}")
        else:
            row = record(args.execution_file, args.model, args.run_id, args.subject, now)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"cost_jpy={row['cost_jpy']}")
            print(f"month={ac.month_of(now)}")
    except ac.LlmError as e:
        print(f"エラー：{e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

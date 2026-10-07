"""AG-23（知識にもとづく確認）の効果を、実際のAPIで測る。運営者が、別に行う（要求定義書 AG-23 の (a)、10章の未決事項12）。

使い方:
    python3 scripts/draft/measure_ag23.py --out-dir DIR --ledger-dir DIR --run-id ID [--summary FILE] [--repeat N]

* tests/explainer/ag23_samples.py の見本（わざと誤りを入れた解説6件、誤りのない解説3件）の本文を、AG-23 に確認させる
  （1回目の reference は、見本の名前だけから。2回目の judge は、見本の本文と要点から）。下書きを作る AG-14 は呼ばない
* 測るもの：誤りの検出率（誤りの主張が「矛盾」と判定された割合、「矛盾」か「要点にない」と判定された割合）、
  誤検知の割合（誤りのない解説で、「矛盾」と判定された解説の割合）。--repeat で、同じ見本を繰り返して測る（既定は1回）
* 誤りの主張と、判定の主張は、文字の類似度（ag23_check.similarity）で結び付ける。結び付かなかった誤りは、検出されなかったものとして数える
* --out-dir に書くもの：ag23-measurement.md（見本の本文は入らない。見本の番号、誤りの種類、判定だけ）、ledger/{yyyy-mm}.jsonl
* AIの利用額は、AG-23 の予算（config/budgets.yaml）の中で行う。結果は、運営者が AG-22 の記録に加える

終了コード: 0 測った / 3 休止中か予算の上限で、測れなかった見本がある / 2 使い方の誤り / 1 それ以外の失敗
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for sub in ("draft", "llm", "textcheck", "bundle", "validate", "edinet"):
    sys.path.insert(0, str(REPO_ROOT / "scripts" / sub))
sys.path.insert(0, str(REPO_ROOT / "tests" / "explainer"))

import ag23_check  # noqa: E402
import agent_call  # noqa: E402
import draft_company as dc  # noqa: E402

JST = dc.JST


def parse_args(argv):
    parser = argparse.ArgumentParser(description="AG-23 の効果を、見本で測る（実際のAPIを使う。運営者が行う）")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--ledger-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--summary", type=Path, metavar="FILE")
    parser.add_argument("--repeat", type=int, default=1, metavar="N")
    return parser.parse_args(argv)


def evaluate(sample: dict, claims: list[dict]) -> list[dict]:
    """誤りのある見本：注入した誤りごとに、結び付いた判定を返す。誤りのない見本：矛盾と判定された主張を返す。"""
    if not sample["errors"]:
        return [{"verdict": c["verdict"], "type": None} for c in claims if c["verdict"] == "conflicting"]
    found = []
    for error in sample["errors"]:
        best = max(claims, key=lambda c: ag23_check.similarity(error["claim"], c["claim"]), default=None)
        matched = best is not None and ag23_check.similarity(error["claim"], best["claim"]) >= ag23_check.MATCH_THRESHOLD
        found.append({"verdict": best["verdict"] if matched else "undetected", "type": error["type"]})
    return found


def measure(sample_set: list[dict], repeat: int, caller_factory, supply: dict) -> dict:
    results, skipped = [], []
    for sample in sample_set:
        for n in range(repeat):
            caller = caller_factory(sample)
            check, _ = ag23_check.run_check(caller, "term", "sample", sample["name"], sample["body"], {"processes": []}, supply)
            if check.skipped:
                skipped.append((sample["id"], check.skipped_reason))
                continue
            results.append({"id": sample["id"], "run": n + 1, "erroneous": bool(sample["errors"]), "found": evaluate(sample, check.claims)})
    errors = [f for r in results if r["erroneous"] for f in r["found"]]
    correct = [r for r in results if not r["erroneous"]]
    rate = lambda a, b: (a / b if b else None)
    return {"results": results, "skipped": skipped,
            "detect_conflict": rate(sum(f["verdict"] == "conflicting" for f in errors), len(errors)),
            "detect_flag": rate(sum(f["verdict"] in ("conflicting", "not_in_reference") for f in errors), len(errors)),
            "false_positive": rate(sum(bool(r["found"]) for r in correct), len(correct)), "n_errors": len(errors), "n_correct": len(correct)}


def percent(value) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def report(m: dict, cost_jpy: float, run_id: str) -> str:
    lines = [f"## AG-23 の効果の測定（実行 {run_id}）", "",
             f"* 誤りの検出率（「矛盾」と判定）：{percent(m['detect_conflict'])}（誤り {m['n_errors']}件）",
             f"* 誤りの検出率（「矛盾」か「要点にない」と判定）：{percent(m['detect_flag'])}",
             f"* 誤検知の割合（誤りのない解説で、「矛盾」と判定）：{percent(m['false_positive'])}（解説 {m['n_correct']}件）",
             f"* AIの利用額：{cost_jpy:.2f}円", "",
             "AIによる確認は、誤りを減らす手段であり、正確性を保証するものではない。この結果は、見本（9件）での値であり、実際の解説での精度ではない。", "",
             "| 見本 | 回 | 誤りの種類 | 判定 |", "| :--- | ---: | :--- | :--- |"]
    for r in m["results"]:
        if r["erroneous"]:
            lines += [f"| {r['id']} | {r['run']} | {f['type']} | {ag23_check.VERDICT_LABEL.get(f['verdict'], '検出されず')} |" for f in r["found"]]
        else:
            lines.append(f"| {r['id']} | {r['run']} | （誤りなし） | {'矛盾と判定（誤検知）' if r['found'] else '矛盾なし'} |")
    if m["skipped"]:
        lines += ["", "測れなかった見本："] + [f"* {i}：{why}" for i, why in m["skipped"]]
    return "\n".join(lines) + "\n"


def main(argv=None, *, now=lambda: datetime.now(JST), client_factory=None, sleep=None, budgets_path=agent_call.BUDGETS_PATH,
         operations_path=agent_call.OPERATIONS_PATH, agents_dir=agent_call.AGENTS_DIR, samples=None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.repeat < 1:
        print("error: --repeat は1以上", file=sys.stderr)
        return 2
    try:
        if samples is None:
            import ag23_samples
            samples = ag23_samples.SAMPLES
        supply = dc.load_yaml(REPO_ROOT / "data" / "supply-chain.yaml", "data/supply-chain.yaml") or {}
        rows: list[dict] = []
        get_client = dc.shared_client_factory(client_factory or (lambda: agent_call.anthropic.Anthropic()))

        def write_rows():
            dc.write_ledger(args.out_dir, rows)

        def caller_for(sample):
            return ag23_check.Caller(rows, write_rows, dict(run_id=args.run_id, subject=f"measure-{sample['id']}", ledger_dir=args.ledger_dir,
                                                            now=now, sleep=sleep or time.sleep, client_factory=get_client,
                                                            budgets_path=budgets_path, operations_path=operations_path, agents_dir=agents_dir))
        m = measure(samples, args.repeat, caller_for, supply)
        cost = round(sum(r["cost_jpy"] for r in rows), 4)
        text = report(m, cost, args.run_id)
        dc.write_text(args.out_dir / "ag23-measurement.md", text)
        print(text)
        if args.summary is not None:
            dc.write_summary(args.summary, text.splitlines())
        return dc.EXIT_SKIPPED if m["skipped"] else 0
    except agent_call.LlmError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except Exception as error:  # noqa: BLE001 - 想定外の例外は、種類だけ示す
        print(f"error: 想定外のエラー（{type(error).__name__}）", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

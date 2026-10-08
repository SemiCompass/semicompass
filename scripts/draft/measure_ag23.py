"""AG-23（知識にもとづく確認）の効果を、実際のAPIで測る。運営者が、別に行う（要求定義書 AG-23 の (a)、10章の未決事項12）。

使い方:
    python3 scripts/draft/measure_ag23.py --out-dir DIR --ledger-dir DIR --run-id ID [--summary FILE] [--repeat N] [--groups G,G]

* tests/explainer/ag23_samples.py の見本の本文を、AG-23 に確認させる。見本は4つの群に分かれる：
  obvious（明らかな誤り、6件）、subtle（細部の誤り、8件）、clean（誤りなし、3件）、detailed（正しいが詳しい、5件）。
  --groups で、測る群を選ぶ（カンマ区切り。既定は4群すべて。選んだ群だけを AG-23 に呼ぶ。費用を抑えるため）
  （1回目の reference は、見本の名前だけから。2回目の judge は、見本の本文と要点から）。下書きを作る AG-14 は呼ばない
* 測るもの（群ごと）：誤りの群（obvious、subtle）は、誤りの主張が「矛盾」と判定された割合と、「矛盾」か「要点にない」と判定された割合。
  誤りのない群（clean、detailed）は、「矛盾」と判定された解説の割合（誤検知）と、「要点にない」が1件以上出た解説の割合。
  --repeat で、同じ見本を繰り返して測る（既定は1回）
* 誤りの主張と、判定の主張は、文字の類似度（ag23_check.similarity）で結び付ける。結び付かなかった誤りは、検出されなかったものとして数える
* --out-dir に書くもの：ag23-measurement.md（見本の本文は入らない。見本の番号、誤りの種類、判定だけ）、ledger/{yyyy-mm}.jsonl
* AIの利用額は、AG-23 の予算（config/budgets.yaml）の中で行う。結果は、運営者が AG-22 の記録に加える

終了コード: 0 測った / 3 休止中か予算の上限で、測れなかった見本がある / 2 使い方の誤り（群の名前の誤りなど）/ 1 それ以外の失敗
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
GROUP_ORDER = ("obvious", "subtle", "clean", "detailed")
GROUP_LABELS = {"obvious": "明らかな誤り", "subtle": "細部の誤り", "clean": "誤りなし", "detailed": "正しいが詳しい"}
ERROR_GROUPS = ("obvious", "subtle")


def parse_args(argv):
    parser = argparse.ArgumentParser(description="AG-23 の効果を、見本で測る（実際のAPIを使う。運営者が行う）")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--ledger-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--summary", type=Path, metavar="FILE")
    parser.add_argument("--repeat", type=int, default=1, metavar="N")
    parser.add_argument("--groups", default=",".join(GROUP_ORDER), metavar="G,G",
                        help="測る群（カンマ区切り）：" + "、".join(GROUP_ORDER) + "。既定は、すべて")
    return parser.parse_args(argv)


def group_of(sample: dict) -> str:
    return sample.get("group") or ("obvious" if sample["errors"] else "clean")


def parse_groups(text: str) -> list[str]:
    """--groups の値。重複と空は除く。群の名前が違うときは ValueError。"""
    names = list(dict.fromkeys(g.strip() for g in text.split(",") if g.strip()))
    bad = [g for g in names if g not in GROUP_LABELS]
    if not names or bad:
        raise ValueError("--groups は、" + "、".join(GROUP_ORDER) + " から選ぶ（カンマ区切り）")
    return names


def evaluate(sample: dict, claims: list[dict]) -> list[dict]:
    """誤りのある見本：注入した誤りごとに、結び付いた判定を返す。誤りのない見本：矛盾と判定された主張を返す。"""
    if not sample["errors"]:  # 誤りのない解説：「矛盾」と「要点にない」と判定された主張
        return [{"verdict": c["verdict"], "type": None} for c in claims if c["verdict"] in ("conflicting", "not_in_reference")]
    found = []
    for error in sample["errors"]:
        best = max(claims, key=lambda c: ag23_check.similarity(error["claim"], c["claim"]), default=None)
        matched = best is not None and ag23_check.similarity(error["claim"], best["claim"]) >= ag23_check.MATCH_THRESHOLD
        found.append({"verdict": best["verdict"] if matched else "undetected", "type": error["type"]})
    return found


def measure(sample_set: list[dict], repeat: int, caller_factory, supply: dict, groups: list[str] | None = None) -> dict:
    """sample_set のうち、groups の群の見本だけを、AG-23 に呼ぶ（groups が None なら、すべて）。"""
    chosen = set(groups) if groups is not None else set(GROUP_ORDER)
    results, skipped = [], []
    for sample in sample_set:
        if group_of(sample) not in chosen:
            continue
        for n in range(repeat):
            caller = caller_factory(sample)
            check, _ = ag23_check.run_check(caller, "term", "sample", sample["name"], sample["body"], {"processes": []}, supply)
            if check.skipped:
                skipped.append((sample["id"], check.skipped_reason))
                continue
            results.append({"id": sample["id"], "run": n + 1, "group": group_of(sample), "erroneous": bool(sample["errors"]),
                            "found": evaluate(sample, check.claims)})
    rate = lambda a, b: (a / b if b else None)
    by_group = {}
    for g in GROUP_ORDER:
        rows = [r for r in results if r["group"] == g]
        if g in ERROR_GROUPS:
            errors = [f for r in rows for f in r["found"]]
            by_group[g] = {"n_samples": len(rows), "n": len(errors),
                           "detect_conflict": rate(sum(f["verdict"] == "conflicting" for f in errors), len(errors)),
                           "detect_flag": rate(sum(f["verdict"] in ("conflicting", "not_in_reference") for f in errors), len(errors))}
        else:
            by_group[g] = {"n_samples": len(rows), "n": len(rows),
                           "false_positive": rate(sum(any(f["verdict"] == "conflicting" for f in r["found"]) for r in rows), len(rows)),
                           "not_in_reference": rate(sum(any(f["verdict"] == "not_in_reference" for f in r["found"]) for r in rows), len(rows))}
    errors = [f for r in results if r["erroneous"] for f in r["found"]]
    correct = [r for r in results if not r["erroneous"]]
    return {"results": results, "skipped": skipped, "by_group": by_group, "chosen": [g for g in GROUP_ORDER if g in chosen],
            "detect_conflict": rate(sum(f["verdict"] == "conflicting" for f in errors), len(errors)),
            "detect_flag": rate(sum(f["verdict"] in ("conflicting", "not_in_reference") for f in errors), len(errors)),
            "false_positive": rate(sum(any(f["verdict"] == "conflicting" for f in r["found"]) for r in correct), len(correct)),
            "n_errors": len(errors), "n_correct": len(correct)}


def _error_verdict(verdict: str) -> str:
    """誤りのある見本の判定の表示。検出された（矛盾、要点にない）か、検出されなかったか（一致と判定、または結び付く主張がない）。"""
    if verdict in ("conflicting", "not_in_reference"):
        return ag23_check.VERDICT_LABEL[verdict]
    return "検出されず（一致と判定）" if verdict == "consistent" else "検出されず"


def percent(value) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def report(m: dict, cost_jpy: float, run_id: str) -> str:
    chosen = m.get("chosen") or list(GROUP_ORDER)
    lines = [f"## AG-23 の効果の測定（実行 {run_id}）", "", "測った群：" + "、".join(GROUP_LABELS[g] for g in chosen), ""]
    err_groups = [g for g in chosen if g in ERROR_GROUPS]
    ok_groups = [g for g in chosen if g not in ERROR_GROUPS]
    if err_groups:
        lines += ["| 群（誤りの群） | 見本の数 | 誤りの数 | 「矛盾」の検出率 | 「矛盾」か「要点にない」の検出率 |", "| :--- | ---: | ---: | ---: | ---: |"]
        lines += [f"| {GROUP_LABELS[g]} | {m['by_group'][g]['n_samples']} | {m['by_group'][g]['n']} | {percent(m['by_group'][g]['detect_conflict'])} | "
                  f"{percent(m['by_group'][g]['detect_flag'])} |" for g in err_groups] + [""]
    if ok_groups:
        lines += ["| 群（誤りのない群） | 解説の数 | 「矛盾」と判定された解説（誤検知） | 「要点にない」が1件以上出た解説 |", "| :--- | ---: | ---: | ---: |"]
        lines += [f"| {GROUP_LABELS[g]} | {m['by_group'][g]['n']} | {percent(m['by_group'][g]['false_positive'])} | "
                  f"{percent(m['by_group'][g]['not_in_reference'])} |" for g in ok_groups] + [""]
    lines += ["全体（参考。群の件数が違うため、群ごとの値を見る）：",
              f"* 誤りの検出率（「矛盾」と判定）：{percent(m['detect_conflict'])}（誤り {m['n_errors']}件）",
              f"* 誤りの検出率（「矛盾」か「要点にない」と判定）：{percent(m['detect_flag'])}",
              f"* 誤検知の割合（誤りのない解説で、「矛盾」と判定）：{percent(m['false_positive'])}（解説 {m['n_correct']}件）",
              f"* AIの利用額：{cost_jpy:.2f}円", "",
              f"AIによる確認は、誤りを減らす手段であり、正確性を保証するものではない。この結果は、見本（{len({r['id'] for r in m['results']})}件）での値であり、"
              "実際の解説での精度ではない。", "",
              "| 見本 | 回 | 誤りの種類 | 判定 |", "| :--- | ---: | :--- | :--- |"]
    for r in m["results"]:
        if r["erroneous"]:
            lines += [f"| {r['id']} | {r['run']} | {f['type']} | {_error_verdict(f['verdict'])} |" for f in r["found"]]
        else:
            conflicts = sum(f["verdict"] == "conflicting" for f in r["found"])
            extra = sum(f["verdict"] == "not_in_reference" for f in r["found"])
            verdict = "矛盾と判定（誤検知）" if conflicts else (f"要点にない {extra}件" if extra else "矛盾なし")
            lines.append(f"| {r['id']} | {r['run']} | （誤りなし） | {verdict} |")
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
        groups = parse_groups(args.groups)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    try:
        if samples is None:
            import ag23_samples
            samples = ag23_samples.ALL
        supply = dc.load_yaml(REPO_ROOT / "data" / "supply-chain.yaml", "data/supply-chain.yaml") or {}
        rows: list[dict] = []
        get_client = dc.shared_client_factory(client_factory or (lambda: agent_call.anthropic.Anthropic()))

        def write_rows():
            dc.write_ledger(args.out_dir, rows)

        def caller_for(sample):
            return ag23_check.Caller(rows, write_rows, dict(run_id=args.run_id, subject=f"measure-{sample['id']}", ledger_dir=args.ledger_dir,
                                                            now=now, sleep=sleep or time.sleep, client_factory=get_client,
                                                            budgets_path=budgets_path, operations_path=operations_path, agents_dir=agents_dir))
        m = measure(samples, args.repeat, caller_for, supply, groups)
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

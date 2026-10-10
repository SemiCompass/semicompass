"""運営者の記録 `/factcheck-ack`（P14、アーキテクチャ設計書 9.1、9.3、データ定義書 9.7、10.4）。

使い方（ops-command のワークフローから）:
    python3 scripts/ops/factcheck_ack.py --repo-dir OPS_LOG_DIR --pr 230 --user hysd --comment-file comment.txt --result-file factcheck_comment.md

コメントの書式：`/factcheck-ack {指紋または番号} {判断} {原因}`
* 指紋：事実確認の結果の表の「記録用の指紋」（10桁）。同じ指紋の主張（別のファイルの同じ文）に、まとめて効く
* 番号：結果の表の番号（C001など）。複数のファイルで同じ番号があるときは、指紋を使うよう返す
* 判断：「修正済み」「誤検知」「原資料を自分で確認済み」（fixed、false_positive、operator_verified でもよい）
* 原因：運用ルール書 10.4 の言葉。1〜200字
* 「確認不能」の主張に「誤検知」は認めない（データ定義書 9.7）
* 記録は、ops-log ブランチの作業用のコピー（--repo-dir）に書く。ops/factcheck/pr-{番号}.json（事実確認が読む）と
  ops/factcheck/{yyyy-mm}.jsonl（月次の集計が読む）。push は、ワークフローが行う
* 運営者かどうかの確認は、ワークフロー側（collaborators の権限）で行う。ここでは行わない
終了コード：0 記録した / 1 受け付けない（書式、指紋、判断の誤り）/ 2 入力・実行の誤り
結果の文は、標準出力に出す（変更案へのコメントに使う）。原資料の本文は扱わない。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DECISIONS = {
    "修正済み": "fixed", "fixed": "fixed",
    "誤検知": "false_positive", "false_positive": "false_positive",
    "原資料を自分で確認済み": "operator_verified", "operator_verified": "operator_verified",
}
FINGERPRINT = re.compile(r"^[0-9a-f]{10}$")
NUMBER = re.compile(r"^C\d{3}$", re.I)
CAUSE_MAX = 200
USAGE = "書式：`/factcheck-ack {指紋または番号} {判断} {原因}`。判断は「修正済み」「誤検知」「原資料を自分で確認済み」のいずれか"
ROW = re.compile(r"^\|\s*(C\d{3})\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*[^|]*\|\s*`([0-9a-f]{10})`\s*\|\s*$")
FILE_HEAD = re.compile(r"^### `([^`]+)`")


class AckError(Exception):
    pass


def parse_comment(text: str) -> tuple[str, str, str]:
    """(指紋または番号, 判断, 原因)。書式の誤りは AckError。"""
    first = text.strip().splitlines()[0] if text.strip() else ""
    parts = first.split(None, 3)
    if not parts or parts[0] != "/factcheck-ack":
        raise AckError(USAGE)
    if len(parts) < 4:
        raise AckError(f"引数が足りない。{USAGE}")
    target, word, cause = parts[1], parts[2], parts[3].strip()
    if word not in DECISIONS:
        raise AckError(f"判断が正しくない（{word}）。{USAGE}")
    if not cause or len(cause) > CAUSE_MAX:
        raise AckError(f"原因は1〜{CAUSE_MAX}字で書く")
    return target, DECISIONS[word], cause


def parse_result_table(comment: str) -> list[dict]:
    """事実確認のコメントの表から、(ファイル、番号、結果、指紋) を読む。"""
    rows, current = [], ""
    for line in comment.splitlines():
        m = FILE_HEAD.match(line)
        if m:
            current = m[1]
            continue
        m = ROW.match(line)
        if m:
            result = re.sub(r"（記録あり）$", "", m[4])
            rows.append({"file": current, "no": m[1].upper(), "kind": m[2], "text": m[3], "result": result, "fingerprint": m[5]})
    return rows


def resolve(target: str, rows: list[dict]) -> dict:
    """指紋または番号から、対象の主張（結果の表の行）を決める。"""
    if FINGERPRINT.match(target):
        hits = [r for r in rows if r["fingerprint"] == target]
        if not hits:
            raise AckError(f"指紋 `{target}` が、最新の事実確認の結果にない。結果の表を確かめる")
        return hits[0]
    if NUMBER.match(target):
        hits = [r for r in rows if r["no"] == target.upper()]
        if not hits:
            raise AckError(f"番号 {target.upper()} が、最新の事実確認の結果にない")
        if len({r["fingerprint"] for r in hits}) > 1:
            raise AckError(f"番号 {target.upper()} は複数のファイルにある。指紋で指定する（{', '.join('`' + r['fingerprint'] + '`' for r in hits)}）")
        return hits[0]
    raise AckError(f"指紋（10桁）か番号（C001）で指定する。{USAGE}")


def check_rules(row: dict, decision: str) -> None:
    if row["result"] == "確認不能" and decision == "false_positive":
        raise AckError("「確認不能」の主張に「誤検知」は認めない（運用ルール書10.4）。「原資料を自分で確認済み」か「修正済み」を使う")
    if row["result"] == "根拠あり":
        raise AckError("根拠ありの主張には、記録は要らない")


def record(repo_dir: Path, pr: int, row: dict, decision: str, cause: str, user: str, now: datetime) -> dict:
    """ops-log の作業用のコピーに書く。同じ指紋の記録は、上書きする。"""
    directory = repo_dir / "ops" / "factcheck"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"pr-{pr}.json"
    data = {"acks": []}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("acks"), list):
                data = loaded
        except ValueError:
            pass
    at = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = {"fingerprint": row["fingerprint"], "no": row["no"], "decision": decision, "cause": cause, "by": user, "at": at}
    data["acks"] = [a for a in data["acks"] if not (isinstance(a, dict) and a.get("fingerprint") == row["fingerprint"])] + [entry]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log = directory / f"{now.astimezone(timezone.utc):%Y-%m}.jsonl"
    line = {"kind": "ack", "at": at, "pr": pr, "no": int(row["no"][1:]), "decision": decision, "cause": cause, "by": user}
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return entry


def run(repo_dir: Path, pr: int, user: str, comment: str, result_comment: str, now: datetime | None = None) -> str:
    target, decision, cause = parse_comment(comment)
    row = resolve(target, parse_result_table(result_comment))
    check_rules(row, decision)
    record(repo_dir, pr, row, decision, cause, user, now or datetime.now(timezone.utc))
    label = {"fixed": "修正済み", "false_positive": "誤検知", "operator_verified": "原資料を自分で確認済み"}[decision]
    return f"記録した：`{row['fingerprint']}`（{row['file']}、{row['no']}）を「{label}」として、{user} が記録。事実確認をやり直す。"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--repo-dir", type=Path, required=True)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--comment-file", type=Path, required=True)
    parser.add_argument("--result-file", type=Path, required=True)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9-]{1,39}", args.user):
        print("アカウント名の形が正しくない")
        return 2
    try:
        comment = args.comment_file.read_text(encoding="utf-8")
        result = args.result_file.read_text(encoding="utf-8")
    except OSError:
        print("入力のファイルを読めない")
        return 2
    try:
        print(run(args.repo_dir, args.pr, args.user, comment, result))
    except AckError as error:
        print(f"受け付けない：{error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

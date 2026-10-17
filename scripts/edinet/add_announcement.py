"""決算発表の行を、data/auto/{slug}.json の announcements に加える（J04 の手動の版。データ定義書 5.6）。

IR重要ポイントの下書き（scripts/draft/draft_ir.py）が書いた announcement.json を、変更案を作る前に反映する。
決算発表の自動の検知（J04）ができるまでは、運営者がワークフローに決算短信のURLと発表日を入れたときに、この処理が書く。

使い方:
    python3 scripts/edinet/add_announcement.py --company advantest --file out/announcement.json

* 同じ決算期・四半期の行があれば、置き換える（発表日の訂正など）。行は発表日の古い順に並べる
* 行の形は schemas/data/auto-company.schema.json の announcement で確かめる。合わなければ、書かない
* updated_at は変えない（J01 の取り込みの日時のため）

終了コード: 0 成功 / 1 失敗 / 2 引数の誤り
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schemas" / "data" / "auto-company.schema.json"


def announcement_validator(schema_path: Path = SCHEMA_PATH) -> Draft202012Validator:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/announcement"})


def merge(data: dict, row: dict) -> tuple[dict, str]:
    """(新しい内容, "added" か "replaced") を返す。"""
    rows = [r for r in data.get("announcements") or []]
    key = (row["fiscal_period_end"], row["quarter"])
    kept = [r for r in rows if (r.get("fiscal_period_end"), r.get("quarter")) != key]
    action = "replaced" if len(kept) < len(rows) else "added"
    kept.append(row)
    kept.sort(key=lambda r: (r["announced_on"], r["fiscal_period_end"], r["quarter"]))
    return {**data, "announcements": kept}, action


def main(argv: list[str] | None = None, root: Path = REPO_ROOT) -> int:
    parser = argparse.ArgumentParser(description="決算発表の行を data/auto/{slug}.json に加える")
    parser.add_argument("--company", required=True, metavar="SLUG")
    parser.add_argument("--file", required=True, type=Path)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    path = root / "data" / "auto" / f"{args.company}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        row = json.loads(args.file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(f"error: data/auto/{args.company}.json か、決算発表の行のファイルを読めなかった", file=sys.stderr)
        return 2
    if data.get("company") != args.company:
        print("error: data/auto のファイルの company が、指定と違う", file=sys.stderr)
        return 2
    problems = list(announcement_validator().iter_errors(row))
    if problems:
        where = "、".join(sorted({"/".join(str(p) for p in e.absolute_path) or "(全体)" for e in problems}))[:200]
        print(f"error: 決算発表の行の形が正しくない（{where}）。書かない", file=sys.stderr)
        return 1
    merged, action = merge(data, row)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{'加えた' if action == 'added' else '置き換えた'}: {args.company} {row['fiscal_period_end']} q{row['quarter']}（発表日 {row['announced_on']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

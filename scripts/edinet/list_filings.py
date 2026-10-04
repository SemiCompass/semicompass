"""EDINETの書類一覧から、指定した企業の有価証券報告書・半期報告書（訂正を含む）を探す調査用のスクリプト。

J01（開示データの取り込み）の最初の段階。書類の一覧を調べて表示するだけで、
書類の本体（XBRL）は取得せず、`data/auto/` には書き込まない。

使い方（キーは環境変数 EDINET_API_KEY だけ。コマンドの引数では受け取らない）:
    EDINET_API_KEY=<キー> python3 scripts/edinet/list_filings.py \\
        --company advantest [--company disco ...] [--from YYYY-MM-DD --to YYYY-MM-DD] \\
        [--include-weekends] [--max-requests 400] [--out 結果.json]

* 企業は、data/companies/{slug}.yaml の edinet_code で探す
* 日付は、1日につきAPIを1回呼ぶ。--from と --to を省略すると、日本時間の前日だけ
* 土日は提出がないため、既定でとばす（--include-weekends で含める。祝日はとばさない）
* 対象は、docTypeCode が config/xbrl-map.yaml の doc_types にある書類。
  取り下げ（withdrawalStatus が 0 以外）の書類は、表に出さず、件数だけ数える
* --out を指定すると、結果をJSONで書く。API の項目名のまま（docID、docTypeCode、periodStart、
  periodEnd、submitDateTime など）の行に、企業の slug を加える。fiscal_period_end への変換はしない

キーは、標準出力、エラー文、例外、ファイルに出さない（リポジトリは公開）。

終了コード: 0 成功 / 1 接続・応答の失敗 / 2 設定・引数の誤り
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import client  # noqa: E402
from client import (  # noqa: E402
    ENV_KEY,
    EXIT_FAILURE,
    EXIT_OK,
    EXIT_USAGE,
    EdinetError,
    default_date,
    redact,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPANIES_DIR = REPO_ROOT / "data" / "companies"
XBRL_MAP_PATH = REPO_ROOT / "config" / "xbrl-map.yaml"
FORBIDDEN_OUT_DIR = REPO_ROOT / "data" / "auto"  # 取り込みの処理（J01）だけが書く場所（CLAUDE.md）
DEFAULT_MAX_REQUESTS = 400
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
EDINET_CODE_PATTERN = re.compile(r"^E[0-9]{5}$")
DOC_TYPE_LABELS = {
    "annual_report": "有価証券報告書",
    "amended_annual_report": "訂正有価証券報告書",
    "semiannual_report": "半期報告書",
    "amended_semiannual_report": "訂正半期報告書",
}
# JSONの行に持たせる、APIの項目名（書類一覧APIの results の項目）
FILING_FIELDS = (
    "docID",
    "edinetCode",
    "docTypeCode",
    "periodStart",
    "periodEnd",
    "submitDateTime",
    "docDescription",
    "withdrawalStatus",
    "docInfoEditStatus",
)


class UsageError(EdinetError):
    """設定・引数の誤り（終了コード2）。"""

    def __init__(self, message: str):
        super().__init__(message, EXIT_USAGE)


def load_companies(slugs: list[str], companies_dir: Path) -> dict[str, str]:
    """slug から企業マスタを読み、{edinet_code: slug} を返す。企業マスタにない slug はエラー。"""
    code_to_slug: dict[str, str] = {}
    for slug in dict.fromkeys(slugs):  # 重複を除き、順番を保つ
        if not SLUG_PATTERN.match(slug):
            raise UsageError(f"slug の形が正しくない: {slug}")
        path = companies_dir / f"{slug}.yaml"
        if not path.is_file():
            raise UsageError(f"企業マスタにない slug: {slug}")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        code = data.get("edinet_code")
        if not isinstance(code, str) or not EDINET_CODE_PATTERN.match(code):
            raise UsageError(f"企業マスタに edinet_code がない: {slug}（外資系日本法人などは、EDINETで探せない）")
        if code in code_to_slug:
            raise UsageError(f"同じ edinet_code の slug が重複している: {code_to_slug[code]}、{slug}")
        code_to_slug[code] = slug
    return code_to_slug


def load_doc_types(config_path: Path) -> dict[str, str]:
    """config/xbrl-map.yaml の doc_types（書類の種類のコード → doc_type）を返す。"""
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except OSError:
        raise UsageError(f"設定ファイルを読めない: {config_path.name}") from None
    doc_types = data.get("doc_types")
    if not isinstance(doc_types, dict) or not doc_types:
        raise UsageError(f"{config_path.name} に doc_types がない")
    return {str(code): str(kind) for code, kind in doc_types.items()}


def plan_dates(start: date, end: date, include_weekends: bool) -> list[date]:
    """start〜end（両端を含む）の、APIを呼ぶ日の一覧。土日は、既定でとばす。"""
    days = []
    current = start
    while current <= end:
        if include_weekends or current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def select_filings(
    results: list[dict], code_to_slug: dict[str, str], doc_types: dict[str, str]
) -> tuple[list[dict], int]:
    """1日分の results から、対象の企業・書類の種類の書類を選ぶ。

    返り値は、(書類の行の一覧、取り下げの件数)。取り下げ（withdrawalStatus が 0 以外）の書類は、
    行に含めず、件数だけ数える。
    """
    filings: list[dict] = []
    withdrawn = 0
    for row in results or []:
        if not isinstance(row, dict):
            continue
        slug = code_to_slug.get(row.get("edinetCode"))
        if slug is None or str(row.get("docTypeCode")) not in doc_types:
            continue
        if str(row.get("withdrawalStatus", "0")) != "0":
            withdrawn += 1
            continue
        filing = {"slug": slug}
        filing.update({field: row.get(field) for field in FILING_FIELDS})
        filings.append(filing)
    return filings, withdrawn


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def format_table(filings: list[dict], doc_types: dict[str, str]) -> str:
    """企業の slug、書類の種類、doc_id、対象期間、提出日時の表。"""
    header = ["slug", "書類の種類", "doc_id", "対象期間", "提出日時"]
    rows = []
    for f in filings:
        kind = doc_types.get(str(f["docTypeCode"]), "")
        label = DOC_TYPE_LABELS.get(kind, str(f["docTypeCode"]))
        period = f"{f['periodStart'] or '-'}〜{f['periodEnd'] or '-'}"
        rows.append([f["slug"], label, str(f["docID"]), period, str(f["submitDateTime"] or "-")])
    widths = [max(_width(r[i]) for r in [header, *rows]) for i in range(len(header))]
    lines = []
    for r in [header, *rows]:
        lines.append("  ".join(cell + " " * (widths[i] - _width(cell)) for i, cell in enumerate(r)).rstrip())
    return "\n".join(lines)


def _valid_date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"日付は YYYY-MM-DD の形で指定する: {text}") from None


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"1以上の整数を指定する: {text}") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"1以上の整数を指定する: {text}")
    return value


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="EDINETの書類一覧から、指定した企業の有価証券報告書・半期報告書（訂正を含む）を探す"
    )
    parser.add_argument("--company", action="append", required=True, metavar="SLUG",
                        help="企業の slug（data/companies/{slug}.yaml）。複数指定できる")
    parser.add_argument("--from", dest="from_date", type=_valid_date, metavar="YYYY-MM-DD",
                        help="日付の範囲の始め。--to と一緒に指定する。省略時は日本時間の前日だけ")
    parser.add_argument("--to", dest="to_date", type=_valid_date, metavar="YYYY-MM-DD",
                        help="日付の範囲の終わり（この日を含む）")
    parser.add_argument("--include-weekends", action="store_true", help="土日も調べる（既定はとばす）")
    parser.add_argument("--max-requests", type=_positive_int, default=DEFAULT_MAX_REQUESTS,
                        help=f"APIの呼び出しの上限（既定 {DEFAULT_MAX_REQUESTS}）。超えそうなら、実行前にエラーで終わる")
    parser.add_argument("--out", type=Path, metavar="FILE", help="結果をJSONで書くファイル。省略時は書かない")
    return parser.parse_args(argv)


def resolve_range(args: argparse.Namespace, now: datetime | None) -> tuple[date, date]:
    if (args.from_date is None) != (args.to_date is None):
        raise UsageError("--from と --to は、両方指定するか、両方省略する")
    if args.from_date is None:
        yesterday = default_date(now)
        return yesterday, yesterday
    if args.from_date > args.to_date:
        raise UsageError("--from は --to より前の日にする")
    today = (now or datetime.now(ZoneInfo("Asia/Tokyo"))).astimezone(ZoneInfo("Asia/Tokyo")).date()
    if args.to_date > today:
        raise UsageError(f"--to が未来の日付（日本時間の今日は {today.isoformat()}）")
    return args.from_date, args.to_date


def check_out_path(path: Path | None) -> None:
    """--out の場所を、実行前に確かめる。`data/auto/` には書かない（CLAUDE.md）。"""
    if path is None:
        return
    resolved = path.resolve()
    if resolved == FORBIDDEN_OUT_DIR or FORBIDDEN_OUT_DIR in resolved.parents:
        raise UsageError("--out に data/auto/ の下は指定できない（取り込みの処理だけが書く場所）")
    if not resolved.parent.is_dir():
        raise UsageError(f"--out のフォルダがない: {path.parent}")
    if resolved.is_dir():
        raise UsageError(f"--out がフォルダになっている: {path}")


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(
    args: argparse.Namespace,
    key: str,
    *,
    code_to_slug: dict[str, str],
    doc_types: dict[str, str],
    days: list[date],
    open_url,
    sleep,
    monotonic,
) -> tuple[list[dict], int, int]:
    """各日の書類一覧（type=2）を取得し、(書類の行、取り下げの件数、API呼び出しの回数) を返す。"""
    edinet = client.EdinetClient(
        key, open_url=open_url, sleep=sleep, monotonic=monotonic, max_requests=args.max_requests
    )
    filings: list[dict] = []
    withdrawn_total = 0
    for day in days:
        body = edinet.get_documents(day, 2)
        found, withdrawn = select_filings(body.get("results"), code_to_slug, doc_types)
        filings.extend(found)
        withdrawn_total += withdrawn
    filings.sort(key=lambda f: (str(f["submitDateTime"] or ""), f["slug"], str(f["docID"])))
    return filings, withdrawn_total, edinet.request_count


def main(
    argv: list[str] | None = None,
    *,
    open_url=client._open,
    sleep=time.sleep,
    monotonic=time.monotonic,
    now: datetime | None = None,
    companies_dir: Path = COMPANIES_DIR,
    config_path: Path = XBRL_MAP_PATH,
) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    key = ""
    try:
        code_to_slug = load_companies(args.company, companies_dir)
        doc_types = load_doc_types(config_path)
        start, end = resolve_range(args, now)
        days = plan_dates(start, end, args.include_weekends)
        if len(days) > args.max_requests:
            raise UsageError(
                f"APIの呼び出しが {len(days)} 回になり、--max-requests（{args.max_requests}）を超える。"
                "範囲を狭めるか、上限を上げる"
            )
        check_out_path(args.out)
        key = os.environ.get(ENV_KEY, "").strip()
        if not key:
            raise UsageError(f"環境変数 {ENV_KEY} が設定されていない")
        if not days:
            print(f"対象の日がない（{start.isoformat()}〜{end.isoformat()} は土日だけ。--include-weekends で含める）")
            return EXIT_OK
        filings, withdrawn, requests = run(
            args, key, code_to_slug=code_to_slug, doc_types=doc_types, days=days,
            open_url=open_url, sleep=sleep, monotonic=monotonic,
        )
    except EdinetError as error:
        print(f"error: {redact(str(error), key)}", file=sys.stderr)
        return error.exit_code
    except Exception as error:  # noqa: BLE001 - 想定外の例外も、キーを伏せて種類だけ示す
        print(f"error: 想定外のエラー（{type(error).__name__}: {redact(str(error), key)}）", file=sys.stderr)
        return EXIT_FAILURE

    print(f"企業: {', '.join(code_to_slug.values())}")
    print(f"期間: {start.isoformat()}〜{end.isoformat()}（調べた日 {len(days)}、API呼び出し {requests}回）")
    if filings:
        print(format_table(filings, doc_types))
    else:
        print("該当する書類はない")
    print(f"該当 {len(filings)}件 / 取り下げ（除外）{withdrawn}件")
    if args.out is not None:
        payload = {
            "generated_at": (now or datetime.now(ZoneInfo("Asia/Tokyo"))).astimezone(ZoneInfo("Asia/Tokyo"))
            .replace(microsecond=0).isoformat(),
            "parameters": {
                "companies": list(code_to_slug.values()),
                "from": start.isoformat(),
                "to": end.isoformat(),
                "include_weekends": args.include_weekends,
                "days_queried": len(days),
                "api_requests": requests,
            },
            "withdrawn_count": withdrawn,
            "filings": filings,
        }
        try:
            write_json(args.out, payload)
        except OSError as error:
            print(f"error: 結果を書けない（{type(error).__name__}）", file=sys.stderr)
            return EXIT_FAILURE
        print(f"結果を書いた: {args.out}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

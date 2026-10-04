"""1社分の data/auto/{slug}.json を、書類の一覧（list_filings.py の結果）と、書類の取り出しから組み立てる。

J01の段階3b。結果は --out-dir に書く。段階3cまでは、`data/auto/` の下は拒否する（段階3cで外す）。

使い方（キーは環境変数 EDINET_API_KEY だけ）:
    EDINET_API_KEY=<キー> python3 scripts/edinet/ingest_company.py --company advantest \\
        --filings-json 一覧.json [--existing data/auto/advantest.json] --out-dir 出力フォルダ [--max-requests 20]

* 一覧の中の、その企業の書類のうち、既存の filings にない doc_id だけを取得して取り込む
* 取り込めない書類（異常、取得の失敗）は、filings に failed で記録し、値は入れない
* 結果が data/auto のスキーマ（jsonschema と、formatの検査）に合格しないときは、書かずに終了コード1
* --retry-failed を付けると、既存の filings の failed の書類も再取得する（一覧にあるものだけ。成功したら failed の行を置き換える）
* 通信の一時的な失敗（429の再試行を使い切った、接続できない、タイムアウト）は、filings に記録せず、
  変更の一覧に not_recorded（transient）として出す。次の実行で再取得される。認証の失敗（401）は、全体を止める
* 取り込む書類がなく、変更もないときは、ファイルを書かない

終了コード: 0 成功 / 1 接続・応答の失敗、またはスキーマに不合格 / 2 設定・引数の誤り
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from jsonschema import Draft202012Validator, FormatChecker

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_auto  # noqa: E402
import client  # noqa: E402
import extract  # noqa: E402
from client import ENV_KEY, EXIT_FAILURE, EXIT_OK, EdinetError, redact  # noqa: E402
from csv_reader import document_rows  # noqa: E402
from extract_document import document_edinet_code  # noqa: E402
from list_filings import (  # noqa: E402
    COMPANIES_DIR,
    FORBIDDEN_OUT_DIR,
    XBRL_MAP_PATH,
    REPO_ROOT,
    UsageError,
    _positive_int,
    load_companies,
)

SCHEMA_PATH = REPO_ROOT / "schemas" / "data" / "auto-company.schema.json"
DEFAULT_MAX_REQUESTS = 20


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="1社分の data/auto/{slug}.json を組み立てる（段階3b）")
    parser.add_argument("--company", required=True, metavar="SLUG", help="企業の slug")
    parser.add_argument("--filings-json", required=True, type=Path, metavar="FILE",
                        help="list_filings.py の --out の結果")
    parser.add_argument("--existing", type=Path, metavar="FILE", help="既存の data/auto/{slug}.json。なければ省略")
    parser.add_argument("--out-dir", required=True, type=Path, metavar="DIR",
                        help="結果（{slug}.json）を書くフォルダ。data/auto/ の下は拒否する（段階3cで外す）")
    parser.add_argument("--retry-failed", action="store_true",
                        help="既存の filings で status が failed の書類も、一覧にあれば再取得する"
                             "（成功したら、failed の行を置き換える）")
    parser.add_argument("--max-requests", type=_positive_int, default=DEFAULT_MAX_REQUESTS,
                        help=f"書類の取得の上限（既定 {DEFAULT_MAX_REQUESTS}）。超えるなら、実行前にエラーで終わる")
    return parser.parse_args(argv)


def check_out_dir(path: Path) -> None:
    resolved = path.resolve()
    if resolved == FORBIDDEN_OUT_DIR or FORBIDDEN_OUT_DIR in resolved.parents:
        raise UsageError("--out-dir に data/auto/ の下は指定できない（段階3cまでは書かない）")
    if not resolved.is_dir():
        raise UsageError(f"--out-dir がフォルダでない、またはない: {path}")


def load_json(path: Path, what: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise UsageError(f"{what}を読めない: {path.name}") from None
    if not isinstance(data, dict):
        raise UsageError(f"{what}の形が正しくない: {path.name}")
    return data


def format_checker() -> FormatChecker:
    """formatの検査を有効にする。date-time は、環境によっては検査が入っていないため、ここで足す。"""
    checker = FormatChecker()
    if "date-time" not in checker.checkers:
        @checker.checks("date-time", raises=ValueError)
        def _date_time(value):  # noqa: ANN001
            return not isinstance(value, str) or bool(datetime.fromisoformat(value).tzinfo)
    return checker


def validate(data: dict) -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=format_checker())
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '(root)'}: {e.message}" for e in validator.iter_errors(data)]


def render_changes(slug: str, changes: list[dict], fetched: int) -> str:
    labels = {"added": "取り込み", "replaced": "値の置き換え", "superseded": "元の書類の状態", "failed": "失敗",
              "anomaly": "異常", "not_recorded": "記録できなかった書類"}
    lines = [f"企業 {slug}: 取得した書類 {fetched}件"]
    if not changes:
        lines.append("変更なし")
    for change in changes:
        lines.append(f"  [{labels.get(change['kind'], change['kind'])}] {change['doc_id']}: {change['message']}")
    return "\n".join(lines)


def main(
    argv: list[str] | None = None,
    *,
    open_url=client._open,
    sleep=time.sleep,
    monotonic=time.monotonic,
    now: datetime | None = None,
) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    key = ""
    try:
        check_out_dir(args.out_dir)
        edinet_code = next(iter(load_companies([args.company], COMPANIES_DIR)))
        listing = load_json(args.filings_json, "書類の一覧")
        rows = [r for r in listing.get("filings") or [] if isinstance(r, dict) and r.get("slug") == args.company]
        existing = load_json(args.existing, "既存のファイル") if args.existing else None
        xbrl_map = yaml.safe_load(XBRL_MAP_PATH.read_text(encoding="utf-8"))
        doc_types = {str(k): v for k, v in xbrl_map["doc_types"].items()}
        known = {f["doc_id"] for f in (existing or {}).get("filings", [])
                 if not (args.retry_failed and f["status"] == "failed")}
        usable, _ = build_auto.classify_rows(rows, edinet_code, doc_types)
        targets, seen = [], set(known)
        for row, _doc_type in usable:
            if row["docID"] not in seen:
                seen.add(row["docID"])
                targets.append(row)
        if len(targets) > args.max_requests:
            raise UsageError(f"取得する書類が {len(targets)}件になり、--max-requests（{args.max_requests}）を超える。"
                             "一覧の範囲を狭めるか、上限を上げる")
        moment = (now or datetime.now(ZoneInfo("Asia/Tokyo"))).astimezone(ZoneInfo("Asia/Tokyo"))
        documents = [{"filing": row, "result": None, "error": None} for row in rows
                     if row.get("docID") not in {t["docID"] for t in targets}]
        if targets:
            key = os.environ.get(ENV_KEY, "").strip()
            if not key:
                raise UsageError(f"環境変数 {ENV_KEY} が設定されていない")
            edinet = client.EdinetClient(key, open_url=open_url, sleep=sleep, monotonic=monotonic,
                                         max_requests=args.max_requests)
            ingested_at = build_auto.jst_text(moment)
            for row in targets:
                documents.append(fetch_one(edinet, row, ingested_at, xbrl_map, key, edinet_code))
        data, changes = build_auto.build(args.company, edinet_code, existing, documents, moment, doc_types,
                                         retry_failed=args.retry_failed)
    except UsageError as error:
        print(f"error: {redact(str(error), key)}", file=sys.stderr)
        return client.EXIT_USAGE
    except EdinetError as error:
        print(f"error: {redact(str(error), key)}", file=sys.stderr)
        return error.exit_code
    except Exception as error:  # noqa: BLE001 - 想定外の例外も、キーを伏せて種類だけ示す
        print(f"error: 想定外のエラー（{type(error).__name__}: {redact(str(error), key)}）", file=sys.stderr)
        return EXIT_FAILURE

    print(render_changes(args.company, changes, len(targets)))
    if existing is None and not data["filings"]:
        print("取り込む書類がなく、既存のファイルもないので、書かない")
        return EXIT_OK
    if data == existing:
        print("変更がないので、書かない")
        return EXIT_OK
    errors = validate(data)
    if errors:
        print("error: スキーマに合格しないので、書かない", file=sys.stderr)
        for message in errors[:20]:
            print(f"  {redact(message, key)}", file=sys.stderr)
        return EXIT_FAILURE
    out_path = args.out_dir / f"{args.company}.json"
    try:
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        print(f"error: 結果を書けない（{type(error).__name__}）", file=sys.stderr)
        return EXIT_FAILURE
    print(f"結果を書いた: {out_path}")
    return EXIT_OK


def fetch_one(edinet, row: dict, ingested_at: str, xbrl_map: dict, key: str, edinet_code: str) -> dict:
    """1書類を取得して取り出す。失敗は、失敗の種類（error）にする。認証の失敗は、全体を止める。"""
    doc = {"filing": row, "result": None, "error": None}
    try:
        raw = edinet.get_document(row["docID"])
    except EdinetError as error:
        if "認証に失敗" in str(error):
            raise
        # 通信の一時的な失敗は、filings に記録しない（次の実行で再取得される）
        doc["error"] = build_auto.TRANSIENT if getattr(error, "transient", False) else "fetch_failed"
        return doc
    try:
        rows = document_rows(raw)
    except ValueError:
        doc["error"] = "zip_format"
        return doc
    code = document_edinet_code(rows)
    if code is not None and code != edinet_code:  # 書類のDEIにEDINETコードがあり、企業と違うときだけ使わない
        doc["error"] = "edinet_code_mismatch"
        return doc
    try:
        doc["result"] = extract.extract(rows, row["docID"], ingested_at, xbrl_map)
    except ValueError:
        doc["error"] = "extract_failed"
    return doc


if __name__ == "__main__":
    sys.exit(main())

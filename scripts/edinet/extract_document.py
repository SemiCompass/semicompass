"""EDINETの書類（CSV形式）1件から、データ定義書5章の形（financials、employees）の値を取り出して表示する。

J01の段階3a。取り出して画面とJSONに出すだけで、`data/auto/` には書き込まない。

使い方（キーは環境変数 EDINET_API_KEY だけ）:
    EDINET_API_KEY=<キー> python3 scripts/edinet/extract_document.py --doc-id S100XXXX \\
        [--company advantest] [--out 結果.json]

* --company を付けると、data/companies/{slug}.yaml の edinet_code と、書類のDEI（EDINETコード）を照らし、
  違えばエラー（取り出さない）
* 画面には、項目ごとに、要素ID、コンテキストID、元の値、換算後の値の表を出す
* ZIPはメモリの中だけで展開する。--out は、data/auto/ の下を拒否する

終了コード: 0 成功（異常があっても、取り出せれば0。画面とJSONに異常を出す）/
1 接続・応答の失敗、またはDEIが読めず取り出しを止めた / 2 設定・引数の誤り
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import client  # noqa: E402
import extract  # noqa: E402
from client import DOC_ID_PATTERN, ENV_KEY, EXIT_FAILURE, EXIT_OK, EdinetError, redact  # noqa: E402
from csv_reader import DEI_EDINET_CODE, document_rows  # noqa: E402
from inspect_document import _printable, format_rows  # noqa: E402
from list_filings import (  # noqa: E402
    COMPANIES_DIR,
    XBRL_MAP_PATH,
    UsageError,
    check_out_path,
    load_companies,
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="EDINETの書類（CSV形式）1件から、financials・employeesの値を取り出す")
    parser.add_argument("--doc-id", required=True, metavar="DOC_ID", help="書類管理番号（S100XXXX）。1件だけ")
    parser.add_argument("--company", metavar="SLUG",
                        help="企業の slug。企業マスタの edinet_code と、書類のEDINETコードが違えばエラー")
    parser.add_argument("--out", type=Path, metavar="FILE",
                        help="結果をJSONで書くファイル（data/auto/ の下は拒否）。省略時は書かない")
    return parser.parse_args(argv)


def document_edinet_code(rows: list[dict]) -> str | None:
    key = next((k for k in rows[0] if k.strip().lower() in ("要素id", "elementid")), None) if rows else None
    value_key = next((k for k in rows[0] if k.strip() in ("値", "value")), None) if rows else None
    if key is None or value_key is None:
        return None
    values = {r[value_key].strip() for r in rows if r[key].strip() == DEI_EDINET_CODE}
    return values.pop() if len(values) == 1 else None


def render(result: dict, edinet_code: str | None) -> str:
    lines = [f"書類 {result['doc_id']}（EDINETコード {edinet_code or '不明'}）"]
    dei = result["dei"]
    if dei:
        lines.append(f"DEI: 会計基準 {dei['accounting_standard']}（{dei['accounting_standard_raw']}）/ "
                     f"連結 {dei['consolidated']} / 期間 {dei['period_type']}（{dei['period_type_raw']}）/ "
                     f"{dei['fiscal_year_start']}〜{dei['period_end']}（決算期末 {dei['fiscal_year_end']}）")
    if result["stopped"]:
        lines.append("DEIを読めないため、取り出しを止めた")
    if result["trace"]:
        headers = ["項目", "要素ID", "コンテキストID", "元の値", "元の単位", "換算後の値", "単位"]
        table = [[_printable(str(t["item"]), 60), t["element"], t["context"],
                  "" if t["original_value"] is None else t["original_value"], t["original_unit"] or "",
                  "(null)" if t["value"] is None else str(t["value"]), t["unit"]] for t in result["trace"]]
        lines += ["", format_rows(headers, table)]
    if result["financial"]:
        lines.append(f"\n売上高の項目名: {result['financial']['net_sales_label']}")
        lines.append(f"セグメント {len(result['financial']['segments'])}件")
    if result["employee"] is None and result["financial"] and result["financial"]["period_type"] == "half":
        lines.append("半期報告書のため、従業員の行は作らない")
    for note in result["notes"]:
        lines.append(f"メモ: {note}")
    if result["anomalies"]:
        lines.append(f"\n異常 {len(result['anomalies'])}件:")
        lines += [f"  [{a['code']}] {a['message']}" for a in result["anomalies"]]
    else:
        lines.append("\n異常なし")
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
        if not DOC_ID_PATTERN.match(args.doc_id):
            raise UsageError(f"doc_id の形が正しくない: {_printable(args.doc_id, 30)}（S100 と英数字4文字）")
        check_out_path(args.out)
        expected_code = None
        if args.company:
            expected_code = next(iter(load_companies([args.company], COMPANIES_DIR)))
        key = os.environ.get(ENV_KEY, "").strip()
        if not key:
            raise UsageError(f"環境変数 {ENV_KEY} が設定されていない")
        xbrl_map = yaml.safe_load(XBRL_MAP_PATH.read_text(encoding="utf-8"))
        edinet = client.EdinetClient(key, open_url=open_url, sleep=sleep, monotonic=monotonic, max_requests=1)
        raw = edinet.get_document(args.doc_id)
        try:
            rows = document_rows(raw)
        except ValueError as error:
            raise EdinetError(f"書類を読めなかった: {error}", EXIT_FAILURE) from None
        code = document_edinet_code(rows)
        if expected_code is not None and code != expected_code:
            raise UsageError(f"--company {args.company} の edinet_code（{expected_code}）と、書類のEDINETコード"
                             f"（{code or '読めない'}）が違う。取り出さない")
        moment = (now or datetime.now(ZoneInfo("Asia/Tokyo"))).astimezone(ZoneInfo("Asia/Tokyo"))
        ingested_at = moment.replace(microsecond=0).isoformat()
        try:
            result = extract.extract(rows, args.doc_id, ingested_at, xbrl_map)
        except ValueError as error:
            raise EdinetError(f"取り出せなかった: {error}", EXIT_FAILURE) from None
    except UsageError as error:
        print(f"error: {redact(str(error), key)}", file=sys.stderr)
        return client.EXIT_USAGE
    except EdinetError as error:
        print(f"error: {redact(str(error), key)}", file=sys.stderr)
        return error.exit_code
    except Exception as error:  # noqa: BLE001 - 想定外の例外も、キーを伏せて種類だけ示す
        print(f"error: 想定外のエラー（{type(error).__name__}: {redact(str(error), key)}）", file=sys.stderr)
        return EXIT_FAILURE

    print(render(result, code))
    if args.out is not None:
        payload = {"generated_at": ingested_at, "doc_id": args.doc_id, "edinet_code": code,
                   "financial": result["financial"], "employee": result["employee"],
                   "anomalies": result["anomalies"], "notes": result["notes"], "stopped": result["stopped"]}
        try:
            args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError as error:
            print(f"error: 結果を書けない（{type(error).__name__}）", file=sys.stderr)
            return EXIT_FAILURE
        print(f"結果を書いた: {args.out}")
    return EXIT_FAILURE if result["stopped"] else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

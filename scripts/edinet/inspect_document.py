"""EDINETの書類（CSV形式）を取得し、実際の要素の名前を調べる調査用のスクリプト。

J01（開示データの取り込み）の段階2。書類取得API（type=5、XBRLをCSVに変換したZIP）で書類を取得し、
数値の行を取り出して、概念ごとの候補の行（要素ID、項目名、コンテキストID、連結・個別、単位、値）を表示する。
config/xbrl-map.yaml の要素名を確かめるための調査で、`data/auto/` には書き込まない。

使い方（キーは環境変数 EDINET_API_KEY だけ。コマンドの引数では受け取らない）:
    EDINET_API_KEY=<キー> python3 scripts/edinet/inspect_document.py \\
        --doc-id S100XXXX [--doc-id S100YYYY ...] [--max-requests 10] [--out 結果.json]

* ZIPは、メモリの中だけで展開する（ディスクに書かない）。展開後の合計の大きさ（200MB）と、
  ファイルの数（500）に上限がある
* CSVの文字コードは、UTF-16、UTF-8（BOM付き）、CP932 の順に試して判定する。列名は、実際のヘッダー行を使う
* 数値の行（値が数値の行）だけを取り出す。文章の行と、要素IDが TextBlock で終わる行は除く
* 概念ごとに、要素IDと項目名の部分一致で探し、最大30行を出す（当期らしい行を先に出す）
* --out には、数値の行のすべてを、列名のままのJSONで書く（`data/auto/` の下は拒否する）

キーは、標準出力、エラー文、例外、ファイルに出さない（リポジトリは公開）。

終了コード: 0 成功 / 1 取得・解析の失敗（--out は、失敗した書類の記録を含めて書く） / 2 設定・引数の誤り
"""

from __future__ import annotations

import argparse
import codecs
import csv
import io
import json
import os
import re
import sys
import time
import zipfile
import zlib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

import client  # noqa: E402
from client import (  # noqa: E402
    DOC_ID_PATTERN,
    ENV_KEY,
    EXIT_FAILURE,
    EXIT_OK,
    EXIT_USAGE,
    EdinetError,
    redact,
)
from list_filings import UsageError, _positive_int, _width, check_out_path  # noqa: E402

DEFAULT_MAX_REQUESTS = 10
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024  # 展開後の合計の大きさの上限
MAX_ZIP_FILES = 500  # ZIPの中のファイルの数の上限
MAX_ROWS_PER_CONCEPT = 30
CSV_FIELD_LIMIT = 50 * 1024 * 1024  # TextBlock の行は、1つの値が大きい

# 列名（実際のヘッダー行の見出し）の候補。比較は、空白と大文字小文字を無視する
COLUMN_ALIASES = {
    "element": ("要素ID", "elementid"),
    "label": ("項目名",),
    "context": ("コンテキストID", "contextid"),
    "consolidated": ("連結・個別", "連結個別"),
    "unit": ("単位", "unit"),
    "value": ("値", "value"),
}
REQUIRED_COLUMNS = ("element", "value")
NUMBER_PATTERN = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)$")
ALLOWED_MEMBERS = {"ConsolidatedMember", "NonConsolidatedMember"}  # 連結・個別の区別だけの軸
REGION_HINTS = ("地域", "日本", "北米", "アジア", "欧州", "米国", "中国", "Geograph", "Region", "Japan",
                "NorthAmerica", "Asia", "Europe", "China", "UnitedStates", "Taiwan", "Korea")

# 概念：(キー, 表示名, 要素IDの部分一致, 項目名の部分一致, コンテキストの条件)
# コンテキストの条件: "total" 連結・個別の区別以外の軸（Member）を含まない / "member" Member を含む /
#                    "region" Member を含み、地域らしい語を含む / None 条件なし
CONCEPTS = (
    ("revenue", "売上高（売上収益を含む）", ("NetSales", "Revenue"), ("売上高", "売上収益"), "total"),
    ("operating_income", "営業利益", ("OperatingIncome", "OperatingProfit"), ("営業利益", "営業損益"), "total"),
    ("ordinary_income", "経常利益", ("OrdinaryIncome",), ("経常利益", "経常損益"), "total"),
    ("net_income", "親会社株主（所有者）に帰属する当期純利益",
     ("ProfitLossAttributableToOwnersOfParent", "NetIncomeLossAttributableToOwnersOfParent",
      "ProfitAttributableToOwnersOfParent"),
     ("親会社株主に帰属する", "親会社の所有者に帰属する"), "total"),
    ("segment_sales", "セグメントの外部顧客への売上", ("ExternalCustomers",), ("外部顧客",), "member"),
    ("region_sales", "地域別の売上", ("ExternalCustomers", "NetSales", "Revenue"), ("外部顧客", "売上"), "region"),
    ("employees", "従業員数", ("NumberOfEmployees",), ("従業員数",), None),
    ("average_age", "平均年齢", ("AverageAge",), ("平均年齢",), None),
    ("average_service", "平均勤続年数", ("AverageLengthOfService",), ("平均勤続年数",), None),
    ("average_salary", "平均年間給与", ("AverageAnnualSalary",), ("平均年間給与",), None),
)
DISPLAY_COLUMNS = (("element", "要素ID"), ("label", "項目名"), ("context", "コンテキストID"),
                   ("consolidated", "連結・個別"), ("unit", "単位"), ("value", "値"))


def _printable(text: str, limit: int = 200) -> str:
    """ZIPの中の名前など、外から来た文字列を、制御文字を除いて短くする。"""
    cleaned = "".join(ch if ch.isprintable() else "?" for ch in text)
    return cleaned if len(cleaned) <= limit else cleaned[:limit] + "…"


def _looks_like_table(text: str) -> bool:
    if not text.strip() or "\x00" in text:
        return False
    first = text.split("\n", 1)[0]
    return "\t" in first or "," in first


def decode_csv(raw: bytes) -> tuple[str, str]:
    """CSVのバイト列を、UTF-16、UTF-8（BOM付き）、CP932 の順に試して文字列にする。

    返り値は、(文字列, 文字コードの名前)。BOMのないUTF-16は、偶数の長さで、デコードした先頭行に
    区切り（タブか、カンマ）があるものだけを採る（UTF-8やCP932を、UTF-16と取り違えないため）。
    判定できないときは ValueError。
    """
    candidates: list[tuple[str, str]] = []
    if raw[:2] == codecs.BOM_UTF16_LE:
        candidates.append(("utf-16", "UTF-16LE（BOMあり）"))
    elif raw[:2] == codecs.BOM_UTF16_BE:
        candidates.append(("utf-16", "UTF-16BE（BOMあり）"))
    elif len(raw) % 2 == 0:
        candidates += [("utf-16-le", "UTF-16LE（BOMなし）"), ("utf-16-be", "UTF-16BE（BOMなし）")]
    candidates += [("utf-8-sig", "UTF-8（BOM付き、またはBOMなし）"), ("cp932", "CP932")]
    for codec, name in candidates:
        try:
            text = raw.decode(codec)
        except UnicodeDecodeError:
            continue
        if _looks_like_table(text):
            return text, name
    raise ValueError("文字コードを判定できない（UTF-16、UTF-8、CP932のどれでも読めない）")


def _normalize(name: str) -> str:
    return re.sub(r"\s+", "", name).lower()


def map_columns(header: list[str]) -> dict[str, int]:
    """ヘッダー行の見出しから、役割（要素ID、項目名など）の列の位置を決める。"""
    positions: dict[str, int] = {}
    normalized = [_normalize(h.lstrip("﻿")) for h in header]
    for role, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if _normalize(alias) in normalized:
                positions[role] = normalized.index(_normalize(alias))
                break
    return positions


def unique_headers(header: list[str]) -> list[str]:
    """同じ見出しが重なるときは、2つ目から番号を付ける（JSONのキーにするため）。"""
    seen: dict[str, int] = {}
    result = []
    for h in header:
        h = h.lstrip("﻿")
        seen[h] = seen.get(h, 0) + 1
        result.append(h if seen[h] == 1 else f"{h}_{seen[h]}")
    return result


def is_numeric(value: str) -> bool:
    return bool(NUMBER_PATTERN.match(value.strip().replace(",", "")))


def parse_csv(text: str) -> tuple[list[str], list[list[str]]]:
    """文字列をCSV（タブ区切りか、カンマ区切り）として読み、(ヘッダー行, データの行) を返す。"""
    first = text.split("\n", 1)[0]
    delimiter = "\t" if first.count("\t") >= first.count(",") else ","
    csv.field_size_limit(CSV_FIELD_LIMIT)
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
    rows = [r for r in rows if r]
    if not rows:
        raise ValueError("CSVが空")
    return rows[0], rows[1:]


def extract_numeric_rows(header: list[str], rows: list[list[str]]) -> tuple[list[dict], dict[str, int]]:
    """数値の行だけを、列名のままの辞書にして返す。文章の行と、TextBlock の行は除く。"""
    positions = map_columns(header)
    missing = [role for role in REQUIRED_COLUMNS if role not in positions]
    if missing:
        raise ValueError(
            "ヘッダー行に、要素ID・値の列が見つからない。実際の列名: "
            + ", ".join(_printable(h, 40) for h in header[:30])
        )
    names = unique_headers(header)
    numeric: list[dict] = []
    for row in rows:
        padded = row + [""] * (len(names) - len(row))
        element = padded[positions["element"]].strip()
        if element.endswith("TextBlock") or not is_numeric(padded[positions["value"]]):
            continue
        numeric.append({names[i]: padded[i] for i in range(len(names))})
    return numeric, positions


def _context_ok(context: str, rule: str | None) -> bool:
    has_member = "Member" in context
    if rule is None:
        return True
    if rule == "member":
        return has_member
    if rule == "region":
        return has_member and any(h.lower() in context.lower() for h in REGION_HINTS)
    # "total": 連結・個別の区別（ConsolidatedMember、NonConsolidatedMember）以外の軸を含まない
    members = [t for t in context.split("_") if t.endswith("Member")]
    return all(m in ALLOWED_MEMBERS for m in members)


def find_candidates(numeric_rows: list[dict], header: list[str], positions: dict[str, int]) -> dict[str, list[dict]]:
    """概念ごとの候補の行を探す。要素IDと項目名の、どちらかの部分一致。当期らしい行を先にする。"""
    names = unique_headers(header)
    column = {role: names[pos] for role, pos in positions.items()}
    found: dict[str, list[dict]] = {}
    for key, _label, id_parts, label_parts, rule in CONCEPTS:
        matches = []
        for row in numeric_rows:
            element = row.get(column["element"], "")
            label = row.get(column.get("label", ""), "")
            context = row.get(column.get("context", ""), "")
            by_id = any(p.lower() in element.lower() for p in id_parts)
            by_label = any(p in label for p in label_parts)
            if (by_id or by_label) and _context_ok(context, rule):
                matches.append(row)
        matches.sort(key=lambda r: "CurrentYear" not in r.get(column.get("context", ""), ""))
        found[key] = matches
    return found


def read_zip(raw: bytes) -> list[tuple[str, int, bytes | None]]:
    """ZIPをメモリの中だけで展開し、[(名前, 展開後の大きさ, CSVならバイト列)] を返す。

    ファイルの数と、展開後の合計の大きさに上限がある。超える場合は ValueError。
    ディスクには書かない。CSV（拡張子 .csv）以外のファイルは、名前と大きさだけを返す。
    """
    try:
        return _read_zip(raw)
    except zipfile.BadZipFile:
        raise ValueError("ZIPとして読めなかった（壊れているか、ZIPではない）") from None
    except (zipfile.LargeZipFile, RuntimeError, NotImplementedError, zlib.error, EOFError) as error:
        raise ValueError(f"ZIPを展開できなかった（{type(error).__name__}）") from None


def _read_zip(raw: bytes) -> list[tuple[str, int, bytes | None]]:
    archive = zipfile.ZipFile(io.BytesIO(raw))
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ZIP_FILES:
            raise ValueError(f"ZIPの中のファイルが多すぎる（{len(infos)}個。上限 {MAX_ZIP_FILES}個）")
        total = sum(i.file_size for i in infos)
        if total > MAX_UNCOMPRESSED_BYTES:
            raise ValueError(
                f"ZIPの展開後の合計が大きすぎる（{total // (1024 * 1024)}MB。上限 {MAX_UNCOMPRESSED_BYTES // (1024 * 1024)}MB）")
        files = []
        budget = MAX_UNCOMPRESSED_BYTES
        for info in infos:
            if info.is_dir():
                continue
            data = None
            if info.filename.lower().endswith(".csv"):
                if info.flag_bits & 0x1:
                    raise ValueError("暗号化されたファイルがある")
                with archive.open(info) as handle:
                    data = handle.read(budget + 1)
                budget -= len(data)
                if budget < 0:
                    raise ValueError("ZIPの展開後の合計が上限を超えた")
            files.append((info.filename, info.file_size, data))
        return files


def inspect_zip(doc_id: str, raw: bytes) -> dict:
    """1つの書類のZIPを調べ、画面に出す内容とJSONに書く内容をまとめる。"""
    result: dict = {"doc_id": doc_id, "files": [], "csv_files": [], "numeric_rows": [], "errors": []}
    try:
        files = read_zip(raw)
    except ValueError as error:
        result["errors"].append(str(error))
        return result
    result["files"] = [{"name": _printable(name), "size": size} for name, size, _ in files]
    for name, _size, data in files:
        if data is None:
            continue
        shown = _printable(name)
        try:
            text, encoding = decode_csv(data)
            header, rows = parse_csv(text)
            numeric, positions = extract_numeric_rows(header, rows)
        except (ValueError, csv.Error) as error:
            result["errors"].append(f"{shown}: {error}")
            continue
        candidates = find_candidates(numeric, header, positions)
        result["csv_files"].append({
            "name": shown, "encoding": encoding, "columns": [h.lstrip("﻿") for h in header],
            "row_count": len(rows), "numeric_row_count": len(numeric), "_candidates": candidates,
            "_names": unique_headers(header), "_positions": positions,
        })
        for values in numeric:
            result["numeric_rows"].append({"doc_id": doc_id, "file": shown, "values": values})
    return result


def format_rows(headers: list[str], rows: list[list[str]]) -> str:
    widths = [max(_width(r[i]) for r in [headers, *rows]) for i in range(len(headers))]
    return "\n".join(
        "  ".join(cell + " " * (widths[i] - _width(cell)) for i, cell in enumerate(r)).rstrip()
        for r in [headers, *rows]
    )


def render(result: dict) -> str:
    """1つの書類の調査結果を、画面に出す文章にする。"""
    lines = [f"■ 書類 {result['doc_id']}"]
    if result["files"]:
        lines.append(f"ZIPの中のファイル（{len(result['files'])}個）:")
        lines += [f"  {f['name']}  {f['size']:,}バイト" for f in result["files"]]
    for csv_file in result["csv_files"]:
        lines.append("")
        lines.append(f"CSV: {csv_file['name']}")
        lines.append(f"  文字コード: {csv_file['encoding']} / 行数: {csv_file['row_count']:,}"
                     f"（数値の行 {csv_file['numeric_row_count']:,}）")
        lines.append("  列名: " + " | ".join(_printable(c, 40) for c in csv_file["columns"]))
        names, positions = csv_file["_names"], csv_file["_positions"]
        for key, label, *_ in CONCEPTS:
            rows = csv_file["_candidates"][key]
            shown = rows[:MAX_ROWS_PER_CONCEPT]
            suffix = f"、表示 {len(shown)}" if len(rows) > len(shown) else ""
            lines.append(f"  【{label}】 候補 {len(rows)}行{suffix}")
            if not shown:
                continue
            table = []
            for row in shown:
                table.append([_printable(row.get(names[positions[role]], "")) if role in positions else "-"
                              for role, _ in DISPLAY_COLUMNS])
            for text in format_rows([title for _, title in DISPLAY_COLUMNS], table).splitlines():
                lines.append("    " + text)
    for message in result["errors"]:
        lines.append(f"（問題）{message}")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="EDINETの書類（CSV形式）を取得し、実際の要素の名前を調べる")
    parser.add_argument("--doc-id", action="append", required=True, metavar="DOC_ID",
                        help="書類管理番号（S100XXXX）。複数指定できる")
    parser.add_argument("--max-requests", type=_positive_int, default=DEFAULT_MAX_REQUESTS,
                        help=f"APIの呼び出しの上限（既定 {DEFAULT_MAX_REQUESTS}）。超えそうなら、実行前にエラーで終わる")
    parser.add_argument("--out", type=Path, metavar="FILE",
                        help="数値の行のすべてをJSONで書くファイル（data/auto/ の下は拒否）。省略時は書かない")
    return parser.parse_args(argv)


def build_payload(results: list[dict], requests: int, doc_ids: list[str], now: datetime | None) -> dict:
    documents = []
    for r in results:
        documents.append({
            "doc_id": r["doc_id"],
            "files": r["files"],
            "csv_files": [{k: v for k, v in c.items() if not k.startswith("_")} for c in r["csv_files"]],
            "errors": r["errors"],
            "numeric_rows": r["numeric_rows"],
        })
    generated = (now or datetime.now(ZoneInfo("Asia/Tokyo"))).astimezone(ZoneInfo("Asia/Tokyo"))
    return {"generated_at": generated.replace(microsecond=0).isoformat(),
            "parameters": {"doc_ids": doc_ids, "api_requests": requests}, "documents": documents}


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
        doc_ids = list(dict.fromkeys(args.doc_id))
        for doc_id in doc_ids:
            if not DOC_ID_PATTERN.match(doc_id):
                raise UsageError(f"doc_id の形が正しくない: {_printable(doc_id, 30)}（S100 と英数字4文字）")
        if len(doc_ids) > args.max_requests:
            raise UsageError(
                f"APIの呼び出しが {len(doc_ids)} 回になり、--max-requests（{args.max_requests}）を超える。"
                "書類を減らすか、上限を上げる")
        check_out_path(args.out)
        key = os.environ.get(ENV_KEY, "").strip()
        if not key:
            raise UsageError(f"環境変数 {ENV_KEY} が設定されていない")
        edinet = client.EdinetClient(
            key, open_url=open_url, sleep=sleep, monotonic=monotonic, max_requests=args.max_requests)
        results: list[dict] = []
        for doc_id in doc_ids:
            try:
                raw = edinet.get_document(doc_id)
            except EdinetError as error:
                results.append({"doc_id": doc_id, "files": [], "csv_files": [], "numeric_rows": [],
                                "errors": [f"取得に失敗した: {redact(str(error), key)}"]})
                continue
            results.append(inspect_zip(doc_id, raw))
    except EdinetError as error:
        print(f"error: {redact(str(error), key)}", file=sys.stderr)
        return error.exit_code
    except Exception as error:  # noqa: BLE001 - 想定外の例外も、キーを伏せて種類だけ示す
        print(f"error: 想定外のエラー（{type(error).__name__}: {redact(str(error), key)}）", file=sys.stderr)
        return EXIT_FAILURE

    for result in results:
        print(render(result))
        print()
    failed = [r["doc_id"] for r in results if r["errors"]]
    print(f"書類 {len(results)}件（API呼び出し {edinet.request_count}回）/ 問題のあった書類 {len(failed)}件")
    if args.out is not None:
        try:
            payload = build_payload(results, edinet.request_count, doc_ids, now)
            args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError as error:
            print(f"error: 結果を書けない（{type(error).__name__}）", file=sys.stderr)
            return EXIT_FAILURE
        print(f"結果を書いた: {args.out}")
    return EXIT_FAILURE if failed else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

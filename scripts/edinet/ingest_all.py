"""複数の企業の書類を、1回の走査でまとめて取り込み、企業ごとの data/auto/{slug}.json を組み立てる。

J01の段階3c（前半）。書類の一覧は、全企業分を1回の走査（日付ごとに1回のAPI呼び出し）で取る。
企業ごとに、既存の data/auto/{slug}.json（あれば）を読み、ingest_company.py と同じ組み立て（build_auto.py）を行う。

使い方（キーは環境変数 EDINET_API_KEY だけ）:
    EDINET_API_KEY=<キー> python3 scripts/edinet/ingest_all.py --company advantest --company disco \\
        --from YYYY-MM-DD --to YYYY-MM-DD --out-dir 出力フォルダ [--summary 概要.md] \\
        [--retry-failed] [--max-requests 400]

* --out-dir：data/auto/ の下は、既定では拒否する。--write-data-auto を付け、かつ環境変数 GITHUB_ACTIONS=true の
  ときだけ、リポジトリの data/auto/ に書く（その場合、--out-dir は data/auto と一致させる）
* 変更があった企業のファイルだけ書く。書く前に、すべての出力を、スキーマ（jsonschema と format の検査）で確かめ、
  1つでも合格しなければ、何も書かずに終了コード1（概要も書かない）
* 企業の間で失敗が出ても、ほかの企業は続ける。認証の失敗（401）、書類の一覧の取得の失敗は、全体を止めて何も書かない
* --max-requests は、書類の一覧と書類の取得の呼び出しの合計の上限。一覧の日数は、実行前に数える。
  取得する書類の数は、一覧を取り、既存のファイルと照らしてから分かるため、最初の取得の前（何も書く前）に数え直す

終了コード: 0 成功（異常や failed があっても0）/ 1 全体を止めた / 2 設定・引数の誤り
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

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_auto  # noqa: E402
import client  # noqa: E402
import ingest_company  # noqa: E402
from client import ENV_KEY, EXIT_FAILURE, EXIT_OK, EdinetError, redact  # noqa: E402
from list_filings import (  # noqa: E402
    COMPANIES_DIR,
    DEFAULT_MAX_REQUESTS,
    FORBIDDEN_OUT_DIR,
    XBRL_MAP_PATH,
    UsageError,
    _positive_int,
    _valid_date,
    load_companies,
    load_doc_types,
    plan_dates,
    resolve_range,
    select_filings,
)

AUTO_DIR = FORBIDDEN_OUT_DIR  # リポジトリの data/auto/
MESSAGE_LIMIT = 200


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="複数の企業の書類を、1回の走査でまとめて取り込む（段階3c前半）")
    parser.add_argument("--company", action="append", required=True, metavar="SLUG",
                        help="企業の slug（data/companies/{slug}.yaml。edinet_code が必要）。複数指定できる")
    parser.add_argument("--from", dest="from_date", type=_valid_date, metavar="YYYY-MM-DD",
                        help="日付の範囲の始め。--to と一緒に指定する。省略時は日本時間の前日だけ")
    parser.add_argument("--to", dest="to_date", type=_valid_date, metavar="YYYY-MM-DD",
                        help="日付の範囲の終わり（この日を含む）")
    parser.add_argument("--include-weekends", action="store_true", help="土日も調べる（既定はとばす）")
    parser.add_argument("--max-requests", type=_positive_int, default=DEFAULT_MAX_REQUESTS,
                        help=f"書類の一覧と書類の取得の呼び出しの合計の上限（既定 {DEFAULT_MAX_REQUESTS}）")
    parser.add_argument("--out-dir", required=True, type=Path, metavar="DIR",
                        help="結果（{slug}.json）を書くフォルダ。data/auto/ の下は、既定では拒否する")
    parser.add_argument("--write-data-auto", action="store_true",
                        help="リポジトリの data/auto/ に書く。環境変数 GITHUB_ACTIONS=true のときだけ許す。"
                             "--out-dir は data/auto と一致させる")
    parser.add_argument("--summary", type=Path, metavar="FILE", help="変更の概要を書くMarkdownのファイル")
    parser.add_argument("--retry-failed", action="store_true",
                        help="既存の filings で status が failed の書類も、一覧にあれば再取得する")
    return parser.parse_args(argv)


def check_out_dir(args: argparse.Namespace) -> Path:
    """--out-dir と --write-data-auto の組み合わせを、実行前に確かめる。書き込み先のフォルダを返す。"""
    out = args.out_dir.resolve()
    auto = AUTO_DIR.resolve()
    inside = out == auto or auto in out.parents
    if args.write_data_auto:
        if os.environ.get("GITHUB_ACTIONS") != "true":
            raise UsageError("--write-data-auto は、環境変数 GITHUB_ACTIONS=true のとき（GitHub Actions の中）だけ使える")
        if out != auto:
            raise UsageError("--write-data-auto のとき、--out-dir は data/auto と一致させる")
        return out
    if inside:
        raise UsageError("--out-dir に data/auto/ は指定できない（--write-data-auto を付け、GitHub Actions の中で実行する）")
    if not out.is_dir():
        raise UsageError(f"--out-dir がフォルダでない、またはない: {args.out_dir}")
    return out


def check_file_target(path: Path | None, what: str) -> None:
    if path is None:
        return
    resolved = path.resolve()
    if resolved == AUTO_DIR.resolve() or AUTO_DIR.resolve() in resolved.parents:
        raise UsageError(f"{what}に data/auto/ の下は指定できない")
    if not resolved.parent.is_dir() or resolved.is_dir():
        raise UsageError(f"{what}を書けない場所: {path}")


def load_existing(slug: str, edinet_code: str) -> tuple[dict | None, str | None]:
    """既存の data/auto/{slug}.json を読む。(内容、飛ばす理由)。なければ (None, None)。"""
    path = AUTO_DIR / f"{slug}.json"
    if not path.is_file():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "既存のファイルを読めない（上書きしないよう、飛ばした）"
    if not isinstance(data, dict) or data.get("company") != slug or data.get("edinet_code") != edinet_code:
        return None, (f"既存のファイルの company・edinet_code が企業と一致しない"
                      f"（company={data.get('company') if isinstance(data, dict) else '?'}、"
                      f"edinet_code={data.get('edinet_code') if isinstance(data, dict) else '?'}）。飛ばした")
    return data, None


def short(text: str, key: str) -> str:
    text = redact(str(text), key).replace("\n", " ")
    return text if len(text) <= MESSAGE_LIMIT else text[:MESSAGE_LIMIT] + "…"


def render_summary(results: list[dict], api: dict, key: str) -> str:
    counts = {k: sum(1 for r in results for c in r["changes"] if c["kind"] == k)
              for k in ("added", "replaced", "failed", "not_recorded")}
    lines = ["# 取り込みの概要", "",
             f"* 追加した書類：{counts['added']}件",
             f"* 置き換えた値：{counts['replaced']}件",
             f"* failed の書類：{counts['failed']}件",
             f"* not_recorded の書類：{counts['not_recorded']}件",
             f"* 飛ばした企業：{sum(1 for r in results if r['skipped'])}社",
             f"* APIの呼び出し：{api['total']}回（書類の一覧 {api['list']}回、書類の取得 {api['fetch']}回）", ""]
    for r in results:
        lines += [f"## {r['slug']}（{r['edinet_code']}）", ""]
        if r["skipped"]:
            lines += [f"* 飛ばした：{short(r['skipped'], key)}", ""]
            continue
        data, changes = r["data"], r["changes"]
        filings = {f["doc_id"]: f for f in data["filings"]}
        if not changes:
            lines += ["* 変更なし", ""]
            continue
        added = [c for c in changes if c["kind"] == "added"]
        if added:
            lines.append("**追加した書類**")
            for c in added:
                f = filings.get(c["doc_id"], {})
                lines.append(f"* {c['doc_id']}：{f.get('doc_type', '?')}、決算期 {f.get('fiscal_period_end', '?')}"
                             f"（{f.get('period_type', '?')}）")
            lines.append("")
        replaced = [c for c in changes if c["kind"] == "replaced"]
        if replaced:
            lines += ["**置き換えた値**", f"* 値 {len(replaced)}件（revisions に {len(replaced)}件を加えた）"]
            lines += [f"* {short(c['message'], key)}" for c in replaced] + [""]
        failed = [c for c in changes if c["kind"] == "failed"]
        if failed:
            lines.append("**failed の書類**")
            lines += [f"* {c['doc_id']}：{short(c['message'], key)}" for c in failed] + [""]
        not_recorded = [c for c in changes if c["kind"] == "not_recorded"]
        if not_recorded:
            lines.append("**not_recorded（filings に書かなかった書類）**")
            lines += [f"* {c['doc_id']}：{c.get('reason', '?')}" for c in not_recorded] + [""]
        anomalies = [c for c in changes if c["kind"] == "anomaly"]
        if anomalies:
            lines.append("**異常**")
            lines += [f"* {c['doc_id']}：{short(c['message'], key)}" for c in anomalies] + [""]
    return "\n".join(lines).rstrip() + "\n"


def write_all(files: dict[Path, str]) -> None:
    """すべてを一時ファイルに書いてから、置き換える（途中で失敗しても、一部だけ書き換わることを避ける）。"""
    temps = {}
    try:
        for path, text in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(path.name + ".tmp")
            temp.write_text(text, encoding="utf-8")
            temps[path] = temp
        for path, temp in temps.items():
            os.replace(temp, path)
    finally:
        for temp in temps.values():
            if temp.exists():
                temp.unlink()


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
        out_dir = check_out_dir(args)
        check_file_target(args.summary, "--summary")
        code_to_slug = load_companies(args.company, companies_dir)
        slug_to_code = {slug: code for code, slug in code_to_slug.items()}
        doc_types = load_doc_types(config_path)
        start, end = resolve_range(args, now)
        days = plan_dates(start, end, args.include_weekends)
        if len(days) > args.max_requests:
            raise UsageError(f"書類の一覧のAPIの呼び出しが {len(days)} 回になり、--max-requests（{args.max_requests}）を"
                             "超える。範囲を狭めるか、上限を上げる")
        key = os.environ.get(ENV_KEY, "").strip()
        if not key:
            raise UsageError(f"環境変数 {ENV_KEY} が設定されていない")
        moment = (now or datetime.now(ZoneInfo("Asia/Tokyo"))).astimezone(ZoneInfo("Asia/Tokyo"))
        edinet = client.EdinetClient(key, open_url=open_url, sleep=sleep, monotonic=monotonic,
                                     max_requests=args.max_requests)
        # 書類の一覧：全企業分を1回の走査で取る
        listed: list[dict] = []
        for day in days:
            found, _withdrawn = select_filings(edinet.get_documents(day, 2).get("results"), code_to_slug, doc_types)
            listed.extend(found)
        listed.sort(key=lambda f: (str(f["submitDateTime"] or ""), f["slug"], str(f["docID"])))
        list_calls = edinet.request_count
        # 企業ごとに、既存のファイルを読み、取得する書類を決める
        results: list[dict] = []
        for slug in slug_to_code:
            code = slug_to_code[slug]
            existing, reason = load_existing(slug, code)
            result = {"slug": slug, "edinet_code": code, "existing": existing, "skipped": reason, "changes": [],
                      "data": None, "targets": [], "rows": [r for r in listed if r["slug"] == slug]}
            if reason is None:
                known = {f["doc_id"] for f in (existing or {}).get("filings", [])
                         if not (args.retry_failed and f["status"] == "failed")}
                usable, _ = build_auto.classify_rows(result["rows"], code, doc_types)
                seen = set(known)
                for row, _doc_type in usable:
                    if row["docID"] not in seen:
                        seen.add(row["docID"])
                        result["targets"].append(row)
            results.append(result)
        planned = list_calls + sum(len(r["targets"]) for r in results)
        if planned > args.max_requests:
            raise UsageError(f"APIの呼び出しが、書類の一覧 {list_calls} 回と書類の取得 "
                             f"{planned - list_calls} 回で合計 {planned} 回になり、--max-requests（{args.max_requests}）を"
                             "超える。範囲を狭めるか、上限を上げる（何も書いていない）")
        # 取得と組み立て。企業の間で失敗が出ても続ける（認証の失敗は、全体を止める）
        ingested_at = build_auto.jst_text(moment)
        xbrl_map = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        for result in results:
            if result["skipped"]:
                continue
            try:
                target_ids = {t["docID"] for t in result["targets"]}
                documents = [{"filing": r, "result": None, "error": None} for r in result["rows"]
                             if r["docID"] not in target_ids]
                for row in result["targets"]:
                    documents.append(ingest_company.fetch_one(edinet, row, ingested_at, xbrl_map, key,
                                                              result["edinet_code"]))
                result["data"], result["changes"] = build_auto.build(
                    result["slug"], result["edinet_code"], result["existing"], documents, moment, doc_types,
                    retry_failed=args.retry_failed)
            except EdinetError as error:
                if "認証に失敗" in str(error):
                    raise
                result["skipped"] = f"取り込みに失敗した（{short(error, key)}）"
            except Exception as error:  # noqa: BLE001 - 1社の失敗で、ほかの企業を止めない
                result["skipped"] = f"取り込みに失敗した（{type(error).__name__}）"
        api = {"total": edinet.request_count, "list": list_calls, "fetch": edinet.request_count - list_calls}
    except UsageError as error:
        print(f"error: {redact(str(error), key)}", file=sys.stderr)
        return client.EXIT_USAGE
    except EdinetError as error:
        print(f"error: {redact(str(error), key)}（何も書いていない）", file=sys.stderr)
        return error.exit_code
    except Exception as error:  # noqa: BLE001 - 想定外の例外も、キーを伏せて種類だけ示す
        print(f"error: 想定外のエラー（{type(error).__name__}: {redact(str(error), key)}）", file=sys.stderr)
        return EXIT_FAILURE

    # 変更があった企業のファイルだけ書く。書く前に、すべてをスキーマで確かめる
    files: dict[Path, str] = {}
    invalid = False
    for result in results:
        data = result["data"]
        if result["skipped"] or data is None or data == result["existing"]:
            continue
        if result["existing"] is None and not data["filings"]:
            continue
        errors = ingest_company.validate(data)
        if errors:
            invalid = True
            print(f"error: {result['slug']}: スキーマに合格しない", file=sys.stderr)
            for message in errors[:10]:
                print(f"  {short(message, key)}", file=sys.stderr)
            continue
        files[out_dir / f"{result['slug']}.json"] = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if invalid:
        print("error: スキーマに合格しない出力があるので、何も書かない", file=sys.stderr)
        return EXIT_FAILURE

    for result in results:
        print(ingest_company.render_changes(result["slug"], result["changes"], len(result["targets"]))
              if not result["skipped"] else f"企業 {result['slug']}: 飛ばした（{short(result['skipped'], key)}）")
    print(f"API呼び出し {api['total']}回 / 書く企業 {len(files)}社")
    try:
        write_all(files)
        if args.summary is not None:
            args.summary.write_text(render_summary(results, api, key), encoding="utf-8")
    except OSError as error:
        print(f"error: 結果を書けない（{type(error).__name__}）", file=sys.stderr)
        return EXIT_FAILURE
    for path in files:
        print(f"結果を書いた: {path}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

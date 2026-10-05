"""EDINETの書類（CSV形式）から、文章の行の「要素ID、項目名、文字数」だけを一覧にする調査用のスクリプト。

原資料束（make_bundle.py）で取り出す節を、運営者が選ぶための調査である。
どの要素が「事業の内容」「セグメント情報」かを、要素IDと項目名で決められるようにする。

使い方（キーは環境変数 EDINET_API_KEY だけ。コマンドの引数では受け取らない）:
    EDINET_API_KEY=<キー> python3 scripts/bundle/inspect_sections.py \\
        --doc-id S100XXXX [--doc-id S100YYYY ...] [--max-requests 10]

* 画面に出すのは、書類ごとの、文章の行の要素ID、項目名、コンテキストID、文字数、CSVの名前だけ。
  **本文の文字は、先頭の数文字も含めて、一切出さない**（リポジトリ、Actionsのログは公開のため。CLAUDE.md 2章10）
* ファイルは書かない。成果物も作らない
* ZIPは、メモリの中だけで展開する

終了コード: 0 成功 / 1 取得・解析の失敗 / 2 設定・引数の誤り
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "edinet"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import client  # noqa: E402
import inspect_document as inspector  # noqa: E402
from client import DOC_ID_PATTERN, ENV_KEY, EXIT_FAILURE, EXIT_OK, EdinetError, redact  # noqa: E402
from list_filings import UsageError, _positive_int  # noqa: E402
from sections import TextRow, text_rows_from_zip  # noqa: E402

DEFAULT_MAX_REQUESTS = 10
LABEL_MAX_LENGTH = 60
HEADERS = ["要素ID", "項目名", "コンテキストID", "文字数", "CSV"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="書類の文章の行の、要素ID・項目名・文字数だけを一覧にする（本文は出さない）")
    parser.add_argument("--doc-id", action="append", required=True, metavar="DOC_ID",
                        help="書類管理番号（S100XXXX）。複数指定できる")
    parser.add_argument("--max-requests", type=_positive_int, default=DEFAULT_MAX_REQUESTS,
                        help=f"APIの呼び出しの上限（既定 {DEFAULT_MAX_REQUESTS}）。超えそうなら、実行前にエラーで終わる")
    return parser.parse_args(argv)


def outline(rows: list[TextRow]) -> list[list[str]]:
    """文章の行を、表示用の行（本文を含まない）にする。"""
    return [
        [r.element_id, inspector._printable(r.label, LABEL_MAX_LENGTH), r.context_id, f"{r.chars:,}", r.file]
        for r in rows
    ]


def render(doc_id: str, rows: list[TextRow], problems: list[str]) -> str:
    lines = [f"=== {doc_id} ===", f"文章の行 {len(rows)}件"]
    if rows:
        lines.append(inspector.format_rows(HEADERS, outline(rows)))
    lines += [f"読めなかったCSV: {p}" for p in problems]
    return "\n".join(lines)


def main(
    argv: list[str] | None = None,
    *,
    open_url=client._open,
    sleep=time.sleep,
    monotonic=time.monotonic,
) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    key = ""
    try:
        doc_ids = list(dict.fromkeys(args.doc_id))
        for doc_id in doc_ids:
            if not DOC_ID_PATTERN.match(doc_id):
                raise UsageError(f"doc_id の形が正しくない: {inspector._printable(doc_id, 30)}（S100 と英数字4文字）")
        if len(doc_ids) > args.max_requests:
            raise UsageError(
                f"APIの呼び出しが {len(doc_ids)} 回になり、--max-requests（{args.max_requests}）を超える。"
                "書類を減らすか、上限を上げる")
        key = os.environ.get(ENV_KEY, "").strip()
        if not key:
            raise UsageError(f"環境変数 {ENV_KEY} が設定されていない")
        edinet = client.EdinetClient(
            key, open_url=open_url, sleep=sleep, monotonic=monotonic, max_requests=args.max_requests)
        failed = 0
        for doc_id in doc_ids:
            try:
                rows, problems = text_rows_from_zip(edinet.get_document(doc_id))
            except EdinetError as error:
                if error.exit_code == client.EXIT_USAGE:
                    raise
                print(f"=== {doc_id} ===\n取得に失敗した: {redact(str(error), key)}\n")
                failed += 1
                continue
            except ValueError as error:
                print(f"=== {doc_id} ===\n書類を読めなかった: {error}\n")
                failed += 1
                continue
            print(render(doc_id, rows, problems))
            print()
            failed += bool(problems)
        print(f"書類 {len(doc_ids)}件（API呼び出し {edinet.request_count}回）/ 問題のあった書類 {failed}件")
        return EXIT_FAILURE if failed else EXIT_OK
    except EdinetError as error:
        print(f"error: {redact(str(error), key)}", file=sys.stderr)
        return error.exit_code
    except Exception as error:  # noqa: BLE001 - 想定外の例外は、本文を含みうるため、種類だけ示す
        print(f"error: 想定外のエラー（{type(error).__name__}）", file=sys.stderr)
        return EXIT_FAILURE


if __name__ == "__main__":
    sys.exit(main())

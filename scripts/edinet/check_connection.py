"""EDINET API（v2）への接続の確認用スクリプト。

書類一覧API（type=1、メタデータだけ）を1回呼び、件数、更新日時、ステータスを表示する。
取り込み（J01）の本体ではなく、ファイルは書き込まない。

APIキーは、環境変数 EDINET_API_KEY から読む（コマンドの引数では受け取らない）。
キーはURLのクエリに入るため、リポジトリが公開であることを前提に、次を守る。
  * キーとキー入りのURLを、標準出力、エラー文、例外のメッセージに出さない
  * 例外は、キーを伏せ字にした文だけを表示する（トレースバックは表示しない）

終了コード: 0 成功 / 1 接続・応答の失敗 / 2 設定・引数の誤り
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import client  # noqa: E402
from client import (  # noqa: E402,F401 - テストと他のスクリプトが、このモジュールの名前で使う
    API_URL,
    ENV_KEY,
    EXIT_FAILURE,
    EXIT_OK,
    EXIT_USAGE,
    MASK,
    MAX_RETRIES,
    MESSAGE_MAX_LENGTH,
    RETRY_BASE_SECONDS,
    RETRY_MAX_SECONDS,
    TIMEOUT_SECONDS,
    EdinetError,
    _call_once,
    _failure_text,
    _NoRedirect,
    _open,
    _retry_wait,
    default_date,
    redact,
)


def fetch_document_list(
    target_date: date,
    key: str,
    *,
    open_url=_open,
    sleep=time.sleep,
    timeout: float = TIMEOUT_SECONDS,
) -> dict:
    """書類一覧API（type=1）を呼び、成功なら `metadata` を返す。失敗は EdinetError。"""
    edinet = client.EdinetClient(key, open_url=open_url, sleep=sleep, timeout=timeout)
    return edinet.get_documents(target_date, 1).get("metadata", {})


def _valid_date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"日付は YYYY-MM-DD の形で指定する: {text}") from None


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="EDINET API（v2）への接続を確かめる")
    parser.add_argument(
        "--date",
        type=_valid_date,
        help="書類一覧を取得する日（YYYY-MM-DD）。省略時は日本時間の前日",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, open_url=_open, sleep=time.sleep) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    key = os.environ.get(ENV_KEY, "").strip()
    if not key:
        print(f"error: 環境変数 {ENV_KEY} が設定されていない", file=sys.stderr)
        return EXIT_USAGE
    target_date = args.date or default_date()
    try:
        metadata = fetch_document_list(target_date, key, open_url=open_url, sleep=sleep)
    except EdinetError as error:
        print(f"error: {redact(str(error), key)}", file=sys.stderr)
        return error.exit_code
    except Exception as error:  # noqa: BLE001 - 想定外の例外も、キーを伏せて種類だけ示す
        print(
            f"error: 想定外のエラー（{type(error).__name__}: {redact(str(error), key)}）",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    resultset = metadata.get("resultset") or {}
    print(f"対象日: {target_date.isoformat()}")
    print(f"件数: {resultset.get('count')}")
    print(f"更新日時: {metadata.get('processDateTime')}")
    print(f"ステータス: {metadata.get('status')}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

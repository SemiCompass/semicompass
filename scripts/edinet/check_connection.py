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
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from urllib.parse import quote, quote_plus, urlencode
from zoneinfo import ZoneInfo

API_URL = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
ENV_KEY = "EDINET_API_KEY"
TIMEOUT_SECONDS = 30
MAX_RETRIES = 3  # 429のときの再試行は最大3回（最初の1回を含めて4回まで呼ぶ）
RETRY_BASE_SECONDS = 30  # 再試行の間隔は 30秒、60秒、120秒
RETRY_MAX_SECONDS = 300
MESSAGE_MAX_LENGTH = 200
MASK = "***"

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2

_QUERY_KEY_PATTERN = re.compile(r"(?i)(Subscription-Key=)[^&\s'\")>]*")


class EdinetError(Exception):
    """接続の確認の失敗。メッセージは、キーを伏せ字にした文だけを持つ。"""

    def __init__(self, message: str, exit_code: int = EXIT_FAILURE):
        super().__init__(message)
        self.exit_code = exit_code


def redact(text: str, key: str | None = None) -> str:
    """文章の中のキーと、`Subscription-Key=` に続く値を伏せ字にする。"""
    text = _QUERY_KEY_PATTERN.sub(r"\1" + MASK, text)
    if key:
        for form in {key, quote(key, safe=""), quote_plus(key)}:
            text = text.replace(form, MASK)
    return text


def default_date(now: datetime | None = None) -> date:
    """日本時間の前日。"""
    now = now or datetime.now(ZoneInfo("Asia/Tokyo"))
    return now.astimezone(ZoneInfo("Asia/Tokyo")).date() - timedelta(days=1)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """リダイレクトを追わない（キー入りのURLを、別の送信先へ送らないため）。"""

    def redirect_request(self, *args, **kwargs):  # noqa: D102
        return None


def _open(request: urllib.request.Request, timeout: float):
    return urllib.request.build_opener(_NoRedirect).open(request, timeout=timeout)


def _status_of(body: dict) -> tuple[str | None, str]:
    """応答のJSONから、ステータスとメッセージを取り出す。

    エラーのときは StatusCode と message（トップレベル）、
    それ以外は metadata.status と metadata.message で返る。
    """
    if "StatusCode" in body:
        return str(body["StatusCode"]), str(body.get("message", ""))
    metadata = body.get("metadata")
    if isinstance(metadata, dict):
        status = metadata.get("status")
        return (None if status is None else str(status)), str(metadata.get("message", ""))
    return None, ""


def _parse_json(raw: bytes) -> dict | None:
    try:
        body = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return body if isinstance(body, dict) else None


def _retry_wait(attempt: int, retry_after: str | None) -> float:
    wait = RETRY_BASE_SECONDS * (2**attempt)
    if retry_after and retry_after.isdigit():
        wait = max(wait, int(retry_after))
    return min(wait, RETRY_MAX_SECONDS)


def fetch_document_list(
    target_date: date,
    key: str,
    *,
    open_url=_open,
    sleep=time.sleep,
    timeout: float = TIMEOUT_SECONDS,
) -> dict:
    """書類一覧API（type=1）を呼び、成功なら `metadata` を返す。失敗は EdinetError。

    429は、間隔を空けて最大 MAX_RETRIES 回まで再試行する。
    """
    query = urlencode({"date": target_date.isoformat(), "type": "1", "Subscription-Key": key})
    attempt = 0
    while True:
        status, message, metadata, retry_after = _call_once(
            f"{API_URL}?{query}", key, open_url, timeout
        )
        if status == "200":
            return metadata
        if status == "429" and attempt < MAX_RETRIES:
            sleep(_retry_wait(attempt, retry_after))
            attempt += 1
            continue
        raise EdinetError(_failure_text(status, message, key, retries=attempt))


def _call_once(url: str, key: str, open_url, timeout: float):
    """1回呼び、(ステータス, メッセージ, metadata, Retry-After) を返す。

    例外は、キーを含みうる元の例外を引き継がず（from None）、伏せ字にした文だけを持つ
    EdinetError にして投げる。
    """
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    http_status: int | None = None
    raw = b""
    retry_after = None
    try:
        response = open_url(request, timeout)
        try:
            raw = response.read()
            http_status = getattr(response, "status", None) or response.getcode()
        finally:
            response.close()
    except urllib.error.HTTPError as error:
        http_status = error.code
        retry_after = error.headers.get("Retry-After") if error.headers else None
        try:
            raw = error.read()
        except Exception:  # noqa: BLE001 - 本文が読めなくても、ステータスで判定する
            raw = b""
        finally:
            error.close()
    except (TimeoutError, urllib.error.URLError, OSError) as error:
        reason = getattr(error, "reason", error)
        if isinstance(reason, TimeoutError) or "timed out" in str(reason):
            text = f"{int(timeout)}秒以内に応答がなかった（タイムアウト）"
        else:
            text = f"接続できなかった（{type(reason).__name__}: {redact(str(reason), key)}）"
        raise EdinetError(text) from None
    except Exception as error:  # noqa: BLE001 - 想定外の例外も、キーを伏せた文に変える
        raise EdinetError(
            f"想定外のエラー（{type(error).__name__}: {redact(str(error), key)}）"
        ) from None

    body = _parse_json(raw)
    status, message = _status_of(body) if body is not None else (None, "")
    if status is None and http_status not in (None, 200):
        # JSONのステータスがないときは、HTTPのステータスで判定する。
        # HTTP 200でも metadata.status がなければ、成功とは扱わない
        status = str(http_status)
    if body is None and http_status == 200:
        raise EdinetError("応答がJSONとして読めなかった") from None
    metadata = body.get("metadata", {}) if body is not None and status == "200" else {}
    return status, message, metadata, retry_after


def _failure_text(status: str | None, message: str, key: str, *, retries: int) -> str:
    detail = redact(message, key)[:MESSAGE_MAX_LENGTH]
    label = {
        "401": "認証に失敗した（キーが正しいか、有効かを確かめる）",
        "429": f"アクセスが多すぎる（再試行を{retries}回行ったが解消しなかった）",
    }.get(status or "", None)
    if status is not None and status.startswith("5"):
        label = f"EDINET側のエラー（停止している可能性がある。ステータス {status}）"
    if label is None:
        label = f"成功ではないステータスが返った（{status}）"
    return f"{label}。{detail}" if detail else label


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

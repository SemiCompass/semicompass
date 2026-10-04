"""EDINET API（v2）のクライアント（共通部品）。

書類一覧API（documents.json）と書類取得API（documents/{docID}）を呼ぶ。check_connection.py（接続の確認）、
list_filings.py（書類の調査）、inspect_document.py（書類の要素の調査）が使う。取り込み（J01）の本体ではなく、ファイルは書き込まない。

リポジトリが公開で、APIキーはURLのクエリに入るため、次を守る。
  * キーとキー入りのURLを、標準出力、エラー文、例外のメッセージ、ログ、ファイルに出さない
  * 例外は、キーを含みうる元の例外を引き継がず（raise ... from None）、キーを伏せ字にした文だけを持つ
  * リダイレクトを追わない（キー入りのURLを、別の送信先へ送らないため）

呼び出しの間隔は1秒以上。429は、間隔を広げて最大3回まで再試行する。タイムアウトは30秒。
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from urllib.parse import quote, quote_plus, urlencode
from zoneinfo import ZoneInfo

API_URL = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
DOCUMENT_URL = "https://api.edinet-fsa.go.jp/api/v2/documents/"  # + docID（書類取得API）
DOC_ID_PATTERN = re.compile(r"^S100[0-9A-Z]{4}$")  # データ定義書2.2のdoc_id
MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024  # 書類取得の応答の大きさの上限
ENV_KEY = "EDINET_API_KEY"
TIMEOUT_SECONDS = 30
MAX_RETRIES = 3  # 429のときの再試行は最大3回（最初の1回を含めて4回まで呼ぶ）
MIN_INTERVAL_SECONDS = 1.0  # 呼び出しの間隔は1秒以上
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

    def __init__(self, message: str, exit_code: int = EXIT_FAILURE, *, transient: bool = False):
        super().__init__(message)
        self.exit_code = exit_code
        self.transient = transient  # 通信の一時的な失敗（429の再試行を使い切った、接続できない、タイムアウト）


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


def _fetch_raw(
    url: str, key: str, open_url, timeout: float, max_bytes: int | None = None, accept: str = "application/json"
):
    """1回呼び、(HTTPのステータス, 応答の本体のバイト列, Retry-After) を返す。

    例外は、キーを含みうる元の例外を引き継がず（from None）、伏せ字にした文だけを持つ
    EdinetError にして投げる。max_bytes を指定すると、それを超える応答は読まずに失敗にする。
    """
    request = urllib.request.Request(url, headers={"Accept": accept})
    http_status: int | None = None
    raw = b""
    retry_after = None
    try:
        response = open_url(request, timeout)
        try:
            raw = response.read() if max_bytes is None else response.read(max_bytes + 1)
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
        raise EdinetError(text, transient=True) from None
    except Exception as error:  # noqa: BLE001 - 想定外の例外も、キーを伏せた文に変える
        raise EdinetError(
            f"想定外のエラー（{type(error).__name__}: {redact(str(error), key)}）"
        ) from None
    if max_bytes is not None and len(raw) > max_bytes:
        raise EdinetError(f"応答が大きすぎる（上限 {max_bytes // (1024 * 1024)}MB）") from None
    return http_status, raw, retry_after


def _call_once(url: str, key: str, open_url, timeout: float):
    """1回呼び、(ステータス, メッセージ, 成功時の応答のJSON, Retry-After) を返す。"""
    http_status, raw, retry_after = _fetch_raw(url, key, open_url, timeout)
    body = _parse_json(raw)
    status, message = _status_of(body) if body is not None else (None, "")
    if status is None and http_status not in (None, 200):
        # JSONのステータスがないときは、HTTPのステータスで判定する。
        # HTTP 200でも metadata.status がなければ、成功とは扱わない
        status = str(http_status)
    if body is None and http_status == 200:
        raise EdinetError("応答がJSONとして読めなかった") from None
    success_body = body if body is not None and status == "200" else {}
    return status, message, success_body, retry_after


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


def _classify_document(http_status: int | None, raw: bytes) -> tuple[str | None, str]:
    """書類取得の応答を判定し、(ステータス, メッセージ) を返す。成功（ZIP）は ("200", "")。

    取得に失敗したときは、HTTPが200でも、JSONのエラーが返ることがある。
    応答の先頭が ZIP（PK）か、JSONかで判定する。
    """
    if raw[:2] == b"PK":
        return "200", ""
    body = _parse_json(raw)
    if body is None:
        if http_status in (None, 200):
            raise EdinetError("応答がZIPでもJSONでもなかった") from None
        return str(http_status), ""
    status, message = _status_of(body)
    if status is None or status == "200":
        # ZIPではないのに成功の印のJSON、またはステータスのないJSONは、成功とは扱わない
        if http_status in (None, 200):
            raise EdinetError("ZIPではなくJSONが返った（書類を取得できなかった）") from None
        status = str(http_status)
    return status, message


class EdinetClient:
    """書類一覧API・書類取得APIのクライアント。1つのインスタンスの中で、呼び出しの間隔と回数を管理する。"""

    def __init__(
        self,
        key: str,
        *,
        open_url=_open,
        sleep=time.sleep,
        monotonic=time.monotonic,
        timeout: float = TIMEOUT_SECONDS,
        min_interval: float = MIN_INTERVAL_SECONDS,
        max_requests: int | None = None,
    ):
        self._key = key
        self._open_url = open_url
        self._sleep = sleep
        self._monotonic = monotonic
        self._timeout = timeout
        self._min_interval = min_interval
        self._max_requests = max_requests
        self._last_call: float | None = None
        self.request_count = 0  # 再試行を含む、APIを呼んだ回数

    def __repr__(self) -> str:
        return f"EdinetClient(key={MASK})"

    def _before_call(self) -> None:
        if self._max_requests is not None and self.request_count >= self._max_requests:
            raise EdinetError(f"APIの呼び出しの上限（{self._max_requests}回）に達した")
        if self._last_call is not None:
            wait = self._min_interval - (self._monotonic() - self._last_call)
            if wait > 0:
                self._sleep(wait)
        self.request_count += 1

    def _with_retries(self, call):
        """call() が (ステータス, メッセージ, 成功時の値, Retry-After) を返す。429は再試行する。"""
        attempt = 0
        while True:
            self._before_call()
            status, message, value, retry_after = call()
            self._last_call = self._monotonic()
            if status == "200":
                return value
            if status == "429" and attempt < MAX_RETRIES:
                self._sleep(_retry_wait(attempt, retry_after))
                attempt += 1
                self._last_call = None  # 再試行の待ち（30秒以上）が、呼び出しの間隔を満たす
                continue
            raise EdinetError(_failure_text(status, message, self._key, retries=attempt),
                              transient=status == "429")

    def get_documents(self, target_date: date, doc_type: int) -> dict:
        """書類一覧API（type=doc_type）を呼び、成功なら応答のJSON全体を返す。失敗は EdinetError。

        doc_type=1はメタデータだけ、2はメタデータと提出書類の一覧（results）。
        429は、間隔を空けて最大 MAX_RETRIES 回まで再試行する。
        """
        query = urlencode(
            {"date": target_date.isoformat(), "type": str(doc_type), "Subscription-Key": self._key}
        )
        url = f"{API_URL}?{query}"

        def call():
            status, message, body, retry_after = _call_once(url, self._key, self._open_url, self._timeout)
            return status, message, body, retry_after

        return self._with_retries(call)

    def get_document(self, doc_id: str, doc_type: int = 5, *, max_bytes: int = MAX_DOWNLOAD_BYTES) -> bytes:
        """書類取得API（type=doc_type）を呼び、成功なら応答（既定のtype=5はCSVのZIP）のバイト列を返す。

        応答の先頭がZIP（PK）なら成功。HTTPが200でも、JSONのエラーが返ることがあるため、
        JSONのステータスで判定する。429は再試行する。失敗は EdinetError。
        """
        if not DOC_ID_PATTERN.match(doc_id):
            raise EdinetError(f"doc_id の形が正しくない: {doc_id[:20]!r}", EXIT_USAGE)
        query = urlencode({"type": str(doc_type), "Subscription-Key": self._key})
        url = f"{DOCUMENT_URL}{doc_id}?{query}"

        def call():
            http_status, raw, retry_after = _fetch_raw(
                url, self._key, self._open_url, self._timeout, max_bytes, accept="*/*"
            )
            status, message = _classify_document(http_status, raw)
            return status, message, raw, retry_after

        return self._with_retries(call)

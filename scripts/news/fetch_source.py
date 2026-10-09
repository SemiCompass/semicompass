"""元記事の取得（J03。運用ルール書 3.1、3.4）。1つのURLから、見出しと本文のテキストを取り出す。

* https だけ。取得先は、運営者が指定したURL（か、収集した候補のURL）だけである。
* 内部のアドレス（localhost、メタデータのアドレスなど）には接続しない。リダイレクトも、https だけに従う。
* 本文は、AIに渡す資料としてだけ使う。保存しない。ログ、要約、変更案に出さない（CLAUDE.md 2章の4、10）。
* HTML は、script・style・nav などを除いてテキストにする。PDF は pypdf で取り出す。
"""

from __future__ import annotations

import html
import io
import ipaddress
import re
import socket
import urllib.error
import urllib.request
from urllib.parse import urlsplit

USER_AGENT = "SemiCompassBot/1.0 (+https://github.com/SemiCompass/semicompass)"
TIMEOUT = 25
MAX_BYTES = 8_000_000
MAX_CHARS = 30_000  # AIに渡す本文の上限
MIN_CHARS = 200     # これより短いときは、本文を取れなかったとみなす（JavaScriptで作るページなど）


class FetchError(Exception):
    """取得に失敗した。メッセージは、本文を含まない。"""


class _HttpsOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith("https://"):
            raise FetchError("https ではない転送先には従わない")
        check_host(urlsplit(newurl).hostname or "")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def check_host(host: str, resolver=socket.getaddrinfo) -> None:
    if not host:
        raise FetchError("URLのホスト名がない")
    try:
        infos = resolver(host, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        raise FetchError("ホスト名を解決できない") from None
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise FetchError("内部のアドレスには接続しない")


def html_to_text(raw: str) -> tuple[str, str]:
    """(見出し, 本文)。"""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S)
    title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", title_match.group(1)))).strip() if title_match else ""
    raw = re.sub(r"<(script|style|noscript|nav|header|footer|aside|form|svg)\b.*?</\1>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<!--.*?-->", " ", raw, flags=re.S)
    raw = re.sub(r"</(p|div|li|tr|h[1-6]|section|article|br)\s*>|<br\s*/?>", "\n", raw, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    lines = [re.sub(r"[ \t　]+", " ", line).strip() for line in text.splitlines()]
    return title, "\n".join(line for line in lines if len(line) >= 2)


def pdf_to_text(body: bytes) -> tuple[str, str]:
    from pypdf import PdfReader  # 依存は scripts/requirements.txt

    reader = PdfReader(io.BytesIO(body))
    text = "\n".join((page.extract_text() or "") for page in reader.pages[:30])
    return "", "\n".join(line.strip() for line in text.splitlines() if line.strip())


def decode(body: bytes) -> str:
    for encoding in ("utf-8", "shift_jis", "euc-jp"):
        try:
            return body.decode(encoding)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", errors="ignore")


def fetch_text(url: str, *, opener=None, resolver=socket.getaddrinfo) -> dict:
    """{url, title, text}。取得できない、本文が短すぎるときは FetchError。"""
    if not url.startswith("https://"):
        raise FetchError("https ではないURLは読まない")
    check_host(urlsplit(url).hostname or "", resolver)
    opener = opener or urllib.request.build_opener(_HttpsOnly())
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf,*/*"})
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            body = response.read(MAX_BYTES + 1)
            content_type = (response.headers.get("Content-Type") or "").lower()
    except urllib.error.HTTPError as error:
        raise FetchError(f"取得を断られた、または見つからない（HTTP {error.code}）") from None
    except (urllib.error.URLError, OSError, TimeoutError):
        raise FetchError("取得できなかった（通信の失敗）") from None
    if len(body) > MAX_BYTES:
        raise FetchError("大きすぎる")
    if "pdf" in content_type or body[:5] == b"%PDF-":
        try:
            title, text = pdf_to_text(body)
        except Exception:  # noqa: BLE001（pypdf は様々な例外を出す。本文は含めない）
            raise FetchError("PDFを読めなかった") from None
    else:
        title, text = html_to_text(decode(body))
    if len(text) < MIN_CHARS:
        raise FetchError("本文を取り出せなかった（短すぎる。JavaScriptで作るページの可能性）")
    return {"url": url, "title": title, "text": text[:MAX_CHARS]}
